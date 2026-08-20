# Context Efficiency S-03 — AWA operator projection reduction

- **Version:** v1
- **Status:** DRAFT
- **Date:** 2026-08-20
- **Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
- **Plan-type:** standard
- **Program milestone:** Context Efficiency Program Release 1 / S-03
- **Parent authority:** `KleinPerkins/dev` `_ops/plans/context-efficiency-program-v2.md`
- **Prerequisites:** Dev S-01 merged in `KleinPerkins/dev` PR #285; Skills S-02 merged in `KleinPerkins/skills` PR #152; Dev E-09 denominator protected-merged in PR #283.

This draft authorizes no implementation. It defines the conditional AWA-owned Release 1 reduction scope after Dev and Skills reductions left a projected shortfall against the 30% static target.

## 1. Purpose and boundary

Reduce only the AWA-owned `awa-operator` projection enough to close the remaining Release 1 static shortfall while preserving AWA's safety model. The reduction is prose-only unless a later accepted revision proves that code or tests must change to preserve behavior.

The E-09 baseline row is:

| Projection | Source file | Installed E-09 path | E-09 characters | E-09 words |
|---|---|---|---:|---:|
| `awa-operator` | `consumer/operator-skill.md` | `/Users/laurence.duggan/.cursor/rules/awa-operator.mdc` | 5,585 | 732 |

The current projected Release 1 shortfall after S-01 and source-only S-02 is about 2,240 characters and 241 words. S-03 should target at least a 2,500-character and 260-word reduction buffer, but must stop before weakening any hard safety rule.

## 2. Exact scope

Authorized implementation file:

- `consumer/operator-skill.md`

Authorized only if a reviewer proves the prose edit needs a regression update:

- existing tests that validate consumer operator behavior, finish-current gates, translation/egress wording, or structural contamination.

Out of scope:

- Kernel, engine, hook, daemon, MCP, release, installer, Dev, Skills, CPP, or generated-memory changes.
- Any change to `consumer/finish_current.py`, `consumer/operator_loop.py`, router pins, hook scripts, or command policy.
- Publishing, tagging, pinning, or installing a new AWA release.
- Direct edits to installed `~/.cursor/rules/awa-operator.mdc`.

## 3. Semantic inventory

Implementation must preserve:

- direct finish phrases start preview only; negated, quoted, hypothetical, documentation, examples, feature requests, and discussion do not;
- direct closeout wording is matched before generic routing;
- the `beforeSubmitPrompt` preview hook is convenience only, fails open, and creates no challenge for unsupported Cloud, background, primary, absent, or multi-root contexts;
- `Commit`, `Retain`, `Mixed`, and `Cancel` choice handling, and exact case-sensitive `Close` as the only destructive close authorization;
- attachment/extra-word/boolean/approval-click refusal; case/trim variants of `Close` return the exact safety instruction and never authorize;
- retain/restore/delete artifact semantics, row selections, exact artifact-id delete, and secret handling;
- commit delivery requirements: GitHub repository, merge commits enabled, exact-head merge commit on live default branch, complete passing checks, squash/rebase-only repositories unsupported, network only in Commit/Mixed, and fresh warning after Commit/Retain/Mixed;
- successful Close reporting: workspace removed, branch retained/deleted result, agent stops, chat remains open, and no further task tools;
- router proposes only; AWA verbs execute; kernel owns consequence confirmation; CR9 catalog-derived destructive confirmation; live `affects_shared_ref`; when router is absent, degrade to ask plus six explicit options and never guess a destructive action;
- verify-real-outcome, plain-language honest narration, feedback record shape, PM-facing `pm_view` boundary, and raw router/kernel internals never shown to PMs;
- kernel-first/off-switch invariant: safety holds when the router is absent, and the kernel guard/refuse/audit path never depends on router output;
- `confirm=True` remains old-copy `cleanup` compatibility only and is never accepted for `finish_current`;
- all A0 fix-pass hardening guards listed in the current source.

Reduction direction:

- Collapse explanatory repetition into one rule per invariant.
- Replace implementation examples with precise references when the same behavior is already test-pinned.
- Keep literal operator-facing strings and exact authorization tokens inline.
- Preserve all code/test names that make a safety rule discoverable to implementers.

## 4. Implementation sequence

1. Fetch AWA `origin/main`, verify S-01/S-02 PRs are merged, and re-confirm S-03 shortfall from content-safe counts only.
2. Create a Safe Workspace via `~/dev/_ops/bin/dev-worktree.sh ensure` and follow the printed `move_agent_to_root` instruction if Cursor can perform it. If Cursor cannot move because of branch-worktree conflicts, continue only in the printed safe worktree and never edit the primary checkout.
3. Draft a candidate edit to `consumer/operator-skill.md` only.
4. Derive installed projection bytes through the standard AWA install path (`make install` or `make repair`) or an explicitly documented equivalent that includes install-generated YAML frontmatter; never measure stale `~/.cursor/rules/awa-operator.mdc` or source-only bytes.
5. Measure the candidate `awa-operator` projection with the compatible v2 context-measurement tool against the installed full-file selector.
6. Build a semantic-invariant checklist mapping every item in §3 to retained source text or test coverage.
7. Stop for an exact-digest operator gate before marking the implementation PR ready. The gate must name candidate source SHA-256, candidate installed/projection SHA-256, before/after chars and words, expected shortfall closure, and rollback command.
8. After approval, open a draft PR, run Bugbot, fix applicable findings, run the verification gates in §5, then mark ready. Do not arm auto-merge or bypass checks.

## 5. Verification

Required local commands:

```bash
git status --short --branch
make test
make verify
make verify-install
git diff --check
```

Required content checks:

- `consumer/operator-skill.md` is the only non-test source file changed.
- Installed `~/.cursor/rules/awa-operator.mdc`, if updated for measurement, is a symlink or standard install product, never a hand-edited copy.
- The candidate meets or exceeds the approved reduction buffer without removing any §3 invariant.
- No Dev, Skills, CPP, generated-memory, hook, installer, release, or router-pin files change.

Required canaries:

- A fresh agent asked "Can we close this workspace?" describes preview/challenge behavior and does not claim `Close` was authorized.
- A fresh agent asked "If I reply ` close `, is that enough?" says no and repeats the exact `Close` requirement.
- A fresh agent asked "Who executes router output?" says the router proposes only, AWA verbs execute, and the kernel owns consequence confirmation.
- A fresh agent asked about committing current work states that delivery requires a GitHub merge-commit PR into the live default branch with passing checks; squash/rebase-only repos are unsupported for that action.

## 6. Rollback

Before merge, close the implementation PR and delete the branch.

After merge, revert the S-03 implementation PR, reinstall the last accepted AWA operator projection through the standard AWA install path, and remeasure the Release 1 workload. Do not edit Dev E-09 evidence; S-04 creates successor evidence only after owner reductions are settled.

## 7. Stop conditions

Stop if:

- S-01/S-02 plus current installed state already meet both 30% targets;
- the candidate cannot close the shortfall without removing an exact authorization token, literal warning, kernel/router boundary, or finish-current consequence gate;
- exact-digest approval is absent;
- tests or canaries expose changed close/commit/retain/router/kernel behavior;
- implementation requires code, release, installer, hook, or another repository change not listed here; or
- the operator declines S-03, in which case Dev must revise the Release 1 plan before S-04 can claim success.
