# Native Codex Interoperability

- **Version:** v1
- **Status:** DRAFT — OWNER PROFILE DECISION, CAPTURE, IMPLEMENTATION, AND ROLLOUT NO-GO
- **Date:** 2026-10-28
- **Architecture authority:** draft
  [ADR 0029](../adr/0029-native-codex-interoperability-boundary.md)
- **Relates to:** accepted ADRs
  [0020](../adr/0020-awa-integrity-surveillance-and-lifecycle.md),
  [0024](../adr/0024-first-prompt-native-entry-recovery.md), and
  [0026](../adr/0026-durable-registration-authority-hardening.md)
- **Preparation baseline:** clean live AWA `main`
  `f8c4714e3817c86c012f067e2fc869f8b5775be7`
- **Plan type:** evidence-first host qualification and separately gated future
  implementation after exact owner decisions

**Goal:** Determine whether native Codex can support either (a) a separately
scoped, honestly bounded AWA registration contract or (b) full AWA parity, then
implement only the exact profile the owner accepts. Never synthesize identity
from `cwd`, PID, environment, attachment, receipts, or native worktree state.

> **Governance stop:** This draft authorizes documentation preparation only.
> It does not authorize live hook capture, settings/config changes, restart,
> source/tests/contracts implementation, AWA state writes, registration,
> protection claims, Close, release, installation, Dev host wiring, canary, or
> ADR 0026 activation. Each gate below is independent; no earlier gate implies a
> later one.

---

## 1. Purpose and boundary

AWA currently has an accepted Cursor-native entry contract. Codex exposes
`session_id`, turn-scoped `turn_id`, and `cwd`, but not Cursor's documented
conversation/generation/root envelope. Tool hooks cover several local tool
paths while explicitly excluding or allowing opt-out/fail-open paths.

This plan prepares one decision without hiding the tradeoff:

- **C-Bounded:** accept a distinct Codex contract for a finite proven local
  surface, with operator copy that explicitly denies a global protection claim;
  or
- **C-Parity:** retain full lifecycle and protection parity and remain
  unsupported until the host supplies and proves it.

The plan preserves:

- ADR 0020's AWA-product / `~/dev` host-wiring boundary and kernel-first
  invariant;
- ADR 0024's refusal to fabricate identity or cleanup authority;
- ADR 0023/0024 cleanup independence and exact-`Close` finish boundary;
- ADR 0026's governance-only, implementation/R0 NO-GO state; and
- external hook-owner zero-access and runnerless operation.

No task edits frozen ADRs or accepted plans. A later accepted successor freezes
byte-identically under the repository convention.

## 2. Verified basis and stop conditions

### 2.1 Preparation evidence recorded 2026-10-28

| Surface | Evidence |
|---|---|
| AWA source | Local base and live `origin/main` both `f8c4714e3817c86c012f067e2fc869f8b5775be7` |
| Workspace | Native attached linked worktree, dedicated branch, canonical personal identity, unique writer lock |
| Governance | ADR/plan indexes read first; ADRs 0020/0023/0024/0026 read from the exact base; structural doc-warden check conformant |
| Doc-warden v2 | `migration_required`, `repository_key:null`, `write_enabled:false`; no v2 semantic authoring receipt is claimed |
| Codex hooks | Release docs provide `session_id`, turn `turn_id`, `cwd`, lifecycle sources, covered local tool classes, and explicit gaps/fail-open behavior |
| Codex worktrees | Release docs distinguish detached native placement, handoff, archive snapshot, restoration, and host cleanup |
| Live behavior | Not captured; no settings, hooks, restarts, AWA state, registration, protection, or cleanup mutations occurred |

### 2.2 Stop and refresh if

- ADR 0029 or this plan changes after its last reviewed hash;
- live main changes native entry, registration, lifecycle, current-session,
  guard, finish, cleanup, hook ownership, installer, or projection semantics;
