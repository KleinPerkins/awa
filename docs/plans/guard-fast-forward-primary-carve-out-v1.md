# Guard Fast-Forward Primary Carve-Out — Let an agent fast-forward a protected primary without an operator step

- **Version:** v1
- **Status:** DRAFT — 2026-08-21
- **Date:** 2026-08-21
- **Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
- **Plan-type:** agentic-execution
- **Relates to:** ADR 0011 (authorizes this design), ADR 0001 (additive-only mutation-scope
  doctrine), ADR 0010 (fetch/push remain mutating), `docs/plans/git-command-policy-hardening-v1.md`
  (sibling classifier plan whose Task 5 currently fast-forwards primaries only behind the operator
  override)
- **Review provenance:** `prompt-architect`-scoped draft authored from live guard-source verification
  (AWA `main` @ `9737d3d`, v1.5.2); design-acceptance-only, implementation gated on a separate
  operator instruction.

**Goal:** Add a narrow, additive carve-out so that on an INCLUDED PRIMARY checkout, a single
`git merge --ff-only [<tracked-upstream>]` of the current branch is ALLOWED (converting today's
enforced `deny` into an `allow`), while every other primary mutation — including every
non-fast-forward merge, every extra flag, and all fetch/push/pull forms — stays denied.

**Architecture:** Implement the allowance at the decision layer (`engine/guard.py::decide_shell` and
the kernel `kernel/hooks/worktree-guard.sh` `check_probe` mirror), parallel to the ADR 0001
target-narrowing and BEFORE the enforced deny. `merge` stays in `_GITMUT` and keeps classifying as
mutating; a new pure predicate `_is_safe_ff_only_merge(command)` recognizes only the exact closed
fast-forward grammar. Runtime fast-forward/clean-tree safety is delegated to git's own `--ff-only`
guarantee; the guard proves only the command shape. Kernel-first duplication-with-parity is retained.

**Tech stack:** Python stdlib, Bash, Git 2.50.1 behavior baseline, `unittest`, AWA contract-freeze
UAT, runnerless PR automation, and the `KleinPerkins/skills` capability-lifecycle binding.

> **For agentic workers:** REQUIRED SUB-SKILL — use `subagent-driven-development` or `executing-plans`
> to implement this plan task-by-task. Each work item's steps use checkbox (`- [ ]`) syntax for
> progress tracking. Do NOT begin Task 1 until the Owner GO/NO-GO gate in §4 is satisfied by a
> separate, explicit operator instruction.

---

## Global Constraints

- Execute only in an AWA Safe Workspace (linked worktree); never edit the primary checkout directly.
- Preserve kernel-first operation: `kernel/hooks/worktree-guard.sh` must not import `engine.guard` or
  depend on the daemon; hook-internal failure must still degrade to allow.
- The carve-out is additive-only (ADR 0001 §1): it may only ever convert a `deny` into an `allow`. It
  must never convert an `allow` into a `deny`, never weaken any existing deny, and any deviation or
  uncertainty must resolve to the enforced deny.
- Keep `merge` mutating in `classify_mutating`/`_git_is_mutating`. The allowance lives ONLY in
  `decide_shell`/`check_probe`. Fast-forward-allow cases are verified as decision-layer allows, never
  by moving them into the read-only corpus.
- `fetch`, `push`, and `pull` receive no allowance on protected primaries (ADR 0010). `git pull
  --ff-only` stays denied because it embeds a fetch.
- No git global option qualifies in v1 (`-C`, `--git-dir`, `--work-tree`, `--namespace`,
  `--super-prefix`, `-c`, `-p`/`--paginate`, `--config-env=`); no prefix wrapper qualifies.
- Do not change host modes, host policy, Cursor hook wiring, or the frozen permission JSON schema
  (`contracts/awa-contract.v1.json`). Permission values/response shapes are unchanged.
