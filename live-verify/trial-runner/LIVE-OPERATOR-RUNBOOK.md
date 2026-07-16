# Live operator runbook — Root-Bound Worktree Finish (Desktop-only surfaces D1–D4)

**Who does what:** the **agent** runs every command and does every verification. The **operator** (a
non-technical PM) only opens one throwaway Cursor window and submits a handful of exact chat prompts.
Nothing here touches a real repo, the real state root, or (by default) the operator's
`~/.cursor/hooks.json`.

**Why this exists:** Layer A ([`run_trial.py`](run_trial.py)) already proves **75** finish/retention
transitions headlessly, end-to-end, through the production surfaces (23 Phase-1 + 33 Phase-2 +
19 Phase-3; see [`RESULTS-finish-all-transitions-trial-20260712.md`](../RESULTS-finish-all-transitions-trial-20260712.md)).
Four surfaces are *inherently* live-Desktop-only and — per `AGENTS.md` — must **not** be claimed from
a headless test:

| ID | Live-only surface | Proven by step |
|----|-------------------|----------------|
| **D1** | Cursor actually renders the warning modal and blocks the submission | L1 (opt-in Part A) |
| **D2** | A live operator **submits** `Close`/`Commit`/`Retain`/`Mixed` and the real consequence happens | L2–L6 |
| **D3** | The agent actually ceases tool calls after a terminal `Close` | L6 |
| **D4** | `Commit` delivery against a **real** GitHub remote | L5 (opt-in) |

To date only `I'm done` (display+block) and `Cancel` were driven live
([`RESULTS-finish-phase2-uat-20260712.md`](../RESULTS-finish-phase2-uat-20260712.md)). This runbook
drives the rest on a throwaway target.

> **Honest caveat (carry it into the results).** On some Cursor builds `beforeSubmitPrompt` is
> *advisory* — the prompt may still reach the model even though the hook asked to block. The pass
> criterion for D1 is the **hook returning `continue:false` / `decision:block_warning` plus a
> metadata-only observation**, *not* the client's enforcement. AWA is kernel-first: the load-bearing
> gate is the kernel's one-use exact-`Close` authorization, which holds with the hook/engine/router
> all absent.

---

## 0. Provision (agent, ~1 min) — before the operator does anything

```bash
bash live-verify/trial-runner/provision-live-uat.sh
```

This builds a **fully disposable** runtime + state root + three throwaway linked worktrees and prints
the disposable env. It never touches the real state root or the operator's `~/.cursor/hooks.json`.
The agent then exports the disposable env in the throwaway window's terminal (the provisioner prints
the exact values):

```bash
export AWA_HOME="$HOME/.local/share/awa-finish-trial-uat/awa/current"
export XDG_STATE_HOME="$HOME/.local/state/awa-finish-trial-uat"
FINISH="$AWA_HOME/consumer/finish_current.py"
```

**FIRST OPERATOR STEP (say this to the operator):**

> *"Open a **new Cursor Desktop window** on this folder:
> `~/.local/share/awa-finish-trial-uat/target-close.wt`, start a normal agent chat there, and submit
> the prompts I give you one at a time. Everything is a throwaway copy — nothing real can be
> affected."*

Two ways to drive the choices (pick one; **Mode B is the default** and needs no hook changes):

- **Mode A — fully hook-driven (proves D1's modal).** Opt-in. The agent backs up and swaps
  `~/.cursor/hooks.json` to a UAT-only file so the disposable hook fires on the operator's real
  submission. See **Appendix — Part A** for the exact backup/swap/restore. Use only if you want to
  re-observe the live modal; do it when no other AWA session is relied upon (hooks are user-global).
- **Mode B — dispatch-driven (default, safest).** The operator still submits every prompt in the
  throwaway window; the agent seeds each pending dialogue with the **production hook script** and runs
  the **production dispatcher** against the operator's exact typed text. `~/.cursor/hooks.json` is
  never touched. Proves D2/D3 (and D4 via L5) with zero risk to any live session.

The agent's Mode-B seed for a step (mints the challenge + dialogue + current-index exactly as the live
hook does, but scoped to the disposable runtime/state and the throwaway worktree):

```bash
WT="$HOME/.local/share/awa-finish-trial-uat/target-close.wt"
printf '{"prompt":"I'"'"'m done","workspace_roots":["%s"],"conversation_id":"uat","generation":1}' "$WT" \
  | AWA_HOME="$AWA_HOME" XDG_STATE_HOME="$XDG_STATE_HOME" "$AWA_HOME/kernel/hooks/before-submit-prompt.sh"
```

(The agent adjusts `WT` to `target-retain.wt` / `target-commit.wt` for L3–L5.)

---

## The live steps (L1–L6)

Each step: **operator prompt** → **observe** → **agent command** → **verify**. The agent captures the
operator's *exact* submitted text and passes it verbatim to the production surface.

