# AWA MCP evolution (v4-expanded) — deterministic discoverability, kernel-gated lifecycle, and doc-warden alignment

**Version:** v1
**Status:** DRAFT — 2026-08-06
**Date:** 2026-08-06
**Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
**Review provenance:** Consolidates the Cursor-local plans `awa_mcp_discoverability_2c3d4da6` (v3, 265 lines) and `awa_mcp_discoverability_d3f4a896` (v4, 322 lines) — v4 is the floor and is a verified strict superset of v3. v4 was hardened by a `deep`-band swarm review (1 probe + 4 territory reviewers + 1 independent verifier; verifier adjudicated at historical commit `@160b2fa`, NOT current HEAD `bb85a5c`), which folded six open gaps as FG1–FG6 and dropped one false-positive. This plan additionally incorporates the operator brief of 2026-08-06 and its eight accompanying ADRs (`docs/adr/0002`–`0009`), which are DRAFT and gate this plan's approval.

---

## 1. Purpose

Make the AWA MCP surface *reliably discoverable and low-effort* for an agent acting on an operator's
natural language, and — as an operator-approved expansion of the v3/v4 floor — extend that surface to
first-class (but **preview-only, kernel-gated**) lifecycle verbs, MCP-initiated Safe Workspace
creation, and read-only engine-owned dynamic resources, while adopting and reconciling the fleet's
`doc-warden` documentation-governance conventions inside this repo. Every expansion is additive to the
v4 floor and is bounded by AWA's kernel-first safety model: MCP routing, guidance, preview, and
resources are **never** authorization; the kernel remains the sole authority for every mutating or
destructive effect, and every optional component (router, daemon, SQLite) must be absent-safe.

This plan consolidates the entire v4 floor (verified as a strict superset of v3 — nothing subtracted)
and augments it with the eight ADRs `docs/adr/0002`–`0009`. It ends at **DRAFT**: it is the execution
record awaiting the operator's GO, at which point its status moves to ACCEPTED in the index (the file
itself is then byte-identical-frozen; a material revision becomes `awa-mcp-evolution-v2.md`).

## 2. Scope and non-goals

### 2.1 In scope

- A single-source, in-engine MCP capability registry (`engine/mcp_catalog.py`) that drives every
  consumer (ADR 0002 / FG4).
- A deterministic, in-engine `awa_route` front door with a pinned closed `awa-route/v1` schema and a
  finish-recognizer parity gate (ADR 0003 / FG1–FG2), plus `awa_workspace_check` and strictly-additive
  result-envelope normalization (FG1), and a technical MCP mode-off glob-metachar restriction (FG3).
- **NEW (operator requirement 1):** MCP lifecycle tools for `protect`/`save`/`resume`/`cleanup`/
  `finish` as **preview/propose surfaces only**, whose mutating/destructive step executes solely
  through the existing kernel gate, authorized only by a one-use operator-chat-turn envelope the
  kernel checks (ADR 0005).
- **NEW (operator requirement 5):** MCP-initiated worktree provisioning — fused `dev-worktree.sh ensure`
  reuse (primary) + an optional disposable whitelisted scratch dir (secondary), with a hard
  never-downgrade-primary-protection constraint (ADR 0006).
- **NEW (operator requirement 2):** read-only dynamic resources exposing engine-owned live state via a
  new `engine/mcp_dynamic_resources.py`, preserving `mcp_resources.py` purity (ADR 0007).
- Privacy-safe usage bookkeeping (M5), a hardened verification gate (M6), and — reworked — doc-warden
  alignment + local-convention reconciliation, plus the optional gated router-reuse Phase 2 (M7; ADRs
  0004, 0008, 0009).

### 2.2 Out of scope (non-goals)

- **Cursor cloud agents** are explicitly out of scope for this entire body of work (operator
  requirement 4). This plan concerns local Desktop/CLI MCP behavior only.
- Router/resources/prompts/DB/MCP on the kernel safety path; router-selected executable code, safety
  class, confirmation, or authorization; MCP SDK migration; Cloud claims; a metrics dashboard
  (inherited verbatim from the v4 floor "Out of scope").
- Giving `doc-warden`'s engine a call-site outside `~/dev`, any cpp/eco-registry participation, a
  `.doc-warden.yml` in this repo, or wiring doc-warden into AWA CI/Makefile (ADR 0008, safety).
- Flipping any ADR or this plan to accepted/ACCEPTED without the operator's GO.

### 2.3 The six pre-resolved operator decisions (recorded; do not reopen without operator override)

1. Lifecycle verbs become first-class MCP functions but **preview/propose only**; authorization/
   execution stays kernel-gated (exact-`Close`, active-root heartbeat, bundle-or-refuse), triggerable
   only by an explicit operator chat-turn — never agent self-authorization. → ADR 0005.
2. Dynamic resources are in scope; architect-discretion on the exact set; operator-approval on final
   scope. → ADR 0007.
3. M7 is fully reworked around doc-warden alignment **and** reconciling AWA's pre-existing local
   `docs/adr` + `docs/plans` convention. → ADR 0008, §5 M7.
4. Cursor cloud agents are out of scope (see §2.2).
5. MCP worktree creation is fused primary (`dev-worktree.sh ensure` reuse) + secondary (disposable
   whitelisted scratch dir), with a hard non-downgrade constraint on primary-checkout protection. →
   ADR 0006.
6. No blanket protection for existing MCP tooling — only actively-used or policy-locked surface needs
   proof-to-kill; nothing qualifies for subtraction today (all 9 tools used/tested; the one resource
   is RETAIN-verdicted on its own narrow merits, not locked against dynamic siblings). → ADR 0009.

### 2.4 Two v4-floor "Out of scope" lines this plan deliberately overrides

The v3 and v4 Cursor plans both list, under "Out of scope and kill criteria": *"MCP execution of
ensure/clean/save/resume/finish; dynamic resources containing paths/leases/commands/modes/recovery/
contracts"* (`awa_mcp_discoverability_d3f4a896.plan.md:314`). Operator requirements 1 and 2 **override**
these two lines as a documented, operator-approved scope change — not a silent contradiction. ADR 0005
(lifecycle) and ADR 0007 (dynamic resources) each name this override explicitly, and both preserve the
underlying safety intent the original lines protected: no MCP self-authorization of a mutating verb
(ADR 0005), and engine-owned-state-only resources that never touch consumer conversational state or
persist user text (ADR 0007).

## 3. Background and context (verified live-state @ `bb85a5c`)

All facts below were verified against disk at HEAD `bb85a5c` (clean worktree). File:line references are
the load-bearing evidence for the ADRs and are spot-verified.

### 3.1 Current MCP surface (nothing dormant)

