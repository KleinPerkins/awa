# Live verification — cloud project hooks (L9/L10)

**Goal:** prove committed `.cursor/hooks.json` fires on a **real cloud agent VM** and that the
AWA cloud guard **degrades to allow** when the kernel guard is absent (must not brick the VM).

**Also closes:** which events exist in cloud vs Desktop (L9 `beforeSubmitPrompt` Desktop-only;
L10 user hooks absent).

## Prereqs

- `bootstrap-hook-probe-uat.sh` (this directory)
- A GitHub remote for the disposable repo (cloud clones from origin), **or** launch cloud on a
  repo that already has committed hooks (e.g. `KleinPerkins/dev` Phase-12 hooks — probe repo is
  cleaner for isolated evidence)

## A — Hook-probe cloud run (recommended)

```bash
# 1. Bootstrap + push to a private throwaway remote
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-cloud-hook-uat
cd ~/awa-cloud-hook-uat
gh repo create KleinPerkins/awa-cloud-hook-uat --private --source=. --push

# 2. Reset shared log before the run
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
```

3. **Launch a cloud agent** on `KleinPerkins/awa-cloud-hook-uat` (Agents Window → Cloud).
4. In the cloud agent chat, paste:

```
Drive these steps in order and report what happened on disk:
1. Run shell: pwd
2. Edit sample.txt — change "edit-me: 1" to "edit-me: 2" and save
3. Read README.md
After each step, note whether you were blocked.
When done, cat the hook log if present:
  cat "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl" 2>/dev/null || echo NO_LOG
```

5. **Capture evidence** from the agent transcript:
   - `events.jsonl` contents (or copy the file off the cloud VM)
   - Whether `sample.txt` changed despite any `afterFileEdit` deny (L4 corroboration)
   - `analyze.py` output if you can run it on the cloud side

```bash
python3 ~/dev/capabilities/awa/hook-probe/analyze.py
```

**Expected cloud delta (if doc-derived facts hold):**

| Event | Expected on cloud |
|-------|-------------------|
| `beforeShellExecution` | ✅ fires |
| `afterFileEdit` | ✅ fires (observation-only) |
| `sessionStart`, `beforeSubmitPrompt`, `beforeMCPExecution`, `stop`, `sessionEnd`, `workspaceOpen` | ❌ absent |

## B — KleinPerkins/dev cloud guard (production path)

Validates the **shipped** Phase-12 hooks on `KleinPerkins/dev`:

1. Launch a **cloud agent** on `KleinPerkins/dev` @ `main`.
2. Ask it to run: `echo AWA_CLOUD_SHELL_TEST` (records whether shell executed).
3. Ask it to create/edit a throwaway file under `/tmp/awa-cloud-edit-test.txt`.

**Degrade-to-allow check (must not brick):** temporarily rename the guard on a **fork** only —
do **not** do this on main. The headless UAT in `worktree-verify.sh` already proves degrade on
a synthetic tree; this live step confirms the committed wrapper on a real cloud VM when the
guard **is** present.

## Evidence to record (SECURITY.md / RESULTS)

For each closed row, record:

- **Date** (UTC)
- **Surface** (`cloud`, Cursor version if shown)
- **Repo/branch** used
- **Command/output:** `events.jsonl` excerpt or `analyze.py` table
- **Verdict:** L9/L10 Verified or still open + reason