- Keep the engine and hook mirrors behaviorally identical through the shared corpus and live-hook
  parity tests. No generated/imported shared classifier module.
- Keep every already-approved plan and accepted ADR byte-identical; reconcile completed/superseded
  status in the mutable index rows only.
- Python 3.9 compatibility inside the hook heredoc (no `X | None` annotations); Bash 3.2 safety (no
  bare apostrophes inside the embedded-Python heredoc). Use no third-party Python dependency.
- Merging this plan and ADR 0011 ACCEPTS THE DESIGN ONLY. Implementation begins only after a separate,
  explicit operator instruction to execute this accepted plan.

## 1. Purpose

An agent that merges work via a Safe Workspace/branch (or whose branch merged remotely) cannot land
it into the local **primary** `main`, because `git merge --ff-only origin/main` on a protected
primary classifies as mutating and is denied (`engine/guard.py` line ~966; hook line ~1184). The only
escapes are an operator relaunch in a Safe Workspace or `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1`. This
plan implements ADR 0011: a fast-forward is uniquely safe (no dirty work to lose given AWA's own
no-other-mutation invariant; no history rewrite/merge-commit/conflict; reversible via reflog +
`ORIG_HEAD`), so it is allowed without an operator step, while every other primary mutation stays
denied.

## 2. Scope and non-goals

In scope:

- Prove `git merge --ff-only` runtime behavior in an offline, isolated fixture.
- Add a pure `_is_safe_ff_only_merge(command)` predicate enforcing the ADR 0011 closed grammar.
- Wire it as an additive allow in `engine/guard.py::decide_shell`, before the enforced deny.
- Mirror it in the kernel hook (`check_probe` + a `safe_ff` signal from the embedded Python).
- Extend the shared corpus and decision/parity/contract tests with the allow set and an exhaustive
  near-miss deny set.
- Bump the AWA product version and ship through the governed PR/release/promotion path.

Non-goals:

- No remote/network allowance; fetch/push/pull stay denied on protected primaries (ADR 0010).
- No `merge` reclassification to read-only; no change to `classify_mutating`'s meaning.
- No git global option or wrapper allowance; no arbitrary-ref, multi-ref, or revision-expression ref.
- No `--autostash`, `--no-verify`, strategy, squash, sign, or any non-`--ff-only` flag.
- No runtime ancestry/clean-tree pre-check in the guard (delegated to git `--ff-only`); a future ADR
  may revisit.
- No host policy/mode change, no Cursor hook-wiring change, no frozen contract v2.

## 3. Background and context (live-state verification)

Verified 2026-08-21 against AWA `main` @ `9737d3d`, `engine.__version__ = 1.5.2`, latest tag
`v1.5.2`:

- `engine/guard.py`: `_GITMUT` (lines ~32–35) includes `merge`; `_git_is_mutating` (line ~327) has no
  merge predicate → merge returns `True`. `decide_shell(cwd, command, policy_path, *,
  allow_primary=False)` (line ~918): after `classify_mutating` (line ~528) is True, the ADR 0001
  additive narrowing runs `_collect_precise_targets` (line ~958) and otherwise returns the enforced
  `deny` (line ~966). For `git merge --ff-only`, `_collect_precise_targets` resolves the target to the
  cwd primary, so it does not already allow — the carve-out must be a distinct check ahead of the
  deny.
- Helpers reused by the predicate already exist: `_segments` (line ~405), `_parse_git_invocation`
  (line ~99), `_has_glob_metachar` (line ~562), `_REDIRECT_OPS` (line ~401).
- `kernel/hooks/worktree-guard.sh`: `_GITMUT` (lines ~146–147); embedded-Python emits `is_mutating`,
  `has_mut_targets`, `mut_targets` (lines ~600, ~818, ~858–864); bash `check_probe` (line ~1142)
  applies the additive narrowing (lines ~1172–1181) then the enforced deny (lines ~1184–1187);
  `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` short-circuits at line ~1002.