### L1 — Preview + block (D1)

- **Operator submits:** `I'm done`
- **Observe (Mode A only):** the fixed **"WARNING: Finish workspace requested"** block renders with
  five options (`Commit`, `Retain`, `Mixed`, `Cancel`, `Close`) each on its own line; the client shows
  the submission blocked (build-dependent — see caveat).
- **Agent verifies (both modes):** read the newest disposable hook observation and confirm the block
  decision + a live challenge exists — **metadata only, no raw prompt/paths:**

```bash
ls -t "$XDG_STATE_HOME/awa/finish-hook-observations/"*.json | head -1 | xargs cat   # decision=block_warning, continue=false
python3 "$FINISH" hook-published                                                    # confirm a live dialogue is pending
```

- **Pass:** `decision=block_warning`, `continue=false`, `identity_outcome=matched`,
  `root_outcome=matched`, observation carries key *names* + `output_sha256` only.

### L2 — Close-variant correction (D2, non-destructive)

- **Operator submits:** `close`  *(lowercase — a deliberate variant)*
- **Agent command:**

```bash
python3 "$FINISH" dispatch --current
```

- **Verify / Pass:** output is exactly `For safety, reply exactly: Close`; the pending dialogue stays
  **LIVE** (`hook-published` still shows it); the worktree is untouched
  (`git -C "$WT" rev-parse HEAD` unchanged) and **no kernel authorization** occurred. Repeat with
  ` Close ` (surrounding spaces) and `CLOSE` — every variant returns the same correction.

### L3 — Retain (D2) — protected, restore-proven artifact

Use `target-retain.wt`. The agent creates the unique target first, then seeds the dialogue there
(Mode B), or has the operator submit `I'm done` in a window opened on it (Mode A).

```bash
WT="$HOME/.local/share/awa-finish-trial-uat/target-retain.wt"
printf 'retain me\n' > "$WT/UAT-RETAIN-SENTINEL.txt"
```

- **Operator submits:** `Retain`
- **Agent commands** (Retain requires an explicit displayed-row selection; secrets need
  `--allow-secrets`; ignored rows are Retain-only). Read the live warning and set `RETAIN_ROW` to
  the number currently shown next to the exact path `UAT-RETAIN-SENTINEL.txt`; never assume an
  ordinal because host/plugin rows may appear between turns:

```bash
CONV=uat
python3 "$FINISH" dispatch --current                                  # -> selection state (never Close)
RETAIN_ROW=<live-number-next-to-UAT-RETAIN-SENTINEL.txt>
python3 "$FINISH" retain --conversation-id "$CONV" --rows "$RETAIN_ROW" # protected + restore-proven artifact
python3 "$FINISH" retain-list                              # shows the artifact id + protected=true
python3 "$FINISH" retain-restore --artifact-id <ID> --destination /tmp/awa-uat-restore
python3 "$FINISH" retain-delete  --artifact-id <ID> --confirm <ID>   # delete requires the exact id again
```

- **Pass:** artifact is `protected` + `restore_proven`; `retain-delete` with a wrong `--confirm`
  refuses, with the exact id deletes; after Retain the dialogue **re-previews** (a fresh warning) and
  a **separate** `Close` is still required — Retain never removes the worktree.

### L4 — Mixed (D2) — row-partitioned commit + retain

Use `target-commit.wt`; add a second commit + an extra file so there are rows to partition.

- **Agent creates uniquely named target rows before preview:**

```bash
WT="$HOME/.local/share/awa-finish-trial-uat/target-commit.wt"
printf 'commit me\n' > "$WT/UAT-MIXED-COMMIT-SENTINEL.txt"
printf 'retain me\n' > "$WT/UAT-MIXED-RETAIN-SENTINEL.txt"
```

- **Operator submits:** `Mixed`
- **Agent commands** (exact, disjoint, complete row partition). Build both comma-separated lists
  from the current display: `COMMIT_ROWS` includes the row next to
  `UAT-MIXED-COMMIT-SENTINEL.txt`; `RETAIN_ROWS` includes the row next to
  `UAT-MIXED-RETAIN-SENTINEL.txt`; and every other displayed row appears in exactly one list:

```bash
python3 "$FINISH" dispatch --current
COMMIT_ROWS=<live-comma-separated-Commit-row-numbers>
RETAIN_ROWS=<live-comma-separated-Retain-row-numbers>
python3 "$FINISH" mixed --conversation-id uat --commit-rows "$COMMIT_ROWS" --retain-rows "$RETAIN_ROWS" --message "uat mixed"
```

- **Pass:** the commit-rows are delivered and the retain-rows become a protected artifact; a
  non-disjoint or incomplete partition refuses; Mixed completes when both actions finish and then
  re-previews (still no removal).