`engine/mcp_server.py` (587 lines) exposes **nine** tools declared in `_TOOLS`
(`engine/mcp_server.py:145`): read-only `awa_status`, `awa_lease_read`, `awa_guard_shell`,
`awa_mode_list`, `awa_mode_get`; and persistent, host-modes-file-scoped `awa_mode_set`,
`awa_mode_remove`, `awa_mode_repair`, `awa_mode_sync`. `initialize.instructions` is **derived** from
the tool dict via `mcp_resources.render_guidance(_TOOLS)` (`engine/mcp_server.py:501`) — not a
hand-written string. `engine/mcp_resources.py` (91 lines) is pure by construction: its docstring
declares "no access to environment, filesystem, policy, contracts, database, or live AWA state"
(`engine/mcp_resources.py:1`–`6`) and it serves one static resource `awa://assistant/operator-guide/v1`.
All 9 tools + the resource are actively used and tested. `engine/mcp_catalog.py` **does not yet exist**
(confirmed absent) — the M1 build gap. Consent scaffolding exists but is intentionally unwired:
`MUTATING_TOOLS` (`engine/mcp_server.py:257`) and `consent_prompt()` whose docstring states it "is not
called by `handle` and is not production-wired" (`engine/mcp_server.py:264`–`268`).

The single static resource's live-verify evidence (`live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md`)
returned verdict **RETAIN** (`:5`): it added no *routing* improvement (0/8 → 8/8 inline; 8/8 inline+resource,
`:10`–`12`) **because it duplicates the inline guidance**, and its retained value is the proven explicit
on-demand fetch. This is evidence against one static, duplicative resource — **not** a policy lock
against new dynamic resources (see ADR 0007, ADR 0009).

### 3.2 Lifecycle vocabulary + the executor build gap

`consumer/intent-catalog.v1.json` is the **sole** lifecycle vocabulary and declares seven verbs:
`protect`(write,mcp), `status`(read,cli), `list_protected`(read,cli), `resume`(write,mcp),
`save`(write,mcp), `cleanup`(destructive,mcp), `finish_current`(destructive,**cli**). The four `mcp`
write/destructive verbs (`protect`/`resume`/`save`/`cleanup`) carry `"tool_path":"mcp"` but have **no**
implemented MCP tool or executor: `OperatorLoop.executor` is an injected callback defaulting to `None`
(`consumer/operator_loop.py:151`, assigned `:158`) with is-`None` guards at both dispatch sites. This is
the build gap ADR 0005 closes — a gap, not a subtraction (ADR 0009). `finish_current` is `tool_path:cli`,
so its MCP surface is preview/hand-off only. Finish authorization is the exact literal `Close`
(case-sensitive, no casefold: `consumer/finish_current.py:333`–`334`; variant rejection
`close_must_be_exact` at `:343`; recognizer `recognize_finish` at `:308`), via a two-phase
preview→authorize path that is kernel-authoritative. `clean` is bundle-or-refuse + active-root heartbeat
gated (fail-closed if the gate lib is missing). This plan does not fork the catalog; the MCP verbs map
onto its existing vocabulary.

### 3.3 Worktree/path model + FG3

`kernel/bin/dev-worktree.sh ensure_worktree()` (~lines 227–315) is the **sole** worktree creation path:
it classifies via `kernel/lib/awa_policy.py` ↔ `engine/policy.py` (parity-tested by
`test_kernel_policy_parity.py`), proceeds only when `class == include` (`dev-worktree.sh:246`), places
worktrees under the managed location, and prints `move_agent_to_root`. `classify()` is first-match-wins;
**only exact `"off"` disables** (any other explicit value fails safe → INCLUDE). `engine/modes.py`
`_reject_broad_off` (`:138`) rejects fully-broad `off` keys (`_BROAD_OFF_RELS = {".", "*", "**"}` and
`_is_pure_glob()` all-metachar, `:133`–`135`, `:142`) but **not** a partial glob like `vendor/*` — so
`awa_mode_set(rel='vendor/*', mode='off')` currently passes and would disable a whole subtree. This is
**FG3**, addressed at the MCP boundary by ADR 0006.

### 3.4 Guardrails already test-enforced (must stay true)

- **Engine⇎consumer/router contamination boundary:** `engine/tests/test_consumer_contamination_structural.py`
  AST-scans every `engine/*.py` (excluding `tests/`) for `consumer`/`intent_router` imports plus a
  router-artifact usage scan, asserting zero. `awa_route` (ADR 0003) and the dynamic-resources module
  (ADR 0007) therefore use only the engine capability graph / engine-owned state.
- **`mcp_resources.py` zero-I/O purity:** pinned by its docstring + tests; ADR 0007 adds a *sibling*
  module rather than extending it.
- **Egress hygiene** (`consumer/egress.py`): only PM-facing copy uses the jargon-free gate; agent-facing
  diagnostics are exempt. Any new PM-facing string reuses the same narrow named exception as the finish
  warning (acceptance-test ledger, §6.3 row 4).
- **Router optionality:** `consumer/router-pin.json` pins `base_sha f44dbadd` (`:7`); the seam test
  *skips* (never fails) router-uninstalled, with a dedicated CI `router-seam` job running it non-skipped
  — the kernel-first / off-switch property (`make verify` passes router-uninstalled).

### 3.5 Definition of "fully discoverable" (verbatim from the v4 floor)

AWA cannot guarantee automatic agent discovery of host-driven resources/prompts. For this milestone,
"fully discoverable" means:

1. Every supported AWA intent is reachable from tool name, description, schema, and
   `initialize.instructions`.
2. One front-door tool routes ambiguous language to the exact MCP operation, resource, CLI verb,
   consumer flow, or explicit unsupported outcome.
3. Every route states required inputs, persistence/destructive effect, authority, verification limit,
   and next action.
4. Resources/prompts ship only when Cursor exposes them and paired trials show incremental value.
5. Router/optional-component absence, failure, or timeout cannot weaken safety or existing MCP
   operations.

### 3.6 Non-negotiable invariants (v4 restated + three new)

Carried forward verbatim in intent from the v4 floor:

- Kernel-first: MCP routing/guidance is never authorization.
- `consumer/intent-catalog.v1.json` remains the sole operator lifecycle-verb vocabulary; this plan does
  not fork it.
- A single in-engine capability registry is the sole authority for every consumer (tools/list,
  validation, ordering, short instructions, operator-guide body, generated reference). No second
  description source.
- Production files under `engine/` import/read neither `consumer` nor `intent_router` (scanner-enforced);
  engine *tests* may import `consumer` for parity checks.
- The engine advisory finish/cleanup recognizer must **agree** with `consumer/finish_current.recognize_finish`
  over a frozen corpus (parity test in `make verify`); `awa_route` never runs the authoritative
  recognizer and never emits `Close`.
- `awa-route/v1` is a pinned closed schema with an explicit reject branch; result-envelope normalization
  is strictly additive to the 9 existing tools; `awa_workspace_check` uses the same envelope;
  `executed`/`authorized` are literal constant `false` on every `awa_route` branch.
- Persistent MCP mode changes reject any glob-metachar key when `mode='off'` (FG3) until a real host
  write-confirmation path is proven.
- Finish/cleanup precedence runs first as advisory hand-off.
- Optional-component-off is first-class: deterministic routes work with no router, daemon, or SQLite.
- Agent-facing technical guidance and PM-facing copy are classified and tested separately.
- No prompt/command/path/cwd/argument/user text is persisted for usage measurement (in-memory-only
  follow-through, never a persisted join key).