- official Codex release documentation changes the event, field, tool-coverage,
  failure, cloud, or worktree lifecycle contract;
- the selected native host/tool contract differs from the accepted capture
  evidence;
- an action would require raw prompts/transcripts, secrets, service/auth writes,
  `chaos-scheduler`, MCP-builder, or a downstream authority copy;
- a primary/concurrent worktree, foreign writer lock, or frozen record would be
  edited; or
- an operation needs a gate that has not named its exact artifact, revision,
  consequences, and rollback.

An unrelated main advance may be rebound only after recording its exact OID and
proving the protected-surface diff does not invalidate the plan.

## 3. Owner decisions

### D0 — preparation direction (the concrete pending decision now)

Choose exactly one direction without accepting architecture or authorizing an
operation:

- `EVALUATE_C_BOUNDED`: prepare the later exact consequence preview needed to
  seek live-capture GO and populate D2/D3; or
- `RETAIN_C_PARITY`: perform no capture and leave native Codex unsupported until
  the host contract itself supplies enough parity evidence.

D0 is not D1, architecture/plan acceptance, capture GO, or implementation GO.
`EVALUATE_C_BOUNDED` merely selects which evidence proposal may be prepared.

### D1 — formal semantic profile (part of architecture acceptance)

Choose exactly one:

| Choice | Accepted claim | Required operator wording | Result while guarantees are missing |
|---|---|---|---|
| `C-Bounded` | Codex-bounded registration for an exact local allowlist only | Name qualified events/tools and every unsupported protection residual | Unsupported outside the allowlist; never globally “protected” or “safe” |
| `C-Parity` | Full parity with accepted Cursor/AWA lifecycle, mutation-path, failure, and cleanup separation | Ordinary AWA claim only after parity is proved | Entire native Codex path remains unsupported |

Silence, general approval, plan acceptance, or implementation GO is not D1.
C-Bounded cannot be selected at D1 until completed D2/D3 evidence is accepted.

### D2 — exact lifecycle allowlist (C-Bounded only)

After the separately approved capture, accept an exact matrix over:

- `SessionStart.source`: `startup`, `resume`, `clear`, `compact`, `fork`;
- `UserPromptSubmit` first and later turns;
- local-to-worktree/worktree-to-local handoff and return;
- branch creation, cwd-at-root, cwd-in-subdirectory, root replacement, and
  multi-root/ambiguous contexts;
- subagent start/stop, parent session inheritance, interrupt, stop, and
  session end; and
- archive, host deletion, restore, and snapshot behavior as observation only.

Each cell is `QUALIFIED_REGISTRATION | OBSERVATION_ONLY | UNSUPPORTED`. No
unknown cell defaults to qualified.

### D3 — exact local tool allowlist and residuals (C-Bounded only)

Accept one closed inventory that distinguishes:

- Bash and unified exec (`PreToolUse` reports both as `Bash`);
- empty `write_stdin` polling versus non-empty input to an input-capable exec
  process handle (the latter is always `NO_AWA_COVERAGE` in v1);
- `apply_patch` (`apply_patch | Edit | Write` matcher aliases);
- each named MCP tool or a reviewed closed server/tool family;
- each other local function tool, including `Agent`/`spawn_agent`;
- hosted tools with no hook coverage;
- specialized opt-out paths; and
- error, timeout, malformed output, missing server, disabled hook, async hook,
  cloud orchestration, and post-effect behavior.

Each row names `PRE-EFFECT_DENY_CAPABLE | EVIDENCE_ONLY | NO_AWA_COVERAGE` and
the tested failure disposition. No wildcard or future tool inherits coverage.

### D4 — operation gates

The owner decisions are separately named:

1. architecture acceptance (ADR bytes plus D1; C-Bounded additionally requires
   completed and accepted D2/D3 evidence, while C-Parity may remain unsupported
   without capture);
2. plan acceptance (C-Bounded requires completed D2/D3 evidence; only
   C-Parity may explicitly defer capture because it remains unsupported);
