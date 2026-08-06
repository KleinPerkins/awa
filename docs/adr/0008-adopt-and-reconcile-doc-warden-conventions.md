# ADR 0008: Adopt AND reconcile doc-warden conventions in the AWA repo
Status: draft — 2026-08-06

## Context

AWA already declares a local docs convention in `docs/adr/README.md` and `docs/plans/README.md`,
self-described as modeled on the same `pr-automation-controller` precedent that `doc-warden` derives
from, adopted "ahead of [doc-warden] reaching general availability … so no rework is expected."
`doc-warden` is an accepted (2026-08-05), byte-identical-frozen governance subsystem in `~/dev/_ops`
(`~/dev/_ops/doc-warden/POLICY.md` v1.0.0). Its execution plan reserves M4 / POC 3d for
"AWA (KleinPerkins/awa) ↔ ~/dev's host overlay (`_ops/awa/`) … establish sole ownership … and
convert the other copy to an explicit pointer/reference — never deleted outright without review …
Operator GO before any cross-repo pointer/removal action." No doc-warden state/receipt exists yet
for `awa` (only `doc-warden-canary`, `ecosystem-orchestrator`, `pr-automation-controller`), so M4 /
POC 3d has genuinely not run. The ADR/plan format is explicitly portable — the same lineage AWA's
docs already claim — so nothing prevents AWA hand-authoring a conforming set now.

AWA's local convention diverges from doc-warden's canonical templates on exactly five dimensions:
(1) ADR status vocabulary (local `proposed|accepted|superseded|deprecated` vs doc-warden
`draft|accepted|superseded`); (2) ADR index columns (local `ADR | Status | One-line decision` vs
doc-warden `ADR | Title | Status | Date`, POLICY §10 rule 5); (3) plan index columns (local
`File | Status | One-line description` vs doc-warden `Plan | Status | Date | Notes`, POLICY §10 rule
4); (4) plan status vocabulary (local `DRAFT | APPROVED — FROZEN | COMPLETE` vs doc-warden
`DRAFT | ACCEPTED | SUPERSEDED`); (5) ADR immutability strictness (local `docs/adr/README.md`
permits an inline `> Update —` blockquote correction on an accepted ADR; doc-warden POLICY §9
refuses that — "byte-identical forever, no exception (not even a status-bullet edit)", explicitly
"stricter than pr-automation-controller's … 1-line status-bullet edit — POC 3b will correct that
wording").

## Decision

Place the new ADRs (0002+) and this plan at the existing `docs/adr` and `docs/plans` roots, number
ADRs sequentially from 0002, and adopt doc-warden's canonical template shape and vocabulary for
**new** artifacts going forward, reconciling the five divergences per-divergence (below). Augment —
not replace — `AGENTS.md` with the marker-delimited pointer block (POLICY §10 rule 6). Record that
AWA is the **owning-repo** side of doc-warden's pending M4 / POC 3d, and that the `~/dev` `_ops/awa/`
overlay copies become pointers later under an Operator-GO-gated, `~/dev`-side change. `docs/adr/0001`
is not retroactively touched.

Per-divergence resolution:
1. **ADR status vocabulary** — new ADRs use doc-warden `draft|accepted|superseded`
   (`Status: draft — 2026-08-06`). ADR 0001 keeps its `accepted` line untouched.
2. **ADR index columns** — keep the local `ADR | Status | One-line decision` shape for now (so the
   0001 row stays byte-identical and the table stays valid); migrating to `ADR | Title | Status |
   Date` (POLICY §10 rule 5) is a deferred, operator-gated, **index-only** change under POC 3d (the
   index row is explicitly mutable; ADR files are not).
3. **Plan index columns** — keep the local `File | Status | One-line description` shape now; migrate
   to `Plan | Status | Date | Notes` (POLICY §10 rule 4) under the same deferred, operator-gated
   change.
4. **Plan status vocabulary** — new plans use doc-warden `DRAFT | ACCEPTED | SUPERSEDED`; this plan
   is `DRAFT`.
5. **ADR immutability** — new ADRs (0002+) adopt doc-warden's stricter byte-identical-forever rule
   (POLICY §9) with **no** inline `> Update —` exception (supersede-only). ADR 0001 is not
   retroactively re-governed. The plan-side analog is reconciled identically: the local
   `docs/plans/README.md` previously permitted a one-line status-bullet note on a superseded (frozen)
   plan — which a live `doc-warden check` flags as `status_bullet_exception`
   (`~/dev/_ops/bin/doc-warden-lib.sh` `dwl_policy_drift_ids_for_plans_readme`) — so new plans now
   record frozen/superseded status in the index row **only**, never by editing the accepted file, and
   the plan README prose is updated to match (this is the plan facet of the same immutability
   dimension, not a sixth dimension).

## Why

- **Silently follow the old local convention (rejected).** Authoring new ADRs under the local
  `proposed`/inline-`> Update —` rules while doc-warden becomes GA would leave an *undeclared*
  divergence. Reconciling it openly in prose keeps the repo out of doc-warden's escalation states.
- **Wait for POC 3d (rejected — blocks).** POC 3d has not run (no `awa` receipt in
  `~/dev/_ops/doc-warden/state/`), and doc-warden requires Operator GO before any cross-repo
  pointer/removal action. Blocking all new AWA governance docs on an unscheduled cross-repo phase is
  rejected.
- **Adopt-going-forward with an explicit reconciliation note (chosen).** Per POLICY §3, an artifact
  that "matches template shape, no drift" is `CONFORMANT` (exit 0). The new ADR/plan **files** and
  the AGENTS marker block match the templates (POLICY §10 rules 1–3, 6), so they are
  CONFORMANT-shaped. The two **index tables**, keeping local columns to preserve the protected
  0001/guard rows, differ from POLICY §10 rules 4/5 — under a strict check that is `DRIFTED` ("exists
  but differs from the governed shape", exit 1, DRIFT-not-VIOLATION, human-PR-repairable), which is
  deliberately **not** the exit-3 `NEEDS_OPERATOR` ("condition not matched by any trigger") or
  `CONTRADICTORY` ("conflicting authoritative sources") escalation. Declaring the variance in prose
  + keeping internally consistent state avoids those two exit-3 states; the deferred column migration
  resolves the DRIFTED index tables to CONFORMANT under POC 3d.

## Consequences

- Enables: a doc-warden-conforming ADR/plan set now, with the divergence surfaced explicitly rather
  than silently chosen; a clean hand-off to POC 3d for the index-column migration and the
  overlay-to-pointer conversion.
- Forecloses (safety, per SECTION K): no `.doc-warden.yml` is added to `awa`; doc-warden's engine
  gets **no** call-site outside `~/dev`; no cpp/eco-registry participation; doc-warden is not wired
  into AWA's Makefile/CI. A dry-run `~/dev/_ops/bin/doc-warden.sh check KleinPerkins/awa` invoked
  *from* `~/dev` (engine stays home, reads AWA's files) is the only allowed engine touch.
- Must stay true: ADR 0001 and the `guard` plan row stay byte-identical; new ADRs are
  supersede-only; the index tables stay internally consistent until the operator-gated migration.
- Defers/creates: the index-column migration and the `~/dev` overlay-to-pointer conversion are
  Operator-GO-gated POC 3d work (plan §M7). This is the meta-ADR for the whole 0002–0009 set.
  Cross-links: all of ADR 0002–0009 (vocabulary/shape they follow), ADR 0009 (subtraction policy),
  plan §M7 (executes this reconciliation).
