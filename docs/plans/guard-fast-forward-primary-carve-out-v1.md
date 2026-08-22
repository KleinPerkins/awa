# Guard Fast-Forward Primary Maintenance Carve-Out — refresh and advance a protected primary without turning it into a workspace

- **Version:** v1
- **Status:** DRAFT — 2026-08-21
- **Date:** 2026-08-21
- **Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
- **Plan-type:** agentic-execution
- **Relates to:** ADR 0001 (additive-only mutation-scope doctrine), draft ADR 0010
  (remote Git policy), draft ADR 0011 (primary fast-forward policy), and
  `docs/plans/git-command-policy-hardening-v1.md`
- **Review provenance:** Refined against live AWA `main` @ `9737d3d` and Skills `main` @
  `3a13f72` using the four-test `plan-refine` method plus a Critical-band review swarm
  (one probe, four territory reviewers, one verifier). No implementation has started.
- **Governance blocker:** This plan may remain a mutable draft, but it MUST NOT become
  ACCEPTED and Task 1 MUST NOT start until draft ADRs 0010 and 0011 are revised in
  lockstep to authorize the maintenance boundary below. This `plan-refine` pass did not
  have authority to edit either ADR.

**Goal:** Let an agent perform the two Git operations actually required to keep a clean
protected primary checkout current with its configured upstream:

1. refresh the configured upstream; then
2. fast-forward the currently checked-out branch to that upstream.

Both operations remain honestly classified as mutating. They receive a narrow
decision-layer allowance only when command shape and live repository state prove that the
agent is doing maintenance, not development work. Commits, branch changes, rewrites,
conflict resolution, arbitrary refs/refspecs, cleanup, and every other primary mutation
remain denied.

**Architecture:** Add one state-aware primary-maintenance recognizer to
`engine/guard.py::decide_shell` and mirror it in the kernel hook's embedded Python plus
`check_probe`. The recognizer accepts only an exact upstream fetch or
fast-forward-only merge, rejects wrappers/assignments/path-qualified executables, binds
all operands to the current branch's configured remote-tracking upstream, and requires an
attached, idle checkout plus a clean state before branch advancement. `fetch` and `merge`
stay in `_GITMUT`; the allowance lives immediately before the existing ADR 0001 target
carve-out and enforced deny. Any parse, state, or parity uncertainty falls through to that
deny.

**Tech stack:** Python stdlib, Bash 3.2, Git 2.50.1 behavior baseline, `unittest`, AWA
contract-freeze UAT, runnerless PR automation, and the governed `KleinPerkins/skills`
Flavor-2 release binding.

> **For agentic workers:** Do not implement this draft. A separate explicit operator
> instruction is required after the governance blocker above is closed and the owner
> accepts this plan. Execute work items in order and use each checkbox as the work ledger.

---

## Global constraints

- Execute only in an AWA Safe Workspace (linked worktree); never edit source in a primary
  checkout.
- Preserve kernel-first operation: `kernel/hooks/worktree-guard.sh` must not import
  `engine.guard`, depend on the daemon, or change the product-wide fail-open behavior for a
  genuine hook-internal failure.
- Keep `fetch` and `merge` mutating in `classify_mutating` / `_git_is_mutating`. The new
  lane is a named decision-layer exception, never a read-only reclassification.
- The exception is additive-only under ADR 0001: it may convert the existing primary
  `deny` to `allow` only when both command and live state are affirmatively proven. A
  malformed command, missing upstream, in-progress operation, target mismatch, or
  inspection failure keeps the deny; dirty/local-only/divergent state keeps the
  branch-advancement deny.
- Permit no development operation on primary: no `add`, `commit`, `checkout`, `switch`,
  `reset`, `rebase`, `cherry-pick`, `revert`, ordinary merge, conflict resolution, stash,
  branch mutation, worktree mutation, or file mutation.
- Permit no unnecessary maintenance family in v1: `pull`, `push`, `remote update`,
  `remote prune`, `fetch --prune`, `gc`, `maintenance`, explicit tag operations,
  arbitrary fetch options/refspecs/URLs, and explicit submodule recursion stay denied.