### L5 — Commit delivery (D2; D4 is the opt-in real-GitHub variant)

- **Operator submits:** `Commit`
- **Agent command (default — local/offline evaluator honesty).** Create a unique target, then use
  the row number shown next to that exact path in the live display:

```bash
WT="$HOME/.local/share/awa-finish-trial-uat/target-commit.wt"
printf 'commit me\n' > "$WT/UAT-COMMIT-SENTINEL.txt"
python3 "$FINISH" dispatch --current
COMMIT_ROW=<live-number-next-to-UAT-COMMIT-SENTINEL.txt>
python3 "$FINISH" commit --conversation-id uat --rows "$COMMIT_ROW" --message "uat commit"
```

  Against the disposable **bare** origin there is no real merged PR, so delivery **refuses honestly**
  and **preserves the local commit** — that is the pass (network is structurally confined to
  Commit/Mixed; the evaluator + full failure matrix are headless-proven in Layer A
  `P2-COMMIT-*`).

- **D4 (opt-in, real GitHub — needs network + a throwaway repo).** Only if you want a *real* merged-PR
  delivery: the agent creates a disposable private repo with **merge commits enabled**, pushes the
  worktree branch, opens+merges a real PR (merge-commit, exact head, checks complete), then runs
  `commit` and confirms the strict proof passes. Tear it down after:

```bash
gh repo create KleinPerkins/awa-finish-uat-<ts> --private --source="$WT" --push   # merge-commit enabled
# ...open + merge a real merge-commit PR into the default branch with complete checks...
COMMIT_ROW=<live-number-next-to-UAT-COMMIT-SENTINEL.txt>
python3 "$FINISH" commit --conversation-id uat --rows "$COMMIT_ROW" --message "uat commit" # strict proof -> ok
gh repo delete KleinPerkins/awa-finish-uat-<ts> --yes                             # cleanup
```

### L6 — Exact `Close`: real removal + agent stop (D2 + D3)

Back in the `target-close.wt` window with a live dialogue (re-seed if needed).

- **Operator submits:** `Close`  *(exact, case-sensitive, no surrounding spaces, no attachment)*
- **Agent command:**

```bash
python3 "$FINISH" dispatch --current
```

- **Verify / Pass (D2):** the throwaway worktree is **really removed** (`test -e "$WT"` is now false;
  `git -C "$HOME/.local/share/awa-finish-trial-uat/target" worktree list` no longer shows it); the
  branch is deleted-vs-retained per disposition (an ephemeral `cursor/worktree/*` with no local-only
  commits is delete-eligible); the dispatcher reports `workspace_removed`, `agent_stopping=true`,
  `chat_remains_open=true`; removal did **zero network**.
- **Verify / Pass (D3):** after the terminal receipt the agent issues **no further task tools** and
  the chat stays open. (The flags are headless-proven; the *cessation itself* is only observable
  here, live.)

> **Second-Close nuance (Mode A / hook-driven).** If a prior step in the *same* dialogue was
> `Commit`/`Retain`/`Mixed`, the hook republishes the warning on the next prompt and **discards even a
> `Close`** — a **second** exact `Close` is then required. In Mode B the agent re-seeds a fresh
> dialogue per step, so this only appears if you drive multiple actions through one hook-owned
> dialogue.

---

## Teardown (agent)

```bash
bash live-verify/trial-runner/teardown-live-uat.sh
```

Removes the disposable runtime + state + throwaway worktrees, **restores the `~/.cursor/hooks.json`
backup if Part A was used**, and verifies the real environment is back to parity. If you created a D4
GitHub repo, confirm it was `gh repo delete`d.

---

## Appendix — Part A (opt-in): make the live modal fire (D1)

Only needed to re-observe the Cursor modal itself. It temporarily points the operator's user-global
hooks at the disposable runtime; it is fully backed up and restored.

```bash
# BACK UP + SWAP (agent, before the operator opens the window):
cp "$HOME/.cursor/hooks.json" "$HOME/.cursor/hooks.json.awa-uat.bak"       # teardown restores this
cp "$HOME/.local/share/awa-finish-trial-uat/uat-hooks.json" "$HOME/.cursor/hooks.json"
# The operator opens target-close.wt in a NEW window (so the swapped hooks load) and submits `I'm done`.

# RESTORE (agent, immediately after L1 — or teardown does it):
mv -f "$HOME/.cursor/hooks.json.awa-uat.bak" "$HOME/.cursor/hooks.json"
```

**Warning:** `~/.cursor/hooks.json` is user-global. While swapped, other live AWA sessions use the
disposable hook. Do Part A only in a dedicated window and restore immediately. If you skip Part A,
D1's modal render stays as its prior live proof (`I'm done`, Phase 2) and everything else (D2/D3/D4)
is still fully driven in Mode B.
