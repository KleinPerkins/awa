---
{"approval":{"actor":"Codex under explicit owner-delegated execution authority; acceptance of reviewed existing classifier API only, not operator personal hash inspection","date":"2026-11-02","review_sha256":"68ae4567671c95d8e395b49d7d2f44e81947d9c649a1773d0faf984ff63d971d"},"authority":"semantic","github_repository_id":1289571438,"id":"ADR-e6393083-530b-5462-9038-377088993223-07a810c7-06f2-5412-a9b1-7c245b20dc95","lifecycle":"approved","mutability":"frozen_after_approval","provenance":[],"relations":[],"repository_key":"e6393083-530b-5462-9038-377088993223","schema":"doc-warden/artifact/v2","supersedes":null,"type":"adr","version":1}
---
# ADR 0033: Adopt the released lexical hard-no-touch classifier API for external consumers

## Context

ADR 0027 owns the generic `awa-hard-no-touch/v1` semantics. The published immutable v1.8.2 maintenance release carries that contract without later mainline registration changes. ShadowSync's accepted extraction architecture consumes AWA's existing lexical classifier before candidate access instead of copying matching logic into Swift. An explicit, bounded external-consumer surface makes that dependency reviewable without expanding the frozen maintenance release.

The qualified source identity to adopt is v1.8.2, commit `cfe9437739d2928014c2156532d1986a8511fd30`, annotated tag object `2c1c29e4df2948316a5c0d1bd504ecf7f25797ff`. Its `kernel/lib/awa_policy.py` SHA-256 is `e149896d854254550765aa1f42e78a83bf17b7a2f49f24bacf96425ebc6c0219`. The exact module is distributed by AWA's standalone installer; the consumer must authenticate the installed release and module before import. A source checkout, a matching version string or a mutable main branch does not establish that identity.

## Decision

Adopt the following existing AWA-owned interface for release-bound external callers:

- `HARD_NO_TOUCH_SCHEMA == "awa-hard-no-touch/v1"`.
- `load_hard_no_touch_matcher(path, home=trusted_home)` reads the selected trusted policy and returns an immutable `HardNoTouchMatcher`.
- `HardNoTouchMatcher.classify(candidate)` performs lexical classification without opening, reading metadata, resolving symlinks, listing, traversing or invoking Git/network operations on the candidate.
- The returned immutable `HardNoTouchDecision` has boolean `matched`, string `kind` and boolean `policy_valid` fields. Their closed combinations are listed below.

| kind | matched | policy_valid |
|---|---|---|
| `exact_root` | true | true |
| `managed_namespace` | true | true |
| `none` | false | true |
| `invalid_policy` | true | false |
| `invalid_candidate` | true | true |

Only the exact `false / none / true` combination can satisfy the caller's hard-no-touch admission check. It is not repository mutation authority, source trust, membership, lifecycle authority, or permission to bypass other policy. Unknown combinations, unexpected types, exceptions or unavailable classification refuse admission.

External callers use the policy-only loader and classifier. They do not call `PolicyConfig.load`, the broader repository classifier, the engine mirror or undocumented private parser helpers to obtain pre-access permission. They pass candidate path text as a string and provide a trusted absolute home derived from the account database; ambient environment variables do not establish home authority.

AWA retains all generic normalization, component-boundary matching and malformed-input semantics. The optional policy field can legitimately be absent or empty under ADR 0027. A consumer requiring deployed protection must separately verify its host owner's policy/configuration binding and deployment prerequisites; it must not reinterpret a generic no-match result as proof of that deployment. Concrete roots and managed namespace prefixes remain exclusively host-owned.

The caller owns authenticated configuration access, bounded input/output, interpreter provenance, module verification, isolated import, cancellation, deadlines and process cleanup. It must supply a coherent policy snapshot and detect replacement/drift before using a response. A platform-specific descriptor snapshot such as an unlinked read-only `/dev/fd` file requires consumer-side qualification against this exact released loader and interpreter; this adoption does not claim a portable descriptor-filesystem guarantee.

An external adapter may define its own versioned request/response envelope, but that envelope does not become a second matching authority. Candidate paths must not enter command arguments, environment variables, diagnostics or release evidence. Refusal tests use synthetic paths and disposable fixtures only.

This decision adopts existing code. It changes neither v1.8.2's immutable assets nor `release/1.8`, the controller binary/configuration, fleet pins, registration semantics or concrete host policy. Future incompatible API or semantic changes need an explicit successor contract and consumer requalification. A new module digest is a new dependency, even if exported names remain unchanged; consumers must never fall back to an unpinned module or local matcher.

## Verification and delivery

AWA's maintainer owns adoption and API compatibility tests. The host-policy owner owns deployed literals and binding generation. Each consumer owns its adapter, publisher trust and installed-runtime qualification.

Before this record can be accepted, independent review must bind the immutable tag/commit/module bytes, confirm the exact public signatures/result combinations against the release, and verify the existing zero-target-access and invalid-policy tests. Any added compatibility test runs against synthetic inputs and does not change released runtime code. Source review and current-main checks qualify the adoption change; they do not replace release-bound consumer testing.

Before ShadowSync enables repository admission, evidence must separately establish the exact installed AWA identity/module, its signed adapter contract, qualified isolated interpreter, current host-policy binding, failure-path and zero-target-access tests, and owned-child cleanup. Fresh installation, installed upgrade, concrete policy deployment and product UAT remain distinct milestones. A pending adoption or mismatched pin keeps the production consumer closed.

## Consequences

External consumers gain one narrow AWA-owned dependency and retain explicit responsibility for deployment trust and operation authority. Generic policy semantics remain in AWA; host policy remains in its owner; application transport and lifecycle remain in the application. Historical accepted records and the immutable maintenance release remain unchanged.

## Evidence to bind at governed preview

- AWA ADR 0027 and exact PR #184 backport provenance through PR #200.
- Published v1.8.2 release and annotated tag, independently downloaded assets and exact module digest.
- Existing AWA release verification and zero-target-access fixtures.
- Skills' exact release pin and isolated direct-install/external-owner upgrade receipts, explicitly distinguished from real-host installation.
- New source/adoption review, compatibility-test output and subsequent merged revision. Do not mark these future items complete from this draft.
