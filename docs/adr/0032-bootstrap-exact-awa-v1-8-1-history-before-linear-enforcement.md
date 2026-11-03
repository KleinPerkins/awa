---
{"approval":{"actor":"Codex release architect under owner-delegated execution authority and the 2026-11-02 exception approval; observed bootstrap correction under standing session override; not an assertion of operator hash inspection","date":"2026-11-03","review_sha256":"b6e3cd6647f341c5e132678c9120a986a54968f559dacfb987c548efce16d168"},"authority":"semantic","github_repository_id":1289571438,"id":"ADR-e6393083-530b-5462-9038-377088993223-cbca9512-7863-5ff5-a9b7-7e17ba27c558","lifecycle":"approved","mutability":"frozen_after_approval","provenance":[],"relations":[],"repository_key":"e6393083-530b-5462-9038-377088993223","schema":"doc-warden/artifact/v2","supersedes":null,"type":"adr","version":1}
---
## Context

ADR0031 and maintenance plan v2 require all maintenance safety rules, including
linear history, before creating `release/1.8` at exact v1.8.1
`ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`. Governance PR198 merged at
`bc8cfaffa8f2a3378ea7959506630a0897f434cb` after complete local verification and
independent review through the existing protected administrator PR route.

On 2026-11-03 GitHub rejected that exact initial ref creation. Rule suite
4870191550 proves only `required_linear_history` failed: the inherited v1.8.1
history includes merge commits. The PR, non-fast-forward, deletion and update
rules passed. Read-back confirmed the branch remains absent. No base, history,
controller or fleet pin was changed. Safety ruleset26417461 and administration
ruleset26417518 remain active against the absent exact ref.

This decision implements the owner's standing execution delegation and approved
one-time exception. It does not claim a new operator hash inspection or release
approval. The exact original base and maintenance patch are preserved.

## Decision

### Narrow supersession

Replace only ADR0031's requirement to apply linear-history enforcement before
the initial ref exists, and the corresponding E1 ordering in maintenance plan
v2. All other requirements remain, including immutable predecessor records,
independent review, full candidate verification, administrator expected-head
squash, merged parent/tree checks, sealing and the separate exact-SHA Release GO.
Do not rewrite or substitute v1.8.1 to obtain a linear ancestor graph.

### Bootstrap controls

Use a third exact-ref ruleset, `awa-v182-maintenance-bootstrap-creation`, with
only the `creation` rule. Its sole temporary bypass actor is GitHub User49759187
in `always` mode. This actor bypasses only the creation rule: it cannot bypass
the independent safety or update rulesets. No App, team or repository role is
added. After exact creation, remove this creation-only bypass permanently.

Execute under one release-administration writer in this order:

1. Revalidate merged governance, exact v1.8.1, absent branch, repository/account
   identity, current payloads, unchanged main rules and controller/fleet fences.
   Install/read back the creation-only rule while full safety remains active.
   Prove all effective rules apply to the absent exact branch.
2. Replace only task-owned safety ruleset26417461 with its reviewed bootstrap
   form: remove `required_linear_history`, keep its no-bypass PR/squash,
   conversation-resolution, deletion and non-fast-forward rules unchanged.
   Keep administration ruleset26417518 unchanged: sole named User49759187,
   PR-only update bypass, `updateAllowsFetchAndMerge=false`.
3. Read back the complete composed controls and confirm the ref remains absent.
   Create it once at exact `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`. No source
   push, maintenance PR, direct update or publication is admitted during bootstrap.
4. Read back the exact created SHA. Restore the original full safety ruleset,
   including linear history; seal the creation ruleset by removing its sole
   bypass. Verify exact rules, GraphQL update parameter, and effective branch
   coverage. Preserve the permanent creation restriction with no bypass.
5. Only after both restorations and unchanged main/controller/fleet evidence may
   E2 admit the already-qualified maintenance candidate. E3 still removes the
   administration bypass after its one expected-head squash merge.

The temporary relaxation is confined to evaluating the existing ancestor graph
at creation. Every subsequent update requires the full linear-history rule;
there is no general history exception and no direct-update authority.

### Failure and recovery

Before each mutation save payload digest and current state. After any ambiguous
API result, read state before retrying. If creation fails and the branch is still
absent, restore full safety and seal the creation bypass before stopping. If a
branch appears at a different SHA, do not update/delete it: restore full safety,
seal both administration and creation bypasses, preserve evidence and investigate.
If the exact branch exists but either safety restoration or sealing fails, keep
the update restriction, prohibit E2/E3/publication, and repair the specific
task-owned ruleset. Never remove main rules, reset a branch or broaden bypasses.

GitHub REST omits false update parameters and adds default PR fields in
read-back. Accept only the exact requested values plus the observed closed
default set: `required_reviewers=[]` and
`require_extra_approval_for_unattributed_changes=true`. Prove
`UpdateParameters.updateAllowsFetchAndMerge=false` through GraphQL rather than
inferring it from an omitted REST field. Unexpected fields or changed values
stop admission.

### Verification and lifetime

Independently review this correction and exact bootstrap/sealed JSON payloads.
Run full AWA verification and document/schema/freeze checks before its governance
PR is ready. Keep prior failed creation evidence. Record bootstrap rule IDs,
timestamps, source SHA, all before/after rule fingerprints, creation result,
restoration and sealing read-backs, and unchanged main/controller/fleet fences.

This exception is consumed by the one exact branch creation. The third creation
ruleset remains sealed; no lasting bypass or second maintenance patch is enabled.
Runtime/product scope, AWA release scope, product installation and UAT gates do
not change. No signing, installation or publication follows from this record.

## Consequences

The original exact base is retained without importing unrelated mainline work or
rebinding the fleet. Initial creation briefly excludes the historical-graph
linear check under a named-user-only creation control; full update protection
is restored before the maintenance PR. This is an explicit correction to the
original bootstrap procedure, not a claim that the first attempt succeeded.

## Evidence

- [GitHub rule suite4870191550](https://api.github.com/repos/KleinPerkins/awa/rulesets/rule-suites/4870191550): exact initial ref rejected solely by inherited merge history.
- [GitHub rules API](https://docs.github.com/en/rest/repos/rules): creation/update rule scopes, per-ruleset bypasses and absent-branch effective-rule read-back.
- [GitHub ruleset composition](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets): all applicable rules aggregate.
- AWA PR198: accepted one-time route; historical ADR0028/0031 and planv1/v2 remain byte-preserved.
