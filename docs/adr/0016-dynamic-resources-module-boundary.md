# ADR 0016: Dynamic resources — a new engine-owned module, preserving mcp_resources.py purity
Status: draft — 2026-08-06

## Context

`engine/mcp_resources.py` is pure by construction: its module docstring states it "intentionally
has no access to environment, filesystem, policy, contracts, database, or live AWA state"
(`engine/mcp_resources.py:1`–`6`); `list_resources()` returns a single fixed descriptor
(`:15`–`25`) and `render_operator_guide()` is bounded to ≤500 words (`:73`–`78`). Live-verify found
that this one *static* resource added no routing benefit — but only because it duplicates the inline
guidance: the score was 0/8 → 8/8 inline and 8/8 inline+resource
(`live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md:10`–`12`), and "did not improve this 8/8
inline score because it intentionally repeats the inline guidance" (`:97`–`98`); its retained value
is the separately proven explicit on-demand fetch (`:5`–`8`). This ADR overrides both v3/v4 plans'
explicit "out of scope: dynamic resources containing paths/leases/commands/modes/recovery/contracts"
line (v4 plan §"Out of scope") as a documented, operator-approved scope change.

## Decision

Expose engine-owned live state — paths, leases, modes, contracts, the CLI verb list, recovery
artifacts, active-root heartbeats, and clean receipts — via a **new** sibling module
`engine/mcp_dynamic_resources.py`, leaving `engine/mcp_resources.py` and its tests byte-true.
Consumer-side conversational state is excluded. The new module ships bounded, read-only tests that
assert no user/prompt text is ever persisted.

## Why

- **Extend `engine/mcp_resources.py` (rejected — breaks purity).** Adding live-state reads to that
  module would violate its stated zero-I/O contract (`engine/mcp_resources.py:1`–`6`) and the tests
  that pin it. Rejected.
- **No dynamic resources at all (rejected).** Operator requirement 2 puts dynamic resources in
  scope. The live-verify finding is narrower than a general prohibition: it is evidence against
  **one static, guidance-duplicating** resource's *routing* value
  (`RESULTS-MCP-GUIDANCE-BASELINE-20260709.md:97`–`98`), not against exposing genuinely new
  engine-owned state. Rejected.
- **New sibling module `engine/mcp_dynamic_resources.py` (chosen).** Engine-owned state already has
  authoritative shapes to read from: the lease shape and identity rule
  (`contracts/awa-contract.v1.json:61`–`71`), the frozen CLI verbs
  (`contracts/awa-contract.v1.json:22`), modes (`engine/modes.py`), the contract file itself
  (`contracts/awa-contract.v1.json`), clean receipts (`clean_receipt/v1`, `:72`), active-root
  heartbeats (`active_root/v1`, `:250`), recovery artifacts, and the engine/kernel CLI verb list
  (`engine/cli.py:5`–`6`; `dashboard/emitter.py` is already a read-only, zero-link state emitter,
  `:2`–`9`). A separate module keeps `mcp_resources.py` byte-true, and the contamination boundary
  (`engine/tests/test_consumer_contamination_structural.py:55`, artifact scan `:68`–`70`) bars it
  from reaching consumer conversational state — which is exactly the state this ADR excludes.

## Consequences

- Enables: read-only exposure of engine-owned live state (paths/leases/modes/contracts/CLI
  verbs/recovery/active-root/clean receipts) as dynamic resources registered through the ADR 0011
  registry.
- Forecloses: any exposure of consumer-side conversational state (contamination boundary); any user
  or prompt text persisted for telemetry; any dynamic resource becoming a routing dependency.
- Must stay true: `engine/mcp_resources.py` and its tests stay byte-identical; the new module is
  read-only, bounded, and persists no user text; resources never hold authorization.
- Defers/creates: `engine/mcp_dynamic_resources.py` and its no-user-text-persistence tests are plan
  work items (M4/M6); explicitly overrides the v3/v4 out-of-scope line as an approved scope change
  (conflict #6). Cross-links: ADR 0011 (registered as a `resource` route kind), ADR 0018 (the one
  static resource is retained, not policy-locked against these dynamic siblings), plan §M4/§M6.