3. live-capture GO;
4. capture settings/install/restart GO, if needed;
5. race/failure canary GO;
6. implementation GO against an exact refreshed baseline;
7. implementation delivery authority for exact revisions;
8. release/tag authority;
9. installation authority;
10. `~/dev` host-wiring authority;
11. activation/UAT canary GO; and
12. broader rollout GO.

No decision implies another. Native archive and AWA Close are never combined.

## 4. Fixed candidate contract

This section is the implementation target only if C-Bounded is selected and
D2/D3 accept the corresponding cells. C-Parity uses the same parser/evidence
discipline but activates nothing until every parity requirement passes.

### 4.1 Closed identity and event envelope

Expected new schema family:

```text
awa-codex-host/v1
awa-codex-native-entry/v1
awa-codex-current-session/v1
awa-codex-heartbeat/v1
awa-codex-root-blocker/v1
```

Required mapping:

```text
key.host             = literal "codex"
key.session_id       = exact supplied non-empty session_id
attempt.turn_id      = exact supplied turn_id only on events that define it
candidate.cwd        = exact supplied cwd, used only to select a root candidate
```

The parser uses strict bounded UTF-8 JSON, rejects duplicate/unknown keys and
non-finite or wrong-typed values, and caps every string/object before semantic
processing. It accepts only exact release-documented event names and fields.
No alias imports Cursor `conversation_id` or `generation_id` meaning. No
environment, PID, attachment, transcript, model, receipt, Git row, or process
cwd repairs missing host fields.

Subagent events inherit the parent session but cannot create another lifecycle
member or register another root. A root-changing event for one existing session
key is a mismatch until an exact owner-accepted transition is defined; v1
defines none.

The two session-state records use the full digest of the canonical
`["codex", session_id]` pair as their filename key and retain the exact host and
session inside the record for equality validation. `awa-codex-current-session/v1`
binds the root/Git identity, accepted profile, contract/runtime digests, AWA
generation, source event, optional source turn, and timestamps.
`awa-codex-heartbeat/v1` binds the same host/session/root/common-directory
identity, boot observation, heartbeat generation, and freshness. PID, boot,
time, and `SessionEnd` remain diagnostic only.

`awa-codex-root-blocker/v1` is keyed by the full canonical-root digest and
contains the exact root/Git identity plus a bounded sorted set of full
host-session key digests. Registration publishes a pending blocker member
before session/heartbeat state and may publish success only after all records
agree. This status order permits an orphan blocker after a crash but never a
successful unblocked registration. A future exact finish removes session
evidence first and the last blocker member last.

Writers use private durable atomic publication and CAS under the lifecycle ->
Codex-session lock order. A pre-existing key with different facts refuses; v1
has no session move. These schemas are not aliases or inputs to Cursor
`awa_current_session/v1`/`active_root/v1` readers. They feed only the Codex
registrar, integrity/discovery, and an additive active-root blocker. Neither
staleness, missing heartbeat, PID exit, SessionEnd, archive, nor host deletion
can clear the blocker or authorize cleanup. Codex-aware exact-`Close` requires
a later accepted finish contract; until then, cleanup from the Codex surface is
unsupported.

The canonical cleanup gate performs one root-keyed bounded blocker lookup
before ordinary disposition. Present malformed, special, unreadable, over-cap,
mismatched, or lock-contended blocker state refuses removal. Absence is
non-blocking only because the registrar must publish the blocker before any
successful or authority-bearing session state. Compatibility tests prove that
roots with no Codex blocker retain existing Cursor behavior.

### 4.2 Root and policy resolution

From candidate `cwd`, resolve without writing:

1. an existing directory with descriptor-safe, no-follow checks on every
   authority-bearing component;
2. canonical physical path and Git top-level;
3. per-worktree Git directory and common Git directory;
4. one exact matching `git worktree list --porcelain` entry;
5. attached branch and exact HEAD;
6. local, non-primary, linked, eligible policy classification;
7. clean content and visible index with no merge/rebase/cherry-pick/bisect or
   other in-progress operation; and
