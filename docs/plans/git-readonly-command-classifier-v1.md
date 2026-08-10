# Git Read-Only Command Classifier Implementation Plan

- **Version:** v1
- **Status:** DRAFT
- **Date:** 2026-08-10
- **Relates to:** `guard-target-path-precision-v1.md`; `docs/adr/0001-target-path-aware-mutation-scope.md`; observed false positive for `git worktree list --porcelain` in `/Users/laurence.duggan/dev/personal/pr-automation-controller`.
- **Review provenance:** Drafted from a read-only AWA guard investigation and fresh source inspection of `engine/guard.py`, `kernel/hooks/worktree-guard.sh`, `kernel/bin/dev-worktree.sh`, `engine/tests/test_guard.py`, `engine/tests/test_guard_hook_wrappers.py`, and the `~/dev` host overlay delegators on 2026-08-10. Hardened the same day with a `plan-refine` swarm focused on classifier grammar, guard parity, test evidence, and rollout safety.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct AWA's shell guard so confirmed read-only Git subcommands inside otherwise mutating command families are allowed on protected primary checkouts, while mutating forms remain denied.

**Architecture:** Keep AWA's kernel-first mirror design: the Python engine classifier and the embedded Python classifier in the Cursor hook get the same subcommand-aware Git helper logic, with hook parity tests proving both paths stay aligned. The first implementation covers local read-only false positives that are deterministic and non-networking; network dry-run and under-classified mutating families are explicitly deferred to separate hardening.

**Tech Stack:** Python stdlib, Bash, Git CLI, `unittest`, AWA kernel hook contract tests, `make verify`.

## Global Constraints

- Work in a Safe Workspace created by AWA before editing source or docs.
- Do not disable AWA protection, change host modes, bypass the Cursor hook, or weaken deny behavior for mutating commands.
- Preserve kernel-first behavior: `kernel/hooks/worktree-guard.sh` must not import `engine.guard`.
- Keep `engine/guard.py` and `kernel/hooks/worktree-guard.sh` classifier behavior in parity.
- Treat unknown Git subcommands, unknown nested actions, ambiguous flags, interactive commands, and parse failures conservatively.
- Distinguish command parse failures from hook-internal failures: `classify_mutating()` keeps unparseable command strings conservative, while `kernel/hooks/worktree-guard.sh` retains its existing fail-open-on-hook-internal-failure policy to avoid bricking Cursor.
- Do not classify network dry-run commands as read-only in this plan; they need a separate behavior proof and policy decision.
- Do not address under-classified mutating families (`branch`, `remote`, `config`, `submodule`, `sparse-checkout`) in this patch; track them separately.

---

## Finding

`git worktree list --porcelain` is read-only, but AWA blocks it on included primary checkouts because `git worktree` is treated as a flat mutating family. The observed product repo, `/Users/laurence.duggan/dev/personal/pr-automation-controller`, has no `_ops/bin/dev-worktree.sh`, so fallback inspection commands hit the global Cursor shell guard directly.

The same defect affects other deterministic local read-only forms currently inside `_GITMUT`:

- `git worktree list`
- `git worktree list --porcelain`
- `git worktree list --porcelain -z`
- `git stash list`
- `git stash show`
- `git stash show --stat`
- `git clean -n`
- `git clean --dry-run`

## Root Cause

`engine/guard.py::_GITMUT` includes `worktree`, `stash`, and `clean`. `engine/guard.py::_segment_is_mutating` skips Git global options and then returns `sub in _GITMUT`; it does not inspect nested actions such as `worktree list` or `stash show`, and it does not recognize `clean --dry-run`.

`kernel/hooks/worktree-guard.sh` duplicates the same logic inside its embedded Python block. That hook is the live Cursor enforcement path; the engine path powers diagnostics and unit coverage.

The host overlay is not the cause. `/Users/laurence.duggan/dev/_ops/cursor-hooks/worktree-guard.sh` delegates to the installed AWA runtime with `AWA_POLICY` and `AWA_GOVERNED_ROOT`. `/Users/laurence.duggan/dev/_ops/policy/worktree-policy.yml` correctly includes `personal/*` and `capabilities/*`. `/Users/laurence.duggan/dev/_ops/policy/worktree-modes.yml` has `default_mode: on`.

## Scope

In scope for this plan:

- Add a second-level Git command classifier for already-recognized mutating families.
- Allow only deterministic, local read-only forms with a closed grammar: `worktree list`, `stash list`, `stash show`, and `clean` dry-run.
- Keep mutating forms denied: `worktree add/remove/move/prune/repair/lock/unlock`, `stash push/save/apply/pop/drop/clear/branch/store/create`, and `clean` without dry-run.
- Add unit and hook parity tests that fail before the fix and pass after it.
- Verify the repo helper fallback path by preserving `kernel/bin/dev-worktree.sh::list_worktrees`, which runs `git worktree list --porcelain`.

Out of scope for this plan:

- `git fetch --dry-run` and `git push --dry-run`. They likely do not mutate local worktree content, but they perform network operations and may have authentication, remote, or hook-adjacent policy implications. Handle them in a follow-up after explicit behavior proof.
- False negatives where AWA currently allows mutating forms because the first-level subcommand is absent from `_GITMUT`, including `git branch -d`, `git remote add`, `git config user.name x`, `git submodule update --init`, and `git sparse-checkout set`. That is a safety-hardening pass, not a false-positive block fix.
- Reclassifying `git status`. It can refresh index metadata, but AWA already treats it as allowed; changing that is a policy decision outside this correction.

## File Structure

- Modify: `engine/guard.py`
  - Add Git subcommand parsing helpers next to `_GITMUT`.
  - Replace `return sub in _GITMUT` with `return _git_is_mutating(rest)`.
  - Keep `_collect_precise_targets()` behavior unchanged except that it naturally runs only for commands still classified mutating.

- Modify: `kernel/hooks/worktree-guard.sh`
  - Mirror the helper definitions inside the embedded Python block.
  - Replace the embedded `return sub in GITMUT` logic with the same `_git_is_mutating(rest)` behavior.
  - Preserve Bash hook response shape and all `check_probe` logic.

- Modify: `engine/tests/test_guard.py`
  - Add classifier-level read-only and still-mutating Git family tests.
  - Add `decide_shell()` tests proving included primaries allow read-only forms and deny mutating forms.

- Create: `engine/tests/git_guard_command_corpus.py`
  - Hold the shared allow/deny command tuples used by both engine and hook tests.

- Modify: `engine/tests/test_guard_hook_wrappers.py`
  - Add live hook subprocess parity tests for the same allow/deny split.

- Modify: `kernel/checks/awa-contract-freeze.sh`
  - Extend the frozen guard contract/UAT matrix so `git worktree list --porcelain` allows and `git worktree add` denies.

- Modify: `docs/plans/README.md`
  - Add this plan to the index.

## Interfaces

The implementation should introduce these engine-level helpers and mirror them in the hook's embedded Python:

```python
_GIT_WORKTREE_READONLY_ACTIONS = {"list"}
_GIT_STASH_READONLY_ACTIONS = {"list", "show"}

def _git_subcommand(rest: list[str]) -> tuple[str, list[str]]:
    """Return the first non-option git subcommand and the remaining args after it."""

def _git_exact_nested_action(args: list[str]) -> tuple[str, list[str]]:
    """Return the nested action only when it is the first token after the Git family."""

def _git_worktree_list_is_readonly(args: list[str]) -> bool:
    """True only for the closed `git worktree list` grammar."""

def _git_stash_list_is_readonly(args: list[str]) -> bool:
    """True only for the closed `git stash list` grammar."""

def _git_stash_show_is_readonly(args: list[str]) -> bool:
    """True only for the closed `git stash show` grammar."""

def _git_clean_is_readonly(args: list[str]) -> bool:
    """True for parsed dry-run clean forms that cannot remove files."""

def _git_is_mutating(rest: list[str]) -> bool:
    """Return whether a git invocation mutates protected local repo state."""
```

`_segment_is_mutating()` should keep its existing wrapper, interpreter, redirect, package-manager, and mutating-program behavior. Only the `prog == "git"` branch changes:

```python
    if prog == "git":
        return _git_is_mutating(rest)
```

The tests should use one canonical command corpus so classifier, decision, hook, and contract coverage do not drift. Create `engine/tests/git_guard_command_corpus.py` with:

