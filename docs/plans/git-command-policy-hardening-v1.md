# Git Command Policy Hardening — Complete Family Classification and Remote Dry-Run Proof

**Version:** v1
**Status:** DRAFT — 2026-08-11
**Date:** 2026-08-11
**Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
**Plan-type:** agentic-execution
**Relates to:** `git-readonly-command-classifier-v1.md`, PR #95, ADR 0001, ADR 0010
**Review provenance:** Initial draft from the operator-approved remote-policy decision, fresh
inspection of AWA `main` at `5be9e68`, Git 2.50.1 documentation, upstream Git source behavior,
and the `writing-plans` workflow. A `plan-refine` swarm is required before acceptance.

**Goal:** Give every invocation in the `branch`, `remote`, `config`, `submodule`, and
`sparse-checkout` families a deliberate outcome: exact proven read-only grammar allows; every
write, network-dependent form, unknown flag/action, malformed form, or ambiguous combination
denies. Preserve denial of all `fetch` and `push` forms on protected primaries.

**Architecture:** Extend the Git-specific parser and per-family predicates in `engine/guard.py`,
then mirror the same pure logic inside the kernel hook's embedded Python. A separate offline
behavior-proof test demonstrates why remote dry-runs are not read-only, while ADR 0010 records the
durable policy. Existing outer classification remains authoritative, so linked worktrees and
standalone scratch repositories continue to allow these commands without weakening primary
protection.

**Tech stack:** Python stdlib, Bash, Git 2.50.1 behavior baseline, upstream Git documentation,
`unittest`, AWA contract-freeze UAT, and runnerless PR automation.

> **For agentic workers:** REQUIRED SUB-SKILL — use `subagent-driven-development` or
> `executing-plans` to implement this plan task-by-task. Each work item's steps use checkbox
> (`- [ ]`) syntax for progress tracking.

---

## Global Constraints

- Execute only in an AWA Safe Workspace; never edit the primary checkout.
- Preserve kernel-first operation: `kernel/hooks/worktree-guard.sh` must not import
  `engine.guard` or depend on the daemon.
- Preserve the hook's fail-open-on-internal-failure behavior; command parse uncertainty remains
  fail-safe/mutating.
- Do not change host modes, host policy, Cursor hook wiring, or the frozen permission JSON schema.
- Unknown nested actions, unknown flags, missing option values, aliases, interactive actions, and
  contradictory combinations deny.
- `fetch` and `push` receive no read-only exception, including `--dry-run`, push `-n`,
  `--no-verify`, and recursive forms.
- `git fetch -n` means `--no-tags`, not dry-run, and remains denied.
- Remote dry-run commands may be used only after the outer guard establishes a linked Safe
  Workspace or standalone scratch repository.
- Keep `docs/plans/git-readonly-command-classifier-v1.md` byte-identical; reconcile its completed
  state in the mutable index only.
- Keep the engine and hook mirrors behaviorally identical through shared-corpus and live-hook tests.
- Use no third-party Python dependency.

## 1. Purpose

PR #95 fixed false-positive denials for a narrow set of local Git queries, but deliberately deferred
two connected safety gaps. First, `fetch/push --dry-run` were not behavior-proven. Second,
`branch`, `remote`, `config`, `submodule`, and `sparse-checkout` were absent from `_GITMUT`, so
their mutating forms silently allowed on protected primaries. This plan closes both gaps with an
evidence-backed remote policy and closed, deny-by-default family grammars.

## 2. Scope and non-goals

In scope:

- Prove remote dry-run side effects in an offline, isolated Git fixture.
- Record the durable protected-primary policy in ADR 0010.
- Add complete policy coverage for the five deferred Git families.
- Treat exact proven local query forms as read-only and the remainder as mutating.
- Prevent `git -C <safe>` from laundering unscoped remote/helper/config mutations.
- Keep engine, decision, live hook, and contract-freeze behavior in parity.
- Synchronize AWA's product version from `1.5.0` to `1.5.1`.
- Ship through the governed PR/release/promotion path.

Non-goals:

- No remote/network sandbox and no claim that Safe Workspace commands are side-effect-free.
- No allowance for fetch/push dry-run on protected primaries.
- No global hardening of arbitrary Git aliases or third-party Git subcommands.
- No reclassification of `git status` or unrelated command families.
- No generated/imported shared classifier module; kernel-first duplication-with-parity remains.
- No host policy/mode changes and no frozen contract v2.
- Rare read-only spellings outside the closed corpus remain deliberately denied until separately
  proven; this is policy, not an unclassified gap.

## 3. Background and context

Verified against `origin/main` at `5be9e68`:

- `engine/guard.py::_GITMUT` includes `fetch` and `push`, but omits `branch`, `remote`, `config`,
  `submodule`, and `sparse-checkout`.
