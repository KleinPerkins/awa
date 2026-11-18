## Continual-learning memory

Machine-mined preferences and workspace facts for this workspace now live in
`agent-learnings.md` (machine-local, git-ignored, never committed). Agents load it as
ancestor context when present; this file holds only hand-authored, human-curated guidance.

## Planning documents and architecture decisions

Before starting or acting on any substantial execution/design plan, read
`docs/plans/README.md` first — the authored convention plus a status-tagged index
of every plan in the directory.

Before recording (or looking up the rationale for) a durable architecture
decision, read `docs/adr/README.md` — the ADR format, numbering, and status
convention, plus an index of every record.

The `doc-warden` governance block below restates these locations in the fleet-standard
marker format (see [`docs/adr/0017-adopt-and-reconcile-doc-warden-conventions.md`](docs/adr/0017-adopt-and-reconcile-doc-warden-conventions.md));
the "read `docs/plans/README.md` first" reading-order guidance above still applies.

<!-- doc-warden:begin -->
## Documentation governance

This repo's documentation structure is governed by `doc-warden`.

| Artifact type | Location |
|---|---|
| Plans | `docs/plans/` — index at `docs/plans/README.md` |
| ADRs | `docs/adr/` — index at `docs/adr/README.md` |
| Runbooks | `docs/runbooks/` |
| Glossary | `docs/GLOSSARY.md` (created when genuine terminology ambiguity arises) |

**Policy:** `~/dev/_ops/doc-warden/POLICY.md`
**Engine:** `~/dev/_ops/bin/doc-warden.sh check KleinPerkins/awa` (read-only health check)
<!-- doc-warden:end -->

## Current G1 source delivery

The operator-authorized G1 cohort transition uses sharded standard GitHub-hosted
Actions for AWA source CI and the qualified Chaos Scheduler App for native delivery.
The current owner policy is [KleinPerkins/dev policy section 5](https://github.com/KleinPerkins/dev/blob/main/_ops/POLICY.md#5-enforcement--source-hosted-delivery-and-installed-host).
It supersedes the old runnerless-controller requirement and the old ShadowSync-only
hosted-runner exception for this enrolled cohort. Self-hosted runners remain forbidden.
The abandoned installed PR controller must not resume.

Automatically obtain a fresh independent review under the originating PR-creation
account with `scripts/local_review.py`, then create through
`scripts/create_review_pr.py` and publish the unedited review receipt. No human
technical review or cross-account substitution replaces that review.

Ordinary capture and creation bind policy bytes to the exact `request.base_sha` registry
Git blob. Use the admitted base versions of both helpers and their enrolled pins when
proposing helper or policy updates; the proposed HEAD registry remains untrusted diff.
Only already-authorized initial owner source evidence may use `--owner-bootstrap-policy`,
which requires the base registry to be absent and explicitly binds the candidate registry.
This local option adds no App admission, merge or activation authority.

Trusted-main admission requires that complete passing independent review of the exact
head, base, whole canonical diff and current policy before accepting CI as PR-admission
evidence, including CI and governance changes. A CI receipt binds execution/contract identity; it is not
a formal proof of arbitrary candidate semantics. Q16 operationally trusts the
enrolled local receipt tooling and accepts same-access receipt forgery as a limit.
The [live GitHub GraphQL input schema](https://docs.github.com/en/graphql/reference/input-objects),
checked through read-only `__type` introspection on 2026-11-17, exposes
`expectedHeadOid: GitObjectID` in both `MergePullRequestInput` and
`EnablePullRequestAutoMergeInput`; both native branches intentionally retain that
API head condition. These facts establish neither delivery nor activation.
GitHub documents [active branch rules and repository ruleset GET endpoints](https://docs.github.com/en/rest/repos/rules)
as requiring Metadata read, including installation tokens. `bypass_actors` may be redacted;
App qualification still requires explicit `current_user_can_bypass: never`. The existing
[same-App read-only qualification](https://github.com/KleinPerkins/intent-router/actions/runs/44165228588)
passed with contents/pull-requests read and no Administration grant. This reference does
not qualify AWA; its own actual qualification remains required.
The actual [AWA native job](https://github.com/KleinPerkins/awa/actions/runs/44200977054/job/134454646356)
on 2026-11-17 downloaded the official `python-3.15.2-darwin-arm64.tar.gz` and reported
`Successfully set up CPython (3.15.2)`, then passed 1,788 tests (15 exact off-switch skips)
and 33 native fixtures. All seven checks passed at `2e7c302`; this is historical runtime
availability evidence, not qualification of a later candidate.
Router declarations are source-reviewed policy covered by the same independent whole-diff
review before CI admission. Producer-source provenance retains the historical upstream
review policy; current AWA policy qualification comes from the current tuple receipt.

Only the qualified App approves and requests native squash or eligible auto-merge;
agents never merge, arm auto-merge or bypass protections. Initial owner admission,
merged-main checks and actual App qualification precede writer activation.
After owner initial source admission, `AWA_CI_ADAPTER_ENROLLED=true` permits
read-only qualification; `REVIEWER_APP_ENABLED` stays OFF until its gates pass.
Source CI and source enrollment do not authorize installation, held AWA rollout,
live host activation or a product release. Original frozen plans and router pin remain unchanged.