8. exact runtime/contract/profile identity.

Native attachment is recorded only as placement evidence and is not required
or sufficient authority. Multi-root, symlinked, detached, primary, excluded,
dirty, in-progress, missing, ambiguous, or policy-ineligible roots refuse.

### 4.3 Locking and transitions

Perform the full preflight, acquire the existing per-common-directory lifecycle
lock, and repeat every authority-bearing check. Fixed nested order:

```text
common-directory lifecycle lock -> Codex receipt/session lock
```

Under lock, require exact current-session/heartbeat, root/Git, lease, SQLite,
attestation, receipt, host profile, runtime, and allowlist state. Then:

1. exact-current success may return a no-op only after complete revalidation;
2. otherwise CAS-publish a monotonic non-green pending receipt;
3. perform at most one already-authorized lifecycle adoption/repair using the
   existing disk -> SQLite -> event -> attestation ordering;
4. re-read the complete result; and
5. CAS pending to terminal only if every identity and generation still matches.

The receipt generation orders AWA evidence only. `turn_id` never orders
lifecycle transitions. Replayed `{session_id, turn_id}` with changed facts,
root reuse, stale CAS, contention, timeout, or partial state refuses. Host hook
failure may fail open for the host operation but cannot publish AWA success.

### 4.4 Exact tool-path semantics

The future product contract must encode the accepted D3 table, not generic
marketing prose. Minimum fixed rules:

- Bash and unified exec share one pre-effect decision only for one-shot,
  non-interactive commands that complete before an input-capable session handle
  is returned. An empty `write_stdin` poll is evidence-only. Any non-empty
  `write_stdin` input has `NO_AWA_COVERAGE`, and any returned input-capable
  process/session is excluded from a protection claim.
- `apply_patch`, MCP, and local function tools require their own exact parser,
  discriminator, serializer, and failure tests before any coverage claim.
- `PermissionRequest` is never treated as universal coverage.
- `PostToolUse`, async hooks, `SessionEnd`, and archive/restore are evidence-only.
- hosted, opt-out, disabled, cloud-unsupported, timeout, malformed, and missing
  handler paths remain explicit residuals.
- unknown/new tools have no AWA coverage. In C-Bounded they must be shown as
  unsupported; in C-Parity they prevent activation.

The plan does not activate ADR 0026 v4 admission. A later ADR must explicitly
compose Codex with that protocol after R0 authority exists; no shared role name
or similar payload is enough.

### 4.5 Evidence and operator projection

`awa-codex-native-entry/v1` stores only the fields enumerated by ADR 0029. It
uses private owned directories/files, no-follow reads, same-directory atomic
publication, fsync, monotonic CAS, freshness, collision-safe names, and closed
value-free reason codes.

For C-Bounded, public/operator output includes:

```text
registration_scope = "codex-bounded"
qualified_events   = <exact accepted list>
qualified_tools    = <exact accepted list>
unsupported        = <exact residual list>
protection_claim   = false
```

For C-Bounded v1, `protection_claim` is the literal `false`. It cannot become
true by narrowing an undefined set of “relevant” paths. A true global claim is
available only under C-Parity after zero material gaps are proved.

No bare green verdict is allowed. Missing/unrun evidence is `not_checked` or
`unsupported`, never zero or success.

### 4.6 Authority separation

- Registration receipts never authorize tool allow, finish, removal, archive,
  restoration, or branch deletion.
- Exact `Close` is still required by AWA's Phase-1 kernel. Archive is not Close.
- AWA owns product schemas/adapters/tests; `~/dev` owns live Codex hook/config
  rows and host activation.
- External mode remains zero-access to the real hook file.
- No release/install/host/canary step may run from implementation GO alone.

## 5. Sanitized evidence protocol — separate GO required