```python
GIT_READONLY_FAMILY_COMMANDS = (
    "git worktree list",
    "git worktree list --porcelain",
    "git worktree list --porcelain -z",
    "git -C /tmp/repo worktree list --porcelain",
    "git stash list",
    "git stash show",
    "git stash show --stat",
    "git stash show stash@{0}",
    "git stash show --stat stash@{0}",
    "git clean -n",
    "git clean -n -d",
    "git clean --dry-run",
    "git clean --dry-run -d -x",
    "git clean --dry-run -- generated.log",
    "git clean -ndx -- generated.log",
)

GIT_MUTATING_FAMILY_COMMANDS = (
    "git worktree add ../repo-wt",
    "git worktree remove ../repo-wt",
    "git worktree move ../repo-wt ../repo-wt2",
    "git worktree prune",
    "git worktree repair",
    "git worktree lock ../repo-wt",
    "git worktree unlock ../repo-wt",
    "git worktree",
    "git worktree -- list",
    "git worktree list --unknown",
    "git stash",
    "git stash -- list",
    "git stash push",
    "git stash save",
    "git stash apply",
    "git stash pop",
    "git stash drop",
    "git stash clear",
    "git stash branch tmp",
    "git stash store abc123",
    "git stash create",
    "git clean -f",
    "git clean -fdx",
    "git clean",
    "git clean -i",
    "git clean -f -- -n",
    "git clean -f -- --dry-run",
    "git clean -- -n",
    "git clean -n -f",
    "git status && git worktree add ../repo-wt",
    "git worktree list --porcelain && git stash pop",
)
```

## Task 1: Engine Classifier Regression Tests

**Files:**
- Create: `engine/tests/git_guard_command_corpus.py`
- Modify: `engine/tests/test_guard.py`

**Interfaces:**
- Consumes: `engine.guard.classify_mutating(command: str) -> bool`
- Produces: failing tests that define the new Git read-only classification contract.

- [ ] **Step 1: Add the canonical corpus and read-only classifier test cases**

Create `engine/tests/git_guard_command_corpus.py` using the exact tuples from the Interfaces section. Import them in `engine/tests/test_guard.py`:

```python
from engine.tests.git_guard_command_corpus import (
    GIT_MUTATING_FAMILY_COMMANDS,
    GIT_READONLY_FAMILY_COMMANDS,
)
```

Then add this method to `TestMutatingClassifier`:

```python
    def test_git_readonly_forms_inside_mutating_families_allowed(self):
        for cmd in GIT_READONLY_FAMILY_COMMANDS:
            self.assertFalse(guard.classify_mutating(cmd), cmd)
```

- [ ] **Step 2: Add still-mutating classifier test cases**

Add this method to `TestMutatingClassifier`:

```python
    def test_git_mutating_forms_inside_mutating_families_still_mutating(self):
        for cmd in GIT_MUTATING_FAMILY_COMMANDS:
            self.assertTrue(guard.classify_mutating(cmd), cmd)
```

- [ ] **Step 3: Run the focused failing tests**

Run:

```bash
python3 -m unittest \
  engine.tests.test_guard.TestMutatingClassifier.test_git_readonly_forms_inside_mutating_families_allowed \
  engine.tests.test_guard.TestMutatingClassifier.test_git_mutating_forms_inside_mutating_families_still_mutating
```

Expected before implementation:

```text
FAILED
```

At least `git worktree list`, `git stash list`, `git stash show --stat`, and `git clean -n` should fail because they currently classify mutating.

- [ ] **Step 4: Commit after this task if executing with commits**

Only if the operator requested commits:

```bash
git add engine/tests/test_guard.py
git commit -m "$(cat <<'EOF'
test(guard): cover read-only git subcommands

EOF
)"
```

## Task 2: Engine Git Subcommand Classifier

**Files:**
- Modify: `engine/guard.py`

**Interfaces:**
- Consumes: `rest: list[str]` from the `prog == "git"` branch of `_segment_is_mutating()`.
- Produces: `_git_is_mutating(rest: list[str]) -> bool`.

- [ ] **Step 1: Add helper constants and functions after `_GIT_TAKES_ARG`**

Add this code:

