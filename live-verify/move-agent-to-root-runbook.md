# Live verification — R-A `move_agent_to_root` fetch/ff-merge

**Goal:** observe whether `move_agent_to_root` triggers a `git fetch` + fast-forward merge of the
target worktree branch when moving the agent root. This was **NEEDS RE-VERIFICATION** because the
default AWA relocation path is native-window adopt (no move), but operators may still use move.

**Safety:** use a **disposable local repo** with a **local-only branch** first (must NOT depend on
origin). No push to governed remotes unless you explicitly opt into the quarantine-ref publish path.

## Setup (local-only branch — expect move WITHOUT fetch to work or fail honestly)

`dev-worktree.sh ensure` only runs on repos classified **`include`**. That requires **both**:

1. Repo path under `~/dev/personal/*`, `~/dev/capabilities/*`, or `~/dev/affirm/src/*`
2. A `remote.origin.url` configured (the remote does **not** need to exist on GitHub for Observation A)

A bare `~/awa-move-uat` outside `~/dev` returns `{"action":"noop","reason":"no origin remote"}` or
`outside governed include patterns` — that is policy, not a bug.

```bash
UAT=~/dev/personal/awa-move-uat
rm -rf "$UAT" "${UAT}.wt"

mkdir -p "$UAT" && cd "$UAT"
git init -q
git config user.email "awa-uat@local.invalid"
git config user.name "AWA UAT"
echo "base content" > README.md
git add . && git commit -q -m "init"
git branch -M main
# Required for classify_repo — URL can be a not-yet-created private repo
git remote add origin "git@github.com:KleinPerkins/awa-move-uat.git"

# Preflight: must show classification: include
~/dev/_ops/bin/dev-worktree.sh status

# Create worktree via AWA shim (prints move_agent_to_root instruction)
OUT=$(~/dev/_ops/bin/dev-worktree.sh ensure --json --path "${UAT}.wt" --branch "cursor/worktree/awa-move-test")
echo "$OUT" | python3 -m json.tool

# Fail fast if ensure noop'd
echo "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("action")=="created" else 1)' \
  || { echo "ensure failed — check classification/status above"; exit 1; }

WT=$(echo "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["rootPath"])')
BR=$(echo "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["branch"])')
echo "Primary:  $UAT"
echo "Worktree: $WT"
echo "Branch:   $BR (local only — not pushed)"
git -C "$UAT" worktree list
```

## Observation A — unpublished branch (default fallback)

1. Note current agent workspace root (should still be `$UAT` primary).
2. Call **`move_agent_to_root`** with `{"rootPath": "<WT path>"}` via cursor-app-control MCP.
3. Record:
   - Did the agent cwd change to the worktree?
   - Any error mentioning "Remote branch not found" / fetch failure?
   - Run in a terminal (if accessible): `git -C "$WT" status` and `git -C "$UAT" worktree list`

**Hypothesis (v2.1 H2):** move on an **unpublished** local branch may fail or skip fetch; AWA default
relocation should prefer native dropdown adopt, not this path.

**Result (Observation A, 2026-07-05 — Verified):** move **failed**; agent root **unchanged**;
`git fetch origin` **was attempted** (failed: repository not found). See
`RESULTS-R-A-2026-07-05.md`.

**Result (Observation B, 2026-07-05 — Verified):** repo exists, worktree branch on `origin`, but
**`main` not on `origin`** → move **failed** with `couldn't find remote ref refs/heads/main`; agent
root **unchanged**. Move fetches **`main`**, not the worktree branch.

## Observation B — published branch (optional, explicit opt-in)

Only if you want to test fetch/ff-merge:

```bash
cd ~/dev/personal/awa-move-uat
gh repo create KleinPerkins/awa-move-uat --private --source=. --push
git push -u origin "$BR"
```

Repeat `move_agent_to_root` and record whether the agent lands in `$WT` with branch synced.

## Evidence to record

| Field | Value |
|-------|-------|
| Date / surface | Desktop + Cursor version |
| Branch on origin? | yes/no |
| move_agent_to_root payload | `rootPath` used |
| Outcome | moved / error message / cwd unchanged |
| fetch/ff-merge observed? | yes/no/unknown |

Paste into `SECURITY.md` under R-A. If unpublished move fails, that **confirms** H2 print-only
fallback is correct — not a regression.
