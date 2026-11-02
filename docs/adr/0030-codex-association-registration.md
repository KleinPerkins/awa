---
{"approval":{"actor":"operator","date":"2026-11-01","review_sha256":"4e32b1d622063be0ce936dda4508ebe985c78876c0abf1e8a5023b9aca860883"},"authority":"semantic","github_repository_id":1289571438,"id":"ADR-e6393083-530b-5462-9038-377088993223-b8269beb-8e45-5b7f-b0a8-f1d08d144435","lifecycle":"approved","mutability":"frozen_after_approval","provenance":[],"relations":[],"repository_key":"e6393083-530b-5462-9038-377088993223","schema":"doc-warden/artifact/v2","supersedes":null,"type":"adr","version":1}
---
# ADR 0030: Codex association registration
Status: draft — 2026-11-01 (semantic acceptance and implementation pending)

This is a separate proposed Codex bookkeeping contract. It changes no accepted
Cursor, protection, cleanup or admission semantics while draft.

## Context


The operator directed an adjusted definition of registration suitable for Codex:
AWA should record a verified, host-reported native chat-to-physical-worktree
association. The native desktop tools expose attachment and workspace evidence.
An association need not establish exclusive writer ownership, complete tool-hook
coverage, or authority to remove the worktree.

The earlier draft ADR 0029 makes registration depend on a hook-session identity,
event/tool qualification, current-session/heartbeat records and a cleanup blocker.
Those are proposed semantics, not accepted Codex authority. Requiring that entire
surface merely to record an association unnecessarily couples bookkeeping to
protection. Accepted ADR 0024 remains the Cursor contract; it must not be patched
to accept invented Codex conversation or generation fields.

For preparation, native tools in this owner chat reported one worktree attachment
and a matching current workspace. Independent Git observations agreed. The
integration chat reported multiple attachment records. Neither observation proves
one chat per worktree, one attachment per chat, permanent attachment identity, or
an atomic host lifecycle. The separate app-server route is optional and parked;
its isolation qualification is not required by this proposal. MCP registrar
migration is a separate owner concern. Existing server-guard baseline/recovery
behavior remains unchanged; no server-guard discovery task is proposed.

## Decision

### 1. Define association registration as bookkeeping

If accepted, this ADR establishes only the `codex-association-agent/v1` profile on
local macOS Codex desktop. A successful record means:

> A trusted reporting agent conveyed fresh native observations identifying this
> chat's current workspace and matching worktree attachment; AWA independently
> checked the physical Git binding and recorded that observation.

"Verified" is scoped to that verification procedure. It is not independent
authentication of a host response, proof that the association still exists,
writer ownership, or a lease. Public copy must include `agent-mediated` and an
observation time, for example: "Codex association registered — agent-mediated
observation as of <time>; protection not assessed."

The record grants no tool admission, lease, exclusive writer window, guard
coverage, active-root blocker, branch/worktree deletion permission, finish,
archive, or restoration authority. Existing independently authorized protection
can still exist; this record neither proves nor disables it. Exact `Close` and
every existing cleanup gate remain unchanged.

### 2. Accept the reporting agent as an explicit trust boundary

The recommended initial contract trusts the reporting agent to call the native
tools in the intended chat context and convey their permitted projection
faithfully. Native `list_artifacts` is context-bound to its invoker;
`read_thread(chat_id)` describes the requested chat, not the identity of its
requester. The observed attachment payload does not provide its own caller chat
ID, host revision or authenticated proof for a separate AWA process.

The existing AWA shell/hook/CLI/MCP entry path has no direct native-app association
client. Therefore the new receiver validates the submitted projection and local
Git facts, but does not authenticate the native part independently. An agent can
lie or replay source claims. A digest, source label, tool-call identifier, local
PID, environment value or signed-by-the-same-agent envelope does not eliminate
that limit. The registry is not a security boundary against the same-user agent.

If independent host authentication is later required, use a separately qualified
direct host bridge with caller-bound delivery. Do not label this initial profile
`host-authenticated`, and do not silently promote it when a new tool appears.

### 3. Use native chat identity and physical worktree bindings

Scope keys to the machine-local AWA store and literal local-desktop host profile.
Use the opaque native chat ID exactly; never equate it with hook `session_id`,
Cursor `conversation_id`, `generation_id`, a turn ID, PID or `DEV_SESSION_ID`.

An attachment is evidence of attachment, not proof of current workspace. A
current registration requires both a fresh native current-workspace report and
a matching worktree attachment. Keep all matching attachment IDs, but do not pick
the first/newest attachment or use `sourceCwd`/creation time as an active pointer.
Duplicate attachment IDs with different facts are conflicts. Other attachments
are explicitly not-currently-validated observations, not automatic registrations.

Bind the selected canonical physical root, per-worktree Git directory and common
Git directory, including measured directory device/inode identities. Branch and
HEAD are mutable observations, not chat/worktree identities. Dirty contents and
detached HEAD alone do not invalidate a factual association. V1 supports local
non-primary linked worktrees; unsupported/excluded roots are not inspected by
guessing their remote. Apply ADR 0027 lexical hard-no-touch checks before target
access, and repeat checks for derived locator paths before accessing them.

### 4. Represent many-to-many relationships and uncertainty honestly

Each chat has at most one current edge under this initial single-current-root
profile, plus bounded historical observations. Several chats may have a current
edge to the same worktree. This is not an exclusive-owner conflict. A chat may
have many attachments; only independently selected current-root evidence promotes
an edge. A future multiple-current-root host requires an explicit successor.

