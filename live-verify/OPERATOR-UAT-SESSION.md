# AWA end-to-end UAT — interactive operator session

> **Session date:** 2026-07-06  
> **AWA pins:** product `a965adf` (round-2 hardening) · host overlay `8d32d6c`  
> **Scope:** Desktop + Cloud, per-repo mode, live MCP write tools, full apply-back  
> **Evidence ledger:** `live-verify/RESULTS-e2e-uat-20260706.md`

Run this in **one Desktop agent chat** (coordinator). Use a **separate Cloud agent** only for Phase 4.

---

## Before you start (~3 min)

### Terminal reset

```bash
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
cd ~/dev/capabilities/awa && AWA_POLICY=~/dev/_ops/policy/worktree-policy.yml \
  AWA_GOVERNED_ROOT=~/dev ./install.sh --repair
bash ~/dev/capabilities/awa/live-verify/bootstrap-eligible-uat.sh
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-mcp-uat
```

Confirm MCP env (Settings → MCP → **awa** enabled; restart Cursor if you changed it):

```bash
python3 -c "import json; print(json.dumps(json.load(open('$HOME/.cursor/mcp.json'))['mcpServers']['awa'], indent=2))"
# Expect env.AWA_POLICY -> ~/dev/_ops/policy/worktree-policy.yml
# Expect env.AWA_GOVERNED_ROOT -> ~/dev
```

---

## Phase 1 — Guard ask-prompt + relocation (Desktop, ~10 min)

**Fixture:** the eligible repo printed by `bootstrap-eligible-uat.sh` (under `~/dev/personal/awa-uat-*`).

1. Open the **eligible fixture** as a **Desktop (Local)** agent root (not Cloud).
2. Ask the agent: `Run: git commit --allow-empty -m uat-guard-test`
3. **Expect:** Cursor **ask** prompt — *"This appears to target an included primary checkout. Use a Safe Workspace first?"*
4. In Terminal:

```bash
~/dev/_ops/bin/dev-worktree.sh ensure --json --path "<FIXTURE>.wt" --branch "cursor/worktree/<basename>"
```

5. Follow the printed **`move_agent_to_root`** instruction (cursor-app-control MCP).
6. Re-run the same commit in the relocated agent — **expect allow** (linked worktree).

**Evidence to paste back:**

- Screenshot or text of the ask prompt (Phase 1)
- `move_agent_to_root` outcome (relocated yes/no)
- Optional: `tail -1 ~/.local/state/awa/detections/receipts.jsonl` after a native file edit in primary

**Headless proxy (already green):** bash hook returns `permission: ask` on primary + `allow` in linked worktree — see `RESULTS-e2e-uat-20260706.md`.

---

## Phase 2 — Live MCP read + write (Desktop, ~10 min)

Open **`~/awa-mcp-uat`** as a **Desktop (Local)** agent. Paste:

```
AWA MCP live UAT (mode write tools). Do ALL steps; paste full JSON outputs.

1. Call awa_status (no args). Paste JSON.
2. Call awa_guard_shell with cwd="/tmp" and command="git status". Paste JSON.
3. Call awa_mode_list (no args). Paste JSON — expect default_mode ask_on.
4. Call awa_mode_set with rel="." and mode="off". MUST fail (broad-off). Paste JSON — expect ok:false.
5. Call awa_mode_set with rel="<FIXTURE_REL>" and mode="ask_on". Paste JSON — expect ok:true.
6. Call awa_mode_get with rel="<FIXTURE_REL>". Paste JSON.
7. Run in terminal:
   cat "${HOME}/.local/state/awa/hook-probe/events.jsonl" 2>/dev/null | tail -30
8. Find a line where event is beforeMCPExecution AND mcp_server_name is "awa" for a WRITE tool (awa_mode_set).
   Paste that line, or say NO_AWA_MCP_WRITE_HOOK_RECORD.
```

Replace `<FIXTURE_REL>` with e.g. `personal/awa-uat-20260706T110803`.

**Pass:** steps 1–6 succeed; step 4 rejected with `isError: true`; step 8 shows `awa_mode_set` in hook log.

---

## Phase 3 — Per-repo mode behavior + dashboard (Desktop, ~10 min)

Using the **eligible fixture** (explicit `ask_on` from Phase 2):

1. Mutating command on **primary** → **ask** (same as Phase 1).
2. `~/dev/_ops/bin/dev-worktree.sh mode set <rel> off` → mutating command **allowed** (no prompt).
3. Restore: `mode set <rel> ask_on`.
4. Create a **second** eligible fixture (no explicit mode entry) → mutating command **asks** (inherits host `default_mode: ask_on`).
5. Dashboard:

```bash
make -C ~/dev worktree-dashboard   # or open awa-worktree-dashboard.canvas.tsx and Refresh
```

**Expect:** fixture in **Ask-on** bucket; `summary.ask_on >= 1`; per-repo `mode: ask_on`.

---

## Phase 4 — Cloud committed hooks (Cloud, ~15 min)

```bash
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-cloud-hook-uat
cd ~/awa-cloud-hook-uat
gh repo create KleinPerkins/awa-cloud-hook-uat-e2e --private --source=. --push
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
```

1. Agents window → **Environment: Cloud**
2. Repository: `KleinPerkins/awa-cloud-hook-uat-e2e`, branch `main`, **new chat**
3. Paste the Check 1 prompt from [`OPERATOR-CLOSEOUT.md`](OPERATOR-CLOSEOUT.md) (shell / edit / read / log).

**Pass:** `beforeShellExecution` in log; `sample.txt` edited; Desktop-only events absent.

Cleanup:

```bash
gh repo delete KleinPerkins/awa-cloud-hook-uat-e2e --yes 2>/dev/null || true
rm -rf ~/awa-cloud-hook-uat
```

---

## Phase 5 — Full lifecycle + apply-back (Desktop, ~20 min)

See [`apply-back-uat-runbook.md`](apply-back-uat-runbook.md). Headless run already opened PR on disposable remote — operator may re-run or verify PR #1 on `KleinPerkins/awa-uat-eligible-20260706T110803`.

Quick verify:

```bash
gh pr view --repo KleinPerkins/awa-uat-eligible-20260706T110803 1
~/dev/_ops/bin/dev-worktree.sh clean --path "<FIXTURE>.wt" --bundle --delete-branch
```

---

## Phase 6 — Closeout message

Paste to your AWA agent:

```
AWA E2E UAT operator closeout (2026-07-06):

=== Phase 1 guard + move ===
(paste)

=== Phase 2 MCP ===
(paste)

=== Phase 3 mode + dashboard ===
(paste)

=== Phase 4 cloud ===
(paste)

=== Phase 5 apply-back ===
PR URL + clean outcome
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `awa` MCP tools not found | Settings → MCP → enable **awa** → restart Cursor |
| Mode tools return "no modes_file" | Re-run install with `AWA_POLICY=~/dev/_ops/policy/worktree-policy.yml` |
| ensure worktree wrong repo | Use `git -C <fixture> worktree add` directly if ensure links wrong common-dir (known edge — see RESULTS) |
| Cloud used for MCP test | MCP + mode write tools require **Desktop Local** |