### 5.1 Post-GO synthetic implementation matrix (not D2/D3 host evidence)

Create fixtures for every D2/D3 row plus:

- missing/empty/oversized/wrong-typed/duplicate/unknown identity fields;
- same session + same turn duplicates, same turn + changed root/event, and
  same session + changed root;
- startup/resume/clear/compact/fork reorder and duplicate delivery;
- cwd root/subdirectory/symlink/missing/multi-root and Git-state drift between
  preflight and lock;
- concurrent prompt/start/tool events, stale writer CAS, timeout at each lock
  and publication boundary, and crash before/after lifecycle effects;
- subagent parent-session inheritance without member creation;
- Bash/unified-exec/write-stdin relationship;
- apply_patch/MCP/local/hosted/opt-out tool coverage; and
- hook disabled, timeout, malformed response, missing MCP server, async,
  SessionEnd, archive, restore, and post-effect paths.

Synthetic fixtures prove parser/state-machine behavior only. They never prove
native host delivery and are not prerequisites or evidence for pre-implementation
D2/D3. D2/D3 qualify host delivery only from release documentation plus the
separately approved sanitized live capture and adjudication. Synthetic fixtures
later verify that an authorized implementation honors the already accepted
matrix; they cannot retroactively populate or widen it.

### 5.2 Future live capture (prohibited until exact consequence preview/GO)

A separately reviewed throwaway capture harness may record only:

- event name and documented source enum;
- presence/type/length class of `session_id`, `turn_id`, and `cwd`;
- ephemeral equality labels (`S1`, `T1`, `R1`) scoped to one capture run;
- cwd relationship class (`root | subdir | changed | missing | ambiguous`), not
  the raw absolute path;
- tool class/discriminator, hook outcome class, ordering counter, and bounded
  monotonic timing bucket; and
- host surface/build when the native tool supplies it, otherwise `unknown`.

Every planned scenario also has an independently committed sanitized ledger
row containing a closed scenario id, scenario/action digest, pre-barrier id,
post-barrier id, expected callback/event counts, observed counts, harness-health
result, hook/config content hashes, process exit class, and completion status.
The pre-barrier is committed before the scenario action and the post-barrier
only after bounded completion/cleanup. A missing barrier, unhealthy harness,
hash drift, count mismatch, or incomplete scenario is failed evidence—not a
negative coverage observation.

It must reject and never persist prompt, transcript path/content, tool input,
model text, attachments, credentials, environment, user identity, raw IDs,
absolute paths, raw logs, or arbitrary URLs. Run output lives only in an exact
throwaway root with a frozen manifest and expiry/deletion plan named by the
future approval.

The consequence preview must separately enumerate any temporary settings file,
hook install, trust prompt, app restart, chat creation/fork/handoff, branch
creation, archive/restore/deletion, subagent, network, or race action. Approval
for one does not authorize another. Archive/delete scenarios must use a
disposable fixture and must not invoke AWA Close.

### 5.3 Adjudication

Two independent passes consume only the sanitized manifest:

1. lifecycle/identity adjudicator fills D2 and refuses every unproven cell;
2. tool/failure adjudicator fills D3 and refuses every unproven coverage claim;
3. both require exact scenario-ledger set equality, healthy barriers, stable
   hook/config hashes, and expected/observed count reconciliation before using
   an absent callback as evidence.

The owner sees exact hashes, counts, scenario coverage, omissions, and residuals
before selecting C-Bounded. C-Parity requires zero material parity gaps; a
waiver silently converting it to bounded is forbidden.

## 6. Future implementation bodies — only after accepted ADR/plan and GO

### Body A — host contract, parser, and receipts

**Expected files:**

- Create `contracts/awa-codex-host.v1.json`
- Create `engine/codex_native_entry.py`
- Create `engine/tests/test_codex_native_entry.py`
- Create `engine/tests/fixtures/codex-native-entry/`
- Modify packaging/inventory only where the accepted manifest requires it

