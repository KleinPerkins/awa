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
