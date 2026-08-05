# AWA guard target-path precision — v1

- **Version:** v1
- **Status:** DRAFT (for review)
- **Date:** 2026-08-05
- **Relates to:** [ADR 0001](../adr/0001-target-path-aware-mutation-scope.md) (the durable
  decision this plan executes); [issue #75](https://github.com/KleinPerkins/awa/issues/75)
  and [issue #34](https://github.com/KleinPerkins/awa/issues/34) (related, explicitly
  NOT fixed by this plan — see §6 Non-goals).
- **Review provenance:** Investigated and drafted by an agent session in
  `pr-automation-controller`, at the operator's explicit request, following a live
  reproduction of the defect during that session's own cleanup work. Every fact in
  §1 was checked directly against disk and the `KleinPerkins/awa` remote on
  2026-08-05 (commands and outputs recorded in §1); nothing here is inferred from
  memory or documentation alone. Not yet reviewed by anyone other than the
  authoring agent — this is a DRAFT pending the executing agent's own
  re-verification (§2) and the owner's GO/NO-GO (§7).

## 0. Purpose and boundary

Fix `beforeShellExecution`'s enforcement hook (`kernel/hooks/worktree-guard.sh`) so a
mutating command whose target path resolves outside every protected primary
checkout is **allowed**, even when the shell's `cwd` is inside one. Today it is
unconditionally denied, using only the command's verb and the cwd — never the
command's own arguments. This directly reproduces as: `rm -f /tmp/anything` run from
inside any protected repo is denied, even though `/tmp` shares no git history with
that repo and the command cannot touch a single tracked file in it.

The fix must be **additive-only**: it may convert an existing `deny` into `allow`
when every resolved target is affirmatively proven safe; it must never convert an
existing `allow` into `deny`, and any uncertainty must fall back to exactly today's
behavior. See [ADR 0001](../adr/0001-target-path-aware-mutation-scope.md) for the
full decision and its consequences.

This plan also establishes `docs/plans/` and `docs/adr/` in this repository (they do
not exist yet) as part of executing it — see §4A.

## 1. Live-state verification record

Every row below was checked directly on 2026-08-05, in this order, against disk and
the `KleinPerkins/awa` GitHub remote (via `gh api`, never `git fetch`/`git pull` —
both are themselves guard-classified mutating commands and were not available to the
investigating session from inside a different protected primary checkout; this is
itself a live instance of the exact defect this plan fixes).

| # | Fact | How verified | Result |
|---|---|---|---|
| 1 | Repo location and remote | `ls ~/dev/capabilities/awa`; `git remote -v` | `~/dev/capabilities/awa`, origin `git@github.com:KleinPerkins/awa.git` |
| 2 | Local `main` vs. true remote `main` | `git rev-parse HEAD` (local) vs. `gh api repos/KleinPerkins/awa/commits/main` (remote, no local mutation) | Local HEAD `0328fcd` (#74); true remote HEAD `0dbdd8c` (#79) — 3 commits ahead, none touching guard/policy/kernel code (`gh api .../compare/0328fcd...main`: #76 relock, #77 policy-pin restage, #79 M3 evidence test) |
| 3 | Installed (live-enforcing) hook vs. this repo's source | `diff kernel/hooks/worktree-guard.sh ~/.local/share/awa/current/kernel/hooks/worktree-guard.sh` | **Byte-identical** (exit 0, no diff) — the installed hook is current with local HEAD, and per row 2, with true remote `main` too, for this file |
| 4 | Installed release version/commit | `cat ~/.local/share/awa/release-pointer.json` | `version: "1.1.1"`, `commit: 81a0b71` (#69), installed 2026-08-01 — behind local HEAD by 5 commits (#70–#74), none touching guard/kernel code either |
| 5 | Current global protection state | `cat ~/dev/_ops/policy/worktree-modes.yml` | `default_mode: on` — protection is LIVE and active fleet-wide right now (governed roots: `personal/*`, `capabilities/*`, `affirm/src/*` per `worktree-policy.yml`), confirmed by this same session's own repeated live denials in `pr-automation-controller` today |
| 6 | `engine/guard.py` vs. `kernel/hooks/worktree-guard.sh` relationship | Direct read of both files + `engine/guard.py` module docstring + `_is_standalone` comment referencing `kernel/lib/awa_policy.py:334-335` | **Three, not two, independently-maintained classification paths**: (a) `engine/guard.py::decide_shell` — Python-native, calls `engine/policy.py::classify` directly; powers the advisory MCP diagnostic tool `awa_guard_shell` only, per that tool's own description ("advisory... the live hook governs"); (b) `kernel/hooks/worktree-guard.sh` — the ACTUAL live enforcement hook wired into `~/.cursor/hooks.json`; its embedded Python re-implements `classify_mutating`/`_segments`/`_skip_wrappers` verbatim (comment: "parity with engine/guard.py") for verb classification ONLY; (c) for the primary/worktree/mode classification itself, the hook does NOT call any Python policy module directly — it shells out to `dev-worktree.sh status` via its own `classify_dir()` bash helper, which in turn uses `kernel/lib/awa_policy.py` (a THIRD, separately-maintained mirror of the same policy logic, for the kernel-only/engine-off code path) |
| 7 | Existing test coverage for this defect class | Read `engine/tests/test_guard.py` (389 lines) and `engine/tests/test_guard_hook_wrappers.py` (335 lines) in full | **Zero existing tests exercise a mutating command whose target differs from `cwd`.** Every existing `decide_shell`/hook-subprocess test call passes the SAME path as both the probed `cwd` and the (implicit) mutation target. The gap is real and untested, not a documented/accepted limitation |
| 8 | Related but distinct open issues | `gh issue list --repo KleinPerkins/awa --state open`; `gh issue view 75`/`34` | #75 (2026-08-03, open): commands whose verb is NOT in any mutating set are still denied; hand-tracing the classifier offline does not reproduce it — root cause unknown, needs live-payload forensics, orthogonal to this plan (misidentifying the verb, not ignoring the target). #34 (2026-07-11, open): `branch_is_cleanup_safe` false-refuses squash-merged multi-commit branches — different subsystem entirely (worktree cleanup safety, not shell classification) |
| 9 | Existing `docs/` governance in this repo | `ls ~/dev/capabilities/awa/docs` | Does not exist — net new (see §4A) |
| 10 | Reference convention to model | Read `pr-automation-controller/docs/plans/README.md` and `docs/adr/README.md` in full | Both fully documented, stable, in active use since 2026-07-11/07-17. Independently corroborated as the fleet's reference convention by a concurrent, UNRELATED cross-fleet documentation-governance review already under design (`~/dev`'s in-progress "doc-warden" initiative — see caveat below) |
| 11 | "doc-warden paradigm" status (operator's phrase; verify before depending on it) | Read `~/.cursor/worktrees/dev/pzxf/_ops/plans/doc-warden-execution-plan-v1.md` (a DIFFERENT, live, uncommitted agent session's worktree in the `dev` repo — read-only, not modified) | **Not yet an established paradigm.** Status line reads "DRAFT — Gate 3 ... not yet an approved/final execution record," dated 2026-08-05 (today). It is a fleet-wide, cross-repo documentation-governance initiative being designed in `KleinPerkins/dev`, uncommitted, mid-swarm-review, in a *different* live session. It independently cites `pr-automation-controller`'s convention as "the fleet's clearest versioned-plan + Nygard-ADR convention" — i.e. it validates modeling on that convention, but it is not itself a mergeable or citable paradigm yet. **This plan does not depend on doc-warden landing, and does not vendor any of its draft content** — it models directly on `pr-automation-controller`'s proven convention (row 10), which doc-warden's own research independently converged on. A forward-compatibility note is included in the new `docs/*/README.md` files (§4A) so no rework is expected if/when doc-warden reaches general availability |
| 12 | Release/versioning mechanism | `git tag --list`; `gh release list`; read `install.sh` (COPY_TREES/COPY_FILES, lines 79-90); read `Makefile` | Six tagged releases (`v1.0.0`–`v1.1.1`), each with a matching `gh release`. `engine/__init__.py:20` and `pyproject.toml:7` both carry the version string (`"1.1.1"`) and must be bumped together. `install.sh` (no `--ref`/`--tag` flag) copies the CURRENT WORKING TREE of wherever it's invoked from into `$XDG_DATA_HOME/awa/current` — "shipping" = merge to `main` → checkout/pull that commit locally → `make repair` (`./install.sh --repair`) |
| 13 | Test-running commands | Read `Makefile` | `make test` (engine suite only, `engine/tests/run-tests.sh`, unittest, local-only/no network); `make verify` (full gate: tests + contract-freeze + zero-link + `install.sh --check` + live-verify) |
| 14 | This repo's own PR-automation governance | `cat .github/pr-automation.json`; `gh pr list --state merged --limit 5` | `awa` is itself a fully-onboarded `pr-automation/v3` fleet repo, `local`-mode gating already proven (PR #79). `protected_paths: [".github", "CODEOWNERS", "_ops"]` — this plan's changes (`engine/`, `kernel/`, `docs/`, `AGENTS.md`) touch none of them, so the standard automated verify → reviewer-App-approve → auto-merge path applies unmodified |
| 15 | No duplicate effort in flight | `gh issue list --search` (guard/precision/path/target terms); `gh pr list --state open`; `git branch -a \| grep -i` guard/precision/path/target | No open issue, PR, or branch already addresses target-path precision |
| 16 | `classify_dir`'s existing per-path probing precedent | Read `kernel/hooks/worktree-guard.sh` lines 529-547 in full | The `afterFileEdit` event handler ALREADY loops over multiple resolved target paths (`paths=(...)`, emitted by the same embedded-Python block) and probes each independently via `dir_for_probe` + `classify_dir` — proven, live, production code for exactly the "probe N candidate paths against the policy classifier" shape this fix needs, just for a different event type |

**If the executing agent finds any row above no longer holds** (e.g. `main` has moved
further, the installed version differs, `default_mode` has changed, or a new PR/issue
now overlaps this work), STOP and re-verify against the ADR and this plan's intent
before proceeding — do not silently proceed on stale ground truth. Re-running the
exact commands in the "How verified" column reproduces every row.

## 2. Inherited scope and ground truth (re-verify before executing)

Before writing any code, the executing agent must re-run and confirm, in its own
worktree:

```bash
git -C ~/dev/capabilities/awa status --short --branch     # expect clean, main
git -C ~/dev/capabilities/awa rev-parse HEAD               # compare to row 2 above
gh api repos/KleinPerkins/awa/commits/main --jq '.sha'     # true remote tip (no git fetch needed)
cat ~/dev/_ops/policy/worktree-modes.yml                   # confirm default_mode: on still holds
```

If `HEAD` has moved, re-read `engine/guard.py`, `kernel/hooks/worktree-guard.sh`,
`engine/tests/test_guard.py`, and `engine/tests/test_guard_hook_wrappers.py` fresh
before editing — this plan quotes exact current line numbers (as of row 2's commit)
that will drift.

## 3. Design (binding; see ADR 0001 for rationale)

### 3.1 Shared extraction primitives (new; duplicated verbatim in both files, parity-tested)

Add to **both** `engine/guard.py` and the embedded Python block in
`kernel/hooks/worktree-guard.sh` (same names/logic in both, consistent with how
`_segments`/`_skip_wrappers`/`classify_mutating` are already duplicated verbatim
across the two files for the identical reason — kernel-first: the hook must work
with zero dependency on the `engine` package being importable):

```python
_PATH_ARG_VERBS = {"rm", "mv", "cp", "mkdir", "rmdir", "ln", "chmod", "chown",
                    "unlink", "shred"}
# Explicitly OUT of scope for v1 (conservative fallback unchanged) -- see ADR 0001 §3:
# "install", "truncate", "dd", "tee" (ambiguous/key-value argument shapes), all _PKG
# package-manager verbs (cwd-relative mutation with no explicit path argument -- cwd-based
# classification is already correct for these, not a gap), and interpreter -c/-e bodies
# (recursion already exists via classify_mutating; left conservative for v1, see §6).

def _has_glob_metachar(s: str) -> bool:
    return any(c in s for c in "*?[")

def _extract_candidate_targets(prog, rest, cwd):
    """Positional (non-flag) arguments for a path-mutating verb, resolved to absolute
    paths. Returns None (== "extraction not confident, fall back to cwd-only
    classification for this whole command") when there are no positional args, or
    when ANY of them contains a shell glob metacharacter (cannot be resolved without
    actually running the shell) -- never a partial list."""
    if prog in _PATH_ARG_VERBS or (prog in _INPLACE and any(
            a == "-i" or a.startswith("-i") for a in rest)):
        positional = [a for a in rest if not a.startswith("-")]
        if not positional or any(_has_glob_metachar(a) for a in positional):
            return None
        return [a if os.path.isabs(a) else os.path.join(cwd, a) for a in positional]
    return None

def _extract_git_target_dir(rest, cwd):
    """git's -C / --git-dir / --work-tree redirect ITS OWN real working directory,
    independent of the shell's cwd -- mirrors the existing arg-skip loop that already
    walks these same flags to find the subcommand. Returns an absolute path (cwd
    itself when no redirecting flag is present)."""
    j, target = 0, cwd
    while j < len(rest):
        a = rest[j]
        if a == "-C" and j + 1 < len(rest):
            target = rest[j + 1]; j += 2; continue
        if a.startswith("--git-dir=") or a.startswith("--work-tree="):
            target = a.split("=", 1)[1]; j += 1; continue
        if a in ("--git-dir", "--work-tree") and j + 1 < len(rest):
            target = rest[j + 1]; j += 2; continue
        j += 1
    return target if os.path.isabs(target) else os.path.join(cwd, target)

_MAX_PRECISE_TARGETS = 8  # bound worst-case classification calls per command; more
                          # than this falls back to cwd-only (conservative, cheap check)

def _collect_precise_targets(command, cwd):
    """Per-segment target collection for a command already known to be mutating
    (classify_mutating(command) is True). Returns None when ANY mutating segment's
    target(s) cannot be confidently resolved -- one command, one decision (ADR 0001
    §4): a single unscoped mutating segment poisons the whole command back to
    cwd-only classification. Returns a deduped list (possibly empty only if there
    were zero mutating segments, which cannot happen given the precondition) otherwise."""
    try:
        segs = _segments(command)
    except ValueError:
        return None
    targets = []
    for toks in segs:
        if not _segment_is_mutating(toks):
            continue
        i = _skip_wrappers(toks)
        if i >= len(toks) or toks[i].startswith("-"):
            return None  # dangling/wrapper-obscured program -- do not guess
        prog = os.path.basename(toks[i])
        rest = toks[i + 1:]
        if prog == "git":
            targets.append(_extract_git_target_dir(rest, cwd))
            continue
        found = _extract_candidate_targets(prog, rest, cwd)
        if found is None:
            return None
        targets.extend(found)
    deduped = sorted(set(targets))
    return deduped[:_MAX_PRECISE_TARGETS] if len(deduped) <= _MAX_PRECISE_TARGETS else None
```

Notes for the implementing agent:

- `_extract_candidate_targets` deliberately checks **every** positional argument for
  `mv`/`cp`/`ln` (not just the destination) — the source is also removed/altered by
  `mv` and must be checked too (ADR 0001 §3 "all positional args", confirmed by the
  `test_mv_cp_both_source_and_dest_checked` acceptance test in §5).
- Redirect targets (`>`, `>>`, etc.) are already extracted by the existing
  `_segment_is_mutating` redirect check — they do not need a second extraction path,
  but **do** need to flow into `_collect_precise_targets`'s returned list; add them
  there (loop the same redirect-token scan already present in `_segment_is_mutating`
  and append any non-`/dev/*` target, resolved absolute) rather than duplicating the
  safe-target-suffix logic a second time.
- A command with a redirect target AND a `_PATH_ARG_VERBS` program in the same
  segment (rare but possible, e.g. `rm -v f > /tmp/log`) must collect targets from
  **both** sources for that segment.

### 3.2 `engine/guard.py` (Python-native path; used by the advisory `awa_guard_shell` MCP tool)

Add a helper that mirrors `decide_shell`'s own primary-classification steps
(reusing `gitutil.resolve`, `lease_mod.read_lease`, `policy_mod.classify` — do not
reimplement policy logic):

```python
def _path_is_protected_primary(path: str, cfg: policy_mod.PolicyConfig) -> bool:
    ctx = gitutil.resolve(path)
    if not ctx.is_git or ctx.is_linked:
        return False
    lz = lease_mod.read_lease(ctx.toplevel or path)
    if lz and lz.get("status", "active") == "active":
        return False
    root = _governed_root(ctx.toplevel or path, cfg)
    rel = _rel(ctx.toplevel or path, root)
    cls = policy_mod.classify(
        rel, ctx.toplevel, cfg,
        hooks_path=_hooks_path(path), has_origin=bool(_origin(path)),
        is_root=(rel == "."), is_standalone=_is_standalone(ctx.toplevel or path, cfg))
    return cls.classification == policy_mod.INCLUDE
```

In `decide_shell` (`engine/guard.py`, current lines 300-339), insert the narrowing
**immediately before** the existing `if classify_mutating(command): return
Decision("deny", ...)` line — do not touch anything before it:

```python
    if classify_mutating(command):
        targets = _collect_precise_targets(command, cwd)
        if targets is not None and not any(
                _path_is_protected_primary(t, cfg) for t in targets):
            return _allow(
                "mutating command, but every resolved target is outside any "
                "protected primary checkout", cls.classification)
        return Decision("deny", _DENY_REASON, cls.classification)
    return _allow("read-only command on primary", cls.classification)
```

### 3.3 `kernel/hooks/worktree-guard.sh` (the live enforcement hook — this is the change that actually matters for protection)

**Do not reimplement policy classification in the embedded Python.** The bash side
already has a proven, tested, live primitive for "is this arbitrary path a protected
primary?" — `classify_dir()` (lines 396-404), which shells out to
`dev-worktree.sh status`. The `afterFileEdit` handler (lines 529-547) already loops
over multiple resolved paths with exactly this probe — reuse that shape, not a new
one.

**Step A — embedded Python (inside the `HOOK_INPUT="$input" python3 - <<'PY' ... PY`
block, current lines 48-339):** add `_PATH_ARG_VERBS`, `_has_glob_metachar`,
`_extract_candidate_targets`, `_extract_git_target_dir`, `_collect_precise_targets`
from §3.1 verbatim (same names/logic as `engine/guard.py`, so the two stay
provably-parity-testable). Then, near the existing `resolved = []` block (lines
290-294) or immediately after, compute:

```python
mut_targets = _collect_precise_targets(cmd, workspace) if classify_mutating(cmd) else None
```

and add two new `print()` lines alongside the existing ones (after line 338's
`paths=(...)` line):

```python
print("has_mut_targets=%s" % ("yes" if mut_targets is not None else "no"))
print("mut_targets=(%s)" % " ".join(shlex.quote(t) for t in (mut_targets or [])))
```

(These become new bash array/scalar variables via the existing `eval "$(...)"`
single-parse mechanism — no new subprocess spawn, no change to the perf-critical
single-python-invocation design.)

**Step B — new bash helper** (place near `classify_dir`, after line 404):

```bash
# Is $1 (an already-resolved absolute path) inside a PROTECTED PRIMARY checkout?
# Mirrors the file-edit handler's own dir_for_probe + classify_dir probe (lines
# 529-547) applied to a candidate mutation target instead of an edited file. Fails
# CLOSED (treats as protected) when the path looks governed but couldn't be
# classified -- uncertainty must never resolve toward allowing an unscoped mutation.
target_is_protected_primary() {
  local target="$1" probe status classification linked
  probe="$(dir_for_probe "$target")"
  [ -n "$probe" ] || return 0
  status="$(classify_dir "$probe" || true)"
  if [ -z "$status" ]; then
    included_looking_path "$probe"   # 0 (protected) if plausibly governed, else 1
    return $?
  fi
  classification="$(printf '%s\n' "$status" | awk -F': ' '$1=="classification"{print $2; exit}')"
  linked="$(printf '%s\n' "$status" | awk -F': ' '$1=="linked-worktree"{print $2; exit}')"
  [ "$classification" = "include" ] && [ "$linked" = "no" ]
}
```

**Step C — wire it into `check_probe`'s mutating branch** (current lines 574-588).
Insert the narrowing between the existing `is_uncertain_include` check and the
existing `respond_deny` call — change only this:

```bash
      # CONFIRMED mutating command on an included primary -> enforced DENY. Cursor honors deny;
      # ask is non-blocking (L4), so deny is the only shape that actually prevents the mutation.
      respond_deny \
        "I didn't make that change, so nothing in your original files was touched. Let's keep going in a separate safe copy instead." \
        "AWA DENIED a mutating command on an INCLUDED PRIMARY checkout ..."
      exit 0
```

to:

```bash
      # NEW: additive narrowing (ADR 0001). If every resolved target is confidently
      # outside any protected primary, the command cannot mutate protected content --
      # allow. Any uncertainty (has_mut_targets=no, or ANY target IS protected) falls
      # through to the existing, unchanged deny below.
      if [ "$has_mut_targets" = "yes" ]; then
        any_target_protected=0
        for _t in "${mut_targets[@]}"; do
          target_is_protected_primary "$_t" && { any_target_protected=1; break; }
        done
        if [ "$any_target_protected" -eq 0 ]; then
          respond_allow
          exit 0
        fi
      fi
      # CONFIRMED mutating command on an included primary -> enforced DENY. Cursor honors deny;
      # ask is non-blocking (L4), so deny is the only shape that actually prevents the mutation.
      respond_deny \
        "I didn't make that change, so nothing in your original files was touched. Let's keep going in a separate safe copy instead." \
        "AWA DENIED a mutating command on an INCLUDED PRIMARY checkout ..."
      exit 0
```

(Keep the existing `agent_message` text byte-identical — it is asserted on on by
existing tests' `assertIn("user_message", resp)` / frozen `deny_shape` contract;
only the new branch above it is added.)

**Do not touch** the `is_uncertain_include` branch, the `payload_ok != yes` branch,
`respond_ask`, `respond_allow`, the fast-path non-mutating short-circuit (lines
493-498), or anything in the `file-edit` event branch — none of those are in scope.

## 4. Execution steps

### 4A. Bootstrap `docs/` governance (one-time; this repo has none today — row 9)

1. Create `docs/plans/README.md` and `docs/adr/README.md` — use the two files staged
   alongside this plan (`docs-plans-README.md` and `docs-adr-README.md` in the same
   handoff batch) verbatim as their content; they already carry the correct index
   rows and the doc-warden forward-compatibility caveat from row 11.
2. Create `docs/adr/0001-target-path-aware-mutation-scope.md` from the staged file of
   the same base name — this is the ADR this plan executes.
3. Create `docs/plans/guard-target-path-precision-v1.md` — this is this plan
   document itself, persisted as the canonical, frozen-on-approval record once
   approved (see §7).
4. Append to the end of `AGENTS.md` (which exists today with only a
   continual-learning pointer section — do not remove that section):

   ```markdown

   ## Planning documents and architecture decisions

   Before starting or acting on any substantial execution/design plan, read
   `docs/plans/README.md` first — the authored convention plus a status-tagged index
   of every plan in the directory.

   Before recording (or looking up the rationale for) a durable architecture
   decision, read `docs/adr/README.md` — the ADR format, numbering, and status
   convention, plus an index of every record.
   ```

### 4B. Implement the fix

5. Apply §3.1 + §3.2 to `engine/guard.py`.
6. Apply §3.1 + §3.3 (Steps A–C) to `kernel/hooks/worktree-guard.sh`.
7. Add the new tests from §5 to `engine/tests/test_guard.py` and
   `engine/tests/test_guard_hook_wrappers.py`.
8. Run `make test`, then the full `make verify`. **Every pre-existing test must
   still pass unchanged** — that is the regression proof that nothing was weakened,
   not just that the new tests pass. If any pre-existing test fails, stop and
   re-examine the change against ADR 0001 §1 (additive-only) before touching a test
   to make it pass.

### 4C. Ship it

9. Bump the version in both `engine/__init__.py` and `pyproject.toml` from `1.1.1`
   to `1.2.0` (minor: backward-compatible narrowing of false positives, no behavior
   removed).
10. Commit (conventional-commits style, matching this repo's existing log, e.g.
    `fix(guard): target-path-aware mutation scope (ADR 0001)`), push a feature
    branch, open a PR. Do not touch `.github`, `CODEOWNERS`, or `_ops` — none of
    this work should need to.
11. Let the repo's own `pr-automation/v3` automation run its course (verifier App
    check `pr-automation / verify`, then the reviewer App's normal approve +
    auto-merge on green — row 14). **Do not run `gh pr merge --auto`, enable/disable
    native auto-merge, or otherwise arm the merge yourself** — that gate belongs to
    the reviewer App. If a check fails or anything looks anomalous, stop and report
    rather than retry blindly.
12. After merge, in `~/dev/capabilities/awa`: pull `main` to the merge commit,
    `git tag v1.2.0`, `gh release create v1.2.0 --title "AWA v1.2.0" --notes
    "Target-path-aware mutation scope (ADR 0001) -- a mutating command whose
    resolved target is outside every protected primary checkout now allows instead
    of denying."`.
13. Run `make repair` (`./install.sh --repair`) to deploy the fix into the actually
    enforcing `~/.local/share/awa/current` runtime.
14. **Live-verify against the original reported defect**: from inside a real
    protected primary checkout (e.g. `~/dev/personal/pr-automation-controller`),
    attempt `rm -f /tmp/awa-guard-precision-livecheck-<timestamp>` (create the file
    first) and confirm it now succeeds where it previously would have been denied.
    Then confirm a same-repo mutation (e.g. `rm` of a scratch file created inside
    that repo's own working tree) is **still denied**, unchanged. Report both
    outcomes to the operator.

## 5. Acceptance-test ledger

New tests (add to `engine/tests/test_guard.py`, class `TestDecideShellDegraded`
unless noted; mirror the existing file's naming/style exactly):

| Test | Setup | Expected |
|---|---|---|
| `test_precise_target_outside_any_repo_allows` | cwd = protected repo; cmd = `rm -f {tmp path outside any repo}` | `allow` |
| `test_precise_target_inside_same_primary_still_denies` | cwd = protected repo; cmd = `rm -f {relative path resolving inside that repo}` | `deny` (unchanged) |
| `test_precise_target_inside_another_protected_primary_denies` | two separate repos, both included; cwd = repo A; cmd targets a path inside repo B | `deny` (protects B) |
| `test_precise_target_inside_linked_worktree_allows` | target resolves inside a linked worktree of some repo | `allow` |
| `test_precise_target_inside_excluded_or_advisory_repo_allows` | target resolves inside a standalone/advisory or excluded repo | `allow` |
| `test_glob_target_falls_back_conservative_denies` | cwd = protected repo; cmd = `rm -rf *` | `deny` (unchanged, conservative) |
| `test_multiple_targets_any_protected_denies` | cmd touches one safe path and one path inside a protected repo | `deny` |
| `test_mv_cp_source_and_dest_both_checked` | destination outside, source inside the protected repo (and the reverse) | `deny` in both directions |
| `test_git_dash_c_target_redirects_classification` | cwd = repo A (protected); cmd = `git -C {repo B} commit -am x` | `deny` when B is protected, `allow` when B is a linked worktree/excluded |
| `test_too_many_targets_falls_back_conservative` | cmd names more than `_MAX_PRECISE_TARGETS` distinct targets | `deny` (unchanged, conservative — bounded-cost fallback) |
| `test_unresolvable_target_conservative_denies` | a target that cannot be classified and does not look governed at all is fine (`allow`); one that looks plausibly governed but can't be classified | `deny`/protected-leaning result, never a silent allow on genuine uncertainty |
| all pre-existing tests in `test_guard.py` | unchanged | must still pass byte-for-byte (regression proof) |

Add to `engine/tests/test_guard_hook_wrappers.py` (subprocess-through-the-real-hook
parity; a smaller mirrored subset per that file's own existing convention relative
to `test_guard.py`'s fuller matrix):

| Test | Setup | Expected |
|---|---|---|
| `test_target_outside_governed_root_allows` | real hook subprocess; payload cwd = repo; command = `rm -f /outside/path` | `permission: allow` |
| `test_target_inside_primary_still_denies` | same, target resolves inside the repo | `permission: deny`, frozen `deny_shape` intact |
| `test_git_dash_c_target_parity` | payload command = `git -C {other repo} commit -am x` | matches the engine-level test's allow/deny split |
| all pre-existing tests in `test_guard_hook_wrappers.py` | unchanged | must still pass byte-for-byte |

**Closing acceptance proof** (not a unit test — a live, manual re-run of the
originally reported defect, §4C step 14): the exact `/tmp` `rm` scenario that
motivated this plan must now allow, post-deploy, on the real installed hook.

## 6. Non-goals (explicit)

- **Not fixing [issue #75](https://github.com/KleinPerkins/awa/issues/75).** That
  defect is "a non-mutating verb is somehow still denied" — a classifier
  misidentification bug with an unknown root cause (suspected live-payload
  tokenization divergence), requiring live-payload capture forensics this plan does
  not perform. This plan's defect is "a confirmed-mutating verb ignores its own
  target" — a different, fully-diagnosed, deterministic gap. Do not conflate the two
  in the PR description or commit message.
- **Not fixing [issue #34](https://github.com/KleinPerkins/awa/issues/34).**
  Different subsystem (`branch_is_cleanup_safe`, worktree-cleanup safety), unrelated
  code path.
- **Not refactoring `kernel/hooks/worktree-guard.sh` to import `engine/guard.py`.**
  The kernel-first duplication-with-parity-tests pattern is retained (ADR 0001 §5).
- **Not extending precision to** `install`, `truncate`, `dd`, `tee`, package-manager
  verbs (`_PKG`), or interpreter `-c`/`-e` recursive script bodies. These keep
  exactly today's cwd-only behavior. Reasonable fast-follow scope, not required for
  this fix to be sound (ADR 0001 Consequences).
- **Not changing** the cloud/background-agent degrade-to-allow logic, the
  operator-override env var, the lease/linked-worktree allow paths, the
  `afterFileEdit` handler, or any `respond_ask` branch — none are touched by this
  design.

## 7. Owner GO/NO-GO gate

The executing agent may proceed autonomously through §4A–§4B (docs bootstrap,
implementation, full local test suite green) without pausing for the operator —
this is bounded, fully-specified, low-ambiguity work with a hard regression gate
(§4B step 8) that fails loudly if anything is wrong.

**Pause and report to the operator before merging (§4C step 11)** if: any
pre-existing test fails and the cause is not obviously a mechanical fix; the
verifier or reviewer App behaves unexpectedly (e.g. does not run, or denies for a
reason unrelated to this change); or live re-verification (§4C step 14) does not
reproduce the expected allow/deny split. Otherwise, the standard fleet
verify-then-auto-merge path (row 14) is the same one every other non-protected-path
PR in this repo already goes through unattended — do not add a manual approval gate
this repo's own governance doesn't otherwise require, and do not self-arm the merge
either way.

Once merged, tagged, released, deployed, and live-verified (§4C steps 12–14), this
plan's own `**Status:**` line should be updated in a **new** frozen note only if a
correction is needed (per `docs/adr/README.md`'s and `docs/plans/README.md`'s own
freeze-on-approval rule) — otherwise flip this file's `Status:` bullet to
`COMPLETE — <date>` in place, since a plan document (unlike an ADR) is explicitly
allowed to carry its own completion status without being "frozen" in the same
byte-identical sense until superseded.