- Shared corpus: `engine/tests/git_guard_command_corpus.py`; parity test:
  `engine/tests/test_guard_hook_wrappers.py`; classifier/decision tests: `engine/tests/test_guard.py`;
  contract-freeze UAT: `kernel/checks/awa-contract-freeze.sh`.
- Linked worktrees share the primary object store + `refs/remotes/*` (a Safe Workspace's
  `git rev-parse --git-common-dir` resolves to the primary `.git`), so fetch-from-worktree +
  ff-only-merge-in-primary needs no primary fetch.

## 4. Approach

**Owner GO/NO-GO gate:** merging this document and ADR 0011 accepts the design and policy, not
execution. An implementer must receive a separate explicit operator instruction before Task 1. NO-GO
leaves the accepted artifacts frozen and makes no source, version, release, downstream, or host
change.

The predicate is a pure boolean over the command string. `True` means "exactly the safe fast-forward
grammar"; `False` means "not proven safe" and therefore leaves the existing deny in place. Reference
implementation (engine; the hook mirrors it annotation-free):

```python
import re

_GIT_FF_UPSTREAM_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+$")


def _git_ref_is_allowed_upstream(token: str) -> bool:
    """A single tracked-upstream-shaped ref: @{upstream}/@{u}, or <remote>/<name> with no
    leading dash and no glob metacharacter. Everything else (bare branch, HEAD~1, glob) -> False."""
    if token in ("@{upstream}", "@{u}"):
        return True
    if token.startswith("-") or _has_glob_metachar(token):
        return False
    return bool(_GIT_FF_UPSTREAM_RE.match(token))


def _is_safe_ff_only_merge(command: str) -> bool:
    """True ONLY for a single-segment, wrapper-free, global-option-free
    `git merge --ff-only [<tracked-upstream>]` with no other flag and at most one allowlisted
    upstream ref. Additive carve-out (ADR 0011): used to convert a deny into an allow on an included
    primary; any deviation returns False (conservative -> deny)."""
    try:
        segs = _segments(command)
    except ValueError:
        return False
    if len(segs) != 1:
        return False
    toks = segs[0]
    if any(t in _REDIRECT_OPS for t in toks):
        return False
    # Only leading VAR=value assignments may precede a BARE git (reject every prefix wrapper).
    j = 0
    while j < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[j]):
        j += 1
    if j >= len(toks) or os.path.basename(toks[j]) != "git":
        return False
    parsed = _parse_git_invocation(toks[j + 1:])
    if parsed is None:
        return False
    global_args, sub, sub_args = parsed
    if global_args or sub != "merge":
        return False
    saw_ff_only = False
    ref_count = 0
    for a in sub_args:
        if a == "--ff-only":
            saw_ff_only = True
            continue
        if a.startswith("-"):
            return False
        ref_count += 1
        if ref_count > 1 or not _git_ref_is_allowed_upstream(a):
            return False
    return saw_ff_only
```

Wiring in `decide_shell`, inside the existing `if classify_mutating(command):` branch, BEFORE the
`_collect_precise_targets` narrowing and the deny:

```python
    if classify_mutating(command):
        if _is_safe_ff_only_merge(command):
            return _allow(
                "fast-forward-only update of the current branch to its tracked upstream "
                "(ADR 0011 additive carve-out); git --ff-only guarantees no merge commit, "
                "no history rewrite, and abort-not-clobber",
                cls.classification)
        targets = _collect_precise_targets(command, cwd)
        ...  # unchanged ADR 0001 narrowing, then the unchanged enforced deny
```

Kernel mirror: the embedded Python computes `is_safe_ff = _is_safe_ff_only_merge(cmd)` and prints
`is_safe_ff=1|0` alongside `is_mutating`; `check_probe` returns `respond_allow` when
`is_mutating=1` and `is_safe_ff=1`, positioned before the additive-target block and the deny (and
after the `is_uncertain_include` ask path, which is unchanged).