```python
_GIT_WORKTREE_READONLY_ACTIONS = {"list"}
_GIT_STASH_READONLY_ACTIONS = {"list", "show"}
_GIT_WORKTREE_LIST_FLAGS = {"--porcelain", "-z", "--verbose", "-v"}
_GIT_STASH_LIST_FLAGS: set[str] = set()
_GIT_STASH_SHOW_FLAGS = {"--stat", "--patch", "-p"}
_GIT_CLEAN_DRY_RUN_FLAGS = {"-n", "--dry-run"}
_GIT_CLEAN_READONLY_FLAGS = {"-n", "--dry-run", "-d", "-x", "-X", "-q"}
_GIT_CLEAN_MUTATING_FLAGS = {"-f", "--force", "-i", "--interactive"}


def _git_subcommand(rest: list[str]) -> tuple[str, list[str]]:
    j = 0
    while j < len(rest):
        a = rest[j]
        if a in _GIT_TAKES_ARG:
            j += 2
            continue
        if a.startswith(("--git-dir=", "--work-tree=", "--namespace=",
                         "--exec-path=", "--super-prefix=")) or (a.startswith("-c") and len(a) > 2):
            j += 1
            continue
        if a.startswith("-"):
            j += 1
            continue
        break
    sub = rest[j] if j < len(rest) else ""
    return sub, rest[j + 1:] if j < len(rest) else []


def _git_exact_nested_action(args: list[str]) -> tuple[str, list[str]]:
    if not args or args[0].startswith("-"):
        return "", args
    return args[0], args[1:]


def _git_flag_name(arg: str) -> str:
    return arg.split("=", 1)[0]


def _git_args_are_known_readonly_flags(args: list[str], allowed: set[str]) -> bool:
    return all(arg in allowed for arg in args)


def _git_worktree_list_is_readonly(args: list[str]) -> bool:
    return _git_args_are_known_readonly_flags(args, _GIT_WORKTREE_LIST_FLAGS)


def _git_stash_list_is_readonly(args: list[str]) -> bool:
    return args == []


def _git_stash_show_is_readonly(args: list[str]) -> bool:
    seen_ref = False
    for arg in args:
        if arg in _GIT_STASH_SHOW_FLAGS:
            continue
        if arg == "--":
            return False
        if arg.startswith("-"):
            return False
        if seen_ref:
            return False
        seen_ref = True
    return True


def _git_clean_is_readonly(args: list[str]) -> bool:
    has_dry_run = False
    parsing_options = True
    for a in args:
        if parsing_options and a == "--":
            parsing_options = False
            continue
        if not parsing_options:
            continue
        if a in _GIT_CLEAN_DRY_RUN_FLAGS:
            has_dry_run = True
            continue
        if a in _GIT_CLEAN_MUTATING_FLAGS:
            return False
        if len(a) > 2 and a.startswith("-") and not a.startswith("--"):
            chars = set(a[1:])
            if "n" in chars:
                has_dry_run = True
            if "f" in chars or "i" in chars:
                return False
            if not chars.issubset(set("ndxXq")):
                return False
            continue
        if _git_flag_name(a) not in _GIT_CLEAN_READONLY_FLAGS:
            return False
    return has_dry_run


def _git_is_mutating(rest: list[str]) -> bool:
    sub, sub_args = _git_subcommand(rest)
    if not sub:
        return False
    if sub not in _GITMUT:
        return False
    if sub == "worktree":
        action, action_args = _git_exact_nested_action(sub_args)
        if action in _GIT_WORKTREE_READONLY_ACTIONS:
            return not _git_worktree_list_is_readonly(action_args)
        return True
    if sub == "stash":
        action, action_args = _git_exact_nested_action(sub_args)
        if action == "list":
            return not _git_stash_list_is_readonly(action_args)
        if action == "show":
            return not _git_stash_show_is_readonly(action_args)
        return True
    if sub == "clean":
        return not _git_clean_is_readonly(sub_args)
    return True
```

- [ ] **Step 2: Replace the flat Git mutating check**

Replace the `prog == "git"` block inside `_segment_is_mutating()` with:

```python
    if prog == "git":
        return _git_is_mutating(rest)
```

- [ ] **Step 3: Run classifier tests**

Run:

```bash
python3 -m unittest engine.tests.test_guard.TestMutatingClassifier
```

Expected after implementation:

```text
OK
```

- [ ] **Step 4: Run degraded decision tests**

Run:

```bash
python3 -m unittest engine.tests.test_guard.TestDecideShellDegraded
```

Expected:

```text
OK
```

- [ ] **Step 5: Commit after this task if executing with commits**

Only if the operator requested commits:

```bash
git add engine/guard.py engine/tests/test_guard.py
git commit -m "$(cat <<'EOF'
fix(guard): classify read-only git subcommands precisely

EOF
)"
```

## Task 3: Engine Decision Tests For Included Primaries

