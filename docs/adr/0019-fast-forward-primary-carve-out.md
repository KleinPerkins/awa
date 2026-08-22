# ADR 0019: Fast-forward-only update of a protected primary's current branch is an allowed carve-out
Status: draft — 2026-08-21

## Context

AWA's shell guard denies every mutating command on an INCLUDED PRIMARY checkout (mode ON):
`engine/guard.py::decide_shell` and its kernel mirror `kernel/hooks/worktree-guard.sh` (`check_probe`)
classify the command, and a confirmed mutation on a protected primary returns an enforced `deny`
(`engine/guard.py` line ~966; hook line ~1184). `_GITMUT` (guard.py line ~32) contains `merge`, and
`_git_is_mutating` has no read-only predicate for it, so **every** `git merge` form — including
`git merge --ff-only origin/main` — classifies as mutating and is denied on a protected primary.

This produces a recurring, legitimate-work failure. An agent does its work in a linked Safe
Workspace (worktree) or the change is merged remotely, and then the local **primary** checkout's
`main` cannot be advanced to the merged commit: the fast-forward `git merge --ff-only origin/main`
is denied, so the merged work never lands locally. The only escapes today are an operator relaunch
in a Safe Workspace or the `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` environment override (guard.py line
~925; hook line ~1002). Both require an operator to intervene for what is, by construction, the
safest possible primary mutation — the sibling plan
`docs/plans/git-command-policy-hardening-v1.md` even performs exactly this fast-forward, but only
behind that operator-set override (its Task 5, Step 7). Agents repeatedly retry the denied command
(the very anti-pattern the deny message warns against), stall, or churn the operator.

A fast-forward is uniquely safe among mutations, and AWA already guarantees the precondition that
makes it safe: because the guard forbids **all other** mutations on a protected primary, a protected
primary is expected to have no local dirty work to clobber. This ADR records the decision to add a
narrow, additive carve-out — in the exact spirit of ADR 0001 — that lets an agent fast-forward a
protected primary's current branch to its already-present tracked upstream without an operator step,
while every other primary mutation (including every non-fast-forward merge) stays denied.

Governing precedents:
- **ADR 0001** (target-path-aware mutation scope): a precise check may **only** ever convert an
  existing `deny` into an `allow` when the command is affirmatively proven safe; it must never turn
  an `allow` into a `deny` or weaken the fallback, and **any** uncertainty collapses back to the
  conservative cwd-only deny. One command, one decision. This carve-out is a new instance of that
  additive-only doctrine.
- **ADR 0010** (remote dry-runs remain mutating): all `git fetch`/`git push` forms — including
  `--dry-run` — stay mutating on protected primaries because they enter object transport and can run
  hooks/helpers and maintenance writes. This ADR does not disturb that: the carve-out is
  fast-forward-**merge**-only and adds no remote/network allowance.

## Decision

1. **A single, additive fast-forward carve-out.** On an INCLUDED PRIMARY checkout, a shell command
   whose one segment is exactly a fast-forward-only merge of the current branch to its already-present
   tracked upstream is **allowed** — converting the existing `deny` into an `allow`. Like ADR 0001,
   this is additive-only: it may only ever turn a `deny` into an `allow`; it never converts an
   `allow` into a `deny`, never weakens any existing deny, and **any** deviation or uncertainty
   resolves back to the enforced deny.

2. **Implemented at the decision layer, not as a "read-only" merge classification.** A fast-forward
   genuinely mutates: it advances a branch ref and updates the index and working tree. `merge`
   therefore stays in `_GITMUT` and `classify_mutating(...)`/`_git_is_mutating(...)` continue to
   report a fast-forward merge as **mutating** (True). The allowance is a **named, bounded exception
   at the decision layer** — `engine/guard.py::decide_shell` and the kernel `check_probe` mirror —
   evaluated inside the existing "mutating on an included primary" branch, parallel to the ADR 0001
   target-narrowing and **before** the enforced deny. This keeps classification honest and confines
   the allowance to the one decision site that protects primaries, rather than leaking it into every
   consumer of `classify_mutating` and every context.

