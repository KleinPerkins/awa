# AWA authoritative verification v4 replacement canary — 2026-09-03

## Canary status

This inert, documentation-only marker triggers a fresh exact-head AWA canary from repaired `main`
through the ordinary verifier/reviewer-App path. It changes no runtime behavior.

PR #156 merged the audited noexec repair. Live receipts and the A01–A21 closure ledger remain
pending and must be handled only by the separately governed parent rollout after this canary passes.

Adding a tracked marker changes the source digest bound by
`live-verify/RESULTS-noexec-repair-process-profile-20260903.md`. Do not bypass that gate, weaken its test, exclude the new file, or hand-edit values merely to obtain green.
