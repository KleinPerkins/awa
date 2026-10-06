# AWA v1.8 Maintenance Release

- **Version:** v1
- **Status:** ACCEPTED — FROZEN
- **Date:** 2026-10-06
- **Architecture authority:** accepted
  [ADR 0028](../adr/0028-govern-v1-8-maintenance-release-line.md)
- **Relates to:** accepted
  [ADR 0027](../adr/0027-hard-no-touch-host-policy.md) and frozen
  [hard-no-touch plan](hard-no-touch-host-policy-v1.md)
- **Release base:** `v1.8.1`,
  `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`
- **Source change:** [PR #184](https://github.com/KleinPerkins/awa/pull/184),
  reviewed head `c4a29c7cc2f2399c0eba4e940dfb827cf5eb624d`,
  main merge `07f5f5820e27ad7557f3b7898fabcc6b41b799be`,
  tree `5cec9ece1ede3d048cc253883ccffb2a4cf754d0`
- **Target release:** `v1.8.2`
- **Approval record:** the operator authorized a protected,
  controller-governed `release/1.8` maintenance line and this earliest
  governance stage on 2026-10-06

**Goal:** publish ADR 0027 as a narrow `v1.8.2` safety patch without shipping
the separately gated registration work on `main`, while retaining AWA's
runnerless exact-head checks, reviewer-App-only approval/auto-merge, immutable
release provenance, and separate Release GO.

> This plan is accepted and immutable. Execute bodies in order. A completed
> body authorizes no later body. Record progress in PRs and verification
> receipts, never by editing this file.

## 1. Fixed boundary

The only maintenance base is `release/1.8`. The only initial patch source is
ADR 0027 / PR #184. The branch starts at exact `v1.8.1` commit `ff978ade...`
and must not exist until both controller eligibility and native ruleset
protection are live.

The maintenance line is not a second development trunk:

- no feature development;
- no wholesale merge from `main`;
- no merge back to `main`;
- no registration/native-entry implementation after `v1.8.1`;
- no direct push after branch creation;
- no release without exact reviewed merge provenance and separate Release GO;
- no Skills, install, Dev, ShadowSync, or activation work in AWA bodies; and
- no GitHub Actions workflow or paid/self-hosted runner.

## 2. Verified starting state

| Surface | Exact state |
|---|---|
| AWA source | `origin/main` `07f5f582...`; clean linked worktree |
| Installed/Skills release | `v1.8.1` `ff978ade...` |
| PR #184 | merged; reviewed/merged tree equality at `5cec9ece...`; five successful checks |
| Candidate viability | exact PR patch on `v1.8.1`; runtime hunks clean; three mechanical provenance/index conflicts; all focused/full/install/doc gates passed |
| Controller | `d244f69a...`; policy rejects `base_ref != configured.default_branch`; schema has no maintenance allowlist |
| AWA policy | `.github/pr-automation.json` default branch `main`, activation generation 3 |
| Ruleset | `kleinperkins-merge-safety` active only on `refs/heads/main` |
| Maintenance artifacts | no remote `release/1.8`, no `v1.8.2`, no open maintenance PR |

If any exact ref, controller contract, ruleset, app id, required-check name, or
merge method changes, stop and refresh this plan through a successor rather
than improvising compatibility.

## 3. Owner and dependency map

### AWA owner

- ADR 0028 and this plan;
- exact patch scope and release base;
- `v1.8.2` candidate, tests, and release evidence;
- exact Release GO and immutable release.

### Controller owner — `KleinPerkins/pr-automation-controller`

- generic schema and evaluator support for explicitly enrolled non-default
  bases;
- verifier/reviewer exact-head behavior for such PRs;
- production deployment and fleet/catalog binding;
- refusal of unsanctioned bases.

The controller change is a separate governed PR in its owner repository. AWA
must not vendor or duplicate it.

### Repository-settings owner

- preview and activation of the exact maintenance ruleset;
- ruleset fingerprint read-back;
- exact branch creation after protection and controller eligibility hold.

### Downstream owners

- Skills: exact commit/tag release descriptor;
- Dev: concrete host literals;
- ShadowSync: Beta 0.9.1 pre-access consumer and activation evidence.

## 4. Body G0 — freeze AWA governance

**Owner:** AWA.

**Files:**

- add ADR 0028;
- add this plan;
- add one ADR index row;
- add one plan index row.

**Required proof:**

1. Accepted bytes state exact scope, owner split, ruleset-before-ref sequence,
   Release GO, synchronization, and EOL.
2. No `.github`, runtime, policy parser, release, branch, ruleset, Skills,
   install, host, or consumer byte changes.
3. Doc-warden, docs lane, full AWA verification, identity/session/data guards,
   and `git diff --check` pass.
4. Open one normal ready PR to `main`; leave auto-merge entirely to the
   controller.

**Stop:** after the PR opens. G1 cannot start until G0 is merged on live
`main`.

## 5. Body G1 — add controller-owned maintenance-base support

**Owner:** `KleinPerkins/pr-automation-controller`.

**Prerequisite:** G0 merged.

The owner implementation must add a closed repository-scoped maintenance-base
enrollment while preserving the configured GitHub default branch. Exact field
names belong to controller schema design, but the product behavior is fixed:

1. Existing repositories with no maintenance enrollment behave byte-for-byte
   as before.
2. An enrollment names exact repository id and exact full ref
   `refs/heads/release/1.8`; no glob, prefix, regex, or arbitrary caller value.
3. The trusted enrollment is loaded from controller-owned catalog or from
   bytes on the protected default branch, never from the maintenance PR's
   candidate tree.
4. PR base is eligible only when it equals configured default branch or one
   exact enrolled maintenance base.
5. Repository `default_branch` must still equal configured `main`.
6. Exact tuple and check/reviewer state bind the actual base ref and current
   base SHA; stale-base heads are refused.
7. Protected-path, author, fork, size, mergeability, episode, check-run,
   approval, and auto-merge rules are unchanged.
8. Reviewer App alone approves and arms auto-merge; agents never do.
9. Unknown, malformed, duplicate, default-shadowing, glob-shaped, or
   unprotected maintenance entries fail closed.
10. Main-only fleet parity and existing repos remain compatible.

**Synthetic acceptance matrix:**

- ordinary main PR remains eligible;
- exact enrolled `release/1.8` PR is eligible;
- `release/1.8.0`, `release/1.8/x`, case variants, and every other base reject;
- configured default/main mismatch rejects;
- stale maintenance base SHA rejects;
- policy loaded from candidate maintenance bytes cannot authorize itself;
- missing maintenance ruleset/fingerprint rejects;
- verifier checks and reviewer approval bind exact head after base update;
- protected paths retain owner/admin-only behavior;
- no Actions workflow/runner appears.

**Delivery:** normal controller PR and deployment through that repository's
governed path. Return release digest, schema version, deployed identity,
catalog/enrollment interface, and test receipts.

**Stop:** AWA does nothing until deployed production behavior is proven.

## 6. Body G2 — enroll AWA and protect the absent ref

**Owner:** AWA repository configuration plus GitHub repository settings.

**Prerequisites:**

- G1 deployed;
- controller owner provides the exact supported enrollment shape;
- AWA `main` still contains G0;
- `release/1.8` and `v1.8.2` are absent; and
- live `v1.8.1` still dereferences to exact `ff978ade...`.

### 6.1 Repository enrollment

Apply only the controller-prescribed AWA enrollment and required digest/
activation-generation changes. Do not guess a field or hand-edit a generated
lock. Run controller compatibility and baseline checks. If protected-path
policy prevents reviewer-App-governed delivery, stop: do not use admin/manual
merge, and return to the controller owner for a supported activation path.

### 6.2 Ruleset preview

Preview a dedicated active ruleset targeting exactly
`refs/heads/release/1.8`, with:

- pull request required;
- squash only and review conversations resolved;
- required approving reviews `0`;
- code-owner review `false`;
- strict verifier-App checks `pr-automation / verify` and
  `pr-automation / job:repo.awa.engine-tests`;
- required linear history;
- deletion blocked; and
- non-fast-forward/force push blocked.

The preview must bind repository id, current ruleset inventory, exact JSON
request bytes, expected fingerprint, and rollback. No broad branch pattern.

### 6.3 Protect before create

Apply the ruleset while the branch is absent. Read it back and prove:

- active enforcement;
- exact include, no unexpected exclude;
- exact two app-owned required checks and integration id;
- exact merge/review/deletion/non-fast-forward rules; and
- controller accepts the resulting ruleset fingerprint.

If any proof is unavailable, remove only the newly created empty-target
ruleset through its authorized rollback and stop without creating the branch.

### 6.4 Create exact release base

Create `refs/heads/release/1.8` at exact `ff978ade...` only after §6.3 passes.
Immediately read back the ref and ruleset, then run a controller-owned
maintenance-base qualification that posts no fake success to a real PR.

Never create an intermediate unprotected branch. Never update `main`.

**Stop:** if controller eligibility cannot be proven without opening a PR.
Otherwise proceed to G3.

## 7. Body G3 — prepare and merge the v1.8.2 backport

**Owner:** AWA.

**Prerequisite:** G2 complete and live.

Create a new linked Safe Workspace from exact `origin/release/1.8`. Apply the
combined PR #184 delta from `03d0d3dd...` to `c4a29c7c...`.

Expected non-semantic release-line reconciliation:

- preserve the v1.8.1 ADR index and append only ADR 0027;
- preserve the v1.8.1 plan index and append only the hard-no-touch plan;
- recompute the historical source-checker and default-policy hashes from the
  candidate bytes.

Add release identity only:

- `engine/__init__.py` → `1.8.2`;
- `pyproject.toml` → `1.8.2`; and
- release identity regression → predecessor `v1.8.1`, candidate `1.8.2`.

No redesign or additional runtime fix is allowed. The changed-file inventory
must equal PR #184's thirteen files plus exactly the three release-identity
files above. Reject any `registration_*`, native-entry implementation,
hook-owner successor, SQL, installer-registration, or post-v1.8.1 mainline
file.

Required local gates:

```text
python3 -m unittest -v engine.tests.test_hard_no_touch_policy
make version
make verify
make verify-install
doc-warden check
git diff --check
```

Re-run exact-base and exact-source provenance checks, review subtractively,
then open one normal ready PR whose base is exactly `release/1.8`. Require both
app checks, exact-head reviewer approval, and controller-owned squash merge.
Never alter auto-merge.

After merge, prove reviewed/merged tree equality and stop. No tag or downstream
mutation.

## 8. Body R1 — explicit Release GO and publication

**Owner:** AWA.

**Prerequisite:** G3 merged and exact evidence assembled.

Present:

- ADR/plan identities;
- controller release digest and maintenance enrollment;
- maintenance ruleset id/fingerprint/read-back;
- branch creation receipt at `ff978ade...`;
- backport source and maintenance PR head/merge/tree chain;
- version equality `1.8.2`;
- focused/full/install/doc verification;
- no registration files;
- release notes and rollback to immutable `v1.8.1`; and
- confirmation that Skills, install, Dev, ShadowSync, and activation have not
  run.

Stop until the operator replies exactly:

```text
GO to publish AWA v1.8.2 at <exact-release/1.8-merge-sha>.
```

On GO only, create and push immutable annotated tag `v1.8.2`, publish the
non-draft/non-prerelease GitHub release, and verify both resolve to the exact
maintenance merge.

## 9. Downstream sequence

After R1:

1. Skills PR pins exact `v1.8.2` commit and truthfully identifies
   `release/1.8`/`v1.8.2` provenance.
2. Repair/install the exact bound runtime and verify release pointer, parser,
   policy-check, and synthetic zero-target-access behavior.
3. Dev PR adds concrete `hard_no_touch_paths` literals.
4. ShadowSync Beta 0.9.1 adds the pre-access consumer.
5. Separately authorize activation and UAT.

No owner combines these as an atomic cross-repository change.

## 10. EOL and rollback

Before G3 merge, rollback removes only candidate PR/branch work; the protected
maintenance base remains at its last reviewed merge. Before release, use a
normal maintenance-base revert PR. After release, never move/delete `v1.8.2`;
publish a separately governed corrective patch.

When ADR 0028's EOL predicates hold:

1. remove controller merge eligibility first;
2. verify no open PR or downstream pin depends on the line;
3. retain immutable tags and release;
4. keep deletion protection until a separate explicit branch-retirement
   decision; and
5. remove the dedicated ruleset only after the ref is retired or permanently
   archived under equivalent protection.

## 11. Acceptance ledger

| Gate | Required evidence |
|---|---|
| A1 AWA authority | ADR 0028 and this plan accepted/frozen; exact scope/base/source/release |
| A2 Controller | Exact non-default allowlist; default branch preserved; unsanctioned bases reject |
| A3 Runnerless | Two verifier-App checks and reviewer-App-only approval/auto-merge; no Actions runner |
| A4 Protection | Ruleset live and fingerprinted before exact branch creation |
| A5 Base | `release/1.8` initially equals `ff978ade...`; no unprotected interval |
| A6 Patch | PR #184 plus release identity only; no registration/mainline contamination |
| A7 Verification | Focused/full/install/doc/controller/baseline/diff gates pass |
| A8 Merge | Ready maintenance-base PR; exact-head checks/approval; reviewed/merged tree equality |
| A9 Release | Separate exact-sha Release GO before immutable tag/publication |
| A10 Downstream | Skills → install → Dev literals → ShadowSync → activation, each separately governed |
| A11 EOL | Merge eligibility removed first; tags retained; branch retirement separately authorized |

## 12. Stop conditions

Stop without branch/ref/release mutation if:

- controller support requires trusting policy from the candidate branch;
- reviewer App cannot govern the maintenance PR;
- a required code-owner/human-review gate would be introduced;
- ruleset-before-branch applicability cannot be proven;
- exact `v1.8.1` base or PR #184 provenance changes;
- candidate includes any unrelated mainline file or semantic redesign;
- any step requires Actions runners, manual merge, agent-controlled
  auto-merge, direct tag, or direct pin; or
- accepted ADR/plan bytes would need editing.