- Existing tools stay available until measured evidence supports a separately versioned rename/removal
  (no blind renames/removals).

**New invariants added by this plan (each with a biting M6 test):**

- **N1 — MCP never self-authorizes a mutating/destructive lifecycle verb.** The operator-chat-turn
  envelope only decides *which* caller may hand the literal token to the kernel; it is not a new
  authority (ADR 0005).
- **N2 — Whitelisting never downgrades an included primary checkout's protection.** The MCP boundary
  rejects any glob-metachar `mode='off'` key and can only add advisory/standalone scope (ADR 0006,
  mirroring FG3).
- **N3 — Dynamic resources are engine-owned-state-only and never persist user text.** The new module is
  read-only, excludes consumer conversational state (contamination boundary), and its tests assert no
  user/prompt text is persisted (ADR 0007).

### 3.7 Current → target tool inventory

- **Kept (9, descriptions tightened, envelopes normalized additively):** `awa_status`, `awa_lease_read`,
  `awa_guard_shell`, `awa_mode_list`, `awa_mode_get`, `awa_mode_set`, `awa_mode_remove`, `awa_mode_repair`,
  `awa_mode_sync`.
- **Added (discoverability floor):** `awa_route` (M2, ADR 0003), `awa_workspace_check` (M3, FG1).
- **Added (this plan's expansion):** lifecycle preview tools for `protect`/`save`/`resume`/`cleanup`/
  `finish` (M3, ADR 0005, preview-only + kernel-gated); an MCP worktree-create tool + disposable-dir
  provisioning (M3, ADR 0006); read-only dynamic resources via `engine/mcp_dynamic_resources.py` (M4,
  ADR 0007).
- **Deferred/optional (gated proof):** out-of-engine router wrapper feeding `awa_route`'s fuzzy fallback
  — now **required-but-gated** (M7 Phase 2, ADR 0004, operator-gated on the scorecard, never a
  dependency); MCP prompts (M4, host-exposure + paired-benefit gated).

No blind renames/removals this release; nothing is subtracted (ADR 0009).

### 3.8 Fix groups (FG1–FG6) as work-item anchors

- **FG1 (API contract):** pin `awa-route/v1` as a concrete closed schema (version discriminator, closed
  enums, required-field list, integer caps, explicit `invalid_request` reject branch); strictly-additive
  envelope normalization; bind `awa_workspace_check` to the same envelope; M6 test asserting
  `executed`/`authorized` literal `false` on every branch. → M2/M3/M6.
- **FG2 (Architecture):** finish-recognizer parity gate (`test_mcp_route_finish_parity.py`, modeled on
  `test_kernel_policy_parity.py`; engine tests may import consumer). → M2/M6.
- **FG3 (Security, the one P1):** technically restrict MCP mode-off scope — reject any glob-metachar key
  for `mode='off'` at the MCP boundary. → M3/M6.
- **FG4 (Architecture):** single-source the registry across all consumers; split short-instructions
  renderer from full-guide renderer; replace the `instructions == operator-guide` equality gate with a
  registry-derivation gate. → M1.
- **FG5 (Testing/drift):** byte-identical generated-doc gate; tool count AND resource count AND full URI
  set asserted as `len == len(registry)`; enumerate every hard-coded count/name site to migrate. → M6.
- **FG6 (Testing/release honesty):** the harness fallback travels into the M6 gate; live-proof gets a
  machine-checkable evidence schema; rollback gets a named regression test. → M0/M6/M7.

## 4. Approach

### 4.1 Deterministic-first discoverability (unchanged from the v4 floor)

Primary discoverability is what Cursor gives agents automatically (tool name, description, schema,
`initialize.instructions`) plus one obvious, deterministic `awa_route` tool resolved entirely from the
engine-owned capability graph. Resources and prompts stay secondary and must earn retention with
evidence. `awa_route` selects and explains; it never executes, authorizes, confirms, or converts natural
language into exact `Close`. The registry (ADR 0002) is the one authority every consumer reads.

### 4.2 Kernel-gated lifecycle via an operator-chat-turn envelope (ADR 0005)

The MCP lifecycle tools surface a **preview** (read-only) of what would happen and **propose** the exact
kernel invocation. The actual mutating/destructive step runs only through the existing kernel gate:
exact-`Close` (case-sensitive), bundle-or-refuse, active-root heartbeat, `class == include`. The
operator's authorization is a one-use, root/session/generation-bound, exact-literal envelope captured
from a real operator chat turn (reusing the `finish_current` mechanism); the **kernel** re-derives and
checks it. No MCP tool may emit `Close`, and an agent cannot self-authorize (invariant N1).

### 4.3 Engine-owned dynamic resources (ADR 0007)

Expose engine-owned live state (paths, leases, modes, contracts, CLI verb list, recovery, active-root,
clean receipts) via a **new** sibling module `engine/mcp_dynamic_resources.py`, leaving
`engine/mcp_resources.py` and its tests byte-true. Consumer conversational state is excluded by the
contamination boundary. The module is read-only and persists no user text (invariant N3).

### 4.4 doc-warden alignment + local-convention reconciliation (ADR 0008)

Author the ADRs/plan at the existing `docs/adr` + `docs/plans` roots; number ADRs from 0002 (0001 is
accepted/untouched). New artifacts adopt doc-warden's canonical **entry** shape and vocabulary going
forward (`draft|accepted|superseded` for ADRs; `DRAFT|ACCEPTED|SUPERSEDED` for plans; byte-identical-
forever with no inline `> Update —` exception). The two index tables keep AWA's local columns for now
(so the protected 0001/guard rows stay byte-identical and the tables stay valid); migrating the index
*columns* to doc-warden's canonical shape is a deferred, operator-gated, index-only change under
doc-warden's POC 3d. `AGENTS.md` is augmented with the marker-delimited pointer block. AWA is the
owning-repo side of doc-warden's pending M4/POC 3d; the `~/dev` `_ops/awa/` overlay copies become
pointers later under an Operator-GO-gated `~/dev`-side change. doc-warden's engine gets no call-site in
this repo.

### 4.5 ADR map

| ADR | Decision | Primary milestone(s) |
|---|---|---|
| [0002](../adr/0002-mcp-capability-registry-single-source.md) | `engine/mcp_catalog.py` single-source registry (FG4) | M1 |
| [0003](../adr/0003-awa-route-deterministic-in-engine-front-door.md) | Deterministic in-engine `awa_route` + closed `awa-route/v1` + finish parity (FG1/FG2) | M2 |
| [0004](../adr/0004-routing-strategy-graduation.md) | Deterministic-first, router-fallback gated on the scorecard (complements 0003) | M7 Phase 2 |
| [0005](../adr/0005-lifecycle-verbs-via-mcp-preview-kernel-gated.md) | Lifecycle MCP tools preview-only + kernel-gated; overrides a v4 out-of-scope line | M3, M6 |
| [0006](../adr/0006-mcp-worktree-creation-and-path-whitelisting.md) | Fused `ensure` reuse + disposable scratch dir; never downgrade primary (FG3 mirror) | M3, M6 |
| [0007](../adr/0007-dynamic-resources-module-boundary.md) | New `engine/mcp_dynamic_resources.py`; overrides a v4 out-of-scope line | M4, M6 |
| [0008](../adr/0008-adopt-and-reconcile-doc-warden-conventions.md) | Adopt + reconcile doc-warden conventions (meta-ADR for 0002–0009) | M7 |
| [0009](../adr/0009-tooling-subtraction-policy.md) | Subtract nothing now; proof-to-kill rule | M7 |

## 5. Work items

Each work item (WI) carries fifteen fields: **Objective · Owning repo · Scope · Interfaces/contracts ·
Prerequisites · Dependencies · Session/PR boundary · Allowed mutations · Non-goals · Steps · Tests/
commands · Evidence to retain · Rollback · Definition of done · Handoff state.** Milestones M0→M7 are
retained from the v4 floor and augmented; the "Owning repo" is `KleinPerkins/awa` for every WI except
where a POC-3d hand-off touches `~/dev` (WI-M7-01, called out explicitly). All build WIs are downstream
of this plan's ACCEPTED status; none may begin while the plan is DRAFT.

### M0 — Authority, baseline, host proof, and harness

**WI-M0-01 — Freeze the blind scenario matrix, capture the paired baseline, prove host surfaces, stand
up the harness (with a travelling fallback).**
- **Objective:** produce the frozen 24-scenario matrix and the current-server baseline, and settle host
  capability + harness feasibility before any build.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** `live-verify/MCP-DISCOVERABILITY-SCENARIOS.md`; baseline capture; live host probes; harness
  feasibility. **Augment:** add scenarios for the new lifecycle preview verbs, MCP worktree creation, and
  dynamic resources (each with expected route, required caveat, forbidden claim/action).
- **Interfaces/contracts:** scenario schema (expected intent/route, caveat, clarification, allowed ops,
  forbidden claims); the `awa-route/v1` and result-envelope contracts they will later assert against.
- **Prerequisites:** plan ACCEPTED.
- **Dependencies:** none (M0 is the root).
- **Session/PR boundary:** one PR: scenarios + baseline artifacts + harness feasibility note.
- **Allowed mutations:** add `live-verify/` artifacts and a harness runner; no engine code changes.
- **Non-goals:** running the candidate matrix (that is M6); building any tool.
- **Steps:** (1) author scenarios incl. the three new surface families + adversarial ambiguity/negation/
  quotation/injection-shaped/malformed-path/router-lie cases; (2) capture automatic metadata bytes,
  first route, calls/turns, outcome, safety result for the current server across the 96-run matrix; (3)
  probe resource-descriptor visibility, `prompts/list|get`, `beforeMCPExecution` enforceability, real
  server identity, in a throwaway runtime + temp MCP entry; (4) stand up the scripted agent runner and
  **confirm feasibility**; if infeasible, record the FG6 fallback that travels into M6.
- **Tests/commands:** harness dry-run; baseline artifact validation.
- **Evidence to retain:** frozen scenarios; baseline RESULTS artifact; host-probe results; harness
  feasibility note (or the fallback declaration).
- **Rollback:** artifacts are additive; delete on abandonment (no engine impact).
- **Definition of done:** scenarios frozen; baseline captured; host branches decided; harness feasible
  **or** fallback explicitly recorded and wired to the M6 gate.
- **Handoff state:** M1 has a frozen target set and a known measurement path.

### M1 — Canonical MCP capability registry (ADR 0002 / FG4)

**WI-M1-01 — Create `engine/mcp_catalog.py` and re-point every consumer in lockstep.**
- **Objective:** one pure-Python registry is the sole source for tools/list, validation, ordering, short
  instructions, operator-guide body, and the generated reference.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** new `engine/mcp_catalog.py`; refactor `engine/mcp_server.py`, `engine/mcp_resources.py`;
  add `docs/MCP-CAPABILITY-REFERENCE.md` generation.
- **Interfaces/contracts:** per-operation record (stable id/name, intent description + use/do-not-use,
  input/output schema + bounds, route kind, read/write/persistent/destructive class, authority +
  verification limit, aliases/examples, related guidance, availability/audience/compat).
- **Prerequisites:** WI-M0-01.
- **Dependencies:** blocks M2 (route resolves from this graph), M3 (envelope + new tools register here),
  M4 (resources register as a route kind).
- **Session/PR boundary:** one PR: registry + lockstep consumer refactor + derivation test.
- **Allowed mutations:** `engine/` MCP modules; generated doc; tests. **No** runtime I/O in the registry
  (determinism); `mcp_resources.py` stays pure (ADR 0007).
- **Non-goals:** adding `awa_route` (M2) or new tools (M3).
- **Steps:** (1) author the registry as pure constants + validators; (2) derive `tools/list`, argument
  validation, ordering, and a **short** `initialize.instructions` from it; (3) split `render_guidance`
  (short) from `render_operator_guide` (full), both catalog-sourced; (4) generate
  `docs/MCP-CAPABILITY-REFERENCE.md`; (5) replace the `instructions == operator-guide` equality gate with
  a registry-derivation gate (name the old assertion's fate).
- **Tests/commands:** single-source derivation test; `make verify`; `make verify-install`.
- **Evidence to retain:** derivation-test output; generated reference.
- **Rollback:** revert the PR; the registry adds no launcher/entry change.
- **Definition of done:** every consumer derives from the one registry; derivation + drift gates green.
- **Handoff state:** M2 can resolve routes from a governed graph.

### M2 — `awa_route`: deterministic in-engine front door (ADR 0003 / FG1–FG2)

**WI-M2-01 — Add `awa_route` with a pinned closed `awa-route/v1` schema + finish-recognizer parity.**
- **Objective:** one deterministic front door that selects+explains a route, never executes/authorizes.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** add `awa_route` to engine `_TOOLS` (no launcher/`install.sh` change); pin `awa-route/v1`;
  add the parity test.
- **Interfaces/contracts:** `awa-route/v1` — `version` discriminator; closed `state`
  (`matched|clarify|candidates|invalid_request`), `source` (`finish_handoff|local_exact|fallback`;
  `router_suggestion` reserved for M7), `route_kind`, `persistence`, `risk`; bounded `candidates[]`/
  `next_actions[]`; `executed:false`/`authorized:false` on every branch; reject branch never echoes
  request/path/traceback.
- **Prerequisites:** WI-M1-01.
- **Dependencies:** M3 lifecycle previews surface here as `consumer_flow`; M7 Phase 2 may add
  `router_suggestion`.
- **Session/PR boundary:** one PR: tool + schema + routing tests + parity test.
- **Allowed mutations:** `engine/` route logic + tests; the shared engine-safe finish phrase table.
- **Non-goals:** any router import (contamination); any execution/authorization.
- **Steps:** (1) validate bounded UTF-8 request, never echo/persist; (2) advisory finish/cleanup
  recognition first (hand-off only); (3) deterministic unique match over graph aliases/examples; (4) no
  unique match → bounded candidates + mandatory clarification; (5) return exactly one route/clarify/
  candidates/reject.
- **Tests/commands:** `test_mcp_routing.py` (incl. authority-constant assertion on every branch,
  `invalid_request` included); `test_mcp_route_finish_parity.py` (frozen corpus incl. negated/quoted/
  hypothetical); `make verify`.
- **Evidence to retain:** routing + parity test output.
- **Rollback:** revert PR; deterministic-only remains the shipped behavior.
- **Definition of done:** front door routes the frozen scenarios; authority-constant + parity gates
  green.
- **Handoff state:** ambiguous language has one obvious, safe entry point.

### M3 — Intent-shaped tools, safer results, and the expansion surfaces

M3 carries the v4 floor (workspace-check + additive envelope + FG3) **and** the operator's new lifecycle
(ADR 0005) and worktree-creation (ADR 0006) surfaces. Default is augment-in-place; a split into a
separate `M3b` is a GO/NO-GO fork (§6.5) flagged for operator approval — the WI structure below is
organized so the split, if approved, is a clean cut along WI boundaries.

**WI-M3-01 — `awa_workspace_check` + strictly-additive envelope + FG3 mode-off restriction (v4 floor).**
- **Objective:** ship the computed workspace check bound to the stable envelope, normalize result
  envelopes additively, and close FG3.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** `awa_workspace_check(cwd)`; additive envelope for the 9 tools; MCP mode-off glob-metachar
  rejection.
- **Interfaces/contracts:** reuse `Classification.reason` enum; keep every current top-level payload key
  at the same name/location/type; add new metadata under one reserved, versioned namespaced key.
- **Prerequisites:** WI-M1-01.
- **Dependencies:** none downstream-blocking.
- **Session/PR boundary:** one PR.
- **Allowed mutations:** `engine/` policy/tool/envelope code + tests. **N2:** MCP boundary only ever adds
  advisory/standalone scope; never writes `off` onto an included primary.
- **Non-goals:** broadening CLI authority; restructuring existing keys (that needs a versioned bump).
- **Steps:** (1) implement `awa_workspace_check` reusing `classify()`/`mode_for()`; (2) additively
  normalize envelopes; (3) reject any glob-metachar key for `mode='off'` at `awa_mode_set`/
  `awa_mode_remove`; (4) recompute effective mode after every write and return the observed result.
- **Tests/commands:** biting regression that `awa_mode_set(rel='vendor/*', mode='off')` is refused via
  MCP; envelope back-compat tests (`test_mcp.py` assertions still pass); `make verify`.
- **Evidence to retain:** FG3 regression output; envelope compat proof.
- **Rollback:** revert PR; prior envelope + broader mode behavior returns (CLI unchanged).
- **Definition of done:** workspace-check shipped; envelopes additive; FG3 closed with a biting test.
- **Handoff state:** the protection model is computable and the mode-off subtree hole is closed.

**WI-M3-02 — Lifecycle MCP tools: preview/propose only, kernel-gated (ADR 0005, overrides a v4
out-of-scope line; closes the executor build gap).**
- **Objective:** give the catalog's `mcp` lifecycle verbs a preview surface while all effects stay behind
  the kernel gate.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** MCP tools for `protect`/`save`/`resume`/`cleanup`/`finish` (preview + propose); wire
  `OperatorLoop.executor` to a kernel-hand-off that carries the operator-chat-turn envelope.
- **Interfaces/contracts:** the one-use, root/session/generation-bound exact-literal envelope; the
  existing kernel finish path (`dev-worktree.sh clean --finish-current --preview` read-only; removal
  requires `--authorization` == exact `Close`); `intent-catalog.v1.json` vocabulary (no new verbs).
- **Prerequisites:** WI-M1-01, WI-M2-01 (routes surface as `consumer_flow`).
- **Dependencies:** shares the non-downgrade discipline with WI-M3-03.
- **Session/PR boundary:** one PR.
- **Allowed mutations:** `engine/` MCP tool code + the executor wiring in `consumer/operator_loop.py`
  (consumer-side executor is consumer code, not an engine→consumer import). **N1:** no MCP self-auth; no
  MCP tool emits `Close`.
- **Non-goals:** a new MCP-owned authorization path; bypassing bundle-or-refuse / active-root / class ==
  include.
- **Steps:** (1) implement preview (read-only) for each verb; (2) implement propose = construct the exact
  kernel invocation; (3) require the operator-chat-turn envelope, checked by the kernel; (4) `finish` is
  hand-off/preview only (`tool_path:cli`).
- **Tests/commands:** agent-cannot-self-authorize test; preview-never-mutates test; envelope one-use/
  binding test; `make verify`.
- **Evidence to retain:** the safety-test output for N1.
- **Rollback:** revert PR; lifecycle returns to CLI/consumer-only (status quo ante).
- **Definition of done:** lifecycle verbs discoverable over MCP; every effect kernel-gated; N1 test green.
- **Handoff state:** the declared `mcp` catalog verbs finally have a safe surface.

**WI-M3-03 — MCP worktree creation + path whitelisting / disposable dir (ADR 0006).**
- **Objective:** fused MCP worktree provisioning that reuses the kernel creation path and offers a
  disposable scratch dir, never downgrading primary protection.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** an MCP tool invoking `dev-worktree.sh ensure` (primary) + optional disposable managed
  scratch-dir creation + whitelisting (secondary).
- **Interfaces/contracts:** `ensure_worktree()` (sole creation path, `class == include` only, managed
  location, lease keyed by `hash(path+branch+common_dir+boot_id)`, `move_agent_to_root` hand-off); the
  FG3 exact-`off`-only rule at the MCP boundary.
- **Prerequisites:** WI-M3-01 (shares the FG3 restriction).
- **Dependencies:** none downstream-blocking.
- **Session/PR boundary:** one PR.
- **Allowed mutations:** `engine/` MCP tool code + tests. **N2:** whitelisting only adds advisory/
  standalone scope; rejects glob-metachar `off`.
- **Non-goals:** a parallel worktree creator that duplicates classify/managed-location/lease.
- **Steps:** (1) MCP tool → `ensure`; (2) optional disposable managed scratch dir (bundle-able/
  recoverable, never a primary); (3) enforce the non-downgrade floor at the boundary.
- **Tests/commands:** whitelisting-never-downgrades-primary test; disposable-dir is managed/recoverable
  test; `make verify`.
- **Evidence to retain:** the N2 safety-test output.
- **Rollback:** revert PR; worktree creation returns to CLI-only.
- **Definition of done:** MCP can create a real Safe Workspace via the kernel path + an optional
  disposable dir; N2 test green.
- **Handoff state:** agents can request isolation over MCP without weakening protection.

### M4 — Resources and conditional prompts (dynamic resources now required, ADR 0007)

**WI-M4-01 — New `engine/mcp_dynamic_resources.py` for engine-owned live state; prompts host-gated.**
- **Objective:** expose read-only engine-owned live state as dynamic resources without touching
  `mcp_resources.py` purity, and add at most one host-proven experimental prompt.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** new sibling module for paths, leases, modes, contracts, CLI verb list, recovery,
  active-root, clean receipts; keep the fixed static resources; conditional prompt only if M0 proved
  exposure + paired benefit.
- **Interfaces/contracts:** authoritative shapes — lease/identity (`contracts/awa-contract.v1.json`),
  frozen CLI verbs, `clean_receipt/v1`, `active_root/v1`; each dynamic resource registered through the
  ADR 0002 registry as a `resource` route kind.
- **Prerequisites:** WI-M1-01 (registry), WI-M0-01 (host exposure branch).
- **Dependencies:** M6 adds the no-user-text-persistence test.
- **Session/PR boundary:** one PR (prompts split to a follow-up PR if host exposure is marginal).
- **Allowed mutations:** new `engine/` module + tests; **N3:** read-only, engine-owned-state-only, no
  user text persisted; `mcp_resources.py` + its tests stay byte-true.
- **Non-goals:** exposing consumer conversational state (contamination boundary); a dynamic resource
  becoming a routing dependency.
- **Steps:** (1) implement the sibling module reading engine-owned shapes read-only; (2) register each as
  a resource route kind; (3) add prompts only on the proven host-exposure branch; (4) keep every resource
  earning unique M0 scenarios.
- **Tests/commands:** no-user-text-persistence test; `mcp_resources.py` byte-true assertion; URI-set drift
  gate (M6); `make verify`.
- **Evidence to retain:** N3 test output; resource-uniqueness mapping to M0 scenarios.
- **Rollback:** revert PR; the one static resource remains (ADR 0009 retention).
- **Definition of done:** dynamic resources shipped via the new module; purity + N3 green.
- **Handoff state:** live engine state is inspectable read-only over MCP, safely.

### M5 — Privacy-safe usage bookkeeping

**WI-M5-01 — Fail-open aggregate counters + read-only `awa-engine mcp-usage`.**
- **Objective:** measure call mix/follow-through with zero user-controlled data and zero behavior impact.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** engine SQLite aggregates (method class, operation id, outcome enum, route source, latency
  bucket, version/day, same-process follow-through boolean); 90-day retention; read-only CLI report.
- **Interfaces/contracts:** aggregates schema with **no** process/session-scoped column; the
  same-process follow-through comparison is in-memory-only within the live stdio process (never a
  persisted join key).
- **Prerequisites:** WI-M1-01.
- **Dependencies:** M6 rollback regression builds on this schema.
- **Session/PR boundary:** one PR.
- **Allowed mutations:** `engine/` telemetry + CLI + tests; telemetry failure cannot alter MCP behavior
  (fail-open).
- **Non-goals:** storing any user text/identifier; a metrics dashboard (out of scope).
- **Steps:** (1) implement fail-open aggregates; (2) in-memory follow-through only; (3) add read-only
  `awa-engine mcp-usage`.
- **Tests/commands:** aggregates-schema-has-no-process/session-column test; zero-user-data test;
  fail-open test; `make verify`.
- **Evidence to retain:** schema test output.
- **Rollback:** revert PR; aggregates are additive and ignorable by old versions (proven in M6).
- **Definition of done:** bookkeeping ships privacy-safe and fail-open.
- **Handoff state:** utilization stays a paired-trial metric; aggregates measure mix only.

### M6 — Verification (augmented with the new safety gates)

**WI-M6-01 — Automated gates: protocol, structural, off-switch, drift, rollback, authority constants,
new-safety tests.**
- **Objective:** make every invariant (including N1–N3) a biting, machine-checked gate in `make verify`.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** extend `test_mcp.py`, `install_mcp_smoke.py`; add `test_mcp_routing.py`,
  `test_mcp_route_finish_parity.py`, `test_mcp_usage.py`; drift gates; rollback regression; the three new
  safety tests.
- **Interfaces/contracts:** FG5 drift gates (`len == len(registry)` for tool count AND resource count
  AND full URI set; byte-identical generated-doc); FG1 authority-constant test; the machine-checkable
  live-proof schema (FG6).
- **Prerequisites:** M1–M5 WIs.
- **Dependencies:** feeds M7's release/rollback proof.
- **Session/PR boundary:** one PR (may split test files, one logical gate group per commit).
- **Allowed mutations:** `engine/tests/`, `live-verify/verify-live-verify.sh`.
- **Non-goals:** live Desktop runs (WI-M6-02).
- **Steps:** (1) registry-derivation + drift gates; (2) `executed`/`authorized` literal-false on every
  `awa_route` branch; (3) finish-recognizer parity; (4) contamination scan confirmation for new engine
  modules; (5) **new:** agent-cannot-self-authorize (N1), whitelisting-never-downgrades-primary (N2),
  dynamic-resource no-user-text-persistence (N3); (6) rollback regression on the M5 schema.
- **Tests/commands:** `make verify`, `make verify-install`, contamination/off-switch tests.
- **Evidence to retain:** the full green gate log; the three new-safety test outputs.
- **Rollback:** revert PR; prior gates remain.
- **Definition of done:** all automated gates green router-uninstalled; N1–N3 biting.
- **Handoff state:** structural + safety correctness proven pre-live.

**WI-M6-02 — Tiered live Cursor Desktop proof (bulk harness or fallback + mandatory safety-critical
human tier).**
- **Objective:** prove routing/safety in real Desktop with machine-checkable evidence.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** Tier 1 (96-run paired matrix via the M0 harness, blinded scoring) or the FG6 fallback
  (reduced operator-run subset, utilization marked indicative/non-gating); Tier 2 (mandatory human, hard
  gate) = the 8 safety-critical scenarios with result-side hook evidence.
- **Interfaces/contracts:** the machine-checkable live-proof schema (exact operator prompt; captured
  result-side hook-decision JSON; Desktop version; timestamps; MCP-config restore attestation before/
  after hash pair).
- **Prerequisites:** WI-M6-01.
- **Dependencies:** none downstream except M7 ship decision.
- **Session/PR boundary:** evidence artifacts + the content-validating checker.
- **Allowed mutations:** `live-verify/` artifacts + `verify-live-verify.sh` (content validation).
- **Non-goals:** any Cloud claim (out of scope); self-report/quoted-error/rehearsal as proof.
- **Steps:** (1) run Tier 1 (or fallback) blinded; (2) run Tier 2 with the operator; (3) content-validate
  every Tier-2 artifact against the schema.
- **Tests/commands:** `verify-live-verify.sh` content validation; scorecard tabulation.
- **Evidence to retain:** Tier-1/Tier-2 RESULTS artifacts with the required structure.
- **Rollback:** none (verification only).
- **Definition of done:** safety-critical scenarios 100% correct routing, zero unsafe claims/actions;
  scorecard bars met (or the fallback path honestly applied).
- **Handoff state:** merge decision has honest, machine-checked live proof.

### M7 — Docs, doc-warden reconciliation, gated router reuse, subtraction, release (REWORKED)

**WI-M7-01 — doc-warden alignment + local-convention reconciliation + POC-3d coordination (ADR 0008).**
- **Objective:** land this repo's governance docs conforming to doc-warden while explicitly reconciling
  AWA's pre-existing local convention, and record the owning-repo side of doc-warden's POC 3d.
- **Owning repo:** KleinPerkins/awa (the POC-3d overlay-to-pointer conversion is a **separate**
  Operator-GO-gated change on the `~/dev` side — named here, not executed here).
- **Scope:** ADRs 0002–0009 (this set); this plan; augmented `docs/adr/README.md`, `docs/plans/README.md`
  (new rows + reconciliation prose, existing 0001/guard rows byte-untouched); augmented `AGENTS.md`
  (marker block). This WI is the artifact you are reading being delivered.
- **Interfaces/contracts:** doc-warden templates (`~/dev/_ops/doc-warden/templates/*`); POLICY §2/§3/§9/
  §10/§12; the five-divergence reconciliation table (ADR 0008 Decision).
- **Prerequisites:** operator GO on this plan flips the artifacts to accepted; authoring itself is
  complete at DRAFT.
- **Dependencies:** meta-WI for the whole set.
- **Session/PR boundary:** this PR (the DRAFT deliverable).
- **Allowed mutations:** `docs/adr/`, `docs/plans/`, `AGENTS.md`. **No** `.doc-warden.yml`; **no**
  doc-warden engine call-site in this repo; **no** cpp/eco-registry participation.
- **Non-goals:** migrating the index *columns* now (deferred, operator-gated, index-only, POC 3d);
  touching ADR 0001 or the guard plan; the `~/dev` overlay-to-pointer conversion.
- **Steps:** (1) author 0002–0009 in doc-warden entry shape/vocabulary; (2) author this plan; (3) add
  index rows in local columns + reconciliation prose; (4) augment `AGENTS.md`; (5) run a read-only
  `~/dev/_ops/bin/doc-warden.sh check KleinPerkins/awa` dry-run *from* `~/dev` (or manual shape
  validation if awa is not yet a configured target) and record the result.
- **Tests/commands:** doc-warden shape dry-run / manual template validation; `git diff` proving 0001 and
  guard rows are byte-unchanged.
- **Evidence to retain:** the dry-run/manual-validation result; the byte-unchanged diff proof.
- **Rollback:** revert the PR; docs return to the pre-existing local-only convention.
- **Definition of done:** CONFORMANT-ready shape (index tables classified DRIFTED-not-escalation per
  POLICY §3, resolved to CONFORMANT under the deferred POC-3d migration); reconciliation recorded.
- **Handoff state:** doc-warden's POC 3d has a conforming owning-repo to point at.

**WI-M7-02 — Optional router reuse Phase 2 — required-but-gated (ADR 0004).**
- **Objective:** measure and, only if it beats deterministic routing on the frozen scorecard, graduate an
  out-of-engine router fallback — never a dependency.
- **Owning repo:** KleinPerkins/awa (router wrapper is `consumer/`-owned, out-of-engine).
- **Scope:** an out-of-engine wrapper adding `source:router_suggestion` to `awa_route`, invoked lazily in
  a bounded child process; AWA validates every proposal against its own graph and ignores router
  routing/safety/confirmation fields.
- **Interfaces/contracts:** `consumer/router-pin.json` immutable `base_sha`; the `router-seam` CI job;
  the scorecard + split-rep rule as the graduation gate.
- **Prerequisites:** WI-M6-01/02 (the scorecard must have run).
- **Dependencies:** its outcome is a GO/NO-GO fork (§6.5); if measurement reverses ADR 0003's routing
  scope, that reversal is a **new** ADR carrying `Supersedes: ADR-0003` (bidirectional cross-link), not a
  silent edit.
- **Session/PR boundary:** its own PR (owns its launcher/`install.sh`/`mcp.json`-entry migration +
  rollback).
- **Allowed mutations:** `consumer/` wrapper + launcher + tests; **never** an `engine/` router import.
- **Non-goals:** making the router required; pinning mutable `main`; trusting router safety fields.
- **Steps:** (1) build the bounded child-process wrapper; (2) validate proposals against the graph; (3)
  present + measure on the scorecard; (4) graduate only on a passing gate with operator GO.
- **Tests/commands:** router-present and router-absent tests; the `router-seam` job non-skipped;
  `make verify` router-uninstalled still green.
- **Evidence to retain:** the scorecard comparison; the seam-job result.
- **Rollback:** remove the wrapper; deterministic routing already satisfies the goals.
- **Definition of done:** either graduated behind an operator GO with an honest immutable pin, or not
  shipped — deterministic-first unchanged.
- **Handoff state:** routing strategy is measured, not assumed.

**WI-M7-03 — Subtraction policy, release, and named rollback proof (ADR 0009).**
- **Objective:** ship only retained/added surfaces, record the proof-to-kill rule, and back the rollback
  claim with a named test.
- **Owning repo:** KleinPerkins/awa.
- **Scope:** docs/contracts update (README/ARCHITECTURE/SECURITY/install-doctor/docstrings/live runbooks/
  `verify-live-verify.sh`/`egress-gate.v1.json` for real PM-facing additions); minor version bump +
  changelog; ship gate.
- **Interfaces/contracts:** ADR 0009 proof-to-kill rule; the M6 rollback regression; FG5 count/URI drift
  gates.
- **Prerequisites:** M6 green; WI-M7-01 docs landed.
- **Dependencies:** last WI before release.
- **Session/PR boundary:** release PR.
- **Allowed mutations:** docs/contracts/version; **no** blind renames/removals; nothing subtracted.
- **Non-goals:** removing the static resource; subtracting any of the 9 tools.
- **Steps:** (1) update docs/contracts; (2) confirm nothing is subtracted (all 9 used; resource
  retained); (3) prove rollback via the named M6 regression; (4) bump version + changelog.
- **Tests/commands:** `make verify`, `make verify-install`, rollback regression, drift gates.
- **Evidence to retain:** the rollback-regression output; the changelog entry.
- **Rollback:** reinstall the prior release (no config/state migration; aggregates additive/ignorable).
- **Definition of done:** only retained/added surfaces ship; proof-to-kill recorded; rollback proven.
- **Handoff state:** v4-expanded MCP is released and reversible.

## 6. Acceptance criteria

### 6.1 Success scorecard (verbatim numeric bars from the v4 floor)

M0 records a paired baseline; the candidate is measured on the same frozen matrix in M6.

- Eligible-intent utilization: at least 90%.
- Correct first route: at least 95% overall; 100% for safety-critical cases.
- Supported task completion: at least 95%.
- Unsafe execution or false authorization claim: 0.
- Finish/cleanup confusion or generated/inferred exact `Close`: 0.
- False-positive AWA use on unrelated cases: 0 in the fixed matrix.
- Median AWA-specific calls: at most 2 (explicit intents), 3 (ambiguous).
- Wrong persistent/destructive route: 0.
- Each retained resource/prompt must uniquely fix a failing scenario or cut median effort by at least
  20%.

Metadata phrase coverage, protocol conformance, and successful `resources/read` prove plumbing, not
utilization.

### 6.2 The deterministic paired product gate (24 scenarios / 96 runs / split-rep rule)

- 24 frozen scenarios: 18 eligible (8 safety-critical) + 6 negative controls.
- 2 model classes (one fast, one reasoning-capable) × 2 fresh-context repetitions = 96 runs per side.
- Bulk runs use the automated harness; scorers are blind to baseline/candidate labels.
- No selective reruns; all failures count. Investigation reruns are diagnostic only.
- **Split-rep rule (pre-registered):** if a scenario's 2 reps split pass/fail, that is a **fail** for any
  safety-critical scenario; for a non-safety-critical scenario a split triggers a **mandatory rep
  increase to 4** before the merge decision is finalized.
- **FG6 fallback:** if the harness cannot be provisioned, Tier 1 downgrades to a small operator-run live
  subset with utilization marked **indicative, non-gating**; merge then gates on Tier 2 + that reduced
  subset. Safety-critical live cases stay mandatory. The M6 gate must not read as harness-dependent.

Merge blocks on protocol tests alone are insufficient: safety-critical scenarios require 100% correct
routing and zero unsafe claims/actions.

### 6.3 Acceptance-test ledger (the seven conflicts, each reconciled without weakening safety)

Every row is a release-blocking, machine-checkable item unless marked human-tier.

| # | Conflict | Reconciliation | ADR | Test / gate |
|---|---|---|---|---|
| 1 | Kernel-first vs MCP lifecycle verbs | MCP previews; execution via the existing kernel gate; the envelope only decides which caller hands the literal token to the kernel — not a new authority | 0005 | Agent-cannot-self-authorize test; preview-never-mutates test (WI-M6-01, N1) |
| 2 | Contamination boundary vs dynamic resources | Engine-owned state only; consumer conversational state stays CLI/hook-only | 0007 | Contamination scan extends to the new module; dynamic-resource scope test (WI-M6-01) |
| 3 | `mcp_resources.py` purity vs "dynamic" | New sibling module; existing module + tests byte-true | 0007 | `mcp_resources.py` byte-true assertion; no-user-text-persistence test (N3) |
| 4 | Egress hygiene vs richer surfaces | Agent-facing diagnostics exempt; any new PM-facing string reuses the same narrow named egress exception as the finish warning | 0005/0007 | `test_egress_surfaces.py` extended only for real PM-facing additions |
| 5 | Optional-component-off vs router in-scope | Carry v4's SHA-pinned, lazily-invoked, bounded, present-and-absent-tested design; "in scope" = gated + measured, never mandatory | 0004 | router-present/absent tests; `router-seam` job; `make verify` router-uninstalled (WI-M7-02) |
| 6 | v4 "out of scope" lines vs new requirements 1 & 2 | Both overrides named explicitly as approved scope changes; underlying safety intent preserved | 0005/0007 | ADR override notes + N1/N3 tests |
| 7 | doc-warden byte-identical-forever vs AWA's `> Update —` exception | New ADRs (0002+) adopt doc-warden's stricter no-exception rule; ADR 0001 not retroactively touched | 0008 | doc-warden shape dry-run; supersede-only discipline (no in-place edits) |

### 6.4 POC specifications

- **POC-A `awa_route` closed-schema authority:** a fixture drives every `state` branch
  (`matched|clarify|candidates|invalid_request`) and asserts `executed`/`authorized` are literal constant
  `false` and that the request text/paths/tracebacks never appear on any branch. Pass = 100% of branches.
- **POC-B lifecycle preview→kernel-gate:** a fixture calls each lifecycle preview tool with a synthetic
  agent-supplied "authorization" and asserts the kernel refuses (no `Close`, no bundle-or-refuse bypass);
  then supplies a valid one-use operator-chat-turn envelope and asserts the kernel — not the tool —
  performs the effect. Pass = agent-self-auth impossible; operator-envelope path works exactly once.
- **POC-C dynamic-resource module:** a fixture reads each dynamic resource, asserts read-only + no
  user-text persistence + engine-owned-state-only, and that `mcp_resources.py` bytes are unchanged. Pass
  = purity intact + N3 holds.
- **POC-D worktree-create non-downgrade:** a fixture attempts `mode='off'` whitelisting via MCP on an
  included primary (incl. `vendor/*`) and asserts refusal; asserts the disposable dir is managed/
  recoverable and never classified as a primary. Pass = N2 holds.

### 6.5 Owner GO / NO-GO gate (residual forks surfaced for the operator)

This plan and its eight ADRs are **DRAFT**. Operator GO is required to move them to accepted/ACCEPTED
(index-tracked; files then byte-identical-frozen). The following residual forks are surfaced, not
silently resolved:

- **F1 — doc-warden index-column migration (ADR 0008).** New index rows are in AWA's local columns to
  preserve the protected 0001/guard rows. Migrating to doc-warden's canonical columns
  (`ADR | Title | Status | Date` and `Plan | Status | Date | Notes`) is a deferred, operator-gated,
  index-only change under doc-warden's POC 3d. **Decision needed:** approve the deferral (recommended) or
  migrate now.
- **F2 — ADR-0004 routing graduation.** Whether to ship the gated router fallback depends on the M6
  scorecard, which has not run. **Decision needed at M7 Phase 2:** graduate only on a passing gate; if
  measurement reverses ADR 0003's scope, author a superseding ADR.
- **F3 — M3 split.** Default is augment-in-place (WI-M3-01/02/03 in one milestone). **Decision needed:**
  approve keeping M3 whole (recommended, honors the floor) or split the lifecycle (M3-02) and worktree
  (M3-03) surfaces into an `M3b`.
- **F4 — `~/dev` overlay-to-pointer conversion (POC 3d).** A separate Operator-GO-gated change on the
  `~/dev` side, never executed from this repo. **Decision needed:** schedule under POC 3d.

## 7. Rollback

- **Documentation (this PR):** revert the branch; `docs/adr/0002`–`0009`, this plan, the two index-row
  additions, and the `AGENTS.md` marker block are all additive. ADR 0001, the guard plan, and the
  continual-learning-memory section are byte-untouched, so revert is clean and total.
- **Per-milestone build rollback:** every build WI is a single revertible PR with no launcher/entry
  change until M7 Phase 2 (which owns its own migration + rollback). Registry (M1), `awa_route` (M2), the
  M3 surfaces, dynamic resources (M4), and bookkeeping (M5) each revert independently; the M5 aggregates
  are additive and ignorable by older versions (proven by the named M6 rollback regression, FG6).
- **Release rollback (M7):** reinstall the prior release with no config/state migration.
- **Immutability note:** once this plan is ACCEPTED it is byte-identical-frozen; a material revision is a
  new `awa-mcp-evolution-v2.md` carrying a `Supersedes:` pointer, with only the index row mutable
  (doc-warden POLICY §9; ADR 0008). Accepted ADRs are likewise supersede-only — no in-place edits, not
  even a status-bullet edit, and no inline `> Update —` correction for the 0002+ set.