**Work:** Freeze the D2 envelope, strict parser, host-tagged key, root resolver,
private receipt schema, monotonic CAS, replay/mismatch refusal, and zero
Cursor/v4 aliasing. Tests must prove RED then GREEN for every accepted leaf and
every refusal.

**Exit:** Source-only tests pass; no installer, live hook, state, or registration
path is active.

### Body B — bounded adapters and under-lock lifecycle

**Expected files:**

- Create `kernel/hooks/awa-codex-session-start.sh`
- Create `kernel/hooks/awa-codex-user-prompt-submit.sh`
- Create only the D3-approved per-tool adapter(s)
- Modify `engine/codex_native_entry.py`
- Modify `kernel/lib/awa_roots.py` only to add the root-keyed bounded Codex
  blocker lookup before ordinary cleanup disposition
- Create `engine/tests/test_codex_native_concurrency.py`
- Create `engine/tests/test_codex_native_tool_coverage.py`
- Create `engine/tests/test_codex_active_root_blocker.py`
- Modify `engine/tests/test_clean_kernel.py` for no-blocker compatibility and
  malformed/contended fail-closed cases

**Work:** Add absolute-deadline adapters, fixed lock order, complete pre/under-
lock validation, exact-current no-op, at-most-once lifecycle effects, closed
serializers, root-blocker-first/status-last publication, canonical cleanup-gate
blocking, process cleanup, and host-failure/no-success behavior. Keep finish
code and cleanup authorization/removal semantics unchanged; the new kernel
lookup is additive deny-only and grants no removal path.

**Exit:** Complete deterministic fault/interleaving matrix passes in disposable
state. Unknown tools and lifecycle sources cannot acquire a positive claim.

### Body C — product projection and compatibility

**Expected files:**

- Modify `engine/integrity.py` only for honest Codex-bounded/not-supported
  projection
- Modify installer/package manifests to ship product bytes without touching
  external host hook files
- Add exact compatibility tests for hook-owner v1-v4 and Cursor native entry
- Add source-only operator-copy tests and contamination/import checks

**Work:** Project the selected profile and residuals, preserve Cursor bytes and
behavior, preserve external zero-access, and prove registration/protection/
cleanup separation. Do not activate ADR 0026.

**Exit:** Full AWA verification is green at exact head; independent review finds
no false authority or unsupported success claim.

### Body D — separately authorized host wiring and canary

AWA release/tag and installation occur only after their own gates. A separate
`~/dev` change may then project exact Codex hook/config rows from the released
AWA contract. It must preserve host ownership, provide rollback, and avoid
duplicating canonical prose.

Activation canary runs only the accepted D2/D3 cells, verifies receipts and
failure residuals, checks no primary/concurrent root changed, and proves no
process or temporary capture state survived. C-Bounded output must still expose
all residuals. C-Parity cannot activate if any residual remains.

## 7. Acceptance ledger

| ID | Requirement | Required evidence | Failure result |
|---|---|---|---|
| NC-01 | No identity synthesized | Parser/refusal matrix for cwd/PID/env/receipt/attachment fallbacks | NO-GO |
| NC-02 | Host-tagged `session_id` only | Exact schema and replay/root-mismatch tests | NO-GO |
| NC-03 | `turn_id` provenance only | No lifecycle ordering use; duplicate/reorder tests | NO-GO |
| NC-04 | Under-lock revalidation | Race matrix for every authority-bearing field | NO-GO |
| NC-05 | Exact tool coverage | Accepted D3 inventory plus native evidence | Residual or NO-GO per profile |
| NC-06 | Fail-open honesty | Timeout/error/malformed/disabled/cloud tests publish no AWA success | NO-GO |
| NC-07 | Cleanup separate | Archive/SessionEnd/receipt cannot call or authorize Close/removal | NO-GO |
| NC-08 | ADR 0026 remains inactive | Import/role/runtime inventory proves no v4 composition | NO-GO |
| NC-09 | Product/host ownership split | AWA external zero-access; Dev-only live projection | NO-GO |
| NC-10 | No sensitive capture | Sanitized schema and forbidden-field corpus | NO-GO |
| NC-11 | Cursor compatibility | Existing native-entry and hook-owner suites byte/behavior compatible | NO-GO |
| NC-12 | Profile-specific copy | C-Bounded residuals visible; C-Parity zero-gap gate | NO-GO |
| NC-13 | Writer/process cleanup | Clean tree/index, lock ownership, no surviving worker/temp state | NO-GO |
| NC-14 | Governed delivery | Exact hashes, review, required checks, reviewer-App merge process | NO-GO |