- A fetch allowance explicitly accepts necessary common-repository writes (objects,
  configured remote-tracking refs, `FETCH_HEAD`, and Git's ordinary fetch bookkeeping).
  Never describe fetch as read-only or isolated by a linked worktree.
- Permit no Git global option. Repository hooks, content filters, transport helpers,
  credential helpers, automatic tag following, and ordinary automatic maintenance remain
  trusted configured Git behavior, not a second AWA sandbox boundary. Their outcomes are
  covered by postcondition checks and plain-language failure handling.
- Reject every leading `VAR=value` assignment, prefix wrapper, path-qualified executable,
  redirect, control operator, command substitution, and additional shell segment.
- Keep engine and kernel behavior identical through one shared command/state corpus,
  source-hook parity tests, and installed-hook contract UAT. Do not create a shared runtime
  import that puts the engine on the kernel path.
- Keep the frozen permission schema (`contracts/awa-contract.v1.json`), host modes, host
  policy, and Cursor hook wiring unchanged.
- Use Python 3.9-compatible syntax in the hook heredoc and Bash 3.2-compatible shell.
- Keep accepted plans/ADRs byte-identical. Draft ADR reconciliation is a separate,
  explicitly authorized documentation action before this plan can be accepted.

## 1. Purpose

AWA currently treats every `fetch`, `pull`, and `merge` as mutating and denies them on an
INCLUDED PRIMARY checkout. This prevents development work on the primary, but it also
prevents the primary from being maintained after work merges through a Safe Workspace or
remote PR.

The former draft solved only the second half: it allowed a shape-only
`git merge --ff-only [ref]` while requiring fetch in a linked worktree. Fresh verification
showed why that is the wrong boundary:

- the primary and every linked worktree resolve to the same Git common directory;
- they resolve `refs/remotes/origin/main` to the same file under that common directory;
- therefore, a fetch from a linked worktree updates the same object database and
  remote-tracking refs as a fetch invoked from the primary.

Requiring the agent to relocate before fetch protects no additional common-repository
state. It only adds an operator/agent detour. The useful boundary is instead:

- **maintenance is allowed** when it can only refresh the configured upstream and advance
  a clean current branch by fast-forward; and
- **work remains denied** when it creates local history, changes branch identity, resolves
  divergence, targets another ref/repository, or changes files for any other purpose.

## 2. Scope and non-goals

In scope:

- One exact upstream-fetch grammar with zero or one remote operand that must equal the
  current branch's configured upstream remote.
- One exact fast-forward grammar with zero or one ref operand that must resolve to the
  current branch's configured upstream ref.
- Local, bounded live-state checks proving a clean, attached, idle checkout with one
  remote-tracking upstream; the merge lane additionally proves `HEAD` equal to or
  ancestral to the live upstream.
- Plain-language refusal reasons for unsupported shape, local work, missing upstream,
  local-only/divergent history, and inspection failure.
- Engine/kernel/shared-corpus/installed-hook parity and offline behavior evidence.
- README, architecture, and security-policy updates replacing the prior all-mutations
  default-deny description with the exact maintenance exception and caller postcondition.
- A minor product release, isolated candidate-install proof, governed Skills pointer
  promotion, live repair, and final dogfood.

Non-goals:

- No generic "maintenance mode" and no blanket bypass for Git.
- No `git pull`; the two atomic operations keep refresh and advancement failures distinct.
- No push, explicit prune, remote update, GC, explicit tag/submodule maintenance,
  arbitrary remote, URL, refspec, or ref.
- No branch switching, detached-HEAD repair, divergence repair, reset, rebase, merge
  commit, conflict resolution, or auto-stash.
- No default-branch discovery or branch switching. The allowance maintains only the
  already-attached current branch; requiring its configured remote-tracking upstream and
  denying local-ahead/divergent history is the relevant safety boundary.
- No hook/filter/transport-helper sandbox. Those configured components are trusted
  repository maintenance behavior, just as they already are when Git runs in a linked
  worktree; AWA remains a work-protection boundary, not an arbitrary-code sandbox.
- No new executable-identity attestation. Bare `git` uses the same ambient shell/PATH
  trust boundary as the existing guard; inline PATH changes, wrappers, and explicit
  executable paths remain rejected so this exception cannot widen that boundary.
- No Git global-option allowance.
- No contract v2, host-policy change, mode change, or new operator-facing CLI verb.
- No cross-command lock or immutable-OID handoff. The guard checks the live upstream
  immediately before merge, and Git's `--ff-only` remains the final atomic ancestry gate:
  a concurrent upstream move can only yield another upstream descendant, a no-op, or a
  refusal—never a merge commit, history rewrite, or conflict resolution.

## 3. Live-state verification

Verified 2026-08-21:

- AWA remote `main` is `9737d3d`; design PR #120 is DRAFT at `a743ad7`, docs-only, and
  has no implementation. This refinement is an uncommitted two-file plan-surface delta
  atop that head.
- `engine.__version__` and `pyproject.toml` report `1.5.2`; latest published tag is
  `v1.5.2`.
- `engine/guard.py` keeps `fetch`, `pull`, and `merge` in `_GITMUT`; fetch is
  unconditionally mutating; `decide_shell` denies confirmed mutations on an included
  primary after the ADR 0001 target carve-out.
- `kernel/hooks/worktree-guard.sh::check_probe` independently mirrors that deny and
  intentionally remains off the engine critical path.
- The AWA primary and its linked Safe Workspace both resolve:
  - common directory: `~/dev/capabilities/awa/.git`
  - `refs/remotes/origin/main`:
    `~/dev/capabilities/awa/.git/refs/remotes/origin/main`
- Official Git documentation confirms:
  - no-argument `git fetch` uses the current branch's configured upstream remote (falling
    back to `origin` only when no upstream exists), applies configured fetch refspecs, and
    writes fetched names/OIDs to `FETCH_HEAD`;
  - fetch may auto-follow reachable tags, recurse into submodules when configured, and run
    automatic maintenance;
  - `--ff-only` advances only by fast-forward and otherwise exits non-zero;
  - `--no-overwrite-ignore` prevents merge from overwriting ignored untracked files;
  - any ref-updating Git command may invoke `reference-transaction`, successful merge
    invokes `post-merge`, and index writes may invoke `post-index-change`; hook lookup is
    controlled by `core.hooksPath`;
  - a `filter` attribute can invoke configured smudge/process commands when blobs are
    written to the worktree.