## 5. Work items

### Task 1: Prove fast-forward runtime behavior offline

**Files:**
- Create: `engine/tests/test_git_ff_only_merge_behavior.py`
- Test: `engine/tests/test_git_ff_only_merge_behavior.py`

**Interfaces:**
- Consumes: `engine.tests.helpers.EngineTestCase`, the local `git` executable, isolated temporary
  repositories (mirror the fixture style of `engine/tests/test_git_remote_dry_run_behavior.py`).
- Produces: `TestGitFfOnlyMergeBehavior` with tests proving: (a) fast-forward advances the current
  branch to a descendant and updates the work tree; (b) an up-to-date ref is a no-op; (c) a divergent
  ref aborts with a non-zero exit and leaves `HEAD` unchanged; (d) `--ff-only` refuses (non-zero,
  unchanged `HEAD`) when a dirty tracked file would be overwritten; (e) a `post-merge` hook runs on a
  real fast-forward. Each assertion records the host `git --version`.

- [ ] **Step 1 — Write the isolated behavior-proof test** covering (a)–(e) above in local bare/clone
  fixtures with `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`; no
  network.
- [ ] **Step 2 — Run the proof**

```bash
python3 -m unittest engine.tests.test_git_ff_only_merge_behavior
```

Expected: `OK`; the tests positively demonstrate the `--ff-only` fast-forward/no-op/abort/refuse
semantics and post-merge-hook execution without network access.

- [ ] **Step 3 — Commit**

```bash
git add engine/tests/test_git_ff_only_merge_behavior.py
git commit -m "test(guard): prove git merge --ff-only fast-forward/abort semantics"
```

**Definition of done:** The `--ff-only` safety properties ADR 0011 relies on are reproducible in an
offline fixture, with the host git version recorded.

### Task 2: Implement and test the engine carve-out

**Files:**
- Modify: `engine/guard.py`
- Modify: `engine/tests/git_guard_command_corpus.py`
- Modify: `engine/tests/test_guard.py`
- Test: `engine/tests/test_guard.py`

**Interfaces:**
- Consumes: existing `_segments`, `_parse_git_invocation`, `_has_glob_metachar`, `_REDIRECT_OPS`,
  `classify_mutating`, `decide_shell`.
- Produces: `_git_ref_is_allowed_upstream(token)`, `_is_safe_ff_only_merge(command)`, and the
  `decide_shell` additive-allow branch (§4). A new corpus tuple `GIT_FF_ONLY_MERGE_ALLOW` (allowed on
  a primary) and `GIT_FF_ONLY_MERGE_NEAR_MISS_DENY` (denied on a primary), plus the invariant that
  every command in BOTH tuples still returns `classify_mutating(...) is True`.

- [ ] **Step 1 — Extend the corpus** with the exhaustive allow and near-miss sets:

```python
GIT_FF_ONLY_MERGE_ALLOW = (
    "git merge --ff-only",
    "git merge --ff-only @{upstream}",
    "git merge --ff-only @{u}",
    "git merge --ff-only origin/main",
    "git merge --ff-only upstream/release/1.2",
)

GIT_FF_ONLY_MERGE_NEAR_MISS_DENY = (
    "git merge",
    "git merge origin/main",
    "git merge --no-ff origin/main",
    "git merge --ff-only --no-verify",
    "git merge --ff-only --autostash",
    "git merge --ff-only --squash origin/main",
    "git merge --ff-only -X theirs origin/main",
    "git merge --ff-only -S",
    "git merge --ff-only -m msg",
    "git merge --ff-only origin/main topic",
    "git merge --ff-only feature-branch",
    "git merge --ff-only HEAD~1",
    "git merge --ff-only -- origin/main",
    "git merge --ff-only 'origin/*'",
    "git -C /tmp merge --ff-only origin/main",
    "git -c core.pager=less merge --ff-only origin/main",
    "git --paginate merge --ff-only origin/main",
    "git pull --ff-only",
    "sudo git merge --ff-only origin/main",
    "git merge --ff-only origin/main && rm -rf protected",
    "git merge --ff-only origin/main > /tmp/log",
)
```

