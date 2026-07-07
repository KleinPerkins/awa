# AWA E2E UAT results — 2026-07-07 (ON/OFF + enforced deny)

**Session:** interactive end-to-end UAT after the ASK_ON removal — modes collapse to **ON/OFF**, and
an included-primary mutation returns an **enforced `deny`** (not `ask`).
**Product pin:** `<fill: HEAD of refactor/remove-ask-on>`
**Host overlay pin:** `<fill: HEAD of refactor/remove-ask-on-overlay>`
**Fixtures:** bootstrapped fresh at session start via `bootstrap-eligible-uat.sh` /
`bootstrap-hook-probe-uat.sh` (this session does NOT reuse the 2026-07-06 dated fixtures).

> Supersedes `RESULTS-e2e-uat-20260706.md` (kept as history). The 2026-07-06 session verified the
> pre-refactor `ask`/`ask_on` behavior; this session verifies the ON/OFF + `deny` behavior.

---

## Scope of change under test

- `MODE_VALUES = ("on","off")`; `ASK_ON` deleted; `classify()` emits only `include|exclude|advisory|not-git`.
- ON = protected: a confirmed mutating command on an included PRIMARY checkout ⇒ hook **`deny`**.
- OFF = no blocking. One fail-safe rule: only `off` disables; any other value ⇒ include/ON.
- Cloud (`is_background_agent` / broker / `/workspace`) ⇒ degrade-to-allow before the deny branch.
- `afterFileEdit` ⇒ allow (observation-only). Infra failure ⇒ allow (anti-brick).

---

## Phase 0 — Preflight

| Check | Result | Evidence |
|-------|--------|----------|
| `make verify` (product worktree) | PENDING | |
| `install.sh --doctor` | PENDING | |
| `awa-contract-freeze.sh` (deny + deny_shape) | PENDING | |
| `worktree-verify.sh` (host overlay) | PENDING | |
| Acceptance grep: zero `ask_on` in runtime code | PENDING | |
| MCP `awa` env | PENDING | |
| Fixtures bootstrapped fresh | PENDING | |

---

## Phase 1 — Guard deny (the load-bearing change)

| Check | Result | Evidence |
|-------|--------|----------|
| Primary mutating → **deny** (bash hook, headless) | PENDING | expect `permission: deny`, `deny_shape` keys |
| Primary read-only → allow | PENDING | |
| Linked worktree mutating → allow | PENDING | |
| **Live Desktop probe: `ask` runs, `deny` blocks** | OPERATOR PENDING | record whether the command executed |
| **Live Cloud probe: mutation allowed (not bricked)** | OPERATOR PENDING | `/workspace` degrade-to-allow |
| `afterFileEdit` → allow (permission ignored) | PENDING | |
| Deny recovery message correct (stop-retry, dropdown/env override) | PENDING | inspect `agent_message` |

**Live ask-then-deny probe (residual to close L4).** On Desktop AND Cloud, drive one
`beforeShellExecution` returning `ask` and one returning `deny` for a mutating command on an included
primary checkout, and record for each whether the command actually ran. Expected: `ask` ⇒ ran
(non-blocking, L4); `deny` ⇒ blocked (Desktop); cloud ⇒ allowed (degrade).

---

## Phase 2 — Modes end-to-end (ON/OFF)

| Check | Result | Evidence |
|-------|--------|----------|
| `mode set <rel> on` / `off` accepted | PENDING | |
| `mode set <rel> ask_on` rejected (2-value set) | PENDING | invalid value error |
| Legacy `default_mode: ask_on` → `on` via `mode repair` | PENDING | |
| Legacy per-repo value → resolves to `on` (protected) | PENDING | classify ⇒ include |
| OFF → guard allow (classification exclude) | PENDING | |
| Dashboard JSON: on/off, no `summary.ask_on`, advisory kept | PENDING | |

---

## Phase 3 — MCP (ON/OFF)

| Check | Result | Evidence |
|-------|--------|----------|
| `awa_mode_set` enum on\|off (no ask_on) | PENDING | |
| `awa_mode_list` resolves host modes file (`default_mode: on`) | PENDING | |
| Broad-off `.` rejected | PENDING | |

---

## Phase 4 — Cloud hooks

| Check | Result | Evidence |
|-------|--------|----------|
| Cloud mutation not blocked (degrade-to-allow) | OPERATOR PENDING | |

---

## Phase 5 — Apply-back lifecycle

| Check | Result | Evidence |
|-------|--------|----------|
| adopt + attest | PENDING | |
| apply-back preview → execute + PR (disposable remote) | PENDING | |

---

## Verdict

| Layer | Status |
|-------|--------|
| Headless / CLI / engine / hook JSON | PENDING |
| Live Desktop deny UX + ask-then-deny probe | OPERATOR SIGN-OFF PENDING |
| Live Cloud degrade-to-allow | OPERATOR SIGN-OFF PENDING |
| Apply-back disposable remote | PENDING |

---

## Cleanup ledger

Track every disposable artifact this session creates so the operator-gated cleanup phase can reverse
it. **Nothing here is deleted by the implementation worker** — cleanup is a separate operator-gated
step.

| Artifact | Kind | Location | Cleanup verb | Status |
|----------|------|----------|--------------|--------|
| `<fixture eligible repo>` | local git repo | `<path>` | operator `rm -rf` after sign-off | OPEN |
| `<fixture eligible remote>` | GitHub repo | `KleinPerkins/<name>` | operator `gh repo delete` | OPEN |
| `<hook-probe repo>` | local git repo | `<path>` | operator `rm -rf` after sign-off | OPEN |
| `<apply-back disposable remote>` | GitHub repo | `KleinPerkins/<name>` | operator `gh repo delete` | OPEN |
| `<linked worktrees created>` | git worktrees | `<paths>` | operator `dev-worktree.sh clean` (bundle-or-refuse) | OPEN |

> The implementation worker records rows here as fixtures are created; it does NOT run any cleanup
> verb (`gh repo delete`, `rm -rf`, `mode remove`, branch/worktree deletion). Those are reserved for
> the operator-gated cleanup phase.