- `_git_is_mutating()` has closed predicates only for `worktree`, `stash`, and `clean`.
- `engine/tests/git_guard_command_corpus.py` is already consumed by classifier, decision, and live
  hook tests, so it is the correct single test corpus to extend.
- `_extract_git_target_dirs()` scans the full Git argument list. Once `branch` becomes mutating,
  nested `branch -C/-c` flags could be mistaken for global Git target options unless parsing is
  split at the exact subcommand boundary.
- AWA's product version is `1.5.0` in both `engine/__init__.py` and `pyproject.toml`; PR #95 did not
  bump either declaration. The latest published release is `v1.2.0`.
- The installed baseline is Apple Git `2.50.1`.

Remote dry-run evidence:

- `git fetch --dry-run` suppresses normal ref/FETCH_HEAD updates but can still transfer objects,
  rewrite shallow state, write partial-clone/bundle configuration, update bundle/remote-HEAD refs,
  and trigger maintenance.
- `git push --dry-run` suppresses stock ref updates but still invokes `pre-push`, transports,
  credential/remote helpers, recursive child pushes, and optional negotiation fetches.
- Therefore neither command provides a deterministic guarantee against overwriting or deleting
  protected state. The operator chose to keep both denied on protected primaries and use a linked
  Safe Workspace or standalone scratch repository instead.

## 4. Approach

The classifier remains a pure boolean policy: `True` means potentially mutating and therefore
eligible for the existing primary-checkout deny path; `False` means the exact parsed command is in
a proven read-only grammar.

The engine and hook will implement:

```python
def _parse_git_invocation(
        rest: list[str],
) -> tuple[list[str], str, list[str]] | None:
    """Return validated global args, exact subcommand, and family args."""


def _git_branch_is_readonly(args: list[str]) -> bool:
    """Accept only closed local branch-listing grammar."""


def _git_remote_is_readonly(args: list[str]) -> bool:
    """Accept only local remote queries; reject network-dependent forms."""


def _git_config_is_readonly(args: list[str]) -> bool:
    """Accept only stable legacy getter grammar with validated option arity."""


def _git_submodule_is_readonly(args: list[str]) -> bool:
    """Accept only explicit, non-recursive status grammar."""


def _git_sparse_checkout_is_readonly(args: list[str]) -> bool:
    """Accept list and validated check-rules grammar."""
```

`_parse_git_invocation()` recognizes only the explicit global-option vocabulary and exact arity
that AWA models. Missing values or unknown global flags return `None`; `_git_is_mutating()` maps
that uncertainty to `True`. Unknown top-level commands remain under the existing behavior unless
they are one of the named policy families.

The five new family names join `_GITMUT`. For each named family, a predicate returns `True` only
for the closed read-only grammar; the family remainder denies. `fetch` and `push` remain
unconditionally mutating.

Target narrowing is disabled for unscoped families:

```python
_GIT_NO_TARGET_NARROWING = {
    "fetch",
    "push",
    "remote",
    "config",
    "submodule",
}
```

Branch and sparse-checkout mutations remain repo-local and may use validated global `-C`,
`--git-dir`, and `--work-tree` targets. Family flags are never parsed as global options.

## 5. Work items

### Task 1: Prove remote dry-run side effects offline

**Files:**
- Create: `engine/tests/test_git_remote_dry_run_behavior.py`
- Test: `engine/tests/test_git_remote_dry_run_behavior.py`

**Interfaces:**
- Consumes: `engine.tests.helpers.EngineTestCase`, local `git` executable, isolated temporary
  repositories.
- Produces:
  `TestGitRemoteDryRunBehavior.test_fetch_dry_run_writes_objects_without_updating_refs_or_fetch_head`
  and
  `TestGitRemoteDryRunBehavior.test_push_dry_run_runs_pre_push_without_updating_remote_refs`.

- [ ] **Step 1 — Write the isolated behavior-proof test**