Reattachment can create or refresh another edge for the same chat. A fresh,
consistent report of a different current root makes the old edge historical;
it does not prove the old attachment was detached or deleted. A fork requires its
own native chat ID and observations; parent identity/attachments do not implicitly
register a child or a collaboration worker.

Archive, deletion, lost access, restoration, missing paths and conflicting native
reports never mean removable. A known archive or disappearance removes only the
bookkeeping current claim, retaining bounded prior observations. A failed query
or incomplete list is unknown, not proof of deletion. Restoration and path reuse
require fresh physical verification; a changed physical binding is a new edge.
An old record cannot silently authenticate a restored/replaced directory.

Freshness is a bounded cache classification, never liveness or write authority.
The linked plan defines observation age, clock handling, caps and exact failure
behavior. No timestamp, expiry, heartbeat absence or process exit triggers
cleanup. Native workspace changes can race observations: AWA's store lock does
not lock the host. Even matching bracket reads are a consistency check, not an
atomic native snapshot or continuous-association guarantee.

### 5. Keep a separate, private, bounded store

The linked plan defines one closed request/record ABI, a single per-chat snapshot
file with an AWA-owned revision, and `record`, `refresh`, `inspect` interfaces.
There is no new authoritative SQLite store, daemon, watcher, hook, root index,
signer, host updater or admission protocol. The recorder never calls Cursor's
registrar, `lifecycle.adopt`, `lifecycle.attest`, lease repair, or ADR 0026 helpers
that exercise admission/deployment authority.

Persist only selected native identifiers, verified physical Git metadata,
allowlisted provenance, times and bounded history. Do not persist raw tool
responses, chat titles, prompts/transcripts, model text, arbitrary arguments,
environment, credentials, unrelated attachment paths or service responses.
Use private owned no-follow files/directories, bounded strict parsing, a per-chat
lock, expected-revision comparison, atomic publication and explicit durability
failure handling. These protect cooperating bookkeeping writers; they do not
exclude other worktree writers or make agent evidence authentic.

### 6. State the successor relationship precisely

Upon concrete acceptance, this proposal replaces only draft ADR 0029's proposed
Codex registration premise (§1–5 and its registration acceptance prerequisites)
and the registration track of draft `native-codex-interoperability-v1.md`.
Preserve both earlier files byte-identically and express disposition in indexes.
Do not mark an accepted ADR superseded merely to add this separate profile.

Re-adopt ADR 0029 §6–7's separation of registration, protection, finish, cleanup
and AWA-product/Dev-host ownership. Accepted ADRs 0020, 0024, 0026 and 0027 remain
unchanged. ADR 0026 implementation and R0 remain NO-GO. Cursor schemas, receipts,
leases, hooks, safety behavior and supported semantics remain unchanged.

Hook/tool coverage qualification remains a separate possible protection project.
Neither full hook parity, A02 capture, a C-Bounded/C-Parity choice, separate
app-server discovery, nor MCP migration is a prerequisite for this bookkeeping
contract. Removing those prerequisites here does not qualify those other paths.

## Consequences

- Native association becomes useful evidence rather than an inherently missing
  host capability. Operator output separates recorded association from protection.
- The initial implementation can be small and testable. Trust in the reporting
  agent is a material, visible limit; it is not hidden behind JSON validation.
- Local publication can serialize cooperating recorders, but cannot atomically
  bind host attachment changes or establish whole-worktree writer exclusion.
- Missing evidence becomes unknown/historical. History is a bounded cache, not a
  complete native lifecycle journal and never a deletion inventory.
- A stronger host-authenticated profile or protection/cleanup integration requires
  separate architecture acceptance and technical evidence.

## Live-state verification record

Preparation checked repository remote `git@github.com:KleinPerkins/awa.git`, live
`main` at `61c3bf1aa0f70b73644512f2befaafc2b31a6d18`, and the source worktree's
equal tree `b4f3b19848673d0e0e32d35f06e9884476cdbec9`. Current native attachment,
workspace and linked Git identity had already been checked in the bounded owner
assessment. These observations are evidence, not a new registration.

AWA's doc-warden v2 authoring profile was enrolled through approved operation
`eb025f57-1b22-48e2-b08a-e49e30b656c2`, preserving all older record bodies and
legacy creation-skeleton evidence. The profile permits governed authoring; it
does not accept this proposed contract or authorize implementation/activation.
The approved integration PRD provides requirements for planning
(REQ-INT-009/010/015/019/020), without inventing an approved AWA PRD.

## Owner acceptance gate

The operator approved preparing this revised approach and the authoring-profile
enrollment. Neither is acceptance of these exact semantic bytes. After independent technical review, concrete semantic
acceptance must name this ADR and the linked plan's exact versions/digests and
accept `codex-association-agent/v1`, including trusted agent mediation,
single-current-root scope, many-to-many relations, freshness/history limits and
the absence of protection/cleanup authority.

Governed draft publication, semantic acceptance, runtime implementation, release,
installation and live activation are distinct outcomes. A merged draft is still
a draft. Do not mark accepted, implement the runtime, or write live AWA state
from drafting authorization. Prepare a concrete operation-bound publication
preview under the supported owner route; do not fabricate a doc-warden receipt,
approval, repository profile, or approved owner PRD. No generic operator code
review or redundant delivery permission is introduced.

## Review provenance

The paired proposal received independent technical review; findings on root
selection, canonical state, failure responses and cache-local uncertainty were
resolved. Final canonical postimages and review evidence remain separate from
owner semantic acceptance. A technical review receipt cannot accept this contract.
