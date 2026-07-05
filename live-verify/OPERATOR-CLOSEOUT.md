# AWA closeout — operator instructions (non-technical)

> **Status (2026-07-05):** Both live checks below are **complete**. This doc is retained as the
> record of how they were run. For ledger evidence see `hook-probe/RESULTS-CLOUD-2026-07-05.md`
> and `hook-probe/RESULTS-MCP-2026-07-05.md`.

---

## What’s left?

| # | Check | Where it runs | Why |
|---|--------|---------------|-----|
| **1** | Cloud hooks | **Cloud** agent | Prove safety hooks fire on Cursor’s cloud computers |
| **2** | AWA MCP tools | **Desktop** agent (this Mac) | Prove the `awa` assistant tools work live |

When both are done, paste the outputs back to your AWA agent. It will update the ledger and close the project.

---

## Before you start (one-time, ~2 min)

### A. Open Terminal on your Mac

You can find **Terminal** in Applications → Utilities, or press **Cmd+Space**, type `Terminal`, press Enter.

### B. Run this single “reset” line

Copy the **entire line** below, paste into Terminal, press **Enter**:

```bash
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
```

This clears an old log file so new results are easy to read. **Nothing important is deleted.**

### C. Know the two Cursor modes

| Mode | How to pick it | Use for |
|------|----------------|---------|
| **Cloud** | Agents window → **Environment → Cloud** | Check **1** |
| **Desktop / Local** | Agents window → **Environment → Local** | Check **2** |

**Agents window** = the panel where you chat with the coding agent (not the main code editor only).

---

# CHECK 1 — Cloud hooks (~15 min)

### What you’re proving

Cursor’s **cloud** agents run the project’s safety hooks (so AWA can gate shell commands in the cloud).

### Step 1.1 — Create a throwaway test repo (Terminal)

Copy and paste **this whole block** into Terminal (all lines at once), press **Enter**:

```bash
bash "${HOME}/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh" "${HOME}/awa-cloud-hook-uat"
cd "${HOME}/awa-cloud-hook-uat"
gh repo create KleinPerkins/awa-cloud-hook-uat --private --source=. --push
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
echo "DONE — repo is on GitHub. Continue in Cursor (Cloud)."
```

**Success looks like:**

- Last line says `DONE — repo is on GitHub`
- You are **not** asked for a password in a scary way (GitHub CLI should already be logged in)

**If `gh repo create` says the repo already exists:** run only:

```bash
cd "${HOME}/awa-cloud-hook-uat"
git push -u origin main
```

**If `gh` is not found:** tell your AWA agent — you need GitHub CLI installed once (`brew install gh`).

### Step 1.2 — Start a **Cloud** agent

1. Open **Cursor**.
2. Open the **Agents** panel (chat for the coding agent).
3. Set **Environment** to **Cloud** (not Local, not Worktree).
4. Choose repository: **`KleinPerkins/awa-cloud-hook-uat`**
5. Branch: **`main`**
6. Start a **new** chat.

### Step 1.3 — Paste this prompt into the **Cloud** agent

Select all, copy, paste into the chat, send:

```
You are running an AWA hook test. Do these steps IN ORDER and report after each one.

STEP 1 — Shell
Run the shell command: pwd
Say whether it ran or was blocked.

STEP 2 — Edit a file
Open the file sample.txt in this repo. Change the line from "edit-me: 1" to "edit-me: 2". Save.
Run: cat sample.txt
Say what the file contains now.

STEP 3 — Read a file
Run: cat README.md

STEP 4 — Hook log (IMPORTANT)
Run this and paste EVERYTHING it prints (even if long):
cat "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl" 2>/dev/null || echo "NO_LOG_FILE"

STEP 5 — Short summary
List which of these happened: shell ran, file edited, log file existed.
```

### Step 1.4 — What to save and send back

Copy from the **Cloud agent’s reply**:

1. The full output from **STEP 4** (the log file contents, or `NO_LOG_FILE`)
2. What `sample.txt` contained after the edit
3. Whether `pwd` ran successfully

**Good result (cloud hooks working):**

- `pwd` ran (not blocked)
- `sample.txt` shows `edit-me: 2`
- Log file contains lines with `"event":"beforeShellExecution"` (and possibly `"afterFileEdit"`)

**Also OK:**

- Log does **not** contain `sessionStart`, `beforeSubmitPrompt`, or `stop` (cloud usually omits those)

**Bad — tell your AWA agent:**

- `NO_LOG_FILE` and the agent definitely ran shell + edit
- Shell was completely blocked / agent could do nothing

### Step 1.5 — Cleanup Check 1 (Terminal, after you saved the output)

```bash
gh repo delete KleinPerkins/awa-cloud-hook-uat --yes 2>/dev/null || true
rm -rf "${HOME}/awa-cloud-hook-uat"
```

