# Hard-No-Touch Host-Policy Contract

- **Version:** v1
- **Status:** ACCEPTED — FROZEN
- **Date:** 2026-10-06
- **Architecture authority:** accepted
  [ADR 0027](../adr/0027-hard-no-touch-host-policy.md)
- **Relates to:** accepted
  [ADR 0002](../adr/0002-awa-dev-overlay.md) and
  [ADR 0020](../adr/0020-awa-integrity-surveillance-and-lifecycle.md)
- **Implementation baseline:** clean AWA `main`
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`
- **Plan type:** bounded agentic execution
- **Approval record:** the operator accepted the exact generic semantics and
  authorized implementation plus one normal ready AWA pull request on
  2026-10-06

**Goal:** Add AWA's earliest canonical, generic
`hard_no_touch_paths` host-policy schema and a deterministic matcher that a
consumer can call before opening a child directory or repository.

**Architecture:** The kernel policy module owns a frozen typed lexical matcher;
the engine policy module independently mirrors it. The optional version-1
field contains separately typed exact roots and managed-namespace prefixes.
Malformed policy or candidate input fails closed. Matching performs no target
filesystem, Git, or subprocess access.

> This plan is accepted and immutable. Execute it as written; record completion
> in commits, verification output, and the pull request rather than editing
> checkboxes or status here.

## 1. Scope and authority boundary

AWA owns:

- the optional host-policy field and value shape;
- lexical normalization and component-boundary matching semantics;
- immutable kernel and engine typed representations;
- fail-closed malformed-input behavior;
- kernel/engine parity and no-target-access tests; and
- synthetic product documentation.

The host overlay owns concrete machine literals. Downstream consumers own the
call site that checks a candidate before traversal or repository discovery.
This body does not add those values or that call site.

## 2. Fixed schema and API semantics

Version-1 host policy gains:

```yaml
hard_no_touch_paths:
  exact_roots:
    - /synthetic/protected/root
  managed_namespace_prefixes:
    - ~/synthetic-managed/protected