```python
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from engine.tests.helpers import EngineTestCase


class TestGitRemoteDryRunBehavior(EngineTestCase):
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        return env

    def _git(self, cwd: Path, *args: str, check: bool = True):
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=check,
            capture_output=True,
            text=True,
            env=self._env(),
        )

    def _fixture(self) -> tuple[Path, Path, Path]:
        root = Path(self._tmp.name)
        remote = root / "remote.git"
        source = root / "source"
        client = root / "client"
        self._git(root, "init", "-q", "--bare", str(remote))
        source.mkdir()
        self._git(source, "init", "-q", ".")
        (source / "tracked.txt").write_text("one\n", encoding="utf-8")
        self._git(source, "add", "tracked.txt")
        self._git(
            source,
            "-c", "user.email=awa-test@example.invalid",
            "-c", "user.name=AWA Test",
            "commit", "-qm", "initial",
        )
        self._git(source, "branch", "-M", "main")
        self._git(source, "remote", "add", "origin", remote.as_uri())
        self._git(source, "push", "-q", "-u", "origin", "main")
        self._git(root, "clone", "-q", "--branch", "main", remote.as_uri(), str(client))
        return remote, source, client

    def test_fetch_dry_run_writes_objects_without_updating_refs_or_fetch_head(self):
        _remote, source, client = self._fixture()
        (source / "tracked.txt").write_text("two\n", encoding="utf-8")
        self._git(source, "add", "tracked.txt")
        self._git(
            source,
            "-c", "user.email=awa-test@example.invalid",
            "-c", "user.name=AWA Test",
            "commit", "-qm", "remote advance",
        )
        self._git(source, "push", "-q", "origin", "main")
        new_oid = self._git(source, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(
            self._git(client, "cat-file", "-e", new_oid, check=False).returncode,
            0,
        )
        refs_before = self._git(
            client, "for-each-ref", "--format=%(refname):%(objectname)"
        ).stdout
        fetch_head = client / ".git" / "FETCH_HEAD"
        fetch_head_before = fetch_head.read_bytes() if fetch_head.exists() else None

        self._git(
            client,
            "-c", "gc.auto=0",
            "-c", "fetch.writeCommitGraph=false",
            "fetch", "--dry-run", "--no-recurse-submodules", "origin",
        )

        self.assertEqual(self._git(client, "cat-file", "-e", new_oid).returncode, 0)
        self.assertEqual(
            self._git(client, "for-each-ref", "--format=%(refname):%(objectname)").stdout,
            refs_before,
        )
        fetch_head_after = fetch_head.read_bytes() if fetch_head.exists() else None
        self.assertEqual(fetch_head_after, fetch_head_before)

    def test_push_dry_run_runs_pre_push_without_updating_remote_refs(self):
        remote, _source, client = self._fixture()
        (client / "local.txt").write_text("local\n", encoding="utf-8")
        self._git(client, "add", "local.txt")
        self._git(
            client,
            "-c", "user.email=awa-test@example.invalid",
            "-c", "user.name=AWA Test",
            "commit", "-qm", "local advance",
        )
        sentinel = Path(self._tmp.name) / "pre-push-ran"
        hook = client / ".git" / "hooks" / "pre-push"
        hook.write_text(
            "#!/bin/sh\n: > \"$AWA_DRY_RUN_SENTINEL\"\n",
            encoding="utf-8",
        )
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        env = self._env()
        env["AWA_DRY_RUN_SENTINEL"] = str(sentinel)

        proc = subprocess.run(
            [
                "git", "-C", str(client), "push", "--dry-run",
                "origin", "HEAD:refs/heads/dry-run-proof",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(sentinel.exists())
        self.assertNotEqual(
            self._git(
                remote,
                "rev-parse", "--verify", "refs/heads/dry-run-proof",
                check=False,
            ).returncode,
            0,
        )
```

- [ ] **Step 2 — Run the proof**

Run:

```bash
python3 -m unittest engine.tests.test_git_remote_dry_run_behavior
```

Expected: `Ran 2 tests` and `OK`; the tests positively demonstrate side effects without external
network access or operator-state writes.

- [ ] **Step 3 — Commit**

```bash
git add engine/tests/test_git_remote_dry_run_behavior.py
git commit -m "test(guard): prove remote git dry-run side effects"
```

**Definition of done:** Fetch dry-run object writes and push dry-run hook execution are
reproducible in isolated local fixtures while normal destination refs remain unchanged.

### Task 2: Record the durable remote-operation policy

**Files:**
- Create: `docs/adr/0010-remote-dry-run-policy.md`
- Modify: `docs/adr/README.md`
- Test: `docs/adr/0010-remote-dry-run-policy.md`

**Interfaces:**
- Consumes: Task 1 test names/results and Git 2.50.1/upstream source evidence.
- Produces: ADR 0010 policy—protected primary plus any fetch/push form is mutating/deny; linked
  Safe Workspace or standalone scratch repository remains eligible for the existing outer allow.

- [ ] **Step 1 — Author ADR 0010**

Write the ADR with these exact decisions:

```markdown
## Decision

1. AWA classifies every `git fetch` and `git push` invocation as potentially mutating on an
   included primary checkout. `--dry-run`, push `-n`, `--no-verify`, and recursive variants do
   not create an exception.
2. The existing outer context decision remains unchanged: linked Safe Workspaces, adopted leases,
   standalone/advisory repositories, Cloud agents, and explicit operator overrides allow before
   command-family enforcement.
3. A future remote exception requires proof, across supported Git versions, of zero Git-managed
   writes, zero remote updates, and zero arbitrary hook/helper execution.
```

- [ ] **Step 2 — Record alternatives and evidence**

Document and reject:

- exact dry-run token allowlisting, because observed writes/hooks contradict the read-only premise;
- blanket denial in Safe Workspaces, because AWA's isolation boundary already makes that unnecessary;
- building a network sandbox, because it is a different product surface and unnecessary for this
  classifier correction.

- [ ] **Step 3 — Update the ADR index**

Add:

```markdown
| [0010](0010-remote-dry-run-policy.md) | Draft — 2026-08-11 | Treat all fetch/push forms, including dry-run, as potentially mutating on protected primaries; use a Safe Workspace or scratch repo instead. |
```

- [ ] **Step 4 — Verify governance shape**

Run:

```bash
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check "$(pwd)"
```

Expected: all baseline items `CONFORMANT`; no `NEEDS_AUTHORING` or `DRIFTED` result attributable to
ADR 0010.

- [ ] **Step 5 — Commit**

```bash
git add docs/adr/0010-remote-dry-run-policy.md docs/adr/README.md
git commit -m "docs(adr): define remote dry-run guard policy"
```

**Definition of done:** The remote boundary and future exception bar are explicit, evidence-backed,
indexed, and governed as a draft ADR.

### Task 3: Drive complete engine policy from failing tests

**Files:**
- Modify: `engine/tests/git_guard_command_corpus.py`
- Modify: `engine/tests/test_guard.py`
- Modify: `engine/guard.py`
- Test: `engine/tests/test_guard.py`

**Interfaces:**
- Consumes: ADR 0010 and existing
  `GIT_READONLY_FAMILY_COMMANDS`/`GIT_MUTATING_FAMILY_COMMANDS`.
- Produces:
  `_parse_git_invocation(rest)`,
  `_git_branch_is_readonly(args)`,
  `_git_remote_is_readonly(args)`,
  `_git_config_is_readonly(args)`,
  `_git_submodule_is_readonly(args)`,
  `_git_sparse_checkout_is_readonly(args)`,
  and updated `_git_is_mutating(rest)`.

- [ ] **Step 1 — Extend the canonical command corpus**

Append these exact cases to the existing tuples:

```python
GIT_READONLY_FAMILY_COMMANDS += (
    "git branch",
    "git branch --show-current",
    "git branch --list",
    "git branch --list -- feature/*",
    "git branch -a",
    "git branch -r",
    "git branch -v",
    "git branch -vv",
    "git remote",
    "git remote -v",
    "git remote --verbose",
    "git remote get-url origin",
    "git remote get-url --push --all origin",
    "git remote show -n origin",
    "git config --list",
    "git config -l",
    "git config --get user.name",
    "git config --get-all remote.origin.fetch",
    "git config --get-regexp ^branch\\.",
    "git config --get-urlmatch http https://example.invalid/",
    "git submodule status",
    "git submodule status --cached -- path/to/submodule",
    "git sparse-checkout list",
    "git sparse-checkout check-rules",
    "git sparse-checkout check-rules -z --skip-checks",
)

GIT_MUTATING_FAMILY_COMMANDS += (
    "git fetch --dry-run",
    "git fetch -n",
    "git fetch --dry-run --set-upstream origin main",
    "git push --dry-run",
    "git push -n",
    "git push --dry-run --no-verify origin HEAD",
    "git push --dry-run --recurse-submodules=on-demand origin HEAD",
    "git branch topic",
    "git branch -d topic",
    "git branch -D topic",
    "git branch -m old new",
    "git branch -c old new",
    "git branch --set-upstream-to=origin/main",
    "git branch --edit-description",
    "git branch --create-reflog topic",
    "git remote add upstream https://example.invalid/repo.git",
    "git remote remove origin",
    "git remote rename origin upstream",
    "git remote set-head origin --auto",
    "git remote set-branches origin main",
    "git remote set-url origin https://example.invalid/repo.git",
    "git remote update",
    "git remote prune origin",
    "git remote prune --dry-run origin",
    "git remote show origin",
    "git config user.name changed",
    "git config --global user.name changed",
    "git config --file /tmp/config user.name changed",
    "git config set user.name changed",
    "git config unset user.name",
    "git config edit",
    "git config rename-section old new",
    "git config remove-section old",
    "git config get user.name",
    "git config list",
    "git submodule",
    "git submodule add https://example.invalid/repo.git child",
    "git submodule init",
    "git submodule deinit child",
    "git submodule update --init",
    "git submodule set-branch --branch main child",
    "git submodule set-url child https://example.invalid/repo.git",
    "git submodule sync",
    "git submodule absorbgitdirs",
    "git submodule foreach 'rm -rf ../protected'",
    "git submodule status --recursive",
    "git sparse-checkout init",
    "git sparse-checkout set src",
    "git sparse-checkout add docs",
    "git sparse-checkout reapply",
    "git sparse-checkout disable",
    "git sparse-checkout unknown-action",
)
```

