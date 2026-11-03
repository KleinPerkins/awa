# ADR 0027: Add a lexical hard-no-touch host-policy contract
Status: accepted — 2026-10-06

## Context

Some host-owned paths must be classified before a consumer opens a child
directory or asks Git to identify a repository. Existing AWA policy fields do
not provide that contract:

- `exclude`, `detectors.read_only_paths`, and modes classify repositories
  after repository discovery;
- `lifecycle_no_touch` protects integrity reconciliation and repair only; and
- a repository identity cannot be used to decide whether opening that
  repository was forbidden.

ADR 0002 assigns the generic host-policy pattern to AWA and concrete host
values to the host overlay. ADR 0020 requires kernel-first safety, engine
parity, and an engine-off safety path. Both accepted records remain
byte-identical.

The operator authorized this exact generic contract and its implementation on
2026-10-06. Host literals, consumer behavior, release, installation, and host
activation remain separately governed.

## Decision

### 1. Add one optional version-1 host-policy field

AWA host policy version 1 gains this additive optional shape:

```yaml
hard_no_touch_paths:
  exact_roots:
    - /synthetic/protected/root
  managed_namespace_prefixes:
    - ~/synthetic-managed/protected
```

`exact_roots` and `managed_namespace_prefixes` are lists of path strings.
Either list may be empty or omitted inside the map. Unknown child keys,
non-list values, non-string entries, empty entries, relative paths, NULs,
user-qualified tildes, and glob metacharacters are malformed.

The field is optional so an existing version-1 policy that omits it produces a
valid empty matcher and retains existing behavior. This additive field does
not justify a host-policy version bump or a new frozen product contract.

### 2. Normalize lexically, never physically

Policy entries and candidate paths use the same lexical normalizer:

1. accept absolute paths plus `~` or `~/...`;
2. expand `~` only from an explicit trusted home or the exact absolute `HOME`
   value—never a user database lookup and never `~other`;
3. normalize separators, trailing separators, `.`, and `..` lexically; and
4. reject an empty, relative, NUL-bearing, or otherwise malformed result.

Classification must not call `realpath`, `resolve`, `stat`, `lstat`, `open`,
`read`, `listdir`, `scandir`, Git, or a subprocess against the candidate.
Symlink aliases therefore do not silently inherit protection from a physical
target; a host that needs multiple lexical aliases lists each alias.

### 3. Match only path-component roots

An exact-root entry matches the normalized root itself and every normalized
descendant. A managed-namespace-prefix entry likewise matches the namespace
root and descendants recursively. Both comparisons require a path-component
boundary:

- `/synthetic/protected` matches `/synthetic/protected` and
  `/synthetic/protected/child`;
- it does not match `/synthetic/protected-sibling`.

The two kinds deliberately share matching mechanics but remain separately
typed. This preserves why a path is protected and lets a downstream consumer
render or govern the categories without basename, substring, or glob
heuristics.

### 4. Expose an immutable kernel matcher with an engine mirror

`kernel/lib/awa_policy.py` is canonical for the engine-off path.
`engine/policy.py` carries an independent mirror, consistent with AWA's
existing policy architecture. Each exposes immutable
`HardNoTouchMatcher`/`HardNoTouchDecision` values through
`PolicyConfig.hard_no_touch_paths`, plus a safe policy-only loader and a
boolean convenience predicate.

The matcher returns only closed outcomes:

- `exact_root`;
- `managed_namespace`;
- `none`;
- `invalid_policy`; or
- `invalid_candidate`.

`invalid_policy` and `invalid_candidate` are matched outcomes. An unreadable
or malformed configured policy therefore cannot silently weaken protection.
`policy-check` rejects a present malformed `hard_no_touch_paths` field. The
decision never returns or logs a configured path.

Kernel and engine parsing, normalization, typed projection, decisions, and
failure behavior are parity-tested. The kernel implementation imports no
engine, router, or consumer code and reads no router output.

### 5. Keep existing meanings distinct

This contract does not change repository inclusion, mode, read-only,
artifact, cleanup, or lifecycle classification:

- `exclude` and modes continue to govern AWA repository eligibility;
- `detectors.read_only_paths` continues to classify reference repositories
  after repository discovery;
- artifact protection continues to govern recovery/retention data; and
- `lifecycle_no_touch` remains limited to lifecycle reconciliation and
  repair.

The new matcher is the pre-access primitive. A downstream consumer must call
it before child-directory or repository access and stop on every matched
outcome. Adding host literals or consumer enforcement is not part of this
decision's AWA implementation.

## Why

- Reusing repository exclusion was rejected because it is evaluated after the
  forbidden repository access and carries a different product meaning.
- Extending `lifecycle_no_touch` was rejected because it is lifecycle-only,
  currently permits glob/physical matching, and would conflate repair
  preservation with universal pre-access refusal.
- `realpath`-based matching was rejected because resolving a target can
  traverse links and inspect the very path that must not be touched.
- Basename, substring, and glob matching were rejected because they
  overmatch siblings and cannot represent a stable root boundary.
- A shared engine import was rejected because engine availability may not
  become load-bearing for kernel safety.
- Embedding concrete host values was rejected by ADR 0002's authority split
  and AWA's zero-link invariant.

## Consequences

Positive:

- AWA owns one portable schema and deterministic pre-access matcher.
- Old policies remain compatible.
- Hosts can supply literals without adding them to global product bytes.
- Synthetic access-spy and parity tests can prove zero target access.

Costs and limits:

- Kernel and engine mirrors must remain in parity.
- Lexical aliases must be configured explicitly.
- The AWA PR alone changes no downstream consumer or live host behavior.
- Release, installation, host values, consumer enforcement, and activation
  remain a serial downstream sequence.

## Live-state verification record

Read-only verification on 2026-10-06 established:

- the governed linked worktree was clean at
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`;
- live `origin/main` resolved to the same commit;
- the worktree was attached to
  `cursor/worktree/awa-20261006125019` before documentation mutation;
- the KleinPerkins noreply commit identity was active;
- the host worktree policy check and worktree doctor were healthy;
- no `_ops/POLICY.md` exists in this repository;
- doc-warden classified the unmodified repository `CONFORMANT`; and
- the current implementation has repository-stage exclusion, read-only, and
  lifecycle-only no-touch policy, but no pre-access hard-no-touch matcher.

## Acceptance and delivery

The operator's 2026-10-06 instruction explicitly accepted this architecture,
accepted the linked frozen plan, and authorized implementation and one normal
ready AWA pull request. That authorization does not authorize host literals,
consumer changes, release, installation, activation, auto-merge control, or
manual merge.

Implementation authority is
[`hard-no-touch-host-policy-v1.md`](../plans/hard-no-touch-host-policy-v1.md).
This accepted ADR is immutable; any material correction requires a successor.