**Files:**
- Modify: `engine/tests/test_guard.py`

**Interfaces:**
- Consumes: `guard.decide_shell(cwd: str, command: str, policy_path: str) -> Decision`
- Produces: decision-level proof that included primaries allow read-only Git family forms and still deny mutating forms.

- [ ] **Step 1: Add allow test in `TestDecideShellDegraded`**

Add this method:

```python
    def test_primary_allows_readonly_git_family_forms(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        for cmd in GIT_READONLY_FAMILY_COMMANDS:
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "allow", cmd)
            self.assertEqual(d.classification, "include", cmd)
```

- [ ] **Step 2: Add deny test in `TestDecideShellDegraded`**

Add this method:

```python
    def test_primary_still_denies_mutating_git_family_forms(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        for cmd in GIT_MUTATING_FAMILY_COMMANDS:
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "deny", cmd)
            self.assertEqual(d.classification, "include", cmd)
```

- [ ] **Step 3: Run decision tests**

Run:

```bash
python3 -m unittest engine.tests.test_guard.TestDecideShellDegraded
```

Expected:

```text
OK
```

- [ ] **Step 4: Commit after this task if executing with commits**

Only if the operator requested commits:

```bash
git add engine/tests/test_guard.py
git commit -m "$(cat <<'EOF'
test(guard): prove primary allows read-only git families

EOF
)"
```

## Task 4: Hook Mirror And Parity Tests

**Files:**
- Modify: `kernel/hooks/worktree-guard.sh`
- Modify: `engine/tests/test_guard_hook_wrappers.py`

**Interfaces:**
- Consumes: the same helper behavior introduced in `engine/guard.py`.
- Produces: live hook subprocess parity for read-only allow and mutating deny.

- [ ] **Step 1: Mirror the helper code inside the hook's embedded Python**

In `kernel/hooks/worktree-guard.sh`, inside the `HOOK_INPUT="$input" python3 - <<'PY'` block, add the same helper constants and functions from Task 2 after the local `takes_arg`/Git classifier constants. Keep comments apostrophe-free inside this heredoc because the existing file documents macOS Bash heredoc parser constraints.

- [ ] **Step 2: Replace the embedded flat Git mutating check**

Replace this embedded hook logic:

```python
        sub = rest[j] if j < len(rest) else ""
        GITMUT = {"commit", "add", "reset", "rebase", "checkout", "switch", "clean",
                  "merge", "cherry-pick", "apply", "restore", "stash", "rm", "mv",
                  "pull", "am", "revert", "worktree", "push", "fetch"}
        return sub in GITMUT
```

with:

```python
        return _git_is_mutating(rest)
```

- [ ] **Step 3: Add hook allow parity test**

Import the shared corpus in `engine/tests/test_guard_hook_wrappers.py`:

```python
from engine.tests.git_guard_command_corpus import (
    GIT_MUTATING_FAMILY_COMMANDS,
    GIT_READONLY_FAMILY_COMMANDS,
)
```

Then add this method to `TestBashGuardWrapperParity`:

```python
    def test_hook_allows_readonly_git_family_forms(self):
        for cmd in GIT_READONLY_FAMILY_COMMANDS:
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "allow", cmd)
```

- [ ] **Step 4: Add hook deny parity test**

Add this method to `TestBashGuardWrapperParity`:

```python
    def test_hook_still_denies_mutating_git_family_forms(self):
        for cmd in GIT_MUTATING_FAMILY_COMMANDS:
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "deny", cmd)
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)
```

- [ ] **Step 5: Run hook tests**

Run:

```bash
python3 -m unittest engine.tests.test_guard_hook_wrappers
```

Expected:

```text
OK
```

- [ ] **Step 6: Commit after this task if executing with commits**

Only if the operator requested commits:

```bash
git add kernel/hooks/worktree-guard.sh engine/tests/test_guard_hook_wrappers.py engine/tests/git_guard_command_corpus.py
git commit -m "$(cat <<'EOF'
fix(kernel): mirror read-only git classifier in guard hook

EOF
)"
```

## Task 5: Contract Freeze Coverage

**Files:**
- Modify: `kernel/checks/awa-contract-freeze.sh`

**Interfaces:**
- Consumes: the installed-source hook under `kernel/hooks/worktree-guard.sh`.
- Produces: contract-level proof that the Cursor-facing permission shape remains stable.

- [ ] **Step 1: Locate the existing guard UAT matrix**

