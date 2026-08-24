# ADR 0019: Clean protected primaries may refresh and fast-forward their configured upstream
Status: accepted — 2026-08-23 (owner sign-off; design PR #120)

## Context

AWA's shell guard denies every mutating command on an INCLUDED PRIMARY checkout (mode ON):
`engine/guard.py::decide_shell` and its kernel mirror `kernel/hooks/worktree-guard.sh` (`check_probe`)
classify the command, and a confirmed mutation on a protected primary returns an enforced `deny`
after ADR 0001's target-path narrowing. `fetch`, `pull`, and `merge` are all honestly classified as
mutating, so the guard also blocks the two operations needed to keep a primary current after work
merges elsewhere.

The original draft allowed only a shape-matched `git merge --ff-only` and required fetch in a linked
Safe Workspace. Fresh review found that boundary both incomplete and illusory: linked worktrees
share the primary's common Git directory, objects, remote-tracking refs, and fetch bookkeeping. The
detour does not isolate fetch's effects, while shape-only merge recognition does not prove the
current branch, upstream, cleanliness, or history relationship.

AWA's product boundary is protection of unshared work, not a sandbox for trusted repository Git
configuration. The useful maintenance boundary is therefore a clean, attached, idle primary with
one configured remote-tracking upstream, exact closed command forms, and conservative local state
inspection.

## Decision

1. **Allow exactly two maintenance operations.** On an INCLUDED PRIMARY checkout, the decision
   layer may convert the existing deny into allow for:
   - `git fetch` or `git fetch <configured-upstream-remote>`; and
   - `git merge --ff-only --no-overwrite-ignore` with no ref, `@{u}`, `@{upstream}`, or the exact
     computed short name of the same configured upstream.

2. **Keep both operations classified as mutating.** `fetch` and `merge` remain in `_GITMUT` and
   continue to return true from the mutating classifier. The exception exists only inside
   `decide_shell` and the kernel `check_probe`, immediately before ADR 0001 target narrowing and the
   enforced included-primary deny.

3. **Require a proven maintenance context before either allow.** The checkout must be the already
   classified included primary, clean (including untracked files), attached to a local branch, idle
   from merge/rebase/cherry-pick/revert/am/sequencer/bisect state, and configured with exactly one
   remote-tracking upstream. Configured fetch destinations must stay within that upstream remote's
   tracking namespace and map its source branch to the expected destination.

4. **Bind every operand to that upstream.** An optional fetch remote must byte-equal the configured
   upstream remote. An optional merge ref must be one of the three exact accepted spellings and
   resolve to the same full remote-tracking ref. Before merge, `HEAD` must equal or be ancestral to
   the live upstream. Git's `--ff-only` re-enforces ancestry atomically, while
   `--no-overwrite-ignore` prevents overwriting ignored untracked files.

5. **Use a closed command and environment grammar.** Only one shell segment beginning with bare
   `git` qualifies. Leading assignments, wrappers, executable paths, Git global options, redirects,
   control operators, substitutions, extra flags/operands, and visible repository-retargeting or
   config-injection Git environment variables disqualify the command. Any parse, subprocess,
   timeout, output, or state uncertainty falls through to deny.

6. **Accept normal configured Git behavior.** Fetch may update common-repository state and invoke
   configured transport, credential, hook, tag-following, and maintenance behavior. Merge may update
   the branch, index, worktree, reflog, and `ORIG_HEAD`, and invoke configured hooks, fsmonitor,
   submodule behavior, and content filters. AWA does not sandbox those trusted components; the
   caller must verify clean status after each allowed command before continuing.

7. **Preserve the wider deny boundary.** `git pull`, every push, fetch with any option, arbitrary
   remote/URL/refspec fetch, explicit prune/tag/submodule/maintenance operations, ordinary merge,
   branch switching, divergence repair, history rewrite, cleanup, and every development command
   remain denied on a protected primary.

8. **Preserve kernel-first parity.** Engine, source hook, and installed hook consume one shared
   command/state corpus but remain independent implementations. The kernel imports no engine code;
   genuine hook-internal failure behavior, the permission schema, host policy/modes, and the explicit
   operator override remain unchanged.

## Why

- **Maintenance requires both refresh and advancement.** Allowing only merge leaves the recurring
  fetch denial intact; moving fetch to a linked worktree changes location but not the shared Git
  state it updates.
- **Live state—not branch-name convention—separates maintenance from development.** Cleanliness,
  one configured remote-tracking upstream, safe refspec destinations, and no local-ahead/divergent
  history are the safety boundary. Default-branch discovery or branch switching adds no protection.
- **Git supplies the final atomic branch guarantee.** `--ff-only` yields an upstream-descendant
  fast-forward, a no-op, or refusal; it cannot create a merge commit or resolve divergence.
  `--no-overwrite-ignore` closes Git's default ignored-file overwrite behavior.
- **Classification remains truthful.** A decision-layer exception solves the operator problem
  without teaching other consumers that fetch or merge is read-only.
- **Trusted Git configuration is not a second threat model.** Hooks, filters, fsmonitor, transport,
  credentials, and maintenance already run under repository/operator configuration in linked
  worktrees. Sandboxing them would create a separate product and would break legitimate repositories.

Alternatives considered:

- **Merge-only allowance — rejected.** It solves only half of the maintenance loop and rests on the
  false premise that linked-worktree fetch isolates common Git writes.
- **`git pull --ff-only` — rejected.** Two atomic operations provide fresh checks and distinct,
  understandable failure feedback.
- **Immutable OID handoff or cross-command lock — rejected.** The guard checks the live upstream
  before merge and `--ff-only` safely handles a moving ref as descendant, no-op, or refusal.
- **Hook/filter/helper suppression — rejected.** It pursues a sandbox outside AWA's protection
  charter and can produce an incorrect working tree for repositories that rely on configured Git
  behavior.
- **Shape-only matching — rejected.** It cannot prove the active branch, upstream identity,
  cleanliness, safe fetch destinations, or local history.
- **Generic maintenance mode — rejected.** The two exact operations are sufficient; broader verbs
  would expand the mutation surface without a current operator need.

## Consequences

- Agents can keep a clean protected primary current through one upstream refresh followed by one
  upstream-bound fast-forward, without a session-wide bypass or worktree relocation.
- Dirty, detached, untracked, in-progress, local-ahead/divergent, unsafe-refspec, wrong-target,
  wrapped, chained, redirected, environment-retargeted, or malformed cases deny before execution.
- Configured Git behavior may still leave residue; the caller must check status after each operation,
  stop on a non-clean result, preserve it, and diagnose from a Safe Workspace.
- Fetch and merge remain mutating; only the primary-protection decision sites know this exception.
- The frozen permission contract, policy/modes, override, Cloud behavior, and kernel-first boundary
  do not change.
- Engine, source-hook, installed-hook, and offline Git behavior evidence become release gates.
- A broader command, target, or authority boundary requires a new ADR and successor plan.

## Live-state verification record

Verified 2026-08-21 and revalidated 2026-08-23 against AWA `origin/main` at `01053f6`,
`engine.__version__ = 1.5.2`, release tag `v1.5.2`, and Apple Git `2.50.1`:

- `engine/guard.py` and `kernel/hooks/worktree-guard.sh` independently keep `fetch`, `pull`, and
  `merge` mutating and deny confirmed included-primary mutations after ADR 0001 target narrowing.
- The AWA primary and linked Safe Workspace resolve the same common directory and
  `refs/remotes/origin/main` path.
- Git documentation confirms ordinary fetch writes, configured helper/hook behavior,
  `--ff-only` ancestry semantics, and `--no-overwrite-ignore` protection.
- The companion plan records the closed grammar, exact local inspections, shared parity corpus,
  offline behavior proof, installed-hook UAT, release sequencing, and caller feedback contract.

Cross-links: ADR 0001 (additive-only target-aware narrowing), ADR 0010 (remote classification and
the sole fetch exception), and
`docs/plans/guard-fast-forward-primary-carve-out-v1.md` (execution and acceptance ledger).
