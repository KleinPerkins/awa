---
{"approval":{"actor":"Codex release architect under owner-delegated execution authority and the 2026-11-02 exception approval; not an assertion of operator hash inspection","date":"2026-11-02","review_sha256":"904c1c0b03cffdf66b51d8f4be3042527e449c856a37578714c422299c589ed4"},"authority":"semantic","github_repository_id":1289571438,"id":"ADR-e6393083-530b-5462-9038-377088993223-c55dfe51-01b1-5212-bd4d-ea4d5f1527e5","lifecycle":"approved","mutability":"frozen_after_approval","provenance":[],"relations":[],"repository_key":"e6393083-530b-5462-9038-377088993223","schema":"doc-warden/artifact/v2","supersedes":null,"type":"adr","version":1}
---
# ADR 0031: One-time administrator release route for AWA v1.8.2

## Context

The owner accepted the one-time exception on 2026-11-02: keep deployed controller
0.13.0 and every fleet controller pin unchanged; publish only the hard-no-touch
backport onto exact v1.8.1 through an independently reviewed, fully verified,
auditable maintenance pull request. This replaces a deployment dependency, not
the product safety requirements. The owner separately delegated execution
decisions for the ShadowSync extraction; that authority is not evidence that a
test, technical review, installation, or product acceptance has passed.

Accepted ADR 0028 and `docs/plans/awa-v1-8-maintenance-release-v1.md` require
deployed maintenance-base support and reviewer-App-only merging. Controller
source support has since merged as controller PR #449, but its deployment would
change the binary digest and require fleet rebinding and qualification. It is
not deployed by this decision. Releasing current AWA main would include unrelated,
separately gated registration implementation and remains prohibited.

On 2026-11-02 AWA main was `d243d22040cd09f49f75ed60384b0e624d802a5a`;
neither `release/1.8` nor `v1.8.2` existed. The repository remains private,
default branch `main`, squash-only, with active ruleset 18819090
(`kleinperkins-merge-safety`). Refresh live observations at every mutation gate.

## Decision

### Scope and supersession

For exactly one initial `v1.8.2` maintenance PR, replace ADR 0028 sections 1, 3,
4 and 5 only insofar as they require deployed controller eligibility, App-owned
checks/approval and App-only merging. Replace the corresponding controller,
enrollment and merge prerequisites in maintenance plan v1 with the procedure
below. All other product scope, preservation, provenance, EOL and release
requirements survive. Accepted predecessor bytes stay unchanged.

The sole base is `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` (v1.8.1).
The sole backport is AWA PR #184: reviewed head
`c4a29c7cc2f2399c0eba4e940dfb827cf5eb624d`, main merge
`07f5f5820e27ad7557f3b7898fabcc6b41b799be`, tree
`5cec9ece1ede3d048cc253883ccffb2a4cf754d0`. Permit its thirteen changed files
plus only the three version-identity files named in plan v1. Reconcile historical
hashes and indexes mechanically. No post-v1.8.1 registration/native-entry code,
new runtime design, workflow, runner or broader maintenance patch is authorized.

### Unchanged authorities

Keep live controller 0.13.0, binary SHA-256
`3d0b6b34d29b6d0c9ae94daa8dd4cd1182ae3bb9375944322c58febc52fec07c`, its
configuration, catalog, credentials and all fifteen fleet controller pins
unchanged. Preserve existing main ruleset bytes, repository default/merge settings,
`.github/pr-automation.json`, generated locks and protected automation. Do not
enable maintenance eligibility or alter ordinary App approval/auto-merge.

The main governance PR still follows existing AWA delivery: ordinary files use
the App route; engine-generated governance receipts under protected `_ops` use
the existing owner/admin path after independent review and full local verification.
The existing main ruleset already permits repository administrators to bypass
through PRs only; do not change it. Retain any App refusal of protected paths as
such, not as a successful verifier run. This exception adds administrator delivery
only for the identified maintenance PR. It creates no generic
operator code-review gate and no standing agent permission to bypass other PRs.

### Protection before creation

Use two new active branch rulesets, both targeting exactly
`refs/heads/release/1.8` with no exclusions, and neither using a managed fleet
ruleset name:

1. `awa-v182-maintenance-safety`: no bypass actors; require PR, squash merge,
   resolved review conversations, linear history, deletion and non-fast-forward
   protection. Require zero GitHub approving reviews and no code-owner or last-push
   approval, because the solo administrator cannot self-approve. Independent
   technical review is mandatory evidence, not a fabricated GitHub approval.
   No controller check is required or reported as a substitute success.
2. `awa-v182-maintenance-administration`: restrict updates with
   `update_allows_fetch_and_merge=false`. Only verified GitHub user KleinPerkins
   (id 49759187) may bypass this ruleset, and only through a pull request.
   This bypass cannot bypass the separate safety ruleset. Do not add creation
   restrictions that require an always-on bypass merely to bootstrap the ref.