Open `kernel/checks/awa-contract-freeze.sh` and find the section that invokes `kernel/hooks/worktree-guard.sh` with before-shell payloads. Keep the existing deny-shape assertions unchanged.

- [ ] **Step 2: Add read-only family allow assertions**

Add guard UAT cases equivalent to:

```bash
assert_guard_permission "git worktree list --porcelain" "allow"
assert_guard_permission "git stash list" "allow"
assert_guard_permission "git stash show --stat" "allow"
assert_guard_permission "git clean --dry-run -d -x" "allow"
```

If the file uses a different helper name, use the existing helper and keep these command strings exact.

- [ ] **Step 3: Add still-denied family mutation assertions**

Add guard UAT cases equivalent to:

```bash
assert_guard_permission "git worktree add ../awa-contract-wt" "deny"
assert_guard_permission "git stash pop" "deny"
assert_guard_permission "git clean -fdx" "deny"
assert_guard_permission "git clean -f -- -n" "deny"
```

Use the file's existing temporary repo/workspace setup; do not create a real persistent worktree for this assertion.

- [ ] **Step 4: Run contract freeze check**

Run:

```bash
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
```

Expected:

```text
contract-freeze: OK
```

- [ ] **Step 5: Commit after this task if executing with commits**

Only if the operator requested commits:

```bash
git add kernel/checks/awa-contract-freeze.sh
git commit -m "$(cat <<'EOF'
test(kernel): freeze worktree list guard behavior

EOF
)"
```

## Task 6: Verification And Release Prep

**Files:**
- Modify only if release is part of the approved implementation: `engine/__init__.py`, `pyproject.toml`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: green local verification and an operator-ready release note.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python3 -m unittest engine.tests.test_guard engine.tests.test_guard_hook_wrappers
```

Expected:

```text
OK
```

- [ ] **Step 2: Run engine suite**

Run:

```bash
bash engine/tests/run-tests.sh
```

Expected:

```text
OK
```

- [ ] **Step 3: Run full verification**

Run:

```bash
make verify
```

Expected:

```text
verify: OK
```

- [ ] **Step 4: Run install lifecycle verification**

Run:

```bash
make verify-install
```

Expected:

```text
verify-install: OK
```

- [ ] **Step 5: Record the separate false-negative hardening follow-up**

Before opening the PR, create or update a follow-up tracker for the known under-classified mutating families. Use this title and scope:

```text
Title: Harden AWA Git classifier for mutating branch/remote/config/submodule/sparse-checkout forms
Scope: classify mutating forms in currently-untracked Git families without introducing broad false positives for read-only forms such as `git branch --show-current`, `git remote -v`, `git config --get`, `git submodule status`, and `git sparse-checkout list`.
```

Do not implement that hardening in this branch.

- [ ] **Step 6: Prepare version bump only after implementation is approved**

If the operator explicitly approves release prep from this implementation branch, bump both version strings from the current value to the next patch version:

```python
# engine/__init__.py
__version__ = "1.5.1"
```

```toml
# pyproject.toml
version = "1.5.1"
```

- [ ] **Step 7: Commit after this task if executing with commits**

Only if the operator requested commits:

```bash
git add engine/__init__.py pyproject.toml
git commit -m "$(cat <<'EOF'
chore(release): bump awa to 1.5.1

EOF
)"
```

## Task 7: Rollout

**Files:**
- No implementation files beyond prior tasks.

**Interfaces:**
- Consumes: green verification and an approved implementation branch.
- Produces: released AWA runtime and host overlay propagation.

- [ ] **Step 1: Open the PR**

Run:

```bash
gh pr create --title "fix: allow read-only git family commands in AWA guard" --body "$(cat <<'EOF'
## Summary
- Allow deterministic read-only Git forms inside mutating families: worktree list, stash list/show, and clean dry-run.
- Keep mutating worktree, stash, and clean forms denied on included primary checkouts.
- Add engine, live hook, and contract-freeze regression coverage.

## Test plan
- python3 -m unittest engine.tests.test_guard engine.tests.test_guard_hook_wrappers
- bash engine/tests/run-tests.sh
- make verify
- make verify-install

