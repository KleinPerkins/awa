# Native Codex hook and prompt-control repair

- **Version:** v1
- **Status:** DRAFT — REPAIR SOURCE; NATIVE QUALIFICATION PENDING
- **Date:** 2026-10-31
- **Relates to:** `native-codex-interoperability-v1.md` and the frozen capture previews v1/v2
- **Authority:** the operator's standing authorization for necessary capture steps and subsequent instruction, “Resolve the issues.” This records execution scope, not a new compatibility or protection acceptance.

## Purpose and verified state

AWA PR #190 merged at `953c6c6d26a0b1714648ce15bb5611708c844a1c` with five passing exact-head App checks. Its tested and merged trees match. The C2/A01 export is deliberately UNPROVEN. It is not qualification.

The later C3/A03 trial stopped during BEFORE: one submitted model prompt produced two callbacks with two distinct session labels. The observer admitted all sessions in the fixture; the capture therefore cannot establish duplicate delivery within a single session. No action/after-control, passing seal, verifier export or coverage claim was made. Its fixture was shut down and removed.

The native UI also reported exit 127 and invalid SessionStart JSON. Targeted hook-only inspection found two repository-relative commands unavailable from the fixture, and inherited Cursor-only AWA adapters. The worktree session hook emits Cursor's `additional_context`, whereas Codex documents `hookSpecificOutput.additionalContext`. Existing AWA hooks can also attempt Cursor-specific state work. They do not establish Codex registration or protection.

## Bounded corrections

1. Preserve the complete v1 bundle and all frozen documents byte-for-byte. Add `live-verify/codex-native-capture-v2/`, restricted to A03 only.
2. Before the control starts, bind the actual target native session through a controller-derived, salted HMAC. Store the binding in a private 0600 `capture/session.bin`, its digest in the run manifest and exactly one S1 mapping in the private labels file. The pre-witness binds this manifest. Never persist the raw session id.
3. Reject foreign/missing session identity before label allocation or ledger append. Require S1 in every ledger event. Keep the exact one-callback expectation for BEFORE, ACTION and AFTER; reject widened counts/routes/scenarios. Record `session_scope = CONTROLLER_BOUND` in exports. This deliberately cannot support host-wide absence claims.
4. Preallocate a private one-byte collector-contention.bin flag. Lock contention sets it durably and makes the run ineligible for export regardless of apparently exact counts or witness health. Never clear or salvage that run. Remove session.bin, salt and labels before offline verification; retain the contention flag through verifier checks and recheck it before copying an export. Preserve descriptor/owner/mode/source checks and fail-open observation. Reject same-session duplicates and forged foreign-session ledger rows.
5. Deliver source through full repository verification and normal verifier/reviewer-App PR handling before any native v2 capture. Offline synthetic tests remain distinct from host evidence.

## Host correction and current restriction

The concrete proposed hook-only correction removes seven obsolete/incompatible user entries from Codex: the missing relative SessionStart and PostToolUse commands, plus AWA's Cursor-only prompt, worktree-session, recovery-maintenance, session-handoff and stop-observer entries. Retain the valid agent-route index-refresh entry, all managed hooks, unrelated configuration and all Cursor configuration. Do not copy configuration/credentials or create a configuration backup.

Automatic approval review rejected this persistent seven-entry removal because it includes security/integrity hooks and requires explicit authorization for that exact change and its ongoing effect. The cleanup was not executed. This is a real host-repair restriction; do not bypass it with alternate writes, disabling controls, wrappers, or a supposedly isolated configuration. Complete unaffected source work, then present the exact change and rejection reason to the operator.

## Acceptance ledger

| Requirement | Verification | Claim boundary |
|---|---|---|
| Reject foreign-session contamination | Synthetic real-observer stdin tests and unchanged label/ledger assertions | Observer scope only |
| Preserve count controls | Duplicate-primary, widened-manifest and foreign-ledger rejection tests | No relaxed success criteria |
| Safe export | Three-phase synthetic verifier test, ephemeral-binding rejection and sticky contention/race refusal | No native capture claim |
| Preserve prior authority | v1 bytes unchanged; no frozen plan/ADR edits | No profile or implementation acceptance |
| Correct host hooks | Exact cleanup still requires authorization accepted by automatic review, followed by fresh supported metadata/UI validation | Not yet applied |

No capture result from this repair can accept D1/D2/D3 or enable AWA-dependent rollout by itself. No native lifecycle cleanup, registration, protection, user-config backup or unrelated repository work is included.