- [ ] **Step 2 — Add ambiguity and target-scope tests**

Add these methods to `TestMutatingClassifier` and `TestDecideShellDegraded`:

```python
def test_git_family_unknown_or_malformed_forms_fail_safe(self):
    for cmd in (
        "git -C",
        "git --unknown-global branch --show-current",
        "git branch --unknown",
        "git remote -- get-url origin",
        "git config --get",
        "git submodule -- status",
        "git sparse-checkout check-rules --unknown",
    ):
        self.assertTrue(guard.classify_mutating(cmd), cmd)


def test_branch_copy_flag_is_not_global_chdir(self):
    self.assertTrue(guard.classify_mutating("git branch -C main copied"))


def test_remote_dry_runs_allow_only_after_safe_workspace_classification(self):
    repo = self.make_repo()
    wt = self.add_worktree(repo, "feat/remote-proof")
    pol = self._policy_for(self._tmp.name)
    for cmd in ("git fetch --dry-run", "git push --dry-run"):
        self.assertEqual(guard.decide_shell(repo, cmd, pol).permission, "deny", cmd)
        self.assertEqual(guard.decide_shell(wt, cmd, pol).permission, "allow", cmd)
```

- [ ] **Step 3 — Run the new tests, verify they FAIL before implementation**

Run:

```bash
python3 -m unittest \
  engine.tests.test_guard.TestMutatingClassifier \
  engine.tests.test_guard.TestDecideShellDegraded
```

Expected: failures showing mutating branch/remote/config/submodule/sparse-checkout forms currently
classify read-only.

- [ ] **Step 4 — Implement validated Git invocation parsing**

Add these constants and parser next to `_GIT_TAKES_ARG`:

```python
_GIT_GLOBAL_VALUE_OPTS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
}
_GIT_GLOBAL_FLAG_OPTS = {
    "-p",
    "--paginate",
    "-P",
    "--no-pager",
    "--no-replace-objects",
    "--bare",
    "--literal-pathspecs",
    "--glob-pathspecs",
    "--noglob-pathspecs",
    "--icase-pathspecs",
    "--no-optional-locks",
    "--no-lazy-fetch",
}
_GIT_GLOBAL_ATTACHED_PREFIXES = (
    "--git-dir=",
    "--work-tree=",
    "--namespace=",
    "--super-prefix=",
    "--config-env=",
)
_GIT_STANDALONE_INFO_ARGS = {
    ("--version",),
    ("--help",),
    ("--exec-path",),
    ("--html-path",),
    ("--man-path",),
    ("--info-path",),
}


def _parse_git_invocation(rest: list[str]):
    global_args: list[str] = []
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in _GIT_GLOBAL_VALUE_OPTS:
            if i + 1 >= len(rest):
                return None
            global_args.extend((arg, rest[i + 1]))
            i += 2
            continue
        if arg in _GIT_GLOBAL_FLAG_OPTS:
            global_args.append(arg)
            i += 1
            continue
        if arg.startswith(_GIT_GLOBAL_ATTACHED_PREFIXES):
            global_args.append(arg)
            i += 1
            continue
        if arg.startswith("-c") and len(arg) > 2:
            global_args.append(arg)
            i += 1
            continue
        if arg.startswith("-"):
            return None
        return global_args, arg, rest[i + 1:]
    return global_args, "", []
```

- [ ] **Step 5 — Implement the closed family predicates**

Use exact arity and option sets:

