# First-prompt and local-tool capture definitions

- **Version:** v1
- **Status:** DRAFT — INERT SOURCE PREPARATION; NEW LIVE PREVIEW AND TECHNICAL ADJUDICATION PENDING
- **Date:** 2026-10-31
- **Relates to:** frozen capture previews v1/v2; hook-control repair v1/v2; draft interoperability plan and ADR 0029
- **Authority:** existing standing operational/source-delivery authorization, within the original fixed-fixture evidence lane. This is no product-adapter, authority, profile, ADR 0026, implementation or activation GO.

## Purpose and verified basis

PR #192 merged at `a754ebd2cc69a871d090ba7e6d36c696ebe533ed`, with exact-head App approval and five passing checks. Its reviewed/merged tree matches. C5/A03 then produced exactly one target-session UserPromptSubmit callback in BEFORE, ACTION and AFTER. The offline export is OBSERVED for that one controller-bound route. Its canonical 3,567-byte result has SHA-256 `38c12b5b7a14064614e7876168943d570981ca07029276014f4a847695db5491`; publication is separately tracked in PR #193. The fixture and controller preparation are removed, four baseline definitions read back unchanged, and startup/MCP warnings remain explicit limitations.

This next preparation preserves v1/v2, frozen plans/ADRs and C5 proof bytes. The existing repaired collector selects only A03. The legacy collector cannot be reused for new qualification claims because it admits foreign sessions and can silently lose contended callbacks.

## 1. A02 first-prompt definition

A prompt cannot be the first controller-submitted prompt if another prompt was first used as its same-session BEFORE control. Never relabel the C5 BEFORE control as a new A02 action. Prepare v3 as a new inert eight-file bundle selecting only the already-catalogued A02 action, `FIRST_SYNTHETIC_PROMPT`, with literal `AWA-CODEX-CAPTURE-A02`.

Before execution the external controller must prove that it created a fresh fixture thread through a supported native interface and has submitted zero turns to it. It must bind that exact opaque session to S1 using the retained raw-32-byte HMAC protocol before the pre-witness. Freshness and literal reply checks are controller/host witness facts, not reconstructed from the public export. If a supported fresh-thread/controller-turn witness is unavailable, this scenario cannot proceed or establish freshness.

| Phase | Exact target events | Meaning |
|---|---|---|
| BEFORE | zero | No controller prompt is submitted in this window; this is no host-wide absence claim |
| ACTION | one UserPromptSubmit, S1, R1 | First controller synthetic prompt only |
| AFTER | one UserPromptSubmit, S1, R1 | One later positive route observation |

The post-witness control pair is exactly `before=0`, `after=<after event sequence>`. Expected action counts are exactly one UserPromptSubmit and zero for every other type. Any unexpected before event, missing/duplicate action, missing/duplicate after event, wrong root/source/session, route/count widening or assertion of SAME_ROUTE health refuses export.

A02 must always export `completion_status=UNPROVEN`, `harness_health=UNKNOWN`, `positive_control_route_match=UNAVAILABLE`, with witness health UNAVAILABLE. A positive action count and after observation do not create a healthy BEFORE control. This retains the conservative unknown-health policy and cannot promote A02 to qualified registration or support a negative claim. Promoting these labels or accepting an observation as a product guarantee is a separate material evidence/acceptance decision.

The new source files are exactly the familiar seven inputs plus generated manifest beneath `live-verify/codex-native-capture-v3/`: README, observer, offline verifier, v3 schema, v3 catalog, v3 forbidden corpus, v3 inert template and MANIFEST. No current source/receipt is rewritten. Schema fields and privacy limits stay closed; no raw tool arguments/results or new captured payload field is added. Only the UserPromptSubmit definition is rendered; there is no unused trust dependency.

## 2. A04/A05 local-tool definitions — inert and unresolved

The original fixed-fixture cases can be prepared together, but remain `executable=false` in v3. The draft D3 text says both Bash and unified exec report Bash, while the legacy catalog assigns distinct BASH/UNIFIED_EXEC predicates. This is a documented contract discrepancy, not a current host fact inferred from the draft. Resolve it against supported current tool offers, hook envelopes and a closed controller invocation witness before enabling either case. A model assertion, executable shell name, wildcard alias or widened predicate is insufficient.

| Case | Candidate fixed effect | Proposed controls, pending tool contract |
|---|---|---|
| A04 | Native one-shot Bash writes only a named synthetic fixture file, with fixed bytes and bound preimage | BEFORE/ACTION/AFTER each one PreToolUse and one PostToolUse; no permission event or extra tool |
| A05 | Native unified exec reads a named synthetic fixture file and completes without an input-capable handle | Same fixed pre/post counts; supported completion/handle witness required |

These are candidate definitions, not enabled count alternatives. Bind exact paths, fixed bytes, preimages, native tool identities, input/handle semantics, permissions and controls before a new operation. If a route/tool distinction is unavailable, record it as unsupported; do not substitute unified exec running a Bash shell for a native Bash tool. Non-empty handle input, hosted/MCP actions, work data, subagents, races and host lifecycle deletion are outside these definitions.

## 3. Retained custody and claim boundaries

Retain v2's target-session rejection before label allocation, sticky fsynced contention flag/original inode, exact source/config/directory identities, descriptor/no-follow ownership and mode checks, private ephemera deletion before offline verification, fail-open `{}`/zero observer response, no context injection or callback replay, process terminality before export, and exact fixture cleanup. Preserve unrelated baseline sources and all their hashes/trust/enabled states. Keep warnings separate from route health.

The source is inert until copied into a separately bound fixture after reviewed merge and required preview/gates. Standing authority avoids generic repeat permission requests; it cannot define missing tool/handle facts, authorize a new data contract by implication, or select/accept a semantic profile. No new live capture begins from this draft alone. D2/D3 remains incomplete; D1 C-Bounded cannot precede completed accepted D2/D3. Registration, protection, implementation, ADR 0026 execution, release and activation remain NO-GO.

## 4. Acceptance ledger

| Requirement | Evidence required |
|---|---|
| No first-prompt promotion | Exact A02 positive rows produce only UNPROVEN/UNKNOWN/UNAVAILABLE; SAME_ROUTE health is refused |
| Counts stay strict | Before/action/after count, sequence, root, source and session negative tests |
| Privacy/custody retained | Foreign/binding encoding/drift, ephemera, flag loss/contention/race refusal tests under both interpreters |
| Local cases stay inert | Catalog selects only A02; renderer installs only one prompt definition |
| Frozen history preserved | v1/v2/proof/plan/ADR byte comparison against the source baseline |
| Source delivery | Independent exact-head technical review, appropriate repository checks and normal reviewer/verifier-App merge |
| New live operation | Separately fixed fresh-thread witness, operation/source/host/input bindings, shutdown/cleanup and technical adjudication of this first-control shape; no generic approval or old approval/hash reuse |

## Review provenance

This is evidence-lane source preparation only. Record actual tests and independent review against the immutable candidate head; never imply native execution or accepted fresh-thread/tool semantics from synthetic tests. PR #193 keeps its own immutable artifact head and normal delivery ownership while this work uses a separate preparation branch.
