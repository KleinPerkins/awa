# AWA E2E UAT results — 2026-07-06

> **SUPERSEDED by 2026-07-07.** This session verified the pre-refactor `ask` / `ASK_ON` behavior.
> The ASK_ON removal (2026-07-07) collapsed modes to ON/OFF and changed an included-primary mutation
> from `ask` to an enforced `deny`. Kept as history; the current runbook + results are
> `RESULTS-e2e-uat-20260707.md`. `ask_on` / `ask` references below reflect the behavior at the time.

**Session:** interactive end-to-end UAT (Desktop + Cloud, full apply-back)  
**Product pin:** `a965adf` (round-2 hardening #14)  
**Host overlay pin:** `8d32d6c` (pre-session) → overlay MCP env repaired at session start via local install  
**Fixtures:** `personal/awa-uat-20260706T110803`, `~/awa-mcp-uat`, `KleinPerkins/awa-uat-eligible-20260706T110803`

---

## Phase 0 — Preflight

| Check | Result |
|-------|--------|
| `make verify` | PASS (187 tests, contract-freeze 7/7, zero-link, verify-live-verify) |
| `install.sh --doctor` | PASS |
| `awa-contract-freeze.sh` | PASS 7/7 |
| `worktree-verify.sh` | PARTIAL — H3 setup UAT rows fail (pre-existing env; kernel guarantee rows PASS) |
| MCP `awa` env | PASS after local install with host policy (`AWA_POLICY`, `AWA_GOVERNED_ROOT`) |
| Fixtures bootstrapped | PASS |

---

## Phase 1 — Guard ask + ensure (headless proxy)

| Check | Result | Evidence |
|-------|--------|----------|
| Primary mutating → ask (bash hook) | **PASS** | `permission: ask`, frozen user_message shape |
| Linked worktree mutating → allow | **PASS** | `permission: allow` in `.wt` |
| `ensure --json` creates worktree | **PASS** | `action: created`, `move_agent_to_root.rootPath` set |
| Live Cursor ask prompt UX | **OPERATOR PENDING** | Requires Desktop agent — see `OPERATOR-UAT-SESSION.md` Phase 1 |
| `move_agent_to_root` relocation | **OPERATOR PENDING** | Requires cursor-app-control MCP |

**Finding (MINOR):** first `dev-worktree.sh ensure` linked worktree under **AWA product** `.git/worktrees/` instead of fixture common-dir. Workaround: `git -C <fixture> worktree add` directly. Document for follow-up.

---

## Phase 2 — Live MCP (headless + operator)

| Check | Result | Evidence |
|-------|--------|----------|
| `tools/list` includes mode tools | **PASS** | 9 tools incl. `awa_mode_set` … `awa_mode_sync` |
| `awa_mode_list` resolves host modes file | **PASS** | `default_mode: ask_on`, path `~/dev/_ops/policy/worktree-modes.yml` |
| Broad-off `.` rejected | **PASS** | `ok: false`, MCP `isError: true` |
| `awa_mode_set` explicit rel | **PASS** | `rel: personal/awa-uat-20260706T110803`, `mode: ask_on` |
| `beforeMCPExecution` on write tool | **OPERATOR PENDING** | Requires Desktop agent + hook-probe log |

---

## Phase 3 — Mode end-to-end (headless + operator)

| Check | Result | Evidence |
|-------|--------|----------|
| ASK_ON → guard ask (engine) | **PASS** | `classification: ask_on`, `permission: ask` |
| OFF → guard allow | **PASS** | `classification: exclude`, `permission: allow` |
| Dashboard `summary.ask_on` + repo row | **PASS** | JSON: `classification: ask_on`, `mode: ask_on` |
| default_mode ask_on (no explicit entry) | **PASS** (headless) | status: `policy default_mode: ask_on` |
| Live dashboard canvas render | **OPERATOR PENDING** | Open canvas + Refresh |

---

## Phase 4 — Cloud hooks

| Check | Result | Evidence |
|-------|--------|----------|
| Cloud probe repo | **PREPARED** | `bootstrap-hook-probe-uat.sh` procedure in `OPERATOR-UAT-SESSION.md` |
| Live cloud agent run | **OPERATOR PENDING** | Re-verify L9/L10 post mode hardening |

Prior evidence (2026-07-05) remains valid for hook event shapes; this session re-runs after guard changes.

---

## Phase 5 — Apply-back lifecycle

| Check | Result | Evidence |
|-------|--------|----------|
| adopt + attest | **PASS** | lease_id + `attested: true` |
| apply-back preview | **PASS** | recovery patch captured, `commits_ahead: 1` |
| apply-back execute + PR | **PASS** | PR https://github.com/KleinPerkins/awa-uat-eligible-20260706T110803/pull/1 |
| recover list | **PASS** | patches under `~/.local/state/awa/recovery/` |
| clean bundle-or-refuse | **PARTIAL** | dirty refusal PASS; clean+bundle succeeded after reset (branch left when HEAD drifted) |

---

## Verdict

| Layer | Status |
|-------|--------|
| Headless / CLI / engine / hook JSON | **GREEN** |
| Live Desktop UX (prompt, MCP hook log, canvas, move) | **OPERATOR SIGN-OFF PENDING** |
| Live Cloud hooks | **OPERATOR SIGN-OFF PENDING** |
| Apply-back disposable remote | **GREEN** |

Operator: complete Phases 1–4 live sections in `OPERATOR-UAT-SESSION.md` and paste closeout block.