3. **Exact closed grammar (deny-by-default).** The carve-out fires **only** for a command matching
   all of the following; every other form stays denied:
   - **Exactly one segment.** Any control operator (`;`, `&&`, `||`, `|`, `&`, newline, subshell) or
     any redirect operator disqualifies the command (ADR 0001 §4: one command, one decision).
   - **A bare `git` program.** Only leading `VAR=value` assignments may precede `git`; any prefix
     wrapper (`sudo`, `env`, `nice`, `timeout`, …) disqualifies the command — a wrapper such as
     `env -C <dir>` could relocate the operation and launder the target.
   - **No git global option at all (v1).** Any global option disqualifies the command — in
     particular `-C`, `--git-dir`, `--work-tree`, `--namespace`, `--super-prefix` (target
     redirection) and `-c`, `-p`/`--paginate`, `--config-env=` (config/pager injection, already
     treated as read-only-blocking by `_git_global_args_block_readonly`). The command must operate on
     the shell cwd's own primary.
   - **Subcommand exactly `merge`, with `--ff-only` present and no other flag.** Any additional flag
     disqualifies the command — e.g. `--no-ff`, `--ff`, `-X`/`--strategy*`, `--squash`, `-m`,
     `-S`/`--gpg-sign`, `--no-verify`, `--autostash`, `--stat`, `-e`, `--`.
   - **At most one positional ref, of an allowlisted upstream shape.** Permitted: zero positional
     refs (git uses the branch's configured upstream), `@{upstream}`, `@{u}`, or a single
     remote-tracking-shaped token matching `^[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+$` with no leading `-`
     and no glob metacharacter (`*`, `?`, `[`). A bare local branch name, a revision expression
     (`HEAD~1`), two refs, or a globbed ref all disqualify the command.

4. **Runtime fast-forward safety rests on git's own `--ff-only` guarantee; the guard proves only the
   shape.** The static classifier cannot know from tokens alone whether a given invocation is truly a
   fast-forward — that depends on the live commit graph. It does not need to. `git merge --ff-only`
   is git's hard runtime invariant: it **either** fast-forwards the current branch to a descendant,
   **or** is a no-op (`Already up to date`), **or** aborts with no mutation
   (`Not possible to fast-forward, aborting`); and it refuses (does not overwrite) when local changes
   would be clobbered. It never creates a merge commit, resolves a conflict, or rewrites history. The
   guard therefore allows the proven-safe **shape** and lets git enforce the runtime property; it
   does **not** re-verify ancestry or working-tree cleanliness in the hot path.

5. **fetch, push, and pull stay denied on protected primaries.** Consistent with ADR 0010, all
   fetch/push forms remain mutating; `git pull --ff-only` remains denied because it embeds a fetch.
   The carve-out is fast-forward-**merge**-only against a ref **already present** in the local object
   store. This is sufficient in practice because AWA's linked worktrees share the primary's common
   `.git` object store and `refs/remotes/*` (a worktree's `git rev-parse --git-common-dir` resolves
   to the primary `.git`): an agent fetches from the Safe Workspace (already allowed there), which
   updates the shared `refs/remotes/origin/*` and downloads the objects, and only the final
   `git merge --ff-only` needs to run in the primary.

6. **The operator override and Safe-Workspace recovery are unchanged.** `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1`
   and the "relaunch in a Safe Workspace" recovery path remain exactly as they are. The carve-out
   removes the need for them **only** for the safe fast-forward case; every other primary mutation
   still requires them.

7. **Engine/kernel parity and kernel-first are preserved.** The carve-out is implemented identically
   in `engine/guard.py::decide_shell` and the kernel hook's `check_probe` (fed by a `safe_ff` signal
   computed in the hook's embedded Python, parallel to `mut_targets`), proven equal by the shared
   corpus, the live-hook parity tests, and the contract-freeze UAT. The kernel hook does not import
   the engine, hook-internal failure still degrades to allow, and the frozen permission schema
   (`allow`/`ask`/`deny`) is unchanged.

## Why

A fast-forward is the one mutation whose safety AWA can prove from first principles under its own
invariant:

- **No dirty work to lose.** The guard already denies every other mutation on a protected primary,
  so the primary is expected clean. Even if it were not, `git merge --ff-only` aborts rather than
  overwrite local changes.
- **No history rewrite, no merge commit, no conflict.** `--ff-only` can only advance a pointer to a
  descendant, no-op, or abort. It is not a merge in the conflict-producing sense.
- **Reversible.** A fast-forward is recorded in the reflog and leaves `ORIG_HEAD`; it is undoable
  (`git reset --hard ORIG_HEAD`). This is categorically unlike the irrecoverable destruction AWA's
  boundary exists to prevent (e.g. `rm -rf .git/objects`, which ADR 0001 §2 explicitly protects).

Residual risks, named and ruled on rather than assumed away:

- **`post-merge` hook execution.** A fast-forward runs the repository's own `post-merge` hook if one
  exists. This is the operator's **own** in-repo code executing a change the operator's history
  already authorizes — not a network/remote surface. It is distinct from ADR 0010's `pre-push`
  concern, where a dry-run reaches transport/credentials/remote helpers. AWA's boundary protects a
  primary's tracked content from accidental clobbering, not the operator from their own configured
  hooks. Accepted, not blocked.
- **Fast-forward to an unintended but genuinely-descendant ref.** Constraining the accepted ref to
  the tracked-upstream shape (Decision 3) plus the operation's reversibility bound this to a low,
  recoverable risk. Even a "wrong" fast-forward advances history non-destructively and is undoable.
- **Reliance on git's `--ff-only` semantics.** The safety argument depends on `--ff-only` behaving as
  documented; the Live-state verification record and the plan's offline behavior-proof test pin that
  behavior to the host git version so a future change is caught rather than silently trusted.

Alternatives considered:

- **A `_git_merge_is_readonly()` predicate wired into `_git_is_mutating` (like the branch/remote/
  config predicates) — rejected.** It is simpler and structurally parallel, but it would label a
  ref-moving, working-tree-updating operation "read-only," which is false; it would allow the
  fast-forward in **every** context and for **every** consumer of `classify_mutating`, not just at
  the primary-protection decision; and it would erode the honesty of the classifier that the rest of
  the guard depends on. The decision-layer carve-out (Decision 2) gets the same operator outcome
  while keeping `merge` classified as the mutation it is.
- **A belt-and-suspenders runtime precheck (`git merge-base --is-ancestor HEAD <upstream>` + a
  clean-tree check) inside `decide_shell` — considered, deferred.** `decide_shell` already shells out
  to git, so this is feasible, but `--ff-only` already enforces both properties atomically at
  execution time, a pre-check would add latency to the hot path and a TOCTOU gap of its own, and it
  duplicates a guarantee git makes airtight. Deferred; a future ADR may add it if a concrete gap
  emerges.
- **Allowing `git pull --ff-only` or a narrow fetch on the primary — rejected.** `pull` embeds a
  fetch, and ADR 0010 keeps all fetch forms denied (object transport, hooks, maintenance writes). The
  shared-object-store worktree path (Decision 5) removes the need to fetch on the primary at all.
- **Widening the grammar (a `-C` to another primary, `--autostash`, arbitrary refs) — rejected for
  v1.** Each expands the proof obligation; deny-by-default with a tight closed grammar is the ADR 0001
  posture. Any widening is a deliberate, higher-numbered ADR, not drift.
- **Leaving the status quo (operator override only) — rejected.** It makes the safest primary
  mutation require the same manual escape as the dangerous ones, which is exactly what traps agents
  and burns operator attention; it also trains agents to reach for `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1`,
  a blunt instrument that disables protection for the whole session.

## Consequences

- An agent can land already-merged/already-present work into the local primary's current branch with
  a plain `git merge --ff-only`, with no operator relaunch and no session-wide override — removing the
  recurring stuck state.
- **No existing deny is weakened.** Every non-fast-forward merge, every extra flag, every chained,
  redirected, wrapper-prefixed, target-redirected, or config-injecting form, and every bare-branch or
  revision-expression ref still denies on a protected primary. The shared corpus's near-miss deny
  cases are the regression mechanism (enumerated in the companion plan).
- `classify_mutating`/`_git_is_mutating` remain honest: a fast-forward merge is still reported as
  mutating; only `decide_shell`/`check_probe` grant the additive allowance. Fast-forward-allow cases
  are therefore verified as **decision-layer** allows (a primary repo where `decide_shell(...)
  .permission == "allow"` while `classify_mutating(...) is True`), never by moving them into the
  read-only corpus.
- ADR 0010 is intact: fetch/push/pull unchanged on protected primaries.
- `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` and Safe-Workspace recovery are unchanged and still required
  for every non-fast-forward primary mutation.
- Engine and kernel mirrors, the shared corpus, and the contract-freeze UAT must agree; the frozen
  contract schema does not change and no new dependency enters the hook path.
- A future material change (widening the grammar, adding the runtime pre-check, or any remote
  allowance) requires a higher-numbered ADR that supersedes the relevant decision here; this ADR is
  byte-immutable once accepted (doc-warden POLICY §9).

## Live-state verification record

Verified 2026-08-21 against the AWA primary checkout at `9737d3d` (branch `main`), `engine.__version__
= 1.5.2`, latest release tag `v1.5.2`:

- `engine/guard.py`: `_MUT`/`_GITMUT` at lines ~29–35 — `_GITMUT` includes `merge`; `_git_is_mutating`
  (line ~327) has no `merge` predicate, so a merge falls through to `return True` (mutating).
  `decide_shell(cwd, command, policy_path, *, allow_primary=False)` (line ~918) issues the enforced
  `deny` (line ~966) after `classify_mutating` (line ~528) and the ADR 0001 additive narrowing via
  `_collect_precise_targets` (lines ~667/958). For `git merge --ff-only`, `_collect_precise_targets`
  resolves the target to the cwd primary itself, so it does not already allow — confirming the
  carve-out must be a distinct check ahead of the deny.
- `kernel/hooks/worktree-guard.sh`: `_GITMUT` at lines ~146–147 (includes `merge`); the embedded
  Python computes and prints `is_mutating`/`has_mut_targets`/`mut_targets` (lines ~600, ~818,
  ~858–864); the bash `check_probe` applies the additive narrowing (lines ~1172–1181) and the
  enforced deny (lines ~1184–1187); `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` short-circuits to allow at
  line ~1002. This is the mirror insertion site for the `safe_ff` signal.
- Shared corpus `engine/tests/git_guard_command_corpus.py` is consumed by the classifier, decision,
  and live-hook tests; contract-freeze UAT is `kernel/checks/awa-contract-freeze.sh`; parity is
  enforced by `engine/tests/test_guard_hook_wrappers.py`.
- Linked-worktree shared store confirmed: a `dev-worktree.sh ensure` Safe Workspace's
  `git rev-parse --git-common-dir` resolves to the primary `…/awa/.git`, so `objects/` and
  `refs/remotes/*` are shared with the primary.
- git `--ff-only` behavior is pinned to Apple Git `2.50.1` (the host baseline recorded in ADR 0010):
  fast-forward on a descendant, `Already up to date` no-op on an ancestor/equal ref, abort with no
  mutation on divergence, and refusal to overwrite a dirty working tree. The companion plan's Task 1
  reproduces these in an offline fixture and records the exact `git --version` so a later divergence
  is re-evaluated rather than mistaken for a classifier defect.

Cross-links: ADR 0001 (additive-only mutation-scope doctrine this carve-out extends) and ADR 0010
(fetch/push remain mutating; the boundary this carve-out is careful not to cross).
