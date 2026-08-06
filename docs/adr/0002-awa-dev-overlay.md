# ADR 0002: Cross-repo authority — awa dev overlay

**Status:** Accepted
**Date:** 2026-08-06
**Owning repository:** KleinPerkins/awa

*Plain-language summary: the AWA repo is the single "manual" for what AWA is and how it
works. `~/dev` is the site-specific "install sheet" — it points at the manual instead of
retyping it. One fact that looked like it belonged here — the Global Capability Binding —
is owned by a third repo (`KleinPerkins/skills`) and is deliberately excluded.*

## Context

AWA ships as a self-contained product (a Standalone System Package) in `KleinPerkins/awa`.
`~/dev` consumes it as a thin host overlay: it supplies machine-specific policy (which repos
are governed), mode defaults, and stable-path delegators, and installs the AWA release.

Both repos had been describing the same product facts. doc-warden's M4 / POC 3d cross-repo
check confirmed it: six topics appeared as **agreeing duplicates** (`DUPLICATE_AUTHORITY`)
across `~/dev`'s `OPERATING-MANUAL.md` §11 and agent rules and AWA's own `ARCHITECTURE.md` /
`README.md` / `SECURITY.md`. Agreeing duplicates still fail governance — they are guaranteed
future drift with no arbiter for which copy wins.

A seventh candidate, `gcb-binding`, came back `DEPENDENT_ONLY`: AWA's governed docs do not
assert it at all (`owner_paths_found: []`). That is not a duplicate to consolidate — it is a
fact owned elsewhere, handled explicitly below.

## Decision

**`KleinPerkins/awa` is the sole canonical owner of AWA _product_ statements** — what AWA is,
how it is packaged, how its safety model works, and how operators interact with it. `~/dev`
carries **pointers** to AWA for those statements, not second copies. `~/dev` owns only
**host-specific data**: which repos are governed (`_ops/policy/worktree-policy.yml`), mode
defaults, and the delegators/hooks that forward to the installed AWA release.

Authority partition for cross-repo profile **`poc3d`** (six governed topics):

| Topic | Canonical owner | Resolution |
|---|---|---|
| `ssp-product-location` | AWA | `~/dev` → pointer |
| `host-overlay-role` | AWA (defines the pattern) | `~/dev` → pointer for the product claim |
| `kernel-first-invariant` | AWA | `~/dev` → pointer |
| `no-duplicated-contract` | AWA (`contracts/awa-contract.v1.json`) | `~/dev` → pointer |
| `operator-copy-honesty` | AWA (`SECURITY.md`) | `~/dev` → pointer |
| `host-policy-literals` | **Split** — AWA owns the *pattern*; `~/dev` owns the *values* (`affirm/*` globs, paths) | `~/dev` keeps the literals; pointer covers the pattern only |

**Excluded by decision — `gcb-binding` → `KleinPerkins/skills`.** The Global Capability
Binding (`global/tools/awa`, a Flavor-2 standalone-release shelf) is external to the AWA
product — it is how the *skills* repo points at the AWA release. AWA does not (and need not)
describe it, and `~/dev`'s mention is a legitimate binding-site reference, not a duplicate of
AWA. Making `~/dev` point at AWA for this would reference prose that does not exist, creating
an **ownerless statement** — forbidden by POC 3d's "never ownerless" rule. `gcb-binding` is
therefore **removed from the `poc3d` profile** and left with its true owner, `KleinPerkins/skills`.

**Operating rule (for PMs and agents):**
- "Change how AWA *works*" → issue/PR in **`KleinPerkins/awa`**.
- "Change which repos AWA *protects on this machine*" → adjust **`~/dev/_ops/policy/worktree-policy.yml`** (via an agent), never by rewriting AWA chapters in `OPERATING-MANUAL.md`.
- "Change the AWA *binding/shelf*" → **`KleinPerkins/skills`** (`global/tools/awa`).

## Alternatives considered

1. **Keep the duplicates (do nothing).** Rejected — guaranteed drift; the exact failure
   doc-warden exists to prevent.
2. **Delete the `~/dev` copies outright.** Rejected — violates §13 (no unreviewed cross-repo
   deletion) and risks orphaning host-specific context.
3. **Make `~/dev` the owner.** Rejected — AWA is the portable product; a host overlay cannot
   own product truth another host would also need.
4. **Blanket "point everything at AWA," including `gcb-binding`.** Rejected — would create an
   ownerless reference (see the exclusion above).
5. **Pointer-to-owner from `~/dev`, topic-by-topic (chosen).** One owner, one reference,
   reversible, each repo's change shipping as its own reviewable PR.

## Why

Two copies of the same rule are two things to keep in sync, with nothing to decide which wins
when they diverge — agents loading `~/dev` rules and readers of AWA's docs can reach different
conclusions. A single owner plus a pointer removes the ambiguity while keeping host-specific
wiring where it belongs. The resolution is deliberately per-topic rather than a blanket sweep:
that is what caught `gcb-binding` before it became a broken reference.

## Consequences

**Positive**
- One place to edit when AWA product behavior or packaging changes.
- `~/dev` agent rules point to this ADR instead of carrying competing narratives.
- Repair ships as **independent PRs** (AWA owner ADR + `~/dev` pointers), never one atomic
  cross-repo transaction — each independently reviewable and revertible.

**Negative / accepted risks**
- `~/dev` readers follow a link for product detail (mitigated: pointer blocks name the exact
  ADR path).
- Redundant prose is **not yet removed** — pointers were added beside the existing copies.
  Subtractive de-duplication is a separate, human-reviewed PR (§13), so nothing becomes
  ownerless in the interim.

## Verification & follow-through

**Verification.** `doc-warden check --cross-repo poc3d` is the ongoing regression check; after
the profile edit it enumerates six governed topics with `gcb-binding` no longer in scope.

**Follow-through (accepted, mechanical):**
1. Remove `gcb-binding` from `_ops/doc-warden/cross-repo-profiles.yml` (`poc3d` profile).
2. Narrow the `~/dev` pointer blocks to the six owned topics — remove `gcb-binding` from the
   topic-id lists in `_ops/rules/agent-context.md`, `_ops/rules/dev-operating-model.mdc`, and
   `OPERATING-MANUAL.md` — folded into the subtractive-dedup pass.
3. Ship the subtractive de-dup PR trimming redundant AWA prose in `OPERATING-MANUAL.md` and
   rules, leaving pointers + host literals only.
4. (Optional, out of scope) Formalize `gcb-binding` ownership in `KleinPerkins/skills` if a
   canonical statement is ever wanted there.

**Cross-repo profile:** poc3d
**Dependent repo:** dev
**Topic ids:** ssp-product-location,host-overlay-role,kernel-first-invariant,no-duplicated-contract,operator-copy-honesty,host-policy-literals
