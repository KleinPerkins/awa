# AWA E2E UAT results — 2026-07-07 (ON/OFF + enforced deny)

**Session:** interactive end-to-end UAT after the ASK_ON removal — modes collapse to **ON/OFF**, and
an included-primary mutation returns an **enforced `deny`** (not `ask`).
**Product pin:** `awa#17` squash-merged to `main` as `5522474` (branch `refactor/remove-ask-on`, deleted on merge).
**Host overlay pin:** `dev#26` squash-merged to `main` as `5374d45` (branch `refactor/remove-ask-on-overlay`, deleted on merge).
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

Operator-gated cleanup executed **2026-07-07** after both PRs merged and all gates passed. Evidence is
recorded here BEFORE any irreversible delete (especially the apply-back proof repo).

### Apply-back / S3 proof — recorded before deletion

- **Repo:** `KleinPerkins/awa-uat-eligible-20260706T110803` (private, created 2026-07-06, init commit `6a969c7`).
- **PR #1:** "uat: apply-back test change" — state **OPEN** at time of record —
  <https://github.com/KleinPerkins/awa-uat-eligible-20260706T110803/pull/1>
  (head `cursor/worktree/awa-uat-20260706T110803` → base `main`). This PR is the apply-back / S3 proof:
  the apply-back flow opened a PR from the linked worktree to the disposable remote.

### Artifacts

| Artifact | Kind | Location | Cleanup verb | Status |
|----------|------|----------|--------------|--------|
| `awa-uat-eligible-20260706T110803` | GitHub repo (apply-back proof) | `KleinPerkins/awa-uat-eligible-20260706T110803` | `gh repo delete` (evidence recorded above) | DELETED 2026-07-07 |
| `awa-uat-20260706T110803` | local git repo (clone of ^) | `~/dev/personal/awa-uat-20260706T110803` | `rm -rf` | REMOVED 2026-07-07 |
| `refactor/remove-ask-on` | local branch (merged `awa#17`→`5522474`) | AWA linked worktree | removed by the parent session during its root move (not by the `clean` verb) | REMOVED 2026-07-07 |
| `refactor/remove-ask-on-overlay` | local branch (merged `dev#26`→`5374d45`) | `~/dev` | `git branch -D` | REMOVED 2026-07-07 |
| `awa-20260707094822` | AWA linked worktree | `~/.local/share/awa/worktrees/awa/awa-20260707094822` | removed by the parent session during its root move (not by the `clean` verb) | REMOVED 2026-07-07 |

### Already absent / no-op (verified read-only)

- Remote throwaways `awa-cloud-hook-uat-e2e`, `awa-cloud-hook-uat`, `awa-applyback-uat`, `awa-move-uat`
  — already deleted (404 on `gh repo view`).
- Host mode entry — already clean (`worktree-modes.yml`: `default_mode: on`, `modes: {}`); no `mode remove` needed.
- Stale `~/dev` branch `cursor/worktree/awa-uat-20260706T110803` — already absent.

### Preserved (evidence / reusable harness — NOT deleted)

- `RESULTS-e2e-uat-20260706.md` (historical, SUPERSEDED banner), all hook-probe / R-A / `workspace_roots`
  regression RESULTS, the `SECURITY.md` ask-not-enforced note, and the bootstrap scripts
  (`bootstrap-eligible-uat.sh` / `bootstrap-hook-probe-uat.sh`).
- Hard-excluded (never touched): `KleinPerkins/{awa,dev,skills,ecosystem-orchestrator}`.

> Residual (operator UI, tracked in the verdict table): the live ask-then-deny probe on Desktop AND
> cloud. The apply-back proof above is retired by record; re-prove apply-back on a fresh disposable
> remote in the next live UAT if a live artifact is desired.
