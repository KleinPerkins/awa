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

## Still open (optional Observation B)

Whether move **succeeds** when `origin` exists and the worktree branch **is** pushed — drive
`live-verify/move-agent-to-root-runbook.md` § Observation B.
