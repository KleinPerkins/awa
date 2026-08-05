# ADR 0001: Mutation-scope decisions must be target-path-aware, not cwd-only

Status: proposed — 2026-08-05

## Context

`kernel/hooks/worktree-guard.sh` (the live `beforeShellExecution` gate) and its engine
mirror `engine/guard.py::decide_shell` decide whether to DENY a shell command using
exactly two signals: (1) does the command's resolved program classify as a mutating
verb (`classify_mutating`), and (2) does the shell's **current working directory**
classify as an INCLUDED PRIMARY checkout. Neither function inspects what path(s) the
command's own arguments actually name.

This is provably over-broad. A command such as `rm -f /tmp/scratch.sh`, executed with
`cwd` inside a protected primary checkout, is DENIED even though `/tmp/scratch.sh` is
outside every git working tree and the command cannot mutate any tracked content in the
protected repo. Live reproduction: two consecutive `rm` attempts against
`/tmp/awa-clean-dev.sh` / `/tmp/awa-clean-pac.sh` from `~/dev/personal/pr-automation-controller`
(primary checkout, `default_mode: on`) both returned the enforced `deny` shape, confirmed
by direct code trace against `kernel/hooks/worktree-guard.sh` (installed copy,
byte-identical to source at the time of this record — see the companion plan's live-state
verification record for the exact diff/hash evidence).

This is a distinct defect class from two already-open issues, which this ADR's decision
does not resolve and the companion plan does not attempt to fix:

- [#75](https://github.com/KleinPerkins/awa/issues/75) — some commands whose resolved
  verb is **not** in any mutating set are still denied; hand-tracing the classifier
  offline does not reproduce the live denial. Root cause unknown (suspected
  payload/tokenization divergence for long, multi-line, heredoc-bearing commands);
  needs live-payload forensics before a fix can even be designed. Orthogonal to this
  ADR: that bug is about **misidentifying the verb**; this ADR is about **ignoring the
  target** once the verb is correctly identified as mutating.
- [#34](https://github.com/KleinPerkins/awa/issues/34) — `branch_is_cleanup_safe` (the
  worktree-cleanup safety check, a different function entirely) false-refuses a
  branch that was squash-merged as more than one source commit. Unrelated subsystem
  (cleanup-safety, not shell-command classification).

## Decision

1. **Scope check is additive, never subtractive.** A precise target-path check may only
   ever convert an existing `deny` into `allow` when every resolved target is
   affirmatively proven safe. It must never convert an existing `allow` into `deny`,
   and it must never weaken the fallback: when a target cannot be confidently resolved
   (a shell glob metacharacter, a missing positional argument, an unrecognized verb
   shape), the decision collapses back to today's cwd-only behavior for that command,
   unchanged. Uncertainty always resolves toward protection, never away from it.

2. **The unit of protection is "some protected primary checkout," not "the cwd's
   repo" specifically.** A command run from protected repo A that targets a path
   inside a *different* protected repo B must still DENY — it is protecting B, not A.
   Only when a target resolves to a location owned by **no** protected primary
   (outside any git working tree, or inside a linked worktree / adopted-lease Safe
   Workspace / excluded / advisory repo) does that target count as safe.

3. **Per-verb target extraction is conservative and explicitly bounded (v1 scope).**
   In scope: the plain file-mutating verbs already in `_MUT`
   (`rm mv cp mkdir rmdir ln chmod chown unlink shred` — `install`, `truncate`, `dd`,
   `tee` excluded for now, see Consequences), redirect targets (already extracted by
   existing logic), `sed/perl/gawk/awk -i` in-place targets, and `git`'s own
   `-C` / `--git-dir` / `--work-tree` target-repo redirection (git's *real* working
   directory per its own documented option grammar, independent of the shell's cwd).
   Out of scope for v1, explicitly: package-manager verbs (`npm install` etc. — these
   mutate cwd-relative state with no explicit path argument, so cwd-based
   classification is already the *correct* answer, not a gap), `dd`/`tee`
   (key=value or ambiguous-stdin argument shapes), interpreter `-c`/`-e` recursive
   script bodies, and any argument containing a shell glob metacharacter (cannot be
   safely resolved without executing the shell). All of these keep exactly today's
   cwd-only behavior.

4. **One command, one decision — any unscoped mutating segment poisons the whole
   command back to conservative.** A chained command (`;`, `&&`, `||`, `|`) is
   evaluated per-segment as today; if *any* mutating segment's targets cannot be
   confidently resolved, the entire command falls back to cwd-only classification
   (never a partial allow).

5. **Duplication-with-parity is retained, not refactored away.** `engine/guard.py`
   and the embedded Python in `kernel/hooks/worktree-guard.sh` remain two
   independently-maintained mirrors (as they are today for the rest of the
   classifier), proven identical by `engine/tests/test_guard_hook_wrappers.py`
   subprocess parity tests. Unifying them behind a single importable module is a
   real architectural option (the hook would need a guaranteed-importable
   `engine` package on `PYTHONPATH` at hook-invocation time) but is deliberately
   deferred — it changes hook startup dependencies and is not required to fix the
   defect this ADR addresses. Recorded here so a future ADR can supersede this
   point deliberately rather than by drift.

## Consequences

- False-positive denials for commands whose blast radius is provably outside every
  protected checkout (the reported case, and its whole class) are eliminated,
  without narrowing protection for any command that can actually touch a protected
  primary's tracked content.
- The classifier gains a small, bounded amount of complexity (target extraction +
  resolution + a second classification pass per candidate path) in exchange for
  a meaningfully smaller false-positive surface. The companion plan's acceptance
  tests are the enforcement mechanism that this complexity does not regress any
  existing DENY.
- `install`, `truncate`, `dd`, `tee`, package-manager verbs, and glob-bearing
  arguments remain exactly as conservative as today — real, but explicitly scoped
  and documented, residual over-blocking. A fast-follow may extend precision to
  these; it is not required for this decision to be sound on its own terms.
- Issues [#75](https://github.com/KleinPerkins/awa/issues/75) and
  [#34](https://github.com/KleinPerkins/awa/issues/34) remain open and unaffected;
  this decision does not claim to resolve either.
