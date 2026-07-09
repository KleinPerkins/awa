# AWA end-to-end UAT — interactive operator session

> **Session date:** 2026-07-07  
> **Scope:** ASK_ON removal — ON/OFF modes, enforced **`deny`** on an included-primary mutation,
> Desktop hard-deny + Cloud degrade-to-allow, live MCP write tools, full apply-back  
> **Evidence ledger:** `live-verify/RESULTS-e2e-uat-20260707.md`

Run this in **one Desktop agent chat** (your primary driving chat). Use a **separate Cloud agent** only for Phase 4.

This session bootstraps its OWN fresh fixtures — it does **not** reference any earlier dated fixture.

---

## Before you start (~3 min)

### Terminal reset + fresh fixtures

```bash
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
cd ~/dev/capabilities/awa && AWA_POLICY=~/dev/_ops/policy/worktree-policy.yml \
  AWA_GOVERNED_ROOT=~/dev ./install.sh --repair
bash ~/dev/capabilities/awa/live-verify/bootstrap-eligible-uat.sh          # prints <FIXTURE> + <FIXTURE_REL>
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-mcp-uat
```

Confirm MCP env (Settings → MCP → **awa** enabled; restart Cursor if you changed it):

```bash
python3 -c "import json; print(json.dumps(json.load(open('$HOME/.cursor/mcp.json'))['mcpServers']['awa'], indent=2))"
# Expect env.AWA_POLICY -> ~/dev/_ops/policy/worktree-policy.yml
# Expect env.AWA_GOVERNED_ROOT -> ~/dev
```

---

## Phase 1 — Guard HARD DENY + ask-then-deny platform probe (Desktop, ~15 min)

**Fixture:** the eligible repo printed by `bootstrap-eligible-uat.sh` (under `~/dev/personal/awa-uat-*`),
classified `include` / mode ON via host `default_mode: on`.

### 1a. Hard deny (not a modal)

1. Open the **eligible fixture** as a **Desktop (Local)** agent root (not Cloud).
2. Ask the agent: `Run: git commit --allow-empty -m uat-guard-test`
3. **Expect:** the command is **blocked** — the hook returns `permission: deny`, the agent surfaces
   the deny recovery message, and the commit does **not** happen (no new commit in `git log`).
   This is a HARD DENY, not an "ask" modal.
4. Recovery (operator): relaunch the agent in a Safe Workspace via the **Cursor Agents-Window
   Worktree dropdown** (AWA adopts the linked worktree → allowed), OR set
   `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` in Cursor's environment/settings and relaunch.
5. Re-run the same commit in the relocated (linked-worktree) agent — **expect allow**.

> Note the deny recovery message explicitly says an inline `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>`
> prefix does NOT work (the hook reads its own process env), and `cd <worktree> && <cmd>` is still
> denied. Confirm the agent does not loop retrying.

### 1b. ask-then-deny platform probe (the residual to close)

Proves the platform fact AWA is built on: Cursor **enforces `deny`** but treats `ask` as
**non-blocking** on the agent path. Use the redrive harness:

```bash
# See desktop-hook-redrive-runbook.md for the capture mechanism.
bash ~/dev/capabilities/awa/hook-probe/redrive-capture.sh   # follow its prompts
```

Record, for **Desktop**: with a hook forced to return `ask`, did the command RUN? (expected: yes —
ask is non-blocking). With a hook forced to return `deny`, was it BLOCKED? (expected: yes).

**Evidence to paste back:**

- Text of the deny message + `git log` proving no commit landed (Phase 1a)
- ask→ran? / deny→blocked? for Desktop (Phase 1b)
- Optional: `tail -1 ~/.local/state/awa/detections/receipts.jsonl` after a native file edit in primary
  (afterFileEdit is observation-only → allow + receipt)

**Headless proxy (already green):** the bash hook returns `permission: deny` on an included primary
mutation, `allow` in a linked worktree, and `allow` on afterFileEdit — see
`RESULTS-e2e-uat-20260707.md` and `engine/tests/test_guard_hook_wrappers.py`.

---

## Phase 2 — Live MCP read + write (Desktop, ~10 min)

Open **`~/awa-mcp-uat`** as a **Desktop (Local)** agent. Paste:

```
AWA MCP live UAT (mode write tools). Do ALL steps; paste full JSON outputs.

1. Call awa_status (no args). Paste JSON.
2. Call awa_guard_shell with cwd="/tmp" and command="git status". Paste JSON.
3. Call awa_mode_list (no args). Paste JSON — expect default_mode on.
4. Call awa_mode_set with rel="." and mode="off". MUST fail (broad-off). Paste JSON — expect ok:false.
5. Call awa_mode_set with rel="<FIXTURE_REL>" and mode="on". Paste JSON — expect ok:true.
6. Call awa_mode_set with rel="<FIXTURE_REL>" and mode="ask_on". MUST fail (only on|off). Paste JSON.
7. Call awa_mode_get with rel="<FIXTURE_REL>". Paste JSON.
8. Run in terminal:
   cat "${HOME}/.local/state/awa/hook-probe/events.jsonl" 2>/dev/null | tail -30
9. Find a line where event is beforeMCPExecution AND mcp_server_name is "awa" for a WRITE tool (awa_mode_set).
   Paste that line, or say NO_AWA_MCP_WRITE_HOOK_RECORD.
```

