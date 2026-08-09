# ADR 0005: Lifecycle verbs via MCP — preview/propose only, kernel-gated by an operator chat-turn
Status: draft — 2026-08-06

## Context

The intent catalog is the sole lifecycle vocabulary (`consumer/intent-catalog.v1.json:4`) and
declares seven verbs. Four carry `"tool_path": "mcp"` but have **no** implemented MCP tool or
executor: `protect` (`:15`, write, `:29`), `resume` (`:70`, write, `:83`), `save` (`:89`, write,
`:102`), and `cleanup` (`:108`, destructive, `:122`). `OperatorLoop.executor` is an unimplemented
injected callback defaulting to `None` (`consumer/operator_loop.py:151`, assigned `:158`) with
is-`None` guards at both call sites (`:276`, `:389`, dispatch at `:282`/`:389`). Consent scaffolding
exists but is deliberately unwired: `MUTATING_TOOLS` (`engine/mcp_server.py:257`) and
`consent_prompt()` (`:264`) with a docstring stating it "is not called by `handle` and is not
production-wired" (`:267`). `finish_current` is `"tool_path": "cli"` (`intent-catalog.v1.json:140`),
destructive (`:139`), and authorized only by the exact literal `Close` (case-sensitive, no
casefold: `consumer/finish_current.py:333`–`334`; variants rejected via `close_must_be_exact` at
`:343`). This ADR overrides both v3/v4 plans' explicit "out of scope: MCP execution of
ensure/clean/save/resume/finish" line (v4 plan §"Out of scope") as a documented, operator-approved
scope change.

## Decision

MCP tools for `protect`/`save`/`resume`/`cleanup`/`finish` are **preview/propose only**. The
mutating or destructive step executes **only** through the existing kernel gate — exact-`Close`
(case-sensitive), bundle-or-refuse, active-root heartbeat, and `class == include`. Operator
authorization is a one-use, root/session/generation-bound, exact-literal envelope captured from a
**real operator chat turn** (reusing the `finish_current` mechanism), and it is the **kernel** — not
the MCP tool — that checks it. An agent cannot self-authorize.

## Why

- **MCP executes via a new MCP-owned authorization (rejected — weakens kernel-first).** This would
  create a second authority beside the kernel. The scaffolding to do so exists but was intentionally
  left unwired precisely to avoid this (`engine/mcp_server.py:257`, `:264`, docstring `:267`), and
  there is no `beforeMCPExecution` confirmation gate wired in `handle` (`engine/mcp_server.py:476`).
  A new MCP auth path is rejected.
- **MCP pure-routing-only, forever (status quo — superseded).** The catalog already promises
  `protect`/`save`/`resume`/`cleanup` over MCP (`intent-catalog.v1.json:29`/`102`/`83`/`122`) but no
  executor backs them (`operator_loop.py:151`,`:276`,`:389`). Leaving that permanently unbuilt would
  strand a declared capability; this is a build gap to close, not a deliberate exclusion (ADR 0009).
- **MCP-preview + kernel-gate (chosen).** Reuse the proven two-phase preview→authorize path:
  `dev-worktree.sh clean --finish-current --preview` is read-only, and removal requires
  `--authorization` to equal exactly `Close` under the finish-only session gate
  (`kernel/bin/dev-worktree.sh:92`–`107`; frozen behavior in `contracts/awa-contract.v1.json:25` and
  the `finish_authorization_rule` at `:91`). MCP surfaces the preview and hands the operator's exact
  chat-turn envelope to the kernel; the kernel re-derives and checks it. Because `finish_current` is
  `tool_path: cli` (`intent-catalog.v1.json:140`), its MCP surface is preview/hand-off only. The MCP
  verbs map onto the catalog's own vocabulary (`protect` = ensure-side protect; `cleanup`(+`clean`);
  `save`; `resume`; `finish_current`) — no new verbs are invented (`intent-catalog.v1.json:4`).

## Consequences

- Enables: first-class MCP lifecycle *discoverability* (the catalog's `mcp` verbs finally have a
  surface) while every mutating/destructive effect stays behind the one kernel gate.
- Forecloses: agent self-authorization. The operator-chat-turn envelope only decides **which** caller
  may hand the literal token to the kernel; it is not a new authority (conflict #1). No MCP tool may
  emit `Close`, bypass bundle-or-refuse, skip the active-root heartbeat, or act on a non-`include`
  class.
- Must stay true: the kernel remains authoritative with the engine/MCP off; the envelope is one-use
  and root/session/generation-bound; preview never mutates.
- Defers/creates: closes the `operator_loop.executor` build gap (a gap, not a subtraction — ADR
  0009) as plan work items in M3/M6. Explicitly overrides the v3/v4 out-of-scope line as an approved
  scope change (conflict #6). Cross-links: ADR 0006 (worktree creation reuses the same non-downgrade
  discipline), ADR 0009 (build-gap vs subtraction), plan §M3/§M6 (safety tests:
  agent-cannot-self-authorize).
