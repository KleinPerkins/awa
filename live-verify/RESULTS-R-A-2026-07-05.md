# R-A `move_agent_to_root` — live Desktop results (2026-07-05)

> Observation A (unpublished / unreachable origin). Closes the load-bearing half of R-A for v2.1
> §H2: the default AWA relocation path must **not** depend on `move_agent_to_root` when the
> worktree branch is local-only or `origin` is unreachable.

## Provenance

- **When:** 2026-07-05 (Desktop agent session).
- **Surface:** Cursor Desktop, Agents Window, **Local** environment.
- **Repo:** disposable UAT `~/dev/personal/awa-move-uat` (classified `include` by `dev-worktree.sh`).
- **Setup:** `dev-worktree.sh ensure` created worktree `~/dev/personal/awa-move-uat.wt` on branch
  `cursor/worktree/awa-move-test` @ `d5ea248`. `origin` URL configured but **GitHub repo not
  created**; worktree branch **not pushed** (`BRANCH_ON_ORIGIN=no`).

## Observation A — call + outcome

**Payload:**

```json
{"rootPath": "/Users/laurence.duggan/dev/personal/awa-move-uat.wt"}
```

**Agent root relocated?** **No.** `pwd` remained `/Users/laurence.duggan/dev/personal/awa-move-uat`
(primary), not the worktree.

**Error (verbatim):**

```text
Failed to move agent root: Failed to checkout migrated branch "main": Command failed: git fetch origin
ERROR: Repository not found.
fatal: Could not read from remote repository.
Please make sure you have the correct access rights and the repository exists.
```

**Fetch/ff-merge?** **`git fetch origin` was attempted** during migration (on `main`), not an
ff-merge of the worktree branch. Move aborted; no relocation.

**Worktree state after failed move (unchanged):**

```text
/Users/laurence.duggan/dev/personal/awa-move-uat        d5ea248 [main]
/Users/laurence.duggan/dev/personal/awa-move-uat.wt     d5ea248 [cursor/worktree/awa-move-test]
```

```text
On branch cursor/worktree/awa-move-test
nothing to commit, working tree clean
BRANCH_ON_ORIGIN=no
```

## Verdict (Observation A)

| Question | Answer |
|----------|--------|
| Does `move_agent_to_root` trigger fetch? | **Yes** — `git fetch origin` during migration |
| Does move succeed with local-only branch + missing remote? | **No** |
| Is agent root unchanged on failure? | **Yes** — primary cwd preserved |
| Confirms v2.1 H2 (no default reliance on move)? | **Yes** |

## Observation C — `main` on `origin`, both refs at `d5ea248` (certainty run, 2026-07-05)

**Setup delta vs B:** `git push -u origin main` — both `origin/main` and
`origin/cursor/worktree/awa-move-test` at `d5ea248`.

**Before move:**

```text
pwd: /Users/laurence.duggan/dev/personal/awa-move-uat
origin/main:                    d5ea248
origin/cursor/worktree/awa-move-test: d5ea248
```

**Payload:** same `rootPath` as A/B.

**Agent root relocated?** **No.** `pwd` remained primary.

**Error (verbatim):**

```text
Failed to move agent root: Failed to checkout migrated branch "main": Command failed: git checkout main
fatal: 'main' is already used by worktree at '/Users/laurence.duggan/dev/personal/awa-move-uat'
```

**Fetch/ff-merge?** **Not observed** in tool output — failure occurred on `git checkout main` inside
the destination worktree. Past the fetch gate (Obs A/B); hit git's **one-branch-per-worktree**
constraint because primary already holds `main` while `.wt` holds `cursor/worktree/awa-move-test`.

## Verdict (Observation C)

| Question | Answer |
|----------|--------|
| Does move succeed when `main` is on `origin` (AWA ensure layout)? | **No** |
| Failure mode | `main` already checked out in primary worktree |
| Fetch/ff-merge observed? | **No** — checkout conflict, not fetch |

## Combined R-A verdict (Observations A + B + C) — **closed**

`move_agent_to_root` **does not relocate** the agent for the AWA `ensure` layout (primary on `main`,
linked worktree on `cursor/worktree/…`) in any tested condition:

| Obs | Condition | Failure |
|-----|-----------|---------|
| A | `origin` unreachable | `git fetch origin` → repository not found |
| B | repo exists; worktree branch on `origin`; `main` not on `origin` | fetch → `couldn't find remote ref refs/heads/main` |
| C | both `main` and worktree branch on `origin` @ same SHA | `git checkout main` → `main` already used by primary worktree |

**Mechanism:** Cursor's move migration tries to **`checkout main`** in the destination worktree after
fetching `origin/main` — it does **not** adopt the worktree's current branch (`cursor/worktree/…`).
That is incompatible with AWA's agent-created worktree pattern and fully confirms v2.1 §H2:
**native-window adopt is the sole default**; `ensure` → printed `move_agent_to_root` must remain
print-only fallback, never an automated relocation path.

**Setup delta vs A:** `KleinPerkins/awa-move-uat` created on GitHub; `cursor/worktree/awa-move-test`
pushed (`d5ea248`, tracks `origin/cursor/worktree/awa-move-test`). **`main` was NOT on `origin`**
(`gh repo create` could not re-add `origin`; only the worktree branch was pushed).

**Payload:** same `rootPath` as Observation A.

**Agent root relocated?** **No.** `pwd` remained `/Users/laurence.duggan/dev/personal/awa-move-uat`.

**Error (verbatim):**

```text
Failed to move agent root: Failed to checkout migrated branch "main": Command failed: git fetch
fatal: couldn't find remote ref refs/heads/main
```

**Fetch/ff-merge?** **`git fetch` attempted for `refs/heads/main` on `origin`** — not for the
worktree branch. No ff-merge; move aborted.

**Worktree state (unchanged):**

```text
/Users/laurence.duggan/dev/personal/awa-move-uat        d5ea248 [main]
/Users/laurence.duggan/dev/personal/awa-move-uat.wt     d5ea248 [cursor/worktree/awa-move-test]
```

## Verdict (Observation B)

| Question | Answer |
|----------|--------|
| Does move succeed when worktree branch is on origin but `main` is not? | **No** |
| What does move fetch? | **`origin` `main`** (not the worktree branch name) |
| Agent root on failure? | **Unchanged** (primary) |

