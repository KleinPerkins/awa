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
Only the qualified App approves and requests native squash or eligible auto-merge;
agents never merge, arm auto-merge or bypass protections. Initial owner admission,
merged-main checks and actual App qualification precede writer activation.
After owner initial source admission, `AWA_CI_ADAPTER_ENROLLED=true` permits
read-only qualification; `REVIEWER_APP_ENABLED` stays OFF until its gates pass.
Source CI and source enrollment do not authorize installation, held AWA rollout,
live host activation or a product release. Original frozen plans and router pin remain unchanged.