Replace `<FIXTURE_REL>` with the value printed by `bootstrap-eligible-uat.sh`.

**Pass:** steps 1–5,7 succeed; step 4 and step 6 rejected with `isError: true`; step 9 shows
`awa_mode_set` in the hook log.

---

## Phase 3 — Per-repo mode behavior + dashboard (Desktop, ~10 min)

Using the **eligible fixture** (explicit `on` from Phase 2):

1. Mutating command on **primary** → **deny** (same as Phase 1a).
2. `~/dev/_ops/bin/dev-worktree.sh mode set <rel> off` → mutating command **allowed** (no block).
3. Restore: `mode set <rel> on`.
4. **Fail-safe check:** `mode set <rel> ask_on` → **error** (only on|off). Then hand-seed a legacy
   value and migrate: append `  <rel>: ask_on` under `modes:` in the modes file, run
   `dev-worktree.sh mode repair`, confirm it becomes `on`, and a mutating primary **denies**.
5. Create a **second** eligible fixture (no explicit mode entry) → mutating command **denies**
   (inherits host `default_mode: on`).
6. Dashboard:

```bash
make -C ~/dev worktree-dashboard   # or open awa-worktree-dashboard.canvas.tsx and Refresh
```

**Expect:** both fixtures in the **Included** bucket; **no `ask_on` bucket / no `summary.ask_on`**;
per-repo `mode: on` (or `mode: ""` for the default-inheriting one); an un-repaired legacy value would
show `mode: invalid` while still classified Included.

---

## Phase 4 — Cloud degrade-to-allow + committed hooks (Cloud, ~15 min)

```bash
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-cloud-hook-uat
cd ~/awa-cloud-hook-uat
gh repo create KleinPerkins/awa-cloud-hook-uat-e2e --private --source=. --push
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
```

1. Agents window → **Environment: Cloud**
2. Repository: `KleinPerkins/awa-cloud-hook-uat-e2e`, branch `main`, **new chat**
3. Paste the Check 1 prompt from [`OPERATOR-CLOSEOUT.md`](OPERATOR-CLOSEOUT.md) (shell / edit / read / log).
4. **Cloud degrade-to-allow:** ask the cloud agent to run a mutating command (e.g.
   `git commit --allow-empty -m cloud-uat`). **Expect: ALLOW** — a Cloud VM is an already-isolated,
   own-branch `/workspace` clone, so the guard degrades to allow *before* the deny branch and never
   hard-blocks it.
5. **Cloud ask-then-deny probe:** repeat the 1b redrive on Cloud and record ask→ran? / deny→blocked?.

**Pass:** `beforeShellExecution` present in log; the cloud mutating command is **allowed** (not
denied); `sample.txt` edited; Desktop-only events absent.

Cleanup (operator-gated — not part of this build's scope):

```bash
gh repo delete KleinPerkins/awa-cloud-hook-uat-e2e --yes 2>/dev/null || true
rm -rf ~/awa-cloud-hook-uat
```

---

## Phase 5 — Full lifecycle + apply-back (Desktop, ~20 min)

See [`apply-back-uat-runbook.md`](apply-back-uat-runbook.md). Drive `ensure` → work in the linked
worktree → commit/push → open PR on the disposable remote → `clean --bundle --delete-branch`.

Quick verify (substitute the remote printed by your fixture bootstrap):

```bash
gh pr view --repo KleinPerkins/<your-eligible-remote> 1
~/dev/_ops/bin/dev-worktree.sh clean --path "<FIXTURE>.wt" --bundle --delete-branch
```

---

## Phase 6 — Closeout message

Paste to your AWA agent:

```
AWA E2E UAT operator closeout (2026-07-07 — ASK_ON removal):

=== Phase 1 hard-deny + ask/deny probe (Desktop) ===
deny blocked commit? (y/n) + ask→ran? / deny→blocked?

=== Phase 2 MCP (on|off only) ===
(paste; step 4 + step 6 must be isError)

=== Phase 3 mode + dashboard ===
ON→deny / OFF→allow / repair migrates ask_on→on; Included bucket, no ask_on bucket

=== Phase 4 cloud degrade-to-allow ===
cloud mutating command ALLOWED? + cloud ask/deny probe

=== Phase 5 apply-back ===
PR URL + clean outcome
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `awa` MCP tools not found | Settings → MCP → enable **awa** → restart Cursor |
| Mode tools return "no modes_file" | Re-run install with `AWA_POLICY=~/dev/_ops/policy/worktree-policy.yml` |
| Agent loops retrying a denied command | Expected message says STOP; relaunch in a Safe Workspace (dropdown) or set the env override |
| Cloud command was denied (not allowed) | Cloud detection failed — confirm `/workspace` root or background-agent signal; file a bug (must degrade to allow) |
| Cloud used for MCP test | MCP + mode write tools require **Desktop Local** |