Preview exact JSON, read back both rulesets and use GitHub's rules-for-branch
endpoint, which supports absent branches, to prove coverage before ref creation.
Refresh main protection and controller pin evidence. If these independent
rulesets change ordinary main eligibility, stop and correct only the new rules;
do not rebind or change the controller to accommodate this exception.

Create the branch once at exact v1.8.1; immediately verify its SHA and protections.
No direct branch update is permitted thereafter. Before any merge, restrict the
administration bypass to the verified named account above and record its identity.
Once the one candidate merges, remove its bypass actor while retaining update,
deletion and non-fast-forward restrictions. The branch is then sealed against
further updates. Failure to seal is an incomplete administration gate and blocks
publication; it is never a reason to delete or force-reset the branch.

### Exact maintenance PR admission

The release administrator is the owner account KleinPerkins, operated by its
authorized release engineer. Independent technical review must be from a separate
context with the complete patch, source provenance, tests and this decision; it
must identify reviewer provenance and limitations truthfully. All findings must
be resolved, with fresh review after material changes. Neither the author nor an
automated check may invent reviewer approval or claim provider independence.

Create one ready PR from the fully verified candidate to `release/1.8`. Record
repository id, PR number, base ref/SHA, exact head/tree, source PR184 chain, patch
digest, complete changed-file allowlist, reviewer report digest, verification
receipt digests and ruleset fingerprints in the admission packet. Incomplete
work is not ready. The controller's refusal of a non-default base is expected
and must remain visible; it is not overridden with forged checks or a new status.

Immediately before merging, re-read the open PR, exact head, base, changed-file
list, repository identity, mergeability, resolved conversations, applicable rules,
review findings and successful verification. Any change invalidates admission.
Execute the GitHub squash-merge endpoint with its expected-head SHA parameter.
No force push, auto-merge manipulation or temporary protection removal is allowed.
The base remains exact v1.8.1 under the sole-admin update restriction. Read back
merged state, actor, target, head, merge SHA, parent and tree. Require the squash
merge parent equals v1.8.1 and merge tree equals the reviewed candidate tree.
Seal the branch and retain the complete administration receipt.

### Verification and release remain separate

Before PR admission require focused hard-no-touch tests, full `make verify`,
full throwaway `make verify-install`, version equality, doc-warden, diff checks,
kernel-off/router-uninstalled and zero-target-access evidence. Use disposable
fixtures only; never inspect or operate on real protected repositories.
Bind each receipt to exact source/tree, command, environment, exit status and
cleanup outcome. Existing historical synthetic success is not a current receipt.

The exact Release GO remains a distinct gate after verified merge and sealing:
`GO to publish AWA v1.8.2 at <exact-release/1.8-merge-sha>.`
The owner has not supplied that future SHA. This exception does not claim it was
already accepted. Only after Release GO may the administrator publish the immutable
annotated tag and release and verify their exact dereferenced commit and artifacts.

### Downstream reconciliation and expiry

Skills owns the exact release descriptor and runtime binding; dev owns concrete
host policy; ShadowSync owns its consumer, installation and activation gates.
Prospective successor records in Skills/ShadowSync must replace their controller
deployment dependency with this receipt-backed release route before downstream
activation. Their accepted historical documents remain unchanged. No software
licensing, visibility, CI-runner or product scope decision changes.

The exception is consumed by the single successful maintenance merge. A failed
attempt may retry only with freshly admitted identical scope and current evidence.
Any second patch, replacement release, changed base/source scope or relaxed
protection requires new authority. Keep the sealed branch and immutable tags;
retirement remains separately authorized under ADR 0028. If publishing fails,
repair the incomplete publication at the same exact tag without rewriting published
bytes, or stop for a new corrective-release decision.

## Consequences

Fleet rebinding is avoided by keeping the deployed binary unchanged. One release
uses audited administrator execution instead of the controller verifier/reviewer.
Those evidence classes must be labeled distinctly. Maintenance branch protection
is stricter than a merely unprotected admin merge but does not prove test results;
exact source-bound independent review and verification supply that assurance.

This decision does not finish hard-no-touch remediation, authorize probing
protected targets, activate ShadowSync, accept UAT, or qualify controller 0.15.0.

## Platform evidence

- [GitHub rules API](https://docs.github.com/en/rest/repos/rules): exact absent-ref
  coverage, individual User bypass, pull-request-only bypass and update restriction.
- [GitHub ruleset creation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository):
  pull-request-only bypass cannot authorize a direct push.
- [GitHub ruleset composition](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets):
  all applicable rulesets aggregate. Capture live API read-back before relying on it.
