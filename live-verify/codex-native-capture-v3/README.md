# Controller-bound first-prompt capture v3 — inert source preparation

This source successor preserves every v1/v2 source byte and prior result. Only
A02 is selectable. It defines a conservative observation of the first synthetic
controller-submitted prompt in a fresh native fixture session. It does not
implement an AWA product adapter, identity authority, registration or protection.
No live capture is authorized by the presence of these files.

## Exact action and controls

The external controller must create a fresh native thread through its supported
host interface, acknowledge its fixture cwd and intended permissions, and record
zero prior controller-submitted turns. A raw native session id stays in memory.
Before the pre-witness, calculate HMAC-SHA256(salt, b"session\0" +
session_id.encode("utf-8")), write its 32 raw .digest() bytes to private 0600
capture/session.bin, bind that file's SHA-256 in the run manifest, and initialize
labels.session to exactly {binding.hex(): "S1"}. Salt, session binding and label
maps never leave private ephemera. Foreign/missing identities are rejected before
label allocation or event append. They cannot become another session's evidence.

A02 is the literal action AWA-CODEX-CAPTURE-A02. No model/user-prompt control may
precede it in the target thread: such a control would itself be the first prompt.
The exact ledger shape is BEFORE with zero target events, ACTION with exactly one
UserPromptSubmit, and AFTER with exactly one subsequent literal prompt callback.
Both callbacks must be S1 at R1. The UserPromptSubmit control sequence is exactly
before=0 and after=the after-event sequence. No missing/extra count alternative,
other route, pre-action prompt, action replacement or post-hoc relabeling is allowed.
The first-action witness and fresh-thread/controller counter must be fixed before
execution; a public export cannot independently reconstruct these private facts.

There is deliberately no healthy BEFORE control. The post-witness must say
health=UNAVAILABLE. Every exported scenario is completion_status=UNPROVEN,
harness_health=UNKNOWN, positive_control_route_match=UNAVAILABLE, even when the
single action callback and after callback are present. A positive count is not a
qualified first-prompt or negative/absence claim. Any later proposal to promote
these labels is a new material evidence/acceptance decision, not standing consent.
Do not reinterpret the prior C5 A03 BEFORE control as an A02 action.

## Retained safety and privacy contract

Use /usr/bin/python3 -I -S -B for the observer and offline verifier. Retain all
no-follow descriptor, owner/mode/link, namespace, source, witness, exact count and
forbidden-field checks. Render only the one UserPromptSubmit definition through
the pure verifier helper; review/trust it through supported controls. Preserve
all unrelated baseline definitions, their hashes, trust and enabled states.
The observer receives a genuine native event only through stdin, returns only
{} and zero, and never injects context, a blocking decision or a replayed payload.
No raw ids, commands/tool input/output, credentials, configuration or transcripts
are persisted by this collector.

Preallocate capture/collector-contention.bin as one private 0600 byte b"0".
Any collector-lock conflict durably writes/fsyncs b"1" and invalidates the entire
epoch, including apparently exact counts or unavailable health. Never reset it
or salvage that epoch. It remains at its original inode through the offline
verifier and the pre-copy recheck. Its zero state is NOT_RECORDED, not proof that
every possible host hook was delivered. Stop/disable the observer and prove
owned roots/observed children terminal before verification. Remove salt.bin,
session.bin and labels.json before verification; retain the contention flag until
cleanup. Source, config and namespace identities must still match. Use a shared
CLOCK_MONOTONIC clock for cross-process spans; callback buckets are process-local.
Copy only the verifier-produced sanitized export; remove the exact fixture after
validated shutdown and retain only approved nonsensitive audit records. Inactive
native trust/session metadata remains outside fixture cleanup.

## Local-tool definitions are inert

A04/A05 remain executable=false. The frozen owner plan distinguishes Bash and
unified exec while describing both pre-tool hooks as Bash; the legacy catalog
uses different BASH/UNIFIED_EXEC discriminators. Current supported tool offers,
hook names, parameter/handle semantics and a closed controller witness must
resolve that discrepancy before any tool case is enabled. Shell choice alone
cannot establish a native tool identity. Do not widen the predicate to both
values, alias an unknown tool, or manufacture an approval from generic consent.
Only fixed fixture writes (A04) and a fixture-local completing exec (A05) are
candidate effects. No work data, hosted/MCP service action, non-empty handle
input, product adapter or authority change is in this source preparation.

The operator's standing authority covers routine in-scope preparation and normal
source delivery. New source/previews must be reviewed, validated and merged before
live use. D2/D3 adjudication, D1/profile acceptance, implementation, registration,
protection, release and host activation remain separate and unaccepted here.