- [ ] **Step 2 — Add classifier + decision tests, verify they FAIL first.** In
  `TestMutatingClassifier`, assert `guard.classify_mutating(cmd) is True` for EVERY command in both
  new tuples (the carve-out must not make any of them read-only). In `TestDecideShellDegraded`, for a
  primary repo `repo` and policy `pol`: assert `decide_shell(repo, cmd, pol).permission == "allow"`
  for each `GIT_FF_ONLY_MERGE_ALLOW`, and `== "deny"` for each `GIT_FF_ONLY_MERGE_NEAR_MISS_DENY`;
  and assert each allow case still allows in a linked worktree.

```bash
python3 -m unittest engine.tests.test_guard.TestMutatingClassifier engine.tests.test_guard.TestDecideShellDegraded
```

Expected: the decision tests FAIL (fast-forward currently denies on a primary); the classifier
assertions PASS already.

- [ ] **Step 3 — Implement `_git_ref_is_allowed_upstream`, `_is_safe_ff_only_merge`, and the
  `decide_shell` additive-allow branch** exactly per §4.
- [ ] **Step 4 — Run the tests, verify they PASS**

```bash
python3 -m unittest engine.tests.test_guard.TestMutatingClassifier engine.tests.test_guard.TestDecideShellDegraded
```

Expected: `OK`.

- [ ] **Step 5 — Commit**

```bash
git add engine/guard.py engine/tests/git_guard_command_corpus.py engine/tests/test_guard.py
git commit -m "feat(guard): allow fast-forward-only update of a protected primary (ADR 0011)"
```

**Definition of done:** On a primary, exactly the ADR 0011 grammar allows and every near-miss denies;
all cases still classify mutating; worktree behavior is unchanged.

### Task 3: Mirror the kernel hook and freeze live-hook parity

**Files:**
- Modify: `kernel/hooks/worktree-guard.sh`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `kernel/checks/awa-contract-freeze.sh`
- Test: `engine/tests/test_guard_hook_wrappers.py`

**Interfaces:**
- Consumes: Task 2's grammar and the shared corpus tuples.
- Produces: the embedded-Python `_git_ref_is_allowed_upstream`/`_is_safe_ff_only_merge` (annotation-
  free), an `is_safe_ff` output line, a `check_probe` allow branch, and contract-freeze UAT coverage.

- [ ] **Step 1 — Write failing hook parity tests.** Assert the live hook returns `allow` for every
  `GIT_FF_ONLY_MERGE_ALLOW` command on a primary probe and `deny` for every
  `GIT_FF_ONLY_MERGE_NEAR_MISS_DENY`; reassert the hook contains no `X | None` annotations.

```bash
python3 -m unittest engine.tests.test_guard_hook_wrappers
```

Expected: FAIL on the fast-forward allow cases before the mirror change.

- [ ] **Step 2 — Mirror the predicate and wiring** into the hook's embedded Python (annotation-free;
  apostrophe-free comments/docstrings), emit `is_safe_ff=1|0`, and add the `check_probe` allow branch
  (mutating included primary + `is_safe_ff=1` → `respond_allow`), before the additive-target block and
  the deny. Do NOT import `engine.guard`.
- [ ] **Step 3 — Extend contract-freeze UAT** with exact allow cases (`git merge --ff-only`,
  `git merge --ff-only origin/main`, `git merge --ff-only @{u}`) and exact deny cases (`git merge`,
  `git merge --no-ff origin/main`, `git merge --ff-only --no-verify`, `git merge --ff-only feature-branch`,
  `git -C /tmp merge --ff-only origin/main`, `git pull --ff-only`). Keep `contracts/awa-contract.v1.json`
  unchanged.
