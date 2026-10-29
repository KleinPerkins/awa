# ADR 0029: Define a host-qualified native Codex interoperability boundary
Status: draft — 2026-10-28 (owner profile decision pending; no implementation authority)

This is a proposed successor to
[ADR 0024](0024-first-prompt-native-entry-recovery.md) for native-host entry
semantics. While this record is draft, ADR 0024 remains the accepted native
entry authority, ADR 0026 remains governance-only with implementation and R0
NO-GO, and native Codex registration and protection remain unsupported. If
accepted, this record re-adopts ADR 0024 unchanged for Cursor and adds only the
owner-selected Codex disposition below. ADRs 0020, 0023, 0024, and 0026 remain
byte-identical.

## Context

AWA's accepted native-entry path is built around Cursor's documented
`conversation_id`, `generation_id`, workspace-root envelope, and separate
kernel/cleanup authorities. Native Codex exposes a different release contract.
Official [Codex hook documentation](https://learn.chatgpt.com/docs/hooks)
currently supplies:

- a common `session_id`, described only as the current Codex session id;
- `turn_id` on turn-scoped events, including `UserPromptSubmit`;
- one session `cwd`, while commands run with that working directory;
- `SessionStart.source` values `startup | resume | clear | compact | fork`;
- `SessionEnd` as synchronous but advisory; and
- `PreToolUse`/`PostToolUse` coverage for Bash (including unified exec),
  `apply_patch`, MCP tools, and most local function tools.

The same documentation does **not** promise that `session_id` is equivalent to
Cursor `conversation_id`, that it is stable across every resume/fork/compact or
worktree handoff, that `turn_id` is a lifecycle generation, that `cwd` is a
canonical Git root, or that lifecycle/tool hooks are exactly-once and totally
ordered. Subagent hooks use the parent `session_id`.

Coverage is also explicitly incomplete. Hosted tools are outside the local
function-tool hook path, specialized tools may opt out, `write_stdin` does not
receive a second `PreToolUse`, and hook errors, timeouts, malformed responses,
missing MCP servers, or unsupported response fields can leave the triggering
operation unblocked. Cloud orchestration does not support ordinary local
command hooks. A background hook cannot block. `PostToolUse` cannot undo an
effect.

Official [Codex worktree documentation](https://learn.chatgpt.com/docs/environments/git-worktrees)
describes native worktree placement, handoff, snapshot, restoration, and
automatic deletion. Those host operations do not establish AWA identity,
registration, protection, or cleanup authority. Archiving a chat and deleting
its worktree is not AWA exact-`Close`.

These are sufficient facts to propose a boundary. They are not sufficient to
claim parity or activate registration.

## Decision

### 1. Preserve the current unsupported state until an exact owner profile is accepted

This draft chooses neither of the two profiles in §3. Native Codex attachment,
the current working directory, a process id, environment variables, a receipt,
or a native worktree snapshot must not be translated into AWA identity or
authority. No existing Cursor receipt, hook-owner contract, or ADR 0026 v4
admission role is reusable by implication.

Until the owner accepts one exact profile and every later gate applicable to an
operation succeeds:

```text
native Codex AWA registration = unsupported
native Codex AWA protection   = unsupported
native archive/snapshot       != AWA Close
```

### 2. If qualified, use a separate host-tagged identity family

Any future Codex contract uses a distinct schema family, expected to begin with
`awa-codex-native-entry/v1`. It never writes or relabels
`awa-native-entry/v1|v2`, never invents Cursor fields, and never enters ADR
0026's durable-registration protocol without a later successor that explicitly
proves and authorizes that composition.

The only candidate normalized mapping is:

```text
lifecycle candidate key = {host: "codex", exact supplied session_id}
attempt provenance      = exact supplied turn_id, when the event defines it
root candidate selector = exact supplied cwd
```

The mapping has strict limits:

- `session_id` is a proposed host lifecycle key, not a conversation id,
  cleanup key, or proof of stability;
- `turn_id` is per-attempt provenance only. It is never a generation, lifecycle
  identity, ordering clock, or replay authority;
- `cwd` selects a root candidate only. It is never identity, authorization, or
  proof that the chat is attached; and
- a subagent's inherited parent `session_id` never creates a separate AWA
  lifecycle member or new registration authority.

Absent, empty, overlong, non-string, duplicate-key, conflicting, or unexpected
identity fields refuse. No environment, PID, transcript, model, attachment,
prior receipt, heartbeat, native attachment, or Git placement may fill a gap.

### 3. Require one explicit owner choice; do not silently weaken parity

The owner must accept exactly one of these mutually exclusive profiles:

#### Profile C-Bounded — separate, explicitly limited Codex contract

Qualify only the locally observed event and tool paths that pass the accepted
capture/canary matrix. Registration may be enabled for that closed local scope
after all later gates. Operator output must say **Codex-bounded registration**
and enumerate unsupported protection paths; it must not say globally
"protected," "safe," or parity-equivalent.

This profile does not weaken any existing AWA kernel. It accepts a narrower
product claim: local Codex actions outside the qualified hook paths have no AWA
protection claim. Host sandboxing remains host behavior, not AWA evidence.
Codex archive/retention may delete a registered native worktree without reaching
the AWA blocker or exact-`Close`; C-Bounded must expose that un-intercepted host
deletion as a material residual.

#### Profile C-Parity — retain full parity and remain unsupported

Require lifecycle stability, root identity, ordering/replay, mutation-path
coverage, failure behavior, and cleanup separation equivalent to the accepted
Cursor/AWA contract. If Codex does not provide and prove those guarantees,
native Codex remains unsupported and no registration or protection path is
activated.

Profile selection is an architecture acceptance decision. Accepting the plan,
a capture protocol, a code review, or a green test does not select it.

### 4. Bind mutation to closed events and under-lock live validation

Profile C-Bounded may qualify only an explicit allowlist derived from accepted
evidence. The candidate events are:

| Codex event/path | Candidate AWA use | Required disposition before qualification |
|---|---|---|
| `SessionStart` | Eager registration opportunity for separately proven `source` values | Unproven sources remain observation-only |
| `UserPromptSubmit` | First-valid-prompt recovery; `turn_id` is attempt provenance | Prompt content is neither consumed nor persisted |
| `PreToolUse:Bash` | Existing shell-kernel adapter candidate; unified exec also reports as Bash | Exact payload/deny/failure parity required |
| `PreToolUse:apply_patch` | Explicit mutation path | Unsupported unless a separate deny-capable contract is accepted |
| `PreToolUse:MCP` | Tool-specific local path | Unsupported unless exact inventories and failures are qualified |
| Other local function tools | Closed per-tool inventory only | Unknown/new names refuse the AWA claim |
| `write_stdin` empty poll | Transport/evidence for prior unified exec | No new admission and no new effect claim |
| `write_stdin` with input | New input to an existing process without another `PreToolUse` | No AWA coverage; disqualifies that process/session from a protection claim |
| Hosted or hook-opt-out tools | None | Explicitly unsupported |
| `SessionEnd`, archive, restore, deletion | Observation only | Never registration cleanup or Close authority |

`PermissionRequest` is not a universal admission hook because it runs only when
Codex is about to request approval. `PostToolUse` is evidence-only because the
effect has already occurred. Async hooks are evidence-only.

Unified-exec protection may be claimed only for a one-shot, non-interactive
command that completes before Codex returns an input-capable session handle.
Once a handle can accept `write_stdin`, later non-empty input is a distinct
unobserved mutation path; the original admission cannot be inherited or
extended to it. Empty polls may carry completion evidence but add no coverage.

Before any registration mutation, the candidate path performs a no-write
preflight and then repeats every authority-bearing check while holding the
per-common-directory lifecycle lock. Under lock it must re-read and require:

1. the exact host-tagged session binding and, for prompt recovery, the exact
   `{session_id, turn_id}` attempt tuple;
2. one canonical existing physical root selected from `cwd`, with no symlinked
   authority-bearing component or multi-root ambiguity;
3. exact Git top-level, attached branch, HEAD, per-worktree Git directory,
   common Git directory, and one matching `git worktree list --porcelain` row;
4. eligible local non-primary linked-worktree policy, clean content and visible
   index, and no in-progress Git operation;
5. complete current-session/heartbeat, lease, SQLite, attestation, and receipt
   identity with no conflict or stale replacement; and
6. the exact accepted host profile, event/source allowlist, installed runtime,
   and contract revision.

Lock order remains:

```text
common-directory lifecycle lock -> Codex receipt/session lock
```

No path may acquire the lifecycle lock while holding the Codex receipt/session
lock. A timeout, contention, malformed state, mismatch, replay, replacement, or
incomplete check refuses registration mutation. A fail-open host hook may still
let the host operation continue; it must never publish AWA registration success.

### 5. Use monotonic, host-specific evidence without invented generation

Codex v1 also requires two separate private state ABIs; it does not reuse
`awa_current_session/v1` or `active_root/v1`, whose Cursor-shaped/raw-session
keys would erase the host boundary:

```text
awa-codex-current-session/v1
awa-codex-heartbeat/v1
awa-codex-root-blocker/v1
```

Both use the full collision-resistant digest of the canonical pair
`["codex", exact session_id]` as their filename key and retain the unhashed
pair inside the record for equality validation. The current-session record
binds schema, host, session id, canonical root/Git identity, accepted profile,
contract/runtime digests, AWA generation, source event, optional source turn,
and timestamps. The heartbeat binds the same host/session/root/common-directory
identity, boot observation, monotonic heartbeat generation, and freshness.
PID, boot, time, and host `SessionEnd` are diagnostic only.

Creation and refresh use owned `0700` directories, owned regular `0600` files,
bounded no-follow reads, same-directory atomic publication, fsync, and CAS under
the fixed lifecycle -> Codex-session lock order. An existing key with different
root/Git/profile/runtime facts is a collision/mismatch refusal, never a move.
SessionEnd may append observation evidence but cannot expire, delete, or
transition either authority-bearing record.

The root-blocker record is keyed by the full digest of the canonical root and
contains the exact root/Git identity plus a bounded, sorted set of full
host-session key digests. Registration publishes the pending blocker member
before any session/heartbeat state and publishes success only after all three
agree. A crash can therefore leave an extra blocker but cannot leave a
successful registration without one. Future exact finish removes session
evidence first and the last blocker member last. Missing is non-blocking only
when no Codex registration transaction has begun; present malformed, special,
unreadable, over-cap, mismatched, or lock-contended blocker state fails cleanup
closed. No TTL, PID, or SessionEnd transition removes a member.

For Codex v1, these records are consumed only by the Codex registrar,
integrity/discovery projection, and the root-keyed active-root **blocker** in
the canonical cleanup gate. Existing
Cursor finish/current-session readers do not consume them. Staleness, missing
heartbeat, PID exit, SessionEnd, archive, or host deletion never clears the
blocker or authorizes cleanup. A Codex-aware exact-`Close`/finish composition
requires its own later accepted contract; until then, cleanup of a registered
Codex root from the Codex surface is unsupported. This bounded limitation is
preferable to aliasing `session_id` into `conversation_id` or creating a stale-
means-removable rule without a reliable host end signal.

The proposed `awa-codex-native-entry/v1` private record binds only proven facts:

- schema, host literal `codex`, exact source event and `SessionStart.source` when
  applicable;
- exact supplied `session_id` and optional exact supplied `turn_id`;
- canonical root, branch, HEAD, per-worktree Git directory, and common Git
  directory;
- accepted profile/contract/runtime identities;
- an AWA-owned monotonic receipt generation, timestamp, result, action, lease
  identity, and closed value-free reason; and
- the exact allowlist/capture-evidence revision used to qualify the attempt.

AWA's receipt generation orders AWA receipt transitions only. It does not claim
to be a Codex turn or lifecycle generation. The record never persists prompt,
tool input, transcript path/content, model text, attachments, credentials,
arbitrary environment, absolute unrelated paths, or raw capture logs.

An exact-current success may return a true no-op only after the complete
under-lock checks pass. Reuse of one `turn_id` with different event/root facts,
reuse of one session key for a different root without an accepted transition,
or a stale writer CAS is a refusal. Lifecycle effects remain at-most-once under
the existing disk -> SQLite -> event -> attestation ordering; a receipt never
authorizes those effects by itself.

### 6. Keep registration, protection, finish, and cleanup authority separate

Codex registration evidence never authorizes shell/tool allow, cleanup,
worktree deletion, branch deletion, archive, restoration, or finish. Existing
active-root, session, Git registration, content/ignored-state, recovery,
operation-state, branch-safety, and exact operator-authorization gates remain
independently mandatory.

Exact `Close` remains the sole finish authorization accepted by AWA's Phase-1
kernel. Native archive, host snapshot, chat deletion, `SessionEnd`, a Codex
permission approval, `confirm=true`, or an AWA receipt is not Close. After AWA
Close, no further task tools run; after native archive alone, no AWA removal
success may be reported.

ADR 0026 remains separate. Its v4 registration admission roles, SQL v2,
deployment authority, R0/R1/C1/R2, and cutover gates are neither activated nor
inherited by this decision.

### 7. Preserve the AWA-product / host-wiring authority boundary

AWA owns the canonical Codex product contract, closed parsers, reason codes,
receipt schema, adapters, tests, and honest operator projection. `~/dev` owns
any live user-level Codex hook/config projection, restart procedure, machine
policy, and activation. AWA external mode retains zero access to the real host
hook file.

No AWA architecture or plan acceptance authorizes Dev edits, installed settings,
hook capture, restart, host activation, release, or canary. Each requires its
own exact artifact/revision and consequence-bound gate. No downstream copy may
duplicate AWA product authority.

## Why

- Reusing Cursor's `conversation_id == session_id` rule would fabricate a
  product guarantee Codex does not publish.
- Treating `turn_id` as `generation_id` would turn attempt provenance into
  false lifecycle authority.
- Treating `cwd` or native attachment as identity would recreate the exact
  synthesized-authority failure ADR 0024 forbids.
- Reusing hook-owner v4 would silently activate a governance-only admission
  design against a different event/serializer contract.
- A separate bounded profile makes a reduced coverage claim reviewable. A
  parity profile keeps the stronger existing safety posture available without
  pretending missing host guarantees exist.

## Consequences

- Native Codex remains unsupported while this draft and its profile choice are
  unresolved.
- Profile C-Bounded, if explicitly accepted and later implemented, can provide
  honest registration for a finite local surface but cannot claim complete AWA
  protection while hosted/opt-out/fail-open paths remain.
- Profile C-Parity preserves the full existing claim and may result in no Codex
  activation until the host contract improves.
- More host-specific schemas and tests are required; shared identity aliases
  and implicit v4 composition are prohibited.
- Native worktree cleanup remains a host lifecycle distinct from AWA Close.

## Live-state verification record

Read-only verification on 2026-10-28 established:

- live remote `main`, local base, and this worktree's starting HEAD were
  `f8c4714e3817c86c012f067e2fc869f8b5775be7`;
- the worktree was linked, clean, detached before the dedicated documentation
  branch, used the canonical KleinPerkins noreply identity, and had no competing
  session lock before writer lock acquisition;
- ADRs 0020, 0023, 0024, and 0026 and both documentation indexes were read from
  that exact base and were not modified;
- official Codex release documentation supplied the fields and limitations in
  Context but published no parity guarantee;
- no hook was installed or executed, no live payload was captured, no AWA state
  was written, and no registration/protection/cleanup outcome was claimed; and
- doc-warden's structural check was conformant, while its v2 repository profile
  reported `migration_required`; this draft therefore uses AWA's existing
  indexed Markdown convention and obtains no v2 semantic receipt.

## Owner acceptance gate

This ADR supersedes nothing while draft. Architecture acceptance requires:

1. fresh exact-byte technical review of this ADR and its linked plan;
2. explicit owner selection of **C-Bounded** or **C-Parity**;
3. if C-Bounded, accepted exact event/source/tool allowlists and explicit
   unsupported residuals based on the separately approved capture/canary
   evidence; and
4. an exact governed promotion of only the draft status/index surfaces allowed
   by the repository convention.

Before that acceptance, the owner may give a preparation direction to either
**evaluate C-Bounded** (which permits only the later consequence-preview process
for seeking capture GO) or **retain C-Parity** (which leaves the path unsupported).
That direction is not profile selection, architecture acceptance, capture GO, or
implementation GO.

Acceptance approves only architecture bytes and one profile. The linked
[execution plan](../plans/native-codex-interoperability-v1.md) requires separate
exact acceptance. Implementation, capture, live hooks, release, installation,
Dev host wiring, activation, race canary, and rollout each require their own
later GO where named by the plan.

Without those gates, the exact instruction is **NO-GO**: do not change source,
tests, contracts, runtime, hooks, settings, AWA state, registration, protection,
finish, cleanup, release, installation, host wiring, or ADR 0026 activation.