```

Rules:

1. The top-level field is optional. Absence means a valid empty matcher.
2. A present field is a map with only `exact_roots` and
   `managed_namespace_prefixes`.
3. Each child is an optional list of strings.
4. Entries must be non-empty absolute paths or `~`/`~/...`; reject relative
   paths, `~other`, NULs, glob metacharacters, non-strings, unknown keys, and
   wrong container types.
5. Expand `~` only from an explicit trusted home or exact absolute `HOME`.
6. Normalize `.`, `..`, repeated/trailing separators lexically.
7. Match root equality or `root + path separator` only. Never basename,
   substring, case-fold, or glob match.
8. Preserve entry kind in the decision even though both kinds protect their
   root and descendants.
9. Invalid policy and invalid candidate decisions are matched/refused.
10. A decision exposes no configured root.

Both policy modules expose:

- frozen `HardNoTouchMatcher` and `HardNoTouchDecision` values;
- `PolicyConfig.hard_no_touch_paths`;
- a safe policy-only loader that fails closed when the policy cannot be
  trusted;
- `classify(candidate)` and `matches(candidate)` matcher methods;
- a closed typed policy projection for parity/round-trip tests; and
- a boolean convenience predicate.

## 3. Kernel-first and zero-access boundary

`kernel/lib/awa_policy.py` must remain independently usable with the engine,
daemon, router, and consumer absent. Its matcher may read the host policy file
and trusted home value. During candidate classification it must not invoke:

- `realpath`, `resolve`, `stat`, `lstat`, `open`, or `read`;
- `listdir`, `scandir`, glob expansion, or symlink traversal;
- Git or any subprocess; or
- engine, router, or consumer code.

`engine/policy.py` mirrors the exact interpretation. The existing
repository-stage classifier remains unchanged.

## 4. Implementation worklist

### Task 1 — Freeze governance before runtime mutation

Create accepted ADR 0027, this accepted/frozen plan, and index rows. Run
doc-warden against the repository and commit those bytes before implementation.
Do not edit the accepted files afterward.

### Task 2 — Implement the kernel contract

In `kernel/lib/awa_policy.py`:

- define closed schema/kind constants;
- add frozen decision and matcher dataclasses;
- add trusted-home and lexical path normalization without target access;
- validate and normalize the optional field;
- add the matcher to `PolicyConfig`;
- add the safe policy-only loader and convenience predicate; and
- retain all old-policy and repository-classifier behavior.

Update `kernel/bin/dev-worktree.sh policy-check` so a present malformed field
is rejected rather than silently accepted. Do not add a Git/repository probe or
change shell-command decisions.

### Task 3 — Mirror the engine contract

Implement the same constants, typed values, loader, normalization, matching,
projection, and fail-closed behavior in `engine/policy.py`. Do not import the
kernel at runtime; parity belongs in tests.

### Task 4 — Add synthetic verification

Add a focused test module and extend policy parity coverage for:

- exact root, descendant, and component-sibling nonmatch;
- managed namespace root and recursive descendants;
- trusted `~`, `.`, `..`, repeated/trailing separator normalization;
- empty, relative, NUL, glob, wrong-type, unknown-key, and malformed-map
  rejection;
- invalid policy/candidate fail-closed behavior;
- a spy that fails on candidate `realpath`/resolve/stat/lstat/open/read/list/
  scan/Git/subprocess access;
- optional-field old-policy compatibility;
- typed projection/reparse semantic round trip;
- kernel/engine parity across valid and invalid cases;
- distinction from repository exclude/read-only and lifecycle-only no-touch;
- kernel-off/router-uninstalled structure; and
- absence of concrete host literals from changed global bytes.

Fixtures must be synthetic strings or temporary policy files. Tests must not
create, inspect, or traverse a real protected path.

### Task 5 — Document only the generic contract

Update the generic default policy, README, ARCHITECTURE, and SECURITY boundary
with synthetic examples. State explicitly that:

- AWA supplies the primitive;
- the host supplies values;
- downstream consumers enforce before access;
- lexical aliases require explicit entries; and
- this contract is distinct from lifecycle and repository-stage policy.

Do not duplicate downstream UX, host values, or host rollout instructions.

### Task 6 — Verify and deliver

Run focused tests, the complete repository verification, install/release-source
checks that apply, doc-warden, guard/session/identity checks, and a subtractive
diff review. Commit and push the implementation, open one normal ready AWA
pull request, and leave auto-merge and merge entirely to the controller.

## 5. Acceptance ledger

| Gate | Required evidence |
|---|---|
| G1 Governance | ADR 0027 and this plan are accepted/frozen before runtime edits; indexes resolve; doc-warden is conformant. |
| G2 Schema | Optional version-1 field parses into immutable typed entries; unknown/malformed input fails closed; absent field is compatible. |
| G3 Matching | Root/descendant matches and component-sibling misses hold for both kinds after trusted lexical normalization. |
| G4 Zero target access | Synthetic spies prove classification performs no target filesystem, repository, Git, or subprocess operation. |
| G5 Kernel-first parity | Kernel works with engine/router absent; engine and kernel produce identical projections and decisions. |
| G6 Semantic isolation | Repository exclude/read-only, artifact protection, and `lifecycle_no_touch` retain their existing meanings. |
| G7 Contamination | Product code, tests, and docs contain no concrete host instance or personal absolute path introduced by this body. |
| G8 Verification | Focused tests, `make verify`, applicable install/source checks, doc-warden, and repository guards pass or any pre-existing failure is evidenced. |
| G9 Delivery | One pushed branch and one normal ready PR; no draft, auto-merge mutation, bypass, or manual merge; clean worktree. |

## 6. Non-goals

- Concrete host-policy values.
- Downstream consumer implementation or user-interface behavior.
- Reference/read-only observational selection.
- Changes to existing mode, include/exclude, artifact, cleanup, guard-command,
  or lifecycle behavior.
- Router, MCP, consumer, daemon, database, hook-owner, or host-job changes.
- Release, tag, installation, host activation, live-state mutation, or UAT.
- A universal symlink-identity guarantee without target filesystem access.

## 7. Stop conditions

Stop and report before broadening scope if implementation would require:

- target filesystem or repository access to classify;
- a concrete host literal in global AWA bytes;
- an engine/router/consumer dependency in the kernel;
- changing existing repository or lifecycle decisions;
- editing an accepted ADR or this frozen plan; or
- host, release, installation, or consumer mutation.

## 8. Delivery sequence after merge

This PR ends at the controller-owned AWA merge. Subsequent separately governed
steps are:

1. release/install the merged AWA contract if the consuming environment
   requires installed runtime bytes;
2. add concrete values in the host overlay;
3. update the Skills-owned consumer against the merged contract; and
4. perform separately authorized activation and UAT.

No step is implied or authorized by the prior step.