- [ ] **Step 4 — Run hook + contract checks, verify they PASS**

```bash
python3 -m unittest engine.tests.test_guard_hook_wrappers
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
```

Expected: `OK` and `awa-contract-freeze: OK`.

- [ ] **Step 5 — Commit**

```bash
git add kernel/hooks/worktree-guard.sh engine/tests/test_guard_hook_wrappers.py kernel/checks/awa-contract-freeze.sh
git commit -m "fix(kernel): mirror fast-forward primary carve-out (ADR 0011)"
```

**Definition of done:** The live Cursor hook, engine mirror, shared corpus, and contract UAT return
identical allow/deny outcomes for the fast-forward grammar and its near-misses.

### Task 4: Prepare the release version and verify the complete implementation

**Files:**
- Modify: `engine/__init__.py`
- Modify: `pyproject.toml`
- Test: `engine/tests/test_git_ff_only_merge_behavior.py`, `engine/tests/test_guard.py`,
  `engine/tests/test_guard_hook_wrappers.py`

**Interfaces:**
- Consumes: Tasks 1–3 and the current `1.5.2` version declarations.
- Produces: a synchronized next product version with an unchanged `contracts/awa-contract.v1.json`.

- [ ] **Step 1 — Verify the release precondition and choose the next version.** Re-verify the latest
  tag live (`git fetch --tags origin`; `gh release list`). This adds new allowed behavior, so bump the
  MINOR component (expected `1.6.0` from `1.5.2`); if releases have advanced, recompute the next
  unused version rather than overwriting newer work. Assert both `engine.__version__` and
  `pyproject.toml` currently read `1.5.2` (or the actual current value) before editing.
- [ ] **Step 2 — Bump both version declarations** (`engine/__init__.py` `__version__` and
  `pyproject.toml` `version`) to the chosen version.
- [ ] **Step 3 — Verify version identity**

```bash
test "$(make -s version)" = "<chosen-version>"
```

- [ ] **Step 4 — Run all required gates**

```bash
python3 -m unittest engine.tests.test_git_ff_only_merge_behavior engine.tests.test_guard engine.tests.test_guard_hook_wrappers
bash engine/tests/run-tests.sh
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
make verify
make verify-install
git diff --check origin/main...HEAD
```

Expected: all commands exit `0`; behavior proof stays offline; contract schema remains v1.

- [ ] **Step 5 — Run defect review until clean.** Run Bugbot over the complete branch; fix every valid
  finding; rerun focused + full verification; repeat until Bugbot reports no defects.
- [ ] **Step 6 — Commit**

```bash
git add engine/__init__.py pyproject.toml
git commit -m "release: prepare AWA <chosen-version>"
```

**Definition of done:** Both version sources report the chosen version, all gates pass, and the branch
has a clean Bugbot review.

### Task 5: Ship, release, promote, and reconcile

**Files:**
- No additional AWA source files unless review finds a defect.
- Modify in a separate governed `KleinPerkins/skills` Safe Workspace (only on release GO):
  `global/tools/awa/meta.yml`, `global/tools/awa/tool.yml`, `global/tools/awa/README.md`,
  `.eco-registry.lock`.

**Interfaces:**
- Consumes: the verified AWA branch and normal AWA/skills PR automation.
- Produces: merged source, an optional approved release, a promoted skills binding, a repaired host
  install, and clean local/remote branch state.

- [ ] **Step 1 — Push and open the implementation PR** (`git push -u origin HEAD`; `gh pr create`
  with a Summary + Test plan body). Keep the ADR/plan-only PR (this document) separate from the
  implementation PR.
