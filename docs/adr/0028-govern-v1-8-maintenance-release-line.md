# ADR 0028: Govern one AWA v1.8 maintenance release line
Status: accepted — 2026-10-06

## Context

AWA `v1.8.1` is the installed and Skills-bound release at
`ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`. The hard-no-touch host-policy
contract from accepted ADR 0027 merged through
[PR #184](https://github.com/KleinPerkins/awa/pull/184): reviewed head
`c4a29c7cc2f2399c0eba4e940dfb827cf5eb624d`, squash merge
`07f5f5820e27ad7557f3b7898fabcc6b41b799be`, and shared tree
`5cec9ece1ede3d048cc253883ccffb2a4cf754d0`.

The commits between `v1.8.1` and PR #184 include separately gated durable
registration work. Its accepted governance keeps release, installation, and
activation distinct and ungranted. Tagging or installing current `main` would
therefore ship unrelated work without its release gates.

An isolated read-only assessment applied the PR #184 change set to exact
`v1.8.1`. Runtime and test hunks applied without semantic conflict. Only the
ADR index, plan index, and historical source-hash record required mechanical
release-line reconciliation. A synthetic `1.8.2` candidate then passed the
31-test hard-no-touch suite, `make verify`, `make verify-install`, doc-warden,
and `git diff --check`, with no registration file in the candidate.

The existing governance cannot yet merge such a candidate:

- `.github/pr-automation.json` names only default branch `main`;
- controller source at `d244f69a1808da25d86c1762466bc6015941dc98`
  rejects a pull request when `base_ref != configured.default_branch`;
- controller policy schema v3 has no maintenance-base allowlist; and
- live ruleset `kleinperkins-merge-safety` targets only `refs/heads/main`.

Creating `release/1.8` now would create an ungoverned shared ref. Directly
tagging a detached candidate would bypass the exact reviewed-merge
provenance used by every recent AWA release.

## Decision

### 1. Authorize exactly one maintenance line

AWA authorizes one persistent maintenance base named exactly
`release/1.8`, created from exact commit
`ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` only after controller eligibility
and native protection are live.

This is not a general feature branch. It may receive only:

1. backward-compatible safety or critical corrective changes already merged
   and reviewed on `main`;
2. release-identity and release-line provenance changes mechanically required
   to publish that correction; and
3. a follow-up corrective patch required to fix a proven defect in the
   maintenance release itself.

The first and currently sole authorized backport is ADR 0027 / PR #184 for
`v1.8.2`. Any other source change requires a successor decision naming its
source merge, risk class, and release.

### 2. Keep ownership split and serial

- **AWA** owns this product release policy, patch scope, exact release base,
  candidate verification, release identity, and Release GO.
- **`KleinPerkins/pr-automation-controller`** owns generic support for
  controller/verifier/reviewer operation on an explicitly allowed
  non-default PR base. AWA must not copy or locally reimplement controller
  authority.
- **GitHub repository settings** own branch protection. The maintenance ref
  must be covered before it exists by a ruleset targeting exactly
  `refs/heads/release/1.8`.
- **KleinPerkins/skills** owns the immutable release descriptor after an AWA
  release exists.
- **KleinPerkins/dev** owns host literals after the exact runtime is bound and
  installed.

Each owner merges independently. No step implies or authorizes the next.

### 3. Preserve runnerless-v3 merge guarantees

A pull request targeting `release/1.8` is eligible only when the deployed
controller:

- recognizes that exact base through a closed, repository-scoped allowlist
  read from trusted default-branch authority;
- retains `main` as the GitHub and configured default branch;
- binds base ref, live base SHA, exact head SHA, open episode, patch digest,
  policy digest, ruleset digest, and activation generation;
- posts the verifier-owned `pr-automation / verify` and
  `pr-automation / job:repo.awa.engine-tests` checks on the exact head;
- permits reviewer-App approval and native squash auto-merge only after every
  ordinary exact-head condition passes; and
- rejects every other non-default base.

Agents never arm or alter auto-merge and never merge manually. No required
human review, code-owner review, GitHub Actions workflow, hosted runner, or
self-hosted runner is introduced.

### 4. Protect before creating

Before `release/1.8` exists, an active ruleset must target that exact ref and
require:

- pull requests with resolved review conversations and squash-only merge;
- linear history;
- both verifier-App checks named above, strict against the current base;
- branch deletion protection; and
- force-push/non-fast-forward protection.

Required approving-review count and code-owner review remain zero so the
reviewer App is not made unsatisfiable. The ruleset must be previewed, applied,
read back, fingerprinted, and accepted by deployed controller policy before
the branch is created. If GitHub cannot prove the ruleset applies to the
not-yet-created ref, branch creation stops.

The branch is then created once, directly at exact `v1.8.1` commit
`ff978ade...`. The first read-back must prove both exact SHA and protection.
No direct update to the branch is allowed after creation.

### 5. Require exact backport provenance

The `v1.8.2` candidate must:

- start from live `release/1.8` at exact `ff978ade...`;
- carry PR #184's accepted ADR/plan, product docs, kernel and engine matchers,
  policy-check validation, default policy, and tests;
- reconcile only release-line indexes and bound historical hashes;
- set both version declarations and their regression to `1.8.2`;
- contain no post-`v1.8.1` registration/native-entry implementation;
- pass focused parity, compatibility, contamination, kernel-off,
  router-uninstalled, full verify, full throwaway install, doc-warden, and
  diff checks; and
- merge through a normal ready PR whose base is exactly `release/1.8`.

The squash merge tree must equal the reviewed candidate tree. The source
PR/head/main-merge/tree and maintenance PR/head/merge/tree are all retained in
release provenance.

### 6. Keep Release GO separate

Maintenance PR merge authorizes no tag, GitHub release, Skills pin, install,
host literal, consumer change, or activation. Publishing requires a later
explicit operator instruction:

```text
GO to publish AWA v1.8.2 at <exact-release/1.8-merge-sha>.
```

The evidence must include exact merge/tree equality, version equality, all
verification receipts, controller approval/checks, ruleset read-back,
rollback to `v1.8.1`, release notes, and confirmation that downstream steps
have not run.

### 7. Synchronize by provenance, not branch merging

PR #184 is already canonical on `main`; the maintenance branch never merges
back into `main`, and `main` is never merged wholesale into `release/1.8`.
Release notes and downstream bindings name both source and maintenance
provenance. A later mainline release includes the same contract from PR #184
without replaying the maintenance commit.

### 8. End the line explicitly

`release/1.8` reaches EOL after all of the following:

1. a later governed mainline AWA release contains ADR 0027;
2. Skills and the installed runtime have moved to that later release; and
3. no supported consumer remains pinned to `v1.8.x`.

EOL removes merge eligibility first. Branch deletion remains protected and
requires a separate explicit decision; EOL never silently deletes the ref or
moves an immutable tag.

## Why

- Releasing current `main` violates unrelated registration release gates.
- A direct detached tag lacks reviewed-merge provenance.
- A protected maintenance line retains narrow scope while preserving the
  existing exact-head, reviewer-App, and immutable-pin model.
- A dedicated exact-ref ruleset avoids weakening `main` and can be activated
  before branch creation.
- One-way provenance prevents a long-lived feature fork and eliminates a
  future merge-back conflict.

## Consequences

Positive:

- ADR 0027 can ship without unreleased registration code.
- The patch remains independently reviewable, rollbackable, and exactly
  pinned.
- Mainline and maintenance provenance remain explicit and non-conflicting.

Costs and constraints:

- Controller-owned multi-base support must ship before AWA can create the
  maintenance ref.
- Ruleset policy and controller fingerprints require a coordinated but serial
  activation.
- The maintenance line is intentionally single-purpose and temporary.

## Live-state verification record

Read-only verification on 2026-10-06 established:

- AWA worktree and `origin/main` were clean at `07f5f582...`;
- `v1.8.1` tag object `15c1634d8468bdf42da9f561d24dee635a6df9b7`
  dereferenced to `ff978ade...`;
- PR #184's reviewed and merged trees were equal;
- all five PR #184 checks passed and reviewer-App approval bound
  `c4a29c7c...`;
- repository merge mode was squash-only with auto-merge and source-branch
  deletion enabled;
- the sole live merge-safety ruleset targeted only `main`;
- no `release/1.8` remote ref, `v1.8.2` tag, or open maintenance PR existed;
- controller code and schema enforced one configured default base; and
- no standing AWA backport/maintenance-line policy existed.

## Acceptance

The operator's 2026-10-06 instruction explicitly authorizes this narrow
maintenance path and its governance stage. Execution is governed by
[`awa-v1-8-maintenance-release-v1.md`](../plans/awa-v1-8-maintenance-release-v1.md).
This accepted ADR is immutable; broader maintenance support requires a
successor.
