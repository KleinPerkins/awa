# Live verification — apply-back full lifecycle (Desktop)

**Goal:** SHA-bound preview → confirm → push + PR → recovery patch → clean (bundle-or-refuse).

## Setup

```bash
bash live-verify/bootstrap-eligible-uat.sh ~/dev/personal/awa-uat-<ts>
cd ~/dev/personal/awa-uat-<ts>
gh repo create KleinPerkins/awa-uat-eligible-<ts> --private --source=. --push
git -C ~/dev/personal/awa-uat-<ts> worktree add -b cursor/worktree/awa-uat-<ts> ~/dev/personal/awa-uat-<ts>.wt
# Make a commit in the worktree, push branch
```

## Lifecycle commands

```bash
WT=~/dev/personal/awa-uat-<ts>.wt
ENGINE=~/.local/share/awa/current/bin/awa-engine.sh

$ENGINE adopt --worktree "$WT"
$ENGINE attest --worktree "$WT"
$ENGINE apply-back --worktree "$WT" --base main          # preview
export AWA_GITHUB_WRITE_TOKEN="$(gh auth token)"
$ENGINE apply-back --worktree "$WT" --base main --execute --confirm
$ENGINE recover list
~/dev/_ops/bin/dev-worktree.sh clean --path "$WT" --bundle --delete-branch
```

## Pass criteria

| Check | Evidence |
|-------|----------|
| Preview captures recovery patch | `recovery_patch` path under `~/.local/state/awa/recovery/` |
| Execute opens PR | `pr_url` in JSON output |
| S3 token split | write op refuses without `AWA_GITHUB_WRITE_TOKEN` (unit-tested; optional live re-check) |
| Clean refuses dirty | dirty worktree → refuse message |
| Clean bundles clean tree | bundle path under recovery |

## Cleanup

```bash
gh repo delete KleinPerkins/awa-uat-eligible-<ts> --yes
rm -rf ~/dev/personal/awa-uat-<ts> ~/dev/personal/awa-uat-<ts>.wt
```