## 8. Verification and review

At each future source body:

1. run exact focused RED/GREEN tests for the changed contract;
2. run `make verify-docs VERIFY_BASE=<exact-base>` for docs-only bodies;
3. run exactly one complete authoritative gate for implementation bodies:
   `make verify-pre-pr` (currently an alias/dependency of `make verify`); never
   run both in one verification invocation;
4. do not repeat `bash install.sh --check`, which the complete gate already
   composes. Run a separate packaging/install/static gate only when the complete
   gate does not cover it or the changed surface requires additional proof
   (for example, `make verify-install` after installer behavior changes);
5. obtain independently routed technical review against exact document/source
   hashes, then resolve every material finding;
6. inspect `git diff --check`, status, branch, HEAD, remote, writer lock, and
   protected frozen-record hashes; and
7. deliver through a ready PR and the repository's verifier/reviewer-App process
   without enabling auto-merge or bypassing checks.

Docs-only verification is non-authoritative for runtime. Synthetic fixtures are
non-authoritative for native host delivery. Reviewer selection does not prove
execution identity when the host reports only a worker handle.

## 9. Non-goals

- No implementation, live capture, settings change, restart, registration,
  protection claim, Close, cleanup, release, install, host wiring, or canary in
  this preparation body.
- No raw transcript/prompt/tool-input logging or memory write.
- No `chaos-scheduler`, MCP-builder, auth/service write, paid runner, or
  downstream distribution.
- No Cursor contract rewrite, ADR 0026 activation, generation fabrication,
  wildcard tool qualification, or archive-as-Close.
- No primary or concurrent worktree edits, lock stealing, or frozen record
  changes.

## 10. Gate order

```text
draft ADR 0029 + draft plan
-> exact-byte independent technical review
-> owner D0: RETAIN_C_PARITY, or EVALUATE_C_BOUNDED as an evidence direction
-> separate live-capture consequence preview and GO (mandatory for C-Bounded)
-> separately approved settings/install/restart/capture/race operations
-> D2/D3 adjudication and exact residuals
-> exact D1 architecture acceptance
-> exact plan acceptance
-> separate exact-baseline implementation GO
-> separate exact-revision implementation delivery authority
-> Bodies A-C with full verification/review
-> ready PR through verifier/reviewer-App merge process
-> separate release/tag authority
-> separate installation authority
-> separate ~/dev host-wiring authority
-> separate activation/UAT canary GO
-> separate broader rollout GO
```

If the owner selects C-Parity and any parity gap remains, the sequence stops at
unsupported. If the owner selects C-Bounded, every residual remains visible and
no later evidence may silently widen the accepted allowlist.

## 11. Current owner gate

This draft asks for no acceptance yet. The concrete pending preparation
direction is D0: **EVALUATE_C_BOUNDED** or **RETAIN_C_PARITY**. The former only
allows preparation of the later capture consequence preview; it does not grant
capture GO. Formal D1 C-Bounded selection requires the separately approved
capture and completed D2/D3 adjudication before architecture or plan acceptance.
Formal C-Parity may be selected without capture and leaves native Codex
unsupported until full guarantees exist.

Without exact ADR acceptance, exact plan acceptance, and the later gate named
for an operation, the instruction remains **NO-GO**.