- These configured Git effects are explicitly accepted as repository maintenance, not
  treated as agent-authored work; the plan verifies and narrates their resulting state.
- The Skills binding is clean at `3a13f72` and consistently pins AWA `v1.5.2` commit
  `a2b13f7` in both `global/tools/awa/meta.yml` and `tool.yml`.

## 4. Decision and approach

### 4.1 Closed maintenance grammar

The recognizer accepts one shell segment and exact bare executable token `git`. It rejects
leading assignments, wrappers, executable paths, redirects, control operators, and command
substitution.

**Upstream refresh:**

```text
git fetch
git fetch <upstream-remote>
```

Rules:

- no Git global option and no fetch option;
- zero positional operands, or exactly one operand byte-equal to the configured upstream
  remote;
- a configured remote-tracking upstream MUST exist before either form qualifies;
- no URL, refspec, `--`, stdin refspec, tag/prune/all/recurse/force/dry-run form, or second
  operand qualifies.

**Fast-forward current branch:**

```text
git merge --ff-only --no-overwrite-ignore
git merge --ff-only --no-overwrite-ignore @{u}
git merge --ff-only --no-overwrite-ignore @{upstream}
git merge --ff-only --no-overwrite-ignore <configured-upstream-short-name>
```

Rules:

- no Git global option;
- merge arguments contain exactly `--ff-only --no-overwrite-ignore`, in that order,
  followed by zero or one ref;
- an explicit ref token must be exactly `@{u}`, `@{upstream}`, or the computed
  `<upstream-remote>/<upstream-branch>` short name, and Git must resolve it to the same
  full remote-tracking ref as `@{upstream}`;
- the former broad slash-token regex is removed; lexical resemblance to `origin/main` is
  never enough;
- no second flag, second ref, revision expression, OID, `--`, or shell
  variable/substitution qualifies.

All allowed forms still return `classify_mutating(command) is True`.

### 4.2 Live maintenance context

After command-shape recognition and before any allow, both mirrors perform only local,
bounded Git inspection in the command's cwd:

1. Confirm the repo is the included primary already classified by the outer guard.
2. Confirm `HEAD` is attached to a local branch.
3. Resolve exactly one configured upstream and require it to be a remote-tracking ref.
4. Resolve its remote name; for `fetch <remote>`, require byte equality.
5. Read every configured `remote.<upstream>.fetch` refspec and require each positive
   destination to stay under `refs/remotes/<upstream>/`; source-only negative refspecs may
   narrow that set. Require at least one positive mapping from the configured upstream
   source branch to the exact configured upstream destination. Missing destinations,
   tag/local-branch destinations, malformed refspecs, stale upstream mappings, and any
   other namespace are not proven maintenance.