```python
_GIT_BRANCH_LIST_FLAGS = {
    "--list", "-a", "--all", "-r", "--remotes",
    "-v", "-vv", "--verbose",
}
_GIT_CONFIG_PREFIX_FLAGS = {
    "--local", "--global", "--system", "--worktree",
    "--includes", "--no-includes", "--null", "-z",
    "--name-only", "--show-origin", "--show-scope", "--fixed-value",
}
_GIT_CONFIG_PREFIX_VALUE_OPTS = {"--file", "--type"}
_GIT_CONFIG_GETTER_ARITY = {
    "--list": {0},
    "-l": {0},
    "--get": {1, 2},
    "--get-all": {1, 2},
    "--get-regexp": {1, 2},
    "--get-urlmatch": {2},
    "--get-color": {1, 2},
    "--get-colorbool": {1, 2},
}


def _git_branch_is_readonly(args: list[str]) -> bool:
    if not args or args == ["--show-current"]:
        return True
    if all(arg in _GIT_BRANCH_LIST_FLAGS - {"--list"} for arg in args):
        return True
    if "--list" not in args:
        return False
    boundary = args.index("--") if "--" in args else len(args)
    return (
        all(arg in _GIT_BRANCH_LIST_FLAGS for arg in args[:boundary])
        and boundary == len(args) or args[boundary] == "--"
    )


def _git_remote_is_readonly(args: list[str]) -> bool:
    if not args or args in (["-v"], ["--verbose"]):
        return True
    prefix = []
    if args and args[0] in ("-v", "--verbose"):
        prefix, args = args[:1], args[1:]
    if args and args[0] == "get-url":
        options = [arg for arg in args[1:-1] if arg in ("--push", "--all")]
        return len(args) >= 2 and len(options) == len(args[1:-1])
    if args and args[0] == "show":
        return len(args) >= 3 and args[1] == "-n" and all(args[2:])
    return False


def _git_config_is_readonly(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        if args[i] in _GIT_CONFIG_PREFIX_FLAGS:
            i += 1
            continue
        if args[i] in _GIT_CONFIG_PREFIX_VALUE_OPTS:
            if i + 1 >= len(args):
                return False
            i += 2
            continue
        break
    if i >= len(args) or args[i] not in _GIT_CONFIG_GETTER_ARITY:
        return False
    return len(args[i + 1:]) in _GIT_CONFIG_GETTER_ARITY[args[i]]


def _git_submodule_is_readonly(args: list[str]) -> bool:
    if not args or args[0] != "status":
        return False
    i = 1
    if i < len(args) and args[i] == "--cached":
        i += 1
    if i == len(args):
        return True
    return args[i] == "--"


def _git_sparse_checkout_is_readonly(args: list[str]) -> bool:
    if args == ["list"]:
        return True
    if not args or args[0] != "check-rules":
        return False
    i = 1
    while i < len(args):
        if args[i] in ("-z", "--skip-checks", "--cone", "--no-cone"):
            i += 1
            continue
        if args[i] == "--rules-file" and i + 1 < len(args):
            i += 2
            continue
        return False
    return True
```

Parenthesize the `branch` return expression explicitly during implementation so Python operator
precedence cannot broaden the allow grammar.

- [ ] **Step 6 — Wire family policy and conservative target handling**

Add the five family names to `_GITMUT`; make parse failure mutating; keep fetch/push always
mutating:

```python
def _git_is_mutating(rest: list[str]) -> bool:
    if tuple(rest) in _GIT_STANDALONE_INFO_ARGS:
        return False
    parsed = _parse_git_invocation(rest)
    if parsed is None:
        return True
    _global_args, sub, sub_args = parsed
    if not sub or sub not in _GITMUT:
        return False
    if sub in {"fetch", "push"}:
        return True
    if sub == "branch":
        return not _git_branch_is_readonly(sub_args)
    if sub == "remote":
        return not _git_remote_is_readonly(sub_args)
    if sub == "config":
        return not _git_config_is_readonly(sub_args)
    if sub == "submodule":
        return not _git_submodule_is_readonly(sub_args)
    if sub == "sparse-checkout":
        return not _git_sparse_checkout_is_readonly(sub_args)
    if sub == "worktree":
        action, action_args = _git_exact_nested_action(sub_args)
        return not (
            action in _GIT_WORKTREE_READONLY_ACTIONS
            and _git_worktree_list_is_readonly(action_args)
        )
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

Parse only the validated global prefix in `_extract_git_target_dirs()`. Return `None` from
`_collect_precise_targets()` for:

```python
_GIT_NO_TARGET_NARROWING = {
    "fetch",
    "push",
    "remote",
    "config",
    "submodule",
}
```

- [ ] **Step 7 — Run the engine tests, verify they PASS**

Run:

```bash
python3 -m unittest \
  engine.tests.test_guard.TestMutatingClassifier \
  engine.tests.test_guard.TestDecideShellDegraded
```

Expected: `OK`.

- [ ] **Step 8 — Commit**

```bash
git add engine/guard.py engine/tests/git_guard_command_corpus.py engine/tests/test_guard.py
git commit -m "fix(guard): classify git command families conservatively"
```

**Definition of done:** Every named family maps exact proven query grammar to read-only and every
other form to mutating; target narrowing cannot reinterpret family flags or launder unscoped
mutations.

### Task 4: Mirror kernel policy and freeze live-hook parity

**Files:**
- Modify: `kernel/hooks/worktree-guard.sh`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `kernel/checks/awa-contract-freeze.sh`
- Test: `engine/tests/test_guard_hook_wrappers.py`

**Interfaces:**
- Consumes: Task 3 constants, parser, predicates, `_GIT_NO_TARGET_NARROWING`, and shared corpus.
- Produces: independently embedded hook implementation with the same permission outcomes and
  contract-freeze UAT coverage.

- [ ] **Step 1 — Write failing hook parity tests**

Add:

```python
def test_hook_git_family_target_ambiguity_denies(self):
    for cmd in (
        "git branch -C main copied",
        f"git -C /tmp config --file {self.repo}/.git/config user.name changed",
        f"git -C /tmp submodule foreach 'rm -rf {self.repo}'",
        f"git -C /tmp push {self.repo} HEAD:refs/heads/changed",
    ):
        resp = self._guard(cmd)
        self.assertEqual(resp.get("permission"), "deny", cmd)
        self.assertIn("user_message", resp)
        self.assertIn("agent_message", resp)
