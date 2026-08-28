# AWA Integrity Execution Priority Addendum — current post-M1 delivery sequence

**Version:** v1
**Status:** ACCEPTED — 2026-08-28
**Date:** 2026-08-28
**Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
**Plan-type:** standard
**Relates to:** accepted [ADR 0020](../adr/0020-awa-integrity-surveillance-and-lifecycle.md) and the [AWA Integrity Surveillance and Lifecycle plan](awa-integrity-surveillance-and-lifecycle-v1.md).
**Review provenance:** direct operator decision on 2026-08-28; documentation-only scope record.

**Goal:** record the current execution priority without changing AWA's accepted architecture,
implemented capabilities, or milestone definitions.
**Architecture:** no architecture changes. ADR 0020 and the accepted execution plan remain the
authority for capability design; this later addendum is authoritative only for current delivery
priority and sequencing.
**Tech stack:** governed Markdown documentation only.

---

## Global Constraints

- Keep accepted ADR 0020 and the accepted execution plan byte-identical.
- Preserve the distinction between a supported capability and its current activation priority.
- Make no code, test, install, credential, host-state, release, or acceptance change.

## 1. Purpose

This addendum records a narrow owner prioritization decision in the governed plan surface, where
AWA keeps execution scope and sequencing. It does not duplicate or supersede the accepted plan's
architecture, contracts, milestone definitions, or acceptance ledger.

## 2. Scope and non-goals

The active delivery sequence is:

1. Complete M1 successfully through its existing delivery and acceptance path. This record neither
   declares M1 complete nor changes its acceptance retroactively.
2. Keep M2 in scope and sequence it after successful M1 completion.
3. Keep M3 in scope and sequence it after M2.
4. Remove M4 from the active delivery sequence indefinitely. M4's optional regenerable export /
   Quickhost share capability remains defined for possible future work, but returns to the sequence
   only after an explicit future reprioritization.

Slack activation/integration work is deprioritized. The already-shipped opt-in
Slack adapter remains supported and unchanged, but stays opted out and unconfigured. Native alerts
remain the active M1 alert path. This is a prioritization decision, not removal, and does not recast
Slack as having never been part of M1.

This record does not authorize M2 or M3 implementation, alter live host state, create or change
Slack credentials or configuration, modify code, or revise M1 acceptance.

## 3. Background and context

The opt-in Slack adapter in `engine/integrity_slack.py` shipped in
[PR #129](https://github.com/KleinPerkins/awa/pull/129). Its existing contract treats absent opt-in
material as `opted_out`; native remains the configured alert path. The accepted plan separately
defines M2 (lifecycle and entry), M3 (ephemeral interface interactivity), and M4 (optional
regenerable export / Quickhost share). Those capability definitions remain intact.

## 4. Approach

Apply this addendum only when deciding what work follows M1: M1 → M2 → M3. Do not schedule M4 or
Slack activation/integration work from the accepted plan without a later explicit operator
reprioritization. Continue to use ADR 0020 and the accepted plan for architecture and implementation
contracts.

## 5. Work items

None. This document records priority only. M2 and M3 each still require separate explicit
implementation authorization.

## 6. Acceptance criteria

- The governed plan index links this accepted addendum.
- The accepted ADR and plan remain byte-identical.
- The repository change contains only this record and its required index entry.
- No code, credential, installation, release, or live-state change accompanies this decision.

## 7. Rollback

There is no implementation or live-state rollback. Because this accepted record is frozen, any
future reprioritization is recorded in a new governed version with a `Supersedes:` pointer plus an
index update; this file is not edited.
