# Live verification — R-A `move_agent_to_root` fetch/ff-merge

**Goal:** observe whether `move_agent_to_root` triggers a `git fetch` + fast-forward merge of the
target worktree branch when moving the agent root. This was **NEEDS RE-VERIFICATION** because the
default AWA relocation path is native-window adopt (no move), but operators may still use move.

**Safety:** use a **disposable local repo** with a **local-only branch** first (must NOT depend on
origin). No push to governed remotes unless you explicitly opt into the quarantine-ref publish path.

## Setup (local-only branch — expect move WITHOUT fetch to work or fail honestly)

```bash
UAT=~/awa-move-uat
rm -rf "$UAT"
mkdir -p "$UAT" && cd "$UAT"
git init -q && git config user.email "awa-uat@local.invalid" && git config user.name "AWA UAT"
echo base >README.md && git add . && git commit -q -m init

# Create worktree via AWA shim (prints move_agent_to_root instruction)
OUT=$(~/dev/_ops/bin/dev-worktree.sh ensure --json --path "$UAT.wt" --branch "cursor/worktree/awa-move-test")
echo "$OUT" | python3 -m json.tool
WT=$(echo "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["rootPath"])')
BR=$(echo "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["branch"])')
echo "worktree=$WT branch=$BR (NOT on origin)"
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

## Observation B — published branch (optional, explicit opt-in)

Only if you want to test fetch/ff-merge:

```bash
cd "$UAT"
git remote add origin "git@github.com:KleinPerkins/awa-move-uat.git"  # create private repo first
git push -u origin main
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