---

# CHECK 2 — AWA MCP tools (~10 min)

### What you’re proving

The **awa** tool connection in Cursor works, and hooks see calls to `awa_status` (not just other tools).

### Step 2.1 — Prepare (Terminal)

```bash
bash "${HOME}/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh" "${HOME}/awa-mcp-uat"
rm -f "${HOME}/.local/state/awa/hook-probe/events.jsonl"
echo "DONE — open ~/awa-mcp-uat in Cursor Desktop agent."
```

### Step 2.2 — Confirm `awa` is enabled in Cursor

1. Open **Cursor Settings** (gear icon or **Cmd+,**).
2. Search for **MCP**.
3. Find **`awa`** in the list — it should be **on/enabled**.
4. If it’s off, turn it on and **restart Cursor** once.

You do **not** need to edit `mcp.json` by hand.

### Step 2.3 — Start a **Desktop (Local)** agent

1. **File → Open Folder…**
2. Choose folder: **`awa-mcp-uat`** in your home folder  
   Full path: `/Users/laurence.duggan/awa-mcp-uat`
3. Open **Agents** panel.
4. Set **Environment** to **Local** (Desktop) — **not Cloud**.
5. Start a **new** chat.

### Step 2.4 — Paste this prompt into the **Desktop** agent

```
AWA MCP live test. Do ALL steps and paste full outputs.

1. Use the awa MCP tool named awa_status (no arguments). Paste the JSON result.

2. Use the awa MCP tool awa_guard_shell with:
   cwd: "/tmp"
   command: "git status"
   Paste the JSON result.

3. Run in terminal and paste output:
   cat "${HOME}/.local/state/awa/hook-probe/events.jsonl" 2>/dev/null | tail -30

4. In that log, find any line where event is beforeMCPExecution AND mcp_server_name is "awa".
   Paste that line. If none, say NO_AWA_MCP_HOOK_RECORD.
```

### Step 2.5 — What to save and send back

1. JSON from **awa_status**
2. JSON from **awa_guard_shell**
3. The hook log lines (step 3)
4. The `beforeMCPExecution` line for **awa**, or `NO_AWA_MCP_HOOK_RECORD`

**Good result:**

- `awa_status` returns JSON mentioning `"wal"` and `"active_leases"` (numbers/lists are fine)
- `awa_guard_shell` returns JSON with `"permission"`
- Log contains `"mcp_server_name":"awa"` and `"tool_name":"awa_status"` (or similar)

**Bad — tell your AWA agent:**

- “Tool awa_status not found” / MCP connection failed
- Tools work but log never shows `mcp_server_name` **awa**

### Step 2.6 — Cleanup Check 2 (Terminal)

```bash
rm -rf "${HOME}/awa-mcp-uat"
```

---

# After both checks — send this to your AWA agent

Paste a single message like:

```
AWA operator closeout results:

=== CHECK 1 CLOUD ===
(paste STEP 4 log + sample.txt result + whether pwd ran)

=== CHECK 2 MCP ===
(paste awa_status JSON, awa_guard_shell JSON, hook log, awa beforeMCPExecution line or NO_AWA_MCP_HOOK_RECORD)
```

The agent will update `SECURITY.md`, merge a PR, and confirm AWA closeout.

---

# Troubleshooting (plain English)

| Problem | What to do |
|---------|------------|
| **“command not found: gh”** | Install GitHub CLI once: `brew install gh`, then `gh auth login`. |
| **“command not found: #”** | You pasted comment lines alone. Paste whole blocks from this doc, not lines starting with `#`. |
| **Cloud agent can’t see the repo** | Re-run Step 1.1; confirm repo exists at github.com/KleinPerkins/awa-cloud-hook-uat. |
| **NO_LOG_FILE on cloud** | Copy the agent’s full reply anyway; AWA agent will diagnose. Retry Check 1 once. |
| **awa tools not found** | Settings → MCP → enable **awa** → restart Cursor → new Local chat in `awa-mcp-uat`. |
| **Accidentally used Cloud for Check 2** | MCP check **must** be Local/Desktop. Start over Check 2 from Step 2.1. |

---

# Optional — you are done with these

- **move_agent_to_root (R-A):** already completed (Observations A–C). No action.
- **Desktop hook re-drive:** optional; not required for closeout.

---

# Quick reference — folders you may see

| Folder | Purpose | Delete when |
|--------|---------|-------------|
| `~/awa-cloud-hook-uat` | Cloud test repo | After Check 1.5 |
| `~/awa-mcp-uat` | Desktop MCP test repo | After Check 2.6 |
| `~/.local/state/awa/hook-probe/events.jsonl` | Hook log | Cleared by reset line; OK to delete anytime |

**Never** copy test hook files into `~/dev` or work repos — tests use throwaway folders only.