```

The existing shared-corpus loops automatically cover every Task 3 allow/deny command.

- [ ] **Step 2 — Run hook tests, verify they FAIL before mirror changes**

Run:

```bash
python3 -m unittest engine.tests.test_guard_hook_wrappers
```

Expected: failures for the newly denied families and ambiguity cases.

- [ ] **Step 3 — Mirror the engine implementation**

Copy the exact Task 3 constants, parser, predicates, dispatch, and target-narrowing behavior into
the quoted embedded-Python heredoc. Keep comments/docstrings apostrophe-free inside that heredoc
because macOS Bash 3.2 misparses bare apostrophes in this nesting shape. Do not import
`engine.guard`.

- [ ] **Step 4 — Extend contract-freeze UAT**

Add exact allow cases:

```python
("git branch --show-current", "allow"),
("git remote get-url origin", "allow"),
("git config --get remote.origin.url", "allow"),
("git submodule status", "allow"),
("git sparse-checkout list", "allow"),
```

Add exact deny cases:

```python
("git fetch --dry-run", "deny"),
("git push --dry-run", "deny"),
("git push -n", "deny"),
("git branch -d topic", "deny"),
("git remote add upstream https://example.invalid/repo.git", "deny"),
("git config user.name changed", "deny"),
("git submodule update --init", "deny"),
("git sparse-checkout set src", "deny"),
```

Keep `contracts/awa-contract.v1.json` unchanged because the permission values and response shapes
do not change.

- [ ] **Step 5 — Run hook and contract checks, verify they PASS**

Run:

```bash
python3 -m unittest engine.tests.test_guard_hook_wrappers
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
```

Expected: `OK` and `awa-contract-freeze: OK`.

- [ ] **Step 6 — Commit**

```bash
git add \
  kernel/hooks/worktree-guard.sh \
  engine/tests/test_guard_hook_wrappers.py \
  kernel/checks/awa-contract-freeze.sh
git commit -m "fix(kernel): mirror complete git family policy"
```

**Definition of done:** The actual Cursor hook, engine mirror, shared corpus, target handling, and
contract UAT return identical outcomes.

### Task 5: Prepare AWA 1.5.1 and verify the complete implementation

**Files:**
- Modify: `engine/__init__.py`
- Modify: `pyproject.toml`
- Test: `engine/tests/test_git_remote_dry_run_behavior.py`
- Test: `engine/tests/test_guard.py`
- Test: `engine/tests/test_guard_hook_wrappers.py`

**Interfaces:**
- Consumes: Tasks 1–4 and current version declarations `1.5.0`.
- Produces: synchronized product version `1.5.1` with unchanged
  `contracts/awa-contract.v1.json`.

- [ ] **Step 1 — Verify the release precondition**

Run:

```bash
test "$(python3 -c 'import engine; print(engine.__version__)')" = "1.5.0"
test "$(python3 - <<'PY'
from pathlib import Path
import re
text = Path("pyproject.toml").read_text(encoding="utf-8")
print(re.search(r'(?m)^version = "([^"]+)"$', text).group(1))
PY
)" = "1.5.0"
test -z "$(git tag -l v1.5.1)"
test -z "$(gh release list --limit 100 | awk '$3 == "v1.5.1" {print $3}')"
```

Expected: exit `0`. If any assertion fails, stop and recalculate the next version rather than
overwriting newer release work.

- [ ] **Step 2 — Bump both version declarations**

```python
# engine/__init__.py
__version__ = "1.5.1"
```

```toml
# pyproject.toml
version = "1.5.1"
```

- [ ] **Step 3 — Verify version identity**

Run:

```bash
test "$(make -s version)" = "1.5.1"
```

Expected: exit `0`.

- [ ] **Step 4 — Run all required gates**

Run:

```bash
python3 -m unittest \
  engine.tests.test_git_remote_dry_run_behavior \
  engine.tests.test_guard \
  engine.tests.test_guard_hook_wrappers