EOF
)"
```

- [ ] **Step 2: Let repo automation handle merge**

Wait for `pr-automation / verify` and reviewer-App approval. Do not run `gh pr merge --auto`, do not enable or disable native auto-merge, and do not bypass the repository automation.

- [ ] **Step 3: Stop unless release and promotion are explicitly approved**

Before tagging, creating a GitHub release, updating `KleinPerkins/skills`, or repairing the local host install, obtain an explicit operator approval for those publication steps. If approval is not present, stop after the merged PR and report that source is merged but not released/promoted.

- [ ] **Step 4: Release after merge using a worktree-safe ref flow**

After the PR is merged to `main`, do not run `git checkout main` from a linked Safe Workspace. Fetch the remote branch, verify the exact merged commit, and tag that object directly:

```bash
git fetch origin main
release_sha="$(git rev-parse origin/main)"
git tag v1.5.1 "$release_sha"
gh release create v1.5.1 --title "AWA v1.5.1" --notes "Allow deterministic read-only Git family commands in the AWA shell guard while preserving denials for mutating forms."
```

- [ ] **Step 5: Update downstream binding through the governed lifecycle**

Record the previous `tools/awa` binding before changing it. Update the global `tools/awa` binding in `KleinPerkins/skills` to point at the new AWA release using the existing capability lifecycle, open the governed PR there, and wait for its normal merge path. Do not hand-vendor AWA into downstream repos.

- [ ] **Step 6: Repair host overlay install with rollback note**

After the skills binding is merged, run the existing overlay repair path so `~/.local/share/awa/current` points at the new release:

```bash
bash /Users/laurence.duggan/dev/_ops/bin/install-dev-awa-overlay.sh
```

If smoke checks fail after repair, revert the skills binding to the recorded prior pin through the same governed lifecycle, rerun the overlay repair, and report the failure with the pre/post release pins.

- [ ] **Step 7: Live-verify original false positive through diagnostics**

Use the AWA diagnostic tool or CLI path, not a blind retry loop, to confirm:

```text
cwd: /Users/laurence.duggan/dev/personal/pr-automation-controller
command: git worktree list --porcelain
expected permission: allow
```

Also confirm:

```text
cwd: /Users/laurence.duggan/dev/personal/pr-automation-controller
command: git worktree add ../awa-should-still-deny
expected permission: deny
```

- [ ] **Step 8: Live-verify host delegators**

Confirm both host delegators are using the new runtime and policy:

```text
/Users/laurence.duggan/dev/_ops/cursor-hooks/worktree-guard.sh:
  expected: delegates to installed AWA guard with AWA_POLICY and AWA_GOVERNED_ROOT set.

/Users/laurence.duggan/dev/_ops/bin/dev-worktree.sh status:
  expected: prints the current repo classification and does not report a missing install.

/Users/laurence.duggan/dev/_ops/bin/dev-worktree.sh list:
  expected: succeeds in a Git repo and emits `git worktree list --porcelain` output rather than being blocked.
```

## Non-Goals

- Do not broadly allow `git worktree`.
- Do not broadly allow `git stash`.
- Do not broadly allow `git clean`.
- Do not classify `git fetch --dry-run` or `git push --dry-run` as read-only in this plan.
- Do not add `branch`, `remote`, `config`, `submodule`, or `sparse-checkout` to `_GITMUT` in this plan.
- Do not change `~/dev/_ops/policy/worktree-policy.yml` or `~/dev/_ops/policy/worktree-modes.yml`.
- Do not change Cursor hook wiring or disable global hook protection.

## Risks And Open Questions

- `git clean -n -f` likely remains dry-run in Git, but this plan deliberately denies it because combining force and dry-run is unnecessary for the observed workflow and raises avoidable ambiguity.
- `git fetch --dry-run` and `git push --dry-run` are likely false positives, but they are network operations. Decide in a separate plan whether AWA's shell guard should treat network-only dry-runs as read-only.
- The current false-negative families should become a separate safety-hardening issue. Recommended issue title: `Harden AWA Git classifier for mutating branch/remote/config/submodule/sparse-checkout forms`.
- If the hook and engine helper copies drift during implementation, the hook parity tests should fail; do not remove those tests to get green.

## Self-Review

- Spec coverage: the plan covers the observed `git worktree list --porcelain` block, the AWA engine path, the live Cursor hook path, the host overlay boundary, similar deterministic local read-only blocks, non-goals, tests, and rollout.
- Placeholder scan: no placeholder steps remain; every code-changing task includes concrete code or exact command assertions.
- Type consistency: helper names and signatures are consistent across the engine, hook, and test tasks.
