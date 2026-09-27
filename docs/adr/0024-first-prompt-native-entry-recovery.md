# ADR 0024: Recover native entry at the first prompt with payload-bound identity
Status: accepted — 2026-09-25 (owner accepted; supersedes ADR 0023)

This is a proposed successor to
[ADR 0023](0023-native-entry-registration-and-honest-worktree-metrics.md). While
this record is draft, ADR 0023 remains the accepted authority and this record
authorizes no implementation. If this record is later accepted, it supersedes
ADR 0023 as the architecture authority: it replaces ADR 0023's
`sessionStart`-as-entry-trigger and `awa-native-entry/v1` write decisions while
re-adopting its discovery, metrics, cleanup, and safety decisions unless this
record says otherwise. ADR 0023 remains byte-identical.

## Context

ADR 0023 correctly closed a real adoption gap, but its trigger premise is too
strong. Current official [Cursor Hooks documentation](https://cursor.com/docs/hooks)
defines three relevant, non-equivalent events:

- `workspaceOpen` is a Desktop/CLI workspace lifecycle event. It fires when a
  workspace opens and again on every workspace-folder change, outside an agent
  session. Its documented payload omits `conversation_id`, `generation_id`,
  `model`, `session_id`, and `transcript_path`. The documentation publishes no
  exactly-once or ordering guarantee.
- `sessionStart` fires when a new composer conversation is created and is
  fire-and-forget. It is not a worktree-entry event. A pre-existing or moved
  conversation can enter a linked worktree without another `sessionStart`.
- `beforeSubmitPrompt` runs after the user sends a prompt and before the backend
  request. As an agent hook, its documented common payload includes
  `workspace_roots`, stable `conversation_id`, and per-turn `generation_id`.
  The common contract does not promise `session_id` for this event. One observed
  payload included it, but an observation is not a durable product contract.

No documented single event therefore combines immediate workspace-entry timing
with exact conversation identity. `workspaceOpen` can indicate a root, but it
cannot authorize conversation-bound registration and is not wired by this
proposal. The truthful fallback is first-prompt recovery.

A direct alternate-event patch would contradict accepted ADR 0023. This
successor decision is required before changing that architecture.

## Proposed decision

### 1. Use two honest registration opportunities

Keep `sessionStart` as an eager compatibility opportunity when its payload
contains the complete, exact identity required below. Add
`beforeSubmitPrompt` as the recovery opportunity for conversations that entered
or moved into a linked worktree without successful eager registration.

`workspaceOpen` remains non-authoritative. This body adds no `workspaceOpen`
hook or behavior; existing root observations may continue to seed read-only
discovery, but they never adopt, attest, bind a session, write success evidence,
or become registration authority. Neither supported registration event is
described as immediate workspace-open registration.

The resulting guarantee is deliberately limited: an eligible native worktree
is recovered no later than its first valid prompt when the engine completes
within the bounded adapter budget. A worktree with neither a successful
`sessionStart` attempt nor a prompt remains observed but unregistered.

### 2. Registration identity comes only from the hook payload

For the registration path, accept one closed supported event envelope and one
unique canonical physical workspace root. All supplied root-bearing fields
must agree on that root. Missing, malformed, non-canonical, symlinked, or
multi-root/ambiguous input refuses without adoption.

This ADR proposes the following documented mapping as the sole normalized
session identity if the ADR is accepted:

```text
normalized session identity = exact conversation_id
```

The basis is Cursor's `sessionStart` documentation, which states that
`session_id` is the same as `conversation_id`. A non-empty explicit
`session_id`, when present on either supported event, must equal
`conversation_id` exactly or registration refuses. `conversation_id` and
`generation_id` must be non-empty and unambiguous. No `DEV_SESSION_ID`,
process environment, cwd, prior receipt, heartbeat, or synthesized identifier
may supply or repair registration identity.

Before registration, the eager or recovery path must heartbeat and bind only
that normalized identity to the exact root, then re-read an exact complete
current-session record plus its live heartbeat membership. Missing, partial,
malformed, contended, stale, or mismatched current-session state refuses.
These records remain evidence, not cleanup authority.

### 3. Replace new writes with `awa-native-entry/v2`

New successful or failed attempts write `awa-native-entry/v2`; readers retain
strict `awa-native-entry/v1` compatibility. A v1 record is valid legacy
observation and discovery evidence, not proof of fields it did not carry. It
must never be relabeled or used to infer source-event, conversation, or prompt
generation. Exact live revalidation may upgrade it through a real v2 attempt.

The closed v2 record binds at least:

- exact `source_event` (`sessionStart` or `beforeSubmitPrompt`);
- equal normalized `session_id` and `conversation_id`;
- exact source `generation_id` plus a monotonic receipt generation;
- canonical root, attached branch, HEAD, per-worktree Git directory, and
  common Git directory;
- timestamp, result, action, lease identity, and a closed reason code.

`result` includes an explicit non-green `pending` state; action and lease are
absent until success. The source event is retained through
pending-to-terminal transition.
`beforeSubmitPrompt` is never stored or reported as `sessionStart`. No prompt,
attachment, transcript, model text, credential, arbitrary environment, or
operator text is persisted.

`source_generation_id` identifies the attempt that last changed v2 evidence; it
is not lifecycle identity. A later prompt generation for the same exact
root/session/conversation may take the exact-current success no-op and leaves
the successful receipt unchanged. If live identity has drifted, the new attempt
must publish its own source generation through the normal pending-to-terminal
transition.

The v1 privacy and durability floor remains: owned `0700` directories, owned
regular `0600` files, bounded no-follow reads, same-directory atomic
publication, fsync durability, freshness checks, replay rejection, and
collision-safe names.

### 4. Serialize lifecycle and receipt transitions without amplification

Registration retains the complete pre-lock and under-lock revalidation from
ADR 0023: policy eligibility; one local non-primary linked registration;
canonical root, branch, HEAD, Git directory, and common directory; attached
state; clean content and visible index; no in-progress Git operation; and
unambiguous lease/SQLite state.

The per-common-directory lifecycle lock remains the mutation boundary. Receipt
transitions are serialized by the receipt lock with monotonic
compare-and-swap. Lock ordering is fixed:

```text
common-directory lifecycle lock -> receipt lock
```

No path may acquire the common-directory lock while holding the receipt lock.
Read-only receipt readers may take the receipt lock alone.

Under the lifecycle lock, the registrar re-reads current-session, heartbeat,
Git, policy, content, lease, and SQLite identity. It then:

1. returns a true no-op for an exact-current success only after all those live
   checks pass, without another receipt generation, adoption, attestation, or
   audit event; a later prompt `generation_id` alone does not defeat this no-op
   or rewrite the source provenance of the successful attempt;
2. otherwise publishes monotonic pending evidence before lifecycle mutation;
3. performs at most one adoption, preserves existing disk -> SQLite -> adopt
   event -> attestation -> attest event ordering, and repairs only exact
   one-to-one state;
4. revalidates the complete live identity and lifecycle result; and
5. publishes success only after lifecycle completion.

A success transition must compare against the pending generation and immutable
attempt identity. A stale or parallel pending writer cannot overwrite success.
If a crash leaves pending evidence after lifecycle completion, a retry may
recover success only after proving the complete attested live state; it does
not emit duplicate adoption or attestation events. Repeated and parallel
delivery of the same event therefore cannot amplify lifecycle effects.

### 5. Put prompt recovery before, not inside, finish

Add a separate quiet adapter process before the unchanged finish consumer. It
receives the original `beforeSubmitPrompt` payload, runs registration under a
hard total sub-deadline, discards all adapter output, and then passes the same
complete valid JSON payload to the existing finish hook.

The adapter is fail-open. Missing files, malformed input, timeout, kill,
contention, or any registrar failure must still run the finish consumer and
preserve its valid JSON, stdout, stderr, exit behavior, warning publication,
and exact-`Close` semantics. It never returns a blocking decision or fails
closed; its only wait is hard-bounded. The registrar is not called from
`consumer/finish_current.py`.

This is a new product role, not a silent overload of
`awa-hook-owner/v2`. A successor contract (expected
`awa-hook-owner/v3`) composes first-prompt recovery with finish recall while
preserving explicit v1/v2 compatibility. AWA owns the role, scripts, schema,
and direct projection. External mode remains zero-access; a later, separate
`~/dev` PR owns external hook-row wiring. No Dev change is authorized here.

### 6. Preserve every independent safety and observability boundary

Engine-off kernel protection, shell-guard authority, cleanup authority,
active-root protection, and current finish authorization remain independent of
registration. Receipts, leases, heartbeats, observations, integrity rows,
events, and metrics never authorize cleanup.

Primary, excluded, detached, dirty, in-progress, malformed, contended, and
ambiguous roots are never adopted. Discovery remains observation-led and
read-only. Existing linked, managed, active, unleased, conflict, and problem
population meanings remain unchanged. Entry-evidence details distinguish v1/v2
and real source event only where needed to explain the invariant; absent or
unchecked data remains null/not checked, never an invented zero or success.

No paid GitHub Actions runner is introduced.

## Why

- **Register from `workspaceOpen` (rejected).** It has workspace timing but no
  conversation identity, may repeat on folder changes, and has no documented
  exactly-once/ordering contract.
- **Treat `sessionStart` as worktree entry (rejected).** It describes composer
  creation. A moved or existing conversation can enter without it.
- **Use environment or synthesized identity (rejected).** It can bind one
  conversation's lifecycle state to another and turns non-authoritative
  context into mutation authority.
- **Call registration from `finish_current.py` (rejected).** It couples an
  adoption side effect to the finish safety consumer and risks changing
  fail-open/JSON behavior.
- **Reuse hook-owner v2 silently (rejected).** V2 declares a different role
  graph. A composed prompt role requires an explicit successor contract.
- **Write v1 with a different event (rejected).** V1 has no source-event or
  conversation provenance; doing so would manufacture evidence and obscure
  prompt-time semantics.

## Consequences

- Native entry missed by `sessionStart` can be recovered at the first valid
  prompt with exact payload identity and bounded local work.
- Registration is not immediate when only prompt recovery is available. That
  limitation is visible and intentional.
- Existing v1 evidence remains readable but cannot claim v2 provenance.
- Prompt handling gains a bounded local pre-step, but adapter failure leaves
  finish behavior unchanged.
- Direct and externally owned hook projections require a versioned product
  contract transition before activation.
- ADR 0023's honest worktree populations, observation-led discovery, and
  independent cleanup gates continue unchanged.

## Non-goals

- No code, contract, test, runtime, hook, job, or state mutation in this
  governance gate.
- No release, version bump, tag, publication, Skills binding, install,
  activation, Desktop UAT acceptance, cleanup, or Dev host edit.
- No registration of primary, excluded, detached, dirty, in-progress, or
  ambiguous roots.
- No new daemon, network dependency, router, cleanup authority, guard
  relaxation, or GitHub Actions runner.

## Live-state verification record

Read-only verification on 2026-09-25 recorded:

- this `bdkd` linked root was clean at
  `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`;
- local `origin/main` and live remote `main` resolved to the same commit;
- annotated tag `v1.8.1` had tag object
  `15c1634d8468bdf42da9f561d24dee635a6df9b7` and dereferenced to
  `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`;
- established reconnaissance recorded root `3qoz` and the protected primary
  clean at `ff978ade`, root `al94` clean at `dcd11dc`, and root `4zjh`
  absent. All are no-touch for this governance task and were not used as
  implementation surfaces; and
- previously established artifact hashes remain evidence only, not files to
  access from no-touch roots.

The official Cursor hook contract was re-read on 2026-09-25. Its documented
event timing and fields support first-prompt recovery, not workspace-open
registration.

## Review provenance

The governance review used one probe and four focused reviewers; all returned
validated findings. It found that a direct alternate-event patch would violate
ADR 0023, the identity contract was incomplete, hook-owner v2 could not be
silently reused, v1 receipt provenance was insufficient, same-receipt
transitions could race, exact-success dedupe needed full live validation, and
the prompt path required a separate timeout-contained adapter plus a complete
current-session gate. It also required a hard total budget and honest
prompt-time language.

The verifier gate was false, so shipping clearance was not evaluated. A second
pass was denied because no trigger existed. This provenance supports the
draft; it is not acceptance or implementation authorization.

## Owner acceptance gate

This ADR supersedes nothing while draft. Acceptance requires an explicit owner
decision naming ADR 0024. If accepted, ADR 0023 remains byte-identical and its
superseded status is recorded only through the governed index convention.

ADR acceptance approves only the proposed architecture. The linked
[execution plan](../plans/native-entry-first-prompt-recovery-v1.md) must also
be accepted, followed by a separate explicit owner implementation **GO**.
Without both decisions, the result is **NO-GO**: leave code, contracts, tests,
hooks, runtime, host wiring, and state unchanged.