bash engine/tests/run-tests.sh
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
make verify
make verify-install
git diff --check
```

Expected: all commands exit `0`; behavior proof stays offline; contract schema remains v1.

- [ ] **Step 5 — Run defect review until clean**

Run Bugbot over the complete branch. Fix every valid finding, rerun focused and full verification,
then repeat Bugbot until it reports no defects.

- [ ] **Step 6 — Commit**

```bash
git add engine/__init__.py pyproject.toml
git commit -m "release: prepare AWA v1.5.1"
```

**Definition of done:** Both version sources report 1.5.1, all verification gates pass, and the
complete implementation has a clean Bugbot review.

### Task 6: Ship, release, promote, and reconcile

**Files:**
- No additional AWA source files unless review finds a defect.
- Modify downstream only through the separately governed `KleinPerkins/skills` release descriptor.

**Interfaces:**
- Consumes: verified AWA 1.5.1 branch and normal AWA/skills PR automation.
- Produces: merged source, optional approved `v1.5.1` release, promoted skills binding, repaired
  host install, and clean local/remote branch state.

- [ ] **Step 1 — Push and open the implementation PR**

```bash
git push -u origin HEAD
gh pr create \
  --title "fix: classify deferred git command families" \
  --body "$(cat <<'EOF'
## Summary
- Prove why fetch/push dry-run remain denied on protected primaries
- Fully classify branch, remote, config, submodule, and sparse-checkout
- Preserve engine/hook parity and prepare AWA 1.5.1

## Test plan
- python3 -m unittest engine.tests.test_git_remote_dry_run_behavior engine.tests.test_guard engine.tests.test_guard_hook_wrappers
- bash engine/tests/run-tests.sh
- AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
- make verify
- make verify-install
- git diff --check
EOF
)"
```

- [ ] **Step 2 — Let governed automation merge**

Wait for `pr-automation / verify` and reviewer-App approval. Never call `gh pr merge --auto`,
change native auto-merge state, or bypass the gate without explicit operator direction.

- [ ] **Step 3 — Reconcile local main after merge**

From the clean primary checkout:

```bash
git fetch origin main
test -z "$(git status --porcelain)"
git merge --ff-only origin/main
```

Expected: local `main` equals `origin/main` and remains clean.

- [ ] **Step 4 — Obtain release/promotion GO**

Before creating/pushing `v1.5.1`, publishing a GitHub release, changing the skills binding, or
repairing the live host install, obtain explicit operator approval.

- [ ] **Step 5 — On GO, tag and publish the exact merge**

```bash
release_sha="$(git rev-parse origin/main)"
test "$(git show "$release_sha:engine/__init__.py" | \
  awk -F'\"' '/^__version__/ {print $2}')" = "1.5.1"
git tag v1.5.1 "$release_sha"
git push origin v1.5.1
gh release create v1.5.1 \
  --verify-tag \
  --title "AWA v1.5.1" \
  --generate-notes
```

Release notes must be reviewed as cumulative from the latest published `v1.2.0`, not described as
classifier-only.

- [ ] **Step 6 — Promote through the governed capability lifecycle**

Update the global `tools/awa` release descriptor in `KleinPerkins/skills`, open its normal governed
PR, and wait for its automation. Do not hand-vendor AWA into downstream repositories.

- [ ] **Step 7 — Repair and live-check the host**

After the skills PR merges:

```bash
bash /Users/laurence.duggan/dev/_ops/bin/install-dev-awa-overlay.sh
/Users/laurence.duggan/dev/_ops/bin/dev-worktree.sh doctor
```

Use diagnostic-only guard checks to confirm one allow and one deny for every family on a protected
primary, plus fetch/push dry-run denial there and allowance in a linked Safe Workspace. Do not
execute the mutating commands during UAT.

- [ ] **Step 8 — Clean the merged branch**

Delete the merged remote feature branch through the normal governed cleanup path. Leave both the
Safe Workspace and primary checkout clean.

**Definition of done:** Source is merged, local main is fast-forwarded, publication occurs only
after explicit GO, the downstream binding and host install point at the verified release, and no
orphan branch/worktree state remains.

## 6. Acceptance criteria

- Remote dry-run side effects are independently and reproducibly proven without external network
  access.
- ADR 0010 denies all fetch/push forms on protected primaries and explains the Safe Workspace
  alternative.
- Every named family has a closed allow grammar and a deny-by-default remainder.
- Unknown or malformed forms cannot silently allow.
- Engine, live hook, decision layer, target narrowing, shared corpus, and contract UAT agree.
- No new dependency enters the hook path; hook-internal failures still degrade to allow.
- AWA reports version 1.5.1 from both version sources and all verification gates pass.
- The prior PR #95 plan remains byte-identical and its completed state is represented only in the
  mutable plan index.

## 7. Rollback

- Before merge: revert the relevant local commit or push a correcting commit; do not amend pushed
  commits.
- After merge: use a normal `git revert` PR. Never rewrite `main`.
- After `v1.5.1` publication: never move or delete the tag. Publish the corrective patch as
  `v1.5.2`.
- If downstream install smoke fails: revert the `KleinPerkins/skills` descriptor through its
  governed PR path and reinstall the previous release.
- ADR 0010 and this plan become byte-identical once accepted; any material policy reversal uses a
  higher-numbered ADR and a `-v2` successor plan.