6. Require no merge, rebase, cherry-pick, revert, am, sequencer, or bisect state.
7. Reject repository-retargeting/config-injection environment state visible to the guard
   (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`,
   `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_CONFIG`,
   `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`, any `GIT_CONFIG_*` entry, `GIT_EXEC_PATH`,
   `GIT_NAMESPACE`, `GIT_SHALLOW_FILE`, `GIT_REPLACE_REF_BASE`,
   `GIT_NO_REPLACE_OBJECTS`, `GIT_CEILING_DIRECTORIES`, and
   `GIT_DISCOVERY_ACROSS_FILESYSTEM`).
8. Require a clean index and worktree, including untracked files
   (`git status --porcelain --untracked-files=all` is empty).
9. For merge only:
   - require an explicit ref, if present, to resolve to the same full upstream ref;
   - require `git merge-base --is-ancestor HEAD @{upstream}` to succeed, proving no
     local-only or divergent commit exists;
   - let the executed `--ff-only` command re-enforce ancestry atomically.

Every inspection uses `GIT_OPTIONAL_LOCKS=0`, has a bounded timeout, and uses closed output
parsing. Missing, ambiguous, non-zero, timed-out, or malformed output means "not proven
maintenance" and falls through to the existing deny. Fetch completion does not authorize
merge permanently; the second command receives a fresh full check, and `--ff-only`
rechecks the moving ref safely at execution.

### 4.3 Accepted effects and protected effects

Accepted maintenance effects:

- fetch may write objects, `FETCH_HEAD`, configured remote-tracking refs, shallow/partial
  clone metadata, and ordinary fetch bookkeeping in the shared common repository;
- fetch may invoke configured hooks/transport/credential helpers, auto-follow reachable
  tags, and run ordinary automatic maintenance;
- safe configured-refspec validation prevents explicit writes to local branches, tags,
  and unrelated namespaces;
- merge may advance only the current branch to its upstream descendant and update
  `HEAD`, index, worktree, reflog, and `ORIG_HEAD`;
- merge may invoke configured repository hooks, fsmonitor, submodule behavior, and content
  filters; these are accepted trusted maintenance effects, and the caller checks their
  resulting state immediately afterward.

Still protected:

- local commit creation or rewrite;
- switching/creating/deleting branches;
- any local-only or divergent history;
- arbitrary remote/ref/refspec updates;
- chained commands, wrappers, environment laundering, or target relocation;
- every unrelated mutation already denied today.

### 4.4 Decision-layer wiring

Engine:

```text
if classify_mutating(command):
    maintenance = classify_primary_maintenance(command, cwd)
    if maintenance.allowed:
        return allow(maintenance.reason)
    # existing ADR 0001 target narrowing
    # existing enforced deny
```

Kernel:

- embedded Python computes the same command kind and live-state verdict;
- it emits a closed `maintenance_kind=none|fetch|fast_forward` value plus a bounded reason
  code;
- `check_probe` allows only a non-`none` result after the existing uncertain-classification
  ask gate and before ADR 0001 target narrowing;
- predicate false/unknown falls through to the existing deny;
- a genuine hook-internal crash retains the product-wide fail-open behavior unchanged.

No permission value, response shape, policy mode, or contract schema changes.

### 4.5 Plain-language feedback

Maintenance-shaped refusals get specific, tested copy:

- **Unsupported form:** nothing ran; show the exact supported operation forms and state that
  extra flags/targets remain blocked.
- **Dirty primary:** nothing ran because local files exist; tell the agent to preserve or
  move that work before maintenance.
- **Detached/missing upstream:** nothing ran because AWA could not identify one tracked
  destination; tell the agent to repair branch tracking in a Safe Workspace.
- **Unsafe fetch configuration:** nothing ran because the configured fetch destination
  is broader than this maintenance lane; tell the agent to repair that configuration in a
  Safe Workspace.
- **Ahead/diverged:** nothing ran because the primary contains local-only or conflicting
  history; tell the agent to reconcile it in a Safe Workspace.
- **Inspection failure:** nothing ran because safety could not be established; do not
  suggest disabling protection or setting the session-wide override for routine
  maintenance.

After each allowed maintenance command, the caller MUST verify clean status before
continuing. If configured repository automation leaves residue, the caller states that
maintenance ran but the primary is no longer clean, stops, preserves the state, and
diagnoses it from a Safe Workspace rather than resetting the primary. This is a
caller/postcondition contract, not copy emitted by the pre-execution guard.

Unrelated primary mutations keep the existing generic denial.

## 5. Work items

### Owner GO/NO-GO gate

Before Task 1:

- [ ] Revise draft ADR 0010 so its remote-command rule distinguishes unnecessary remote
  dry-runs/push from the accepted upstream-fetch maintenance operation and removes the
  false linked-worktree-isolation rationale.
- [ ] Revise draft ADR 0011 from "merge-only" to the exact fetch + fast-forward lane,
  including live-state preconditions and accepted configured Git effects.
- [ ] Re-run doc-warden and design review on the ADR/plan set.
- [ ] Obtain explicit owner acceptance plus a separate instruction to implement.

If any box is open, STOP. No source, test, version, release, Skills, or host change is
authorized.

### Task 1: Prove the maintenance state envelope offline

**Files:**
- Create: `engine/tests/test_git_primary_maintenance_behavior.py`
- Test: `engine/tests/test_git_primary_maintenance_behavior.py`

**Interfaces:**
- Consumes: local Git, isolated bare remote, one primary clone, one linked worktree,
  and representative repository configuration.
- Produces: reproducible evidence for shared-common-dir fetch effects and
  upstream-bound fast-forward effects.

- [ ] Build a fully local fixture with global/system config disabled and no network.
- [ ] Prove primary and linked worktree resolve the same common directory and upstream
  tracking ref.
- [ ] From the primary, run the canonical upstream fetch and assert:
  - expected objects, tracking ref, and `FETCH_HEAD` update;
  - `HEAD`, current local branch, index, worktree, and unrelated refs do not change;
  - no remote ref changes.
- [ ] Run the canonical fast-forward and assert:
  - `HEAD` becomes the upstream descendant with no merge commit;
  - index/worktree are clean and match the target;
  - configured hook/filter fixtures execute according to ordinary Git behavior and their
    resulting state is observed rather than attributed to agent-authored work;
  - an ignored untracked path that the target would overwrite causes Git to refuse with
    that path unchanged;
  - the linked worktree's branch, index, and worktree files remain unchanged while shared
    upstream metadata updates are visible there.
- [ ] Move the upstream ref between a simulated preflight and merge, then prove the
  executed merge yields only an upstream-descendant fast-forward, a no-op, or a refusal.
- [ ] Prove equal/up-to-date is a no-op and divergence exits non-zero with `HEAD`
  unchanged.
- [ ] Make a configured fetch or merge hook leave residue, prove the postcondition detects
  it, and assert the maintenance flow stops without reset/cleanup or a second command.
- [ ] Record `git --version` in test diagnostics.

```bash
python3 -m unittest engine.tests.test_git_primary_maintenance_behavior
```

Expected: `OK`.

**Definition of done:** The test observes the exact allowed state envelope rather than
claiming fetch is read-only or treating trusted configured Git effects as a separate AWA
sandbox boundary.

### Task 2: Implement the engine recognizer and state-aware decision

**Files:**
- Modify: `engine/guard.py`
- Modify: `engine/tests/git_guard_command_corpus.py`
- Modify: `engine/tests/test_guard.py`

**Interfaces:**
- Consumes: existing shell segmentation, Git invocation parser, Git context resolution,
  and `decide_shell`.
- Produces: a closed command recognizer, bounded live-state inspector, maintenance reason
  codes, and decision-layer allow.

- [ ] Add shared `PRIMARY_MAINTENANCE_ALLOW_SHAPES` and
  `PRIMARY_MAINTENANCE_NEAR_MISS_DENY` corpora. Every entry in both MUST still classify
  mutating.
- [ ] Add fail-before decision tests for the canonical fetch and fast-forward forms.
- [ ] Add command-shape negatives for:
  - any fetch option; URL/refspec/stdin/all/prune/recurse/force/dry-run/multiple operands;
  - merge missing/reordering either required safety flag, any extra merge flag, any `-c`
    value, or any other global option;
  - leading `PATH=`, `GIT_DIR=`, `GIT_WORK_TREE=`, and `GIT_CONFIG_COUNT=`;
  - `env`, `command`, `sudo`, path-qualified `/tmp/git`, chain, redirect, substitution;
  - wrong named ref, OID, revision expression, second ref, shell variable/substitution,
    and extra flag;
  - `pull`, `push`, `remote update`, `remote prune`, `gc`, and `maintenance`.
- [ ] Add live-state fixtures for:
  - clean attached branch + one upstream (allow);
  - optional fetch remote exact match plus omitted/`@{u}`/`@{upstream}`/short-name merge
    operands bound to the exact upstream (allow);
  - fetch and fast-forward both deny with dirty tracked/untracked files; detached HEAD,
    missing upstream, local upstream,
    wrong remote/ref, unsafe or stale configured fetch destination, local-ahead,
    divergence, every in-progress state, timeout, malformed output, and risky visible Git
    environment (deny).
- [ ] Implement the recognizer and local inspector with bounded subprocess calls.
- [ ] Wire the allow inside the mutating branch before ADR 0001 narrowing.
- [ ] Assert linked-worktree and non-included behavior remains unchanged.

```bash
python3 -m unittest \
  engine.tests.test_guard.TestMutatingClassifier \
  engine.tests.test_guard.TestDecideShellDegraded
```

Expected: fail before implementation, then `OK`.

**Definition of done:** Only the closed command + live-state intersection allows; every
near miss keeps the prior deny; classification remains mutating.

### Task 3: Mirror the kernel hook and prove source/installed parity

**Files:**
- Modify: `kernel/hooks/worktree-guard.sh`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `kernel/checks/awa-contract-freeze.sh`

**Interfaces:**
- Consumes: Task 2's shared corpora and state fixture builder.
- Produces: annotation-free embedded-Python recognizer/inspector, closed reason codes,
  `check_probe` allow branch, source-hook parity, and installed-hook UAT.

- [ ] Add failing source-hook tests for every allow shape, shape near miss, and live-state
  case from Task 2.
- [ ] Mirror command parsing and state checks in the hook without importing the engine.
- [ ] Ensure predicate false/unknown falls through to deny while a forced genuine
  hook-internal failure still exercises the existing fail-open contract.
- [ ] Drive one shared stateful adversarial corpus through `decide_shell`, the source hook,
  and the installed/role-resolved hook.
- [ ] Keep contract UAT lean: one canonical fetch allow, one canonical fast-forward allow,
  and representative denials for dirty state, wrong upstream/ref, environment laundering,
  Git global option, fetch refspec, and pull/push.
- [ ] Keep `contracts/awa-contract.v1.json` unchanged.

```bash
python3 -m unittest engine.tests.test_guard_hook_wrappers
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
```

Expected: `OK` and `awa-contract-freeze: OK`.

**Definition of done:** Engine, source hook, and installed hook agree for both command and
state; uncertainty never widens the maintenance allowance.

### Task 4: Add operator feedback, prepare the version, and verify the whole branch

**Files:**
- Modify: `engine/guard.py`
- Modify: `kernel/hooks/worktree-guard.sh`
- Modify: `engine/tests/test_guard.py`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `engine/__init__.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `SECURITY.md`

**Interfaces:**
- Produces: plain-language maintenance refusal reasons and synchronized next minor
  version.

- [ ] Add exact-copy tests for unsupported form, dirty, missing upstream, divergence,
  unsafe fetch configuration, and inspection failure; assert routine-maintenance copy
  never recommends disabling AWA, resetting the primary, or using the primary override.
- [ ] Update README/architecture/security guard policy so it names the exact maintenance
  exception, preserves the default deny for development, records accepted configured Git
  behavior, and requires the caller's post-command clean-status check.
- [ ] Re-verify the live latest release/tag without mutating a primary. This new allowed
  behavior requires a MINOR bump (expected `1.6.0` from `1.5.2`; recompute if releases
  advanced).
- [ ] Update both version declarations and verify identity.

```bash
test "$(make -s version)" = "<chosen-version>"
python3 -m unittest \
  engine.tests.test_git_primary_maintenance_behavior \
  engine.tests.test_guard \
  engine.tests.test_guard_hook_wrappers
bash engine/tests/run-tests.sh
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
make verify
make verify-install
git diff --check origin/main...HEAD
```

- [ ] Run Bugbot over the complete implementation branch; fix every valid finding and
  rerun focused/full verification until clean.

**Definition of done:** Copy is plain and actionable, versions agree, every local gate
passes, and complete-branch defect review is clean.

### Task 5: Ship, stage-prove, release, promote, and reconcile

**Files:**
- No additional AWA source files unless review finds a defect.
- Later, in a separately governed `KleinPerkins/skills` Safe Workspace:
  `global/tools/awa/meta.yml`, `global/tools/awa/tool.yml`,
  `global/tools/awa/README.md`, `.eco-registry.lock`.

**Interfaces:**
- Consumes: Tasks 1–4, the exact verified AWA merge commit, isolated install fixtures,
  runnerless PR automation, and explicit release/promotion/live-install GO.
- Produces: the immutable release, synchronized Skills binding, repaired live host,
  maintained protected primaries, and clean branch/worktree state.

- [ ] Push and open a separate implementation PR with Summary + Test plan. Keep the
  design-only PR separate.
- [ ] Wait for runnerless `pr-automation / verify` and reviewer-App governance. Never
  call `gh pr merge --auto`, change auto-merge state, bypass checks, or force-push.
- [ ] Verify the exact merge commit is on live `main` and carries the chosen version.
- [ ] Before publication, install the exact merge commit into an isolated HOME/XDG
  fixture and run installed-hook dogfood:
  - canonical fetch allow;
  - canonical upstream-bound fast-forward allow;
  - dirty/wrong-upstream/environment/refspec/pull/push denials;
  - final clean state and exact `HEAD == @{upstream}`.
- [ ] Obtain explicit release/promotion/live-install GO. A failed isolated proof leaves
  the old release, Skills pin, and live install untouched.
- [ ] On GO, tag and publish the exact verified merge commit.
- [ ] In a fresh Skills Safe Workspace, update both immutable commit pins and readable
  version references, regenerate/check the ecosystem lock, run Skills verification, and
  open the separately governed PR. Wait for its reviewer automation.
- [ ] Repair the live host to the published release and run `dev-worktree.sh doctor`.
- [ ] Dogfood each clean protected primary with the exact lane:

```bash
git fetch
git status --short
git merge --ff-only --no-overwrite-ignore
git status --short
```

- [ ] Require empty status output after each maintenance command. Then verify attached
  branch, configured upstream, and `HEAD == @{upstream}`; verify representative near
  misses still deny.
- [ ] Clean merged feature branches/worktrees through the normal governed cleanup path.

**Definition of done:** Candidate behavior is proven before publication; source release,
Skills pin, and live host converge on the exact verified commit; protected primaries are
clean and current; no orphan branch/worktree state remains.

## 6. Acceptance criteria

- The governing draft ADRs and this plan describe the same two-operation maintenance
  boundary before any implementation begins.
- On an included primary, only canonical upstream fetch and upstream-bound ff-only merge
  allow, and only in the proven live state.
- Fetch and merge remain classified mutating; no broader consumer mistakes them for
  read-only commands.
- Primary and linked-worktree common-state behavior is proven, not described as isolated.
- Dirty work prevents both maintenance operations. Detached, missing/local/wrong upstream,
  local-ahead, divergent,
  in-progress, unsafe/stale configured fetch destination, wrong ref, malformed, timed-out,
  retargeted, wrapped, chained, redirected, and extra-option cases deny in engine, source
  hook, and installed hook as applicable.
- Configured Git hooks, filters, helpers, tag following, and ordinary maintenance retain
  standard Git behavior; postconditions surface any residue. The merge refuses to
  overwrite ignored untracked files and cannot create a merge commit or resolve
  divergence.
- Pull, push, explicit prune, remote update, GC/maintenance, branch mutation, arbitrary
  remote/ref/refspec, and every development command remain denied.
- Maintenance failures produce specific plain-language next steps and never recommend a
  blanket bypass.
- The permission contract, host policy/modes, and kernel-first boundary remain unchanged.
- Isolated installed-host dogfood passes before release/promotion; source release, Skills
  pin, and live host converge only after explicit GO.

## 7. Rollback

- Before merge: correct with a new commit; never amend a pushed commit.
- After merge but before release: revert through a normal PR; the old Skills pin/live
  release remain untouched.
- After release: never move/delete the tag; publish a corrective patch and revert the
  Skills pointer through its governed PR.
- If the live install fails, reinstall the previous immutable release and run
  `dev-worktree.sh doctor`; do not reset a primary.
- Remove or narrow the allowance only through a new ADR plus successor plan after this
  plan is accepted; accepted artifacts remain byte-identical.
