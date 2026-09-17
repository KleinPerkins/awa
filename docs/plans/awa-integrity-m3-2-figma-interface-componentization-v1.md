# AWA Integrity M3.2 — Figma-backed interface design and server-rendered componentization

- **Version:** v1
- **Status:** DRAFT
- **Date:** 2026-09-17
- **Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
- **Plan-type:** agentic-execution
- **Relates to:** [ADR 0020](../adr/0020-awa-integrity-surveillance-and-lifecycle.md), the frozen
  [integrity surveillance and lifecycle plan](awa-integrity-surveillance-and-lifecycle-v1.md), and
  its accepted [delivery-priority addendum](awa-integrity-execution-priority-addendum-v1.md).
- **Review provenance:** drafted from `origin/main` at
  `5b734c70ab1db80879b7a4936c31ae948a92a4e5` after M3.1
  [PR #165](https://github.com/KleinPerkins/awa/pull/165) merged with every runnerless check passing.

**Goal:** turn the functional M3.1 console into a clear, accessible interface for a non-technical PM
operator, using Figma to approve the visual contract and small Python render helpers to implement it,
without replacing AWA's local, no-build, server-rendered architecture.

**Architecture:** keep `engine/integrity_console.py` as the deterministic HTML/CSS renderer and
`engine/integrity_server.py` as the foreground-only loopback delivery boundary. Figma specifies
responsive states, reusable visual components, and tokens; reviewed Python constants and pure render
helpers remain the runtime source. No React application, package manager, bundler, generated frontend,
standing service, or network asset is introduced.

**Tech stack:** Figma during the authorized design pass; Python 3.9 stdlib; semantic HTML; inline
deterministic CSS; the existing CSP-hashed clock-only script; `unittest`; existing runnerless PR
automation. No GitHub Actions runner or recurring infrastructure.

> This draft authorizes no Figma mutation and no implementation. After acceptance, execution still
> requires a separate explicit owner GO. Each work body is one Draft PR, left unarmed.

---

## Global constraints and inherited threat model

- Preserve ADR 0020: kernel-first; one evaluator/public projection; stale, missing, or malformed
  status never appears green; AWA owns product code while `~/dev` owns live host wiring.
- Preserve M3.1's lifecycle: bind only `127.0.0.1` on an OS-selected ephemeral port; mint a fresh
  high-entropy token per launch; run foreground-only; stop after bounded idle; persist no token.
- Preserve request gates: exact token path, exact `Host`, exact POST `Origin`, no CORS, no proxy
  headers, bounded headers/body, POST-only check execution, no destructive route.
- Preserve response protections: `Cache-Control: no-store`, `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`, strict CSP, no remote asset or font, no token or sensitive
  value in response bodies, logs, screenshots, fixtures, or generated artifacts.
- Preserve data boundaries: render only the closed `awa-integrity-public/v1` projection. Never add
  raw evidence, secrets, absolute host paths, credentials, or arbitrary status fields to the UI.
- Preserve the static console: action-free, token-free, deterministic, private `0600`, and
  self-staling through the existing clock-only script. Served interactivity remains a relative,
  empty-body HTML form; no `fetch`, XHR, WebSocket, cookies, local storage, analytics, or telemetry.
- Preserve compatibility: Python 3.9, no frontend build step, no runtime dependency, no new service,
  no paid runner, no performance SLA, and no `chaos-scheduler` or Cursor Canvas use.
- Treat Figma Code Connect as optional and capability-gated. Its templates are UI/framework-agnostic
  but require JavaScript/TypeScript authoring. Direct mapping may be unavailable or not configured in
  the authorized environment; use it only when both available and configured. Do not add
  JavaScript/TypeScript, package tooling, React, or another frontend stack solely to obtain Code
  Connect.

## 1. Current state and roadmap boundary

`origin/main` at `5b734c70` contains M3.1's functional console:

- `integrity_console.render()` deterministically renders the closed public projection;
- `render_no_status()` provides first-run recovery;
- `IntegrityConsoleServer` serves the latest referenced projection and a POST-only check action;
- the server handles absent status, corrupt/unavailable status, request-local GET failures,
  evaluator failure, idle shutdown, and browser-open failure without leaking the token;
- tests pin loopback/token/Host/Origin/CORS/form/CSP/redaction/idle behavior.

All 13 active AWA implementation task bodies from M1-A.1 through M3.1 are merged. This is
**implementation completion, not rollout completion**: the frozen plan body remains byte-identical,
its mutable index row records the 13/13 implementation status, and §12 is the canonical ledger for
deferred rollout gates. The accepted priority addendum separately keeps M4/Quickhost export outside
the active sequence and Slack activation opted out.

M3.2 is a new, separate milestone. It neither reopens those completed implementation bodies nor
silently completes the §12 rollout gates.

## 2. Operator outcome

The operator can open the private console and answer, without knowing AWA internals:

1. Is AWA healthy, needs attention, or critical?
2. When was it checked, and when will the result become stale?
3. What needs attention in plain language?
4. Can I safely run checks now?
5. What happened if status cannot be read or the check fails?
6. Why did the console stop, and what exact local command restarts it?

Severity is never communicated by color alone. Technical identifiers may remain available as
secondary detail, but the primary hierarchy and copy are operator-facing.

## 3. Goals and non-goals

### Goals

- Approve one responsive Figma component/state specification before each corresponding code slice.
- Establish a small token and component vocabulary mapped directly to pure Python render boundaries.
- Cover every truthful server/status state with clear copy, action availability, and recovery guidance.
- Improve keyboard, screen-reader, zoom, contrast, reduced-motion, and narrow-screen usability.
- Preserve deterministic static output and security-sensitive HTTP behavior.
- Add focused DOM/content/token contracts and a bounded visual-parity review without a new CI service.

### Non-goals

- React, JSX, JavaScript/TypeScript application code, npm, a bundler, client routing, hydration, or a
  design-system framework; specifically, no JS/TS or package tooling solely for Code Connect.
- Figma Code Connect as a prerequisite, generated application code, or Figma as a runtime dependency.
- New evaluator fields, lifecycle actions, destructive controls, repair/quarantine UI, or exports.
- Persistent server, background daemon, auto-refresh/polling, notifications, remote assets, telemetry,
  multi-machine access, Quickhost, or a broad AWA UI redesign.
- Any rollout activity in the canonical deferred-gates ledger (§12).
- Performance budgets or screenshot pixel identity across browser/OS font-rendering engines.

## 4. Figma-first workflow

Execution uses the Figma integration only after plan acceptance and explicit implementation GO:

1. **Figma Gate 0:** before any discovery or design mutation, the owner identifies an authorized
   existing destination file or explicitly authorizes creation of one empty destination file. Record
   the file key and authorization basis in the Draft PR without secrets or tokenized URLs.
2. If a new destination is authorized, create only the blank file first. Then, for either an existing
   or new destination, search the connected design system and available libraries before creating any
   frame or component. Record the selected existing
   components, variables, and styles; if no suitable system is accessible, use the minimum local
   primitives required by this plan rather than inventing a broad library.
3. Import no production data, tokenized URL, host path, username, machine identifier, or secret.
   Figma fixtures use synthetic counts, timestamps, reasons, and generations.
4. Design the minimum end-to-end slice first: shell, status summary, freshness, primary action,
   no-status recovery, and healthy state at desktop and narrow widths.
5. Review that slice with the owner before implementation. Then design the remaining warning,
   critical, failure, unavailable, and shutdown-guidance states using the approved primitives.
6. Define component variants and responsive behavior, including focus, disabled/unavailable action,
   long copy, large counts, and 200% zoom. Avoid decorative variants with no runtime state.
7. Attempt Code Connect only after the source boundaries exist and only if direct mapping is available
   and configured in the authorized environment. If it is unavailable or unconfigured, record that
   capability state in the PR and use §6 plus tests; do not add its required JS/TS authoring or package
   tooling solely to enable it.
8. Treat owner-approved Figma frames as the visual specification. Runtime HTML is still generated
   only from reviewed repository source; no Figma export writes production source automatically.

## 5. Required state contract

Every state gets desktop and narrow Figma frames, a deterministic synthetic fixture, semantic output
assertions, and explicit action/recovery behavior.

The **normative restart command** is `awa-engine integrity console --serve --open`. Every reference
to restart guidance below means that exact command text, never a capability URL or token.

| State | Primary message | Action and recovery contract |
|---|---|---|
| No status / first run | “No status yet” | Show `Run checks now`; never imply green; explain that the first check creates local status. |
| Healthy | “AWA is healthy” | Show freshness and last-check time; action remains available in served mode. |
| Degraded / warning | “AWA needs attention” | Explain affected checks in plain language; keep technical id secondary; offer only `Run checks now`. |
| Critical | “AWA needs immediate attention” | Distinct icon/text/heading, not color-only; never expose repair/destructive action. |
| Fatal check failure | “Checks could not complete” | HTTP 500 after evaluator/commit failure; send a token-free page with no action form, then close the server as M3.1 does. Show exactly `Restart the console, then run checks again.` and the normative restart command. |
| Status unavailable/corrupt | “Status cannot be read” | Recoverable request-local HTTP 503; keep the server available and retain the relative `Run checks now` form so a valid POST can recover in-session. |
| Stale | “Status is stale / critical” | Existing clock-only script forces effective red after `fresh_until`; explain that a new check is required. |
| Console idle shutdown | “This console closes after 5 minutes idle” | Persistent guidance on every served console page shows the normative restart command. Never embed the current capability URL/token. After shutdown, browser connection failure is expected and no daemon restarts it. |
| Static snapshot | “Private snapshot” | No form/button/restart action, no token, and no behavior beyond clock-only staleness. |

There is no deterministic rendered “check running” state. The existing synchronous empty-body form
submission remains sufficient for this ephemeral local console: every served action area persistently
says **“Checks may take a moment; this page returns when complete,”** and the browser's native loading
indication is the pending feedback until the POST completes and redirects. Add no asynchronous state,
polling, background work, or second client script.

## 6. Component and token taxonomy

Keep helpers in `engine/integrity_console.py` for M3.2. Do not create a package or generic component
framework unless a second real renderer consumer appears.

| Figma / UI primitive | Python/server-rendered boundary |
|---|---|
| `IntegrityPage` | `render()` / `render_no_status()` and a shared private page-shell helper |
| `StatusSummary` | pure helper receiving effective state, heading, supporting copy, freshness |
| `StatusIcon` | inline semantic text/SVG only if self-contained and decorative markup is hidden |
| `ActionForm` | served-only helper; relative POST action only; absent from static output |
| `MetricCard` | pure helper for the four existing closed-projection counts |
| `CheckList` | semantic list/table helper for existing invariant id, severity, redacted reason |
| `HistoryList` | bounded existing history projection; responsive table/list presentation |
| `Notice` | no-status, unavailable, request-failure, stale, and idle/restart guidance variants |

Tokens stay as CSS custom properties inside the deterministic `_STYLE` source:

- semantic colors: surface, elevated surface, text, muted text, border, healthy, warning, critical,
  focus; all contrast-checked and never the sole state signal;
- typography: system stack only, bounded heading/body/label scale, readable line length;
- spacing/radius/border: a small named scale used by all helpers;
- responsive breakpoints: content-driven, with one narrow layout threshold unless evidence requires
  another;
- motion: none required; honor `prefers-reduced-motion` if any transition is later justified.

Figma variable names should match these semantic token names. Repository values are reviewed and
copied explicitly; no generated token pipeline or synchronization service is added.

## 7. Accessibility and responsive acceptance

- One `h1`, logical heading order, landmarks, lists/tables with headers, and form labels/instructions.
- Overall status uses visible text plus a non-color cue; status changes and error pages have clear
  document titles. Do not use `aria-live` for values that cannot update in place.
- Full keyboard operation with a visible focus indicator; no focus trap; minimum 44×44 CSS-pixel
  primary target where layout permits.
- WCAG AA contrast for normal text and meaningful controls; do not encode severity through hue alone.
- Works at 320 CSS px, common desktop width, 200% browser zoom, long invariant names/reasons, and
  large counts without horizontal page scrolling. Data tables may become stacked labeled rows.
- Source order matches reading order. No hover-only information. System fonts only.
- Pending-submission and failure copy does not overpromise completion, safety, delivery, or recovery.

## 8. Determinism, security, and source-of-truth rules

1. `awa-integrity-public/v1` remains the sole data input. Component helpers receive normalized closed
   values, never the raw status.
2. Python/CSS source is the runtime authority. Figma is the owner-approved visual specification;
   this plan is the execution mapping. Generated `console/<N>.html` remains derived and is never
   hand-edited or committed.
3. Rendering the same normalized projection and mode produces byte-identical HTML. Stable ordering,
   JSON embedding escapes, HTML escaping, CSP hashes, `0600` artifacts, and no-remote-asset tests stay.
4. Static and served modes remain explicit. Static CSP keeps `form-action 'none'`; served CSP permits
   only the exact tokenized loopback form URL in the response header/meta while page markup uses the
   relative action. No token appears in HTML body.
5. Error pages and no-status pages use shared approved visual primitives but remain token-free,
   closed-data renderers. Generic HTTP status and body semantics remain 404/500/503 as applicable.
6. No design fixture, screenshot, PR description, golden file, or test failure includes a live token,
   host path, secret, or real machine status.

## 9. Work bodies

### Owner gate 0 — plan acceptance and implementation authorization

- [ ] Owner accepts this plan.
- [ ] Owner separately says GO for M3.2 execution.
- [ ] Owner identifies an authorized existing Figma destination file, or explicitly authorizes
  creating one empty destination file.

Without all three checks, stop before Figma mutation or code changes. Record the destination file key
and authorization basis without secrets; if a new file is authorized, create it blank and then perform
library/design-system discovery before any frame or component.

### M3.2-A — minimum end-to-end Figma-to-Python slice

**Outcome:** approved shell/tokens plus production no-status and healthy states, while all existing
other states continue to render.

1. After Figma Gate 0, search the existing Figma design system/libraries and record reuse choices.
2. Build synthetic desktop/narrow frames for shell, no-status, healthy, freshness, action, metrics,
   focus, and idle/restart guidance.
3. **Owner checkpoint 1:** approve the visual direction, component names, copy, and responsive behavior.
4. Refactor only enough of `integrity_console.py` to add semantic CSS tokens and pure shell/summary/
   action/metric helpers; implement the approved no-status and healthy variants.
5. Keep the closed projection, static/served split, CSP, token, routes, methods, and HTTP semantics
   unchanged. Add focused deterministic, state-copy, token-free, CSP, semantic, and narrow-markup tests.
6. Open one Draft PR with the §10 reproducibility record; run Bugbot and security review; leave
   unarmed.

**Production step:** first-run and healthy operators receive the approved interface on the existing
M3.1 server; warning/error paths remain functional through existing rendering.

### M3.2-B — complete truthful state coverage

**Outcome:** every state in §5 uses the approved component vocabulary and recovery copy.

1. Design degraded, critical, stale, request-failure, unavailable/corrupt, and static
   variants from M3.2-A primitives at desktop/narrow widths.
2. **Owner checkpoint 2:** approve all state hierarchy, copy, actions, and non-color cues.
3. Implement variants as pure renderer helpers. Convert the existing 500/503 text responses to
   deterministic HTML pages without changing status codes, evaluator calls, token handling, or M3.1's
   split behavior: fatal 500 closes the server and has no form; recoverable request-local 503 keeps the
   server and relative `Run checks now` form.
4. Add the §5 persistent synchronous-submission copy beside the served action. Treat browser-native
   loading as sufficient pending feedback; add no rendered running state, new script, route,
   background worker, or persisted state.
5. Add one focused test per state plus redaction and status-code coverage. Assert fatal 500 closes the
   server, has no form, and contains the exact recovery sentence plus normative restart command;
   assert recoverable 503 keeps the server and relative `Run checks now` form and permits a successful
   in-session POST; assert static output has no restart action and no destructive route.
6. Open one Draft PR with the §10 reproducibility record; run Bugbot and security review; leave
   unarmed.

**Production step:** every reachable operator state is coherent and recoverable without technical
knowledge, while server behavior remains M3.1-compatible.

### M3.2-C — accessibility, responsive, and parity hardening

**Outcome:** approved end-to-end interface with bounded evidence and no compatibility residue.

1. Exercise all synthetic fixtures at 320 px, desktop, and 200% zoom; keyboard-only and screen-reader
   structure; long text/counts; forced stale clock; static and served modes.
2. Compare deterministic local renders with owner-approved Figma frames using synthetic data and no
   live token. Record the reproducible review facts required by §10; any ephemeral screenshots used
   during review are discarded, not committed. Do not make cross-browser pixel equality a CI gate.
3. Add stable regression checks for DOM landmarks/headings, component/state presence, token names,
   contrast values, no horizontal page overflow in the chosen local browser check, CSP hashes,
   deterministic HTML, redaction, and all M3.1 HTTP/security invariants.
4. Attempt Code Connect only if direct mapping is available and configured in the authorized
   environment. Otherwise record that state and rely on §6 plus tests; do not add JS/TS authoring,
   package tooling, or change architecture solely for it.
5. Remove superseded CSS/markup helpers only after all fixtures and tests prove parity.
6. **Owner checkpoint 3:** approve visual parity and operator usability from synthetic local evidence.
7. Open one Draft PR with the §10 reproducibility record; run Bugbot and security review; leave
   unarmed.

**Production step:** the full interface is accessible, responsive, deterministic, and regression
protected. The §12 rollout gates remain deferred.

## 10. Focused test and acceptance matrix

| Concern | Required proof |
|---|---|
| State completeness | One synthetic deterministic fixture and exact heading/action/recovery assertions for every §5 state. |
| Static/served parity | Shared visual components; static has no action/token. Interactive served states use only the relative empty-body POST form; fatal 500 has no form. |
| Security | Existing loopback/token/Host/Origin/no-CORS/proxy/body/method/destructive-route tests stay green; error bodies leak nothing. |
| CSP/redaction | Exact header/meta CSP relationship, hashes, no remote assets, escaped JSON/HTML, no path/secret/token fixtures. |
| Failure recovery | Fatal 500: exact recovery sentence + normative restart command, no form, server closes. Recoverable request-local 503: relative `Run checks now` form remains, server stays available, valid POST recovers in-session. |
| Accessibility | Automated semantic assertions plus recorded keyboard/zoom/screen-reader-structure review; AA token contrast calculation. |
| Responsive | Synthetic 320 px/desktop/200% evidence for every state, long copy, large counts, and responsive table/list behavior. |
| Determinism | Same normalized projection/mode yields byte-identical HTML; generated artifact remains `0600` and status-referenced. |
| Lifecycle | Fresh port/token per launch; rejected traffic does not extend idle; valid activity does; shutdown closes socket. Every served idle-shutdown guidance surface and fatal-500 page contains the exact normative restart command; static output contains no restart action. |
| Pending feedback | Served action shows the persistent “Checks may take a moment” copy; synchronous POST/303 behavior stays; no rendered running state or added script. |

Every implementation Draft PR description must include a reproducibility record with:

- authorized Figma file and relevant node links;
- reused library assets/components/variables;
- synthetic fixture ids used for each reviewed state;
- browser name and exact version;
- viewport dimensions and zoom for each review pass;
- horizontal-overflow result (`pass` or an exact failing state/width).

Commit no screenshot, Figma export, generated HTML, or other generated UI review artifact. If an
ephemeral screenshot is used during review, discard it before commit.

Per Draft PR, run the smallest relevant tests first:

```bash
python3 -m unittest engine.tests.test_integrity_console engine.tests.test_integrity_server -v
git diff --check
VERIFY_BASE=origin/main make verify-docs
```

For code-bearing M3.2 PRs, also run the repository's authoritative `make verify` before review.
Do not execute any §12 deferred rollout gate unless separately authorized.

## 11. Migration and rollback

- No schema, status file, route, command, port, token, or persisted-state migration is planned.
- Existing projections render through the new helpers; unknown/unavailable input stays fail-closed
  to a non-green/error state.
- Land A → B → C serially. Do not keep a parallel renderer, feature flag, generated CSS bundle, or
  legacy page after C proves all state fixtures.
- Before merge, correct with a new commit or close the Draft PR. After merge, revert the relevant PR
  normally. Because status/projection schemas are unchanged, rollback requires no state conversion.
- If implementation requires a new script, async route, client data fetch, persistent process,
  frontend build, projection field, or remote asset, stop and draft a new architecture decision
  before proceeding.

## 12. Canonical deferred rollout-gates ledger

M3.2 completion means the reviewed repository implementation and synthetic local evidence are ready.
It does not mean the original roadmap or M3.2 is released or active on the operator's machine. This
is the single M3.2 ledger for deferred host/release activity; earlier sections reference it rather
than restating it.

Deferred until separate explicit authorization:

- release/tag and any Skills pointer update;
- installation or repair of the live AWA runtime;
- `~/dev` host wiring/activation;
- live Cursor Desktop UAT, including real browser launch and operator walkthrough;
- Slack activation and M4 export/Quickhost work.

If the later authorized Figma search finds more than one suitable library/design system, selecting
the preferred one is part of owner checkpoint 1; it does not block plan acceptance now.

No unresolved architecture or interaction decision remains before plan acceptance. The ordinary
owner acceptance, separate implementation GO, and Figma Gate 0 destination authorization remain
explicit execution gates in §9.

## 13. ADR assessment

No new ADR is required. This plan implements the already-authorized “thin interface” and ephemeral
M3 increment in ADR 0020 while preserving its renderer, no-build delivery, closed projection,
security model, and lifecycle. Figma supplies an approval surface and component vocabulary, not a
new runtime architecture.

A new ADR becomes necessary only if execution proposes a durable change such as a frontend build
toolchain, additional client script/network behavior, persistent service, new projection contract,
remote asset, or weakened token/Host/Origin/CSP/form boundary.