- [ ] **Step 2 — Let governed automation merge.** Wait for `pr-automation / verify` and reviewer-App
  approval. NEVER call `gh pr merge --auto`, enable/disable native auto-merge, or bypass the
  reviewer-App gate — in this repo only the reviewer App arms native auto-merge.
- [ ] **Step 3 — Verify the exact merged revision from the Safe Workspace** (`gh pr view --json
  mergeCommit`; assert it is an ancestor of `origin/main` and carries the chosen version). No primary
  checkout is mutated from the linked worktree.
- [ ] **Step 4 — Obtain release/promotion GO.** Before tagging, publishing a GitHub release, changing
  the skills binding, or repairing the live host install, obtain explicit operator approval.
- [ ] **Step 5 — On GO, tag and publish the exact merge** (`git tag <v>`; `git push origin <v>`;
  `gh release create <v> --verify-tag --generate-notes`). Review notes as cumulative from the latest
  published release.
- [ ] **Step 6 — Promote through the governed capability lifecycle.** In a fresh `KleinPerkins/skills`
  Safe Workspace (`dev-worktree.sh ensure` + move to root), bind `global/tools/awa` to the immutable
  release commit, refresh the human-readable version/commit references, run `eco-lock.sh write/check`
  and `verify-skills.sh`, and open a governed PR; wait for the skills reviewer automation to merge.
- [ ] **Step 7 — Reconcile protected primaries and live-check the host.** Fast-forwarding the
  protected AWA and skills primaries to the merged `origin/main` is now itself an ALLOWED carve-out —
  once this plan ships, `git merge --ff-only origin/main` no longer requires
  `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1`. For each primary: confirm clean + on `main`, fetch from a Safe
  Workspace (fetch stays denied on the primary), then `git merge --ff-only origin/main` on the
  primary; then repair the host overlay and run `dev-worktree.sh doctor`. Use diagnostic-only guard
  checks to confirm one allow (`git merge --ff-only origin/main`) and the deny near-misses on a
  protected primary. (This step is the plan's own dogfood of ADR 0011.)
- [ ] **Step 8 — Clean the merged branch.** Delete the merged remote feature branch(es) through the
  normal governed cleanup path; leave the Safe Workspace and primary clean.

**Definition of done:** Source is merged, publication occurs only after explicit GO, the downstream
binding and host install point at the verified release, the protected primaries are fast-forwarded via
the new carve-out, and no orphan branch/worktree state remains.

## 6. Acceptance criteria

- `git merge --ff-only` runtime safety (fast-forward / no-op / abort / refuse-to-clobber / post-merge
  hook) is reproducibly proven offline with the host git version recorded.
- On a protected primary, exactly the ADR 0011 grammar allows; every enumerated near-miss denies;
  linked-worktree behavior is unchanged.
- `classify_mutating`/`_git_is_mutating` still report every fast-forward-merge form as mutating; the
  allowance exists only in `decide_shell`/`check_probe`.
- fetch/push/pull remain denied on protected primaries (ADR 0010 intact).
- Engine, live hook, shared corpus, and contract UAT agree; no new dependency enters the hook path;
  hook-internal failure still degrades to allow; the frozen contract schema is unchanged.
- AWA reports the chosen version from both version sources and all verification gates pass.
- ADR 0011 and this plan remain byte-identical once accepted; sibling accepted ADRs/plans are
  untouched, their status reconciled in the index rows only.

## 7. Rollback

- Before merge: revert the relevant local commit or push a correcting commit; never amend pushed
  commits.
- After merge: use a normal `git revert` PR. Never rewrite `main`.
- After release publication: never move or delete the tag; publish a corrective patch version.
- If downstream install smoke fails: revert the `KleinPerkins/skills` descriptor through its governed
  PR path and reinstall the previous release.
- ADR 0011 and this plan become byte-identical once accepted; any material policy reversal (removing
  the carve-out, widening the grammar, adding a runtime pre-check, or any remote allowance) uses a
  higher-numbered ADR and a `-v2` successor plan.
