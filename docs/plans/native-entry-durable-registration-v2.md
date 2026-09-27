# Native Entry Durable Registration

- **Version:** v2
- **Status:** DRAFT (for review)
- **Date:** 2026-09-26
- **Supersedes:** frozen
  [`native-entry-first-prompt-recovery-v1.md`](native-entry-first-prompt-recovery-v1.md)
  only if this plan is later accepted; while this plan is draft, v1 remains
  the accepted frozen plan
- **Architecture authority:** draft
  [ADR 0025](../adr/0025-durable-registration-episodes-and-tool-admission.md);
  accepted [ADR 0024](../adr/0024-first-prompt-native-entry-recovery.md)
  remains authoritative until ADR 0025 is explicitly accepted
- **Planning baseline:** local PR #175 head
  `b88325768f26f8d98aecb2722d5fb253379bba47`; local `origin/main`
  `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`
- **Plan type:** agentic execution only after `C0-DESIGN`; shipping only after
  separate post-implementation `C1-SHIPPING` and each named owner gate
- **Version discipline:** acceptance freezes this file byte-identically; every
  material change then requires v3
- **Evidence:** four completed bounded spikes and source-confirmed document
  findings; no implementation, hard-power, isolated-child, or rollout proof

**Goal:** Make registration a durable, crash-recoverable relational protocol
that precedes intercepted local Agent work whenever functioning AWA can
positively identify an included linked worktree. Give dirty or recognized
in-progress work an operator-authorized preservation route without weakening
the deny-all non-green gate.

**Architecture:** A dedicated full-durability SQLite database owns immutable
episode identities, canonical physical-member identities and versions,
requests, phases, effects, references, notices, and rescue workflows. An
under-common-directory `CLAIMED -> EFFECT_IN_FLIGHT` intent CAS is the only
authorization for lifecycle I/O. Immutable per-effect leases and a sealed
effect graph resolve through a four-way fresh readback predicate. Tool
admission double-collects a lightweight ordered canonical-member vector around
one database snapshot. Optional JSON episode output is display-only.

> **Governance stop:** This DRAFT authorizes documentation only. Implementation
> is **NO-GO**. The owner-choice component C0-D1 through C0-D8 was satisfied on
> 2026-09-26, but `C0-DESIGN` remains **UNSATISFIED**. The verifier's
> `shipping_clearance` is neither required nor expected before implementation;
> C0-DESIGN consumes findings, adjudications, and coverage. No code, contract,
> test, schema, runtime, hook, job, state, PR, release, installation, host,
> Skills, or live-UAT task below may begin now. This revision textually
> disposes source-confirmed draft findings but implements or proves none of
> them.

---

## 1. Purpose, inheritance, and boundary

ADR 0024 and PR #175 provide exact payload identity, eager `sessionStart`,
bounded first-prompt recovery, native-entry v2 evidence, a separate adapter,
and hook-owner v3. They do not establish a durable result before each later
Agent tool or parent subagent launch.

This successor keeps, unless explicitly replaced:

- normalized `conversation_id` as lifecycle identity and `generation_id` as
  event provenance only;
- private bounded evidence with no prompt, transcript, task text, tool input,
  content, credential, or arbitrary environment;
- clean/idle initial adoption, one lease lineage, and conservative repair;
- kernel-first protected-primary denial and engine-off behavior;
- independent finish, active-root, cleanup, and operator-authorization gates;
- observation-led read-only discovery and honest worktree populations; and
- AWA product ownership with `~/dev` as sole live hook/local-jobs owner.

It replaces:

- the aggregate episode file as mutable authority;
- paired file/database success publication;
- `B2` as implicit effect authorization;
- a mutable pre-COMMIT active lease;
- the old state names and invalidation behavior;
- reliance on malformed permission JSON;
- inherited or inferred child admission; and
- the indefinite dirty/in-progress manual stop.

Strict `awa-native-entry/v1|v2` remains legacy discovery evidence. Neither
schema can make a successor member green. No implementation, PR #175, GitHub,
release, installation, host, Skills, Dev, primary, no-touch root, runtime, or
live-state mutation is part of this documentation body.

## 2. Baseline and evidence

### 2.1 Protected baseline recorded 2026-09-26

| Surface | Recorded state |
|---|---|
| Current linked root before documentation edits | `b88325768f26f8d98aecb2722d5fb253379bba47` |
| Local `origin/main` | `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` |
| PR #175 | Operator-described Draft/unarmed; no GitHub mutation is authorized |
| ADR 0020 SHA-256 | `f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98` |
| ADR 0023 SHA-256 | `71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051` |
| ADR 0024 SHA-256 | `cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911` |
| Frozen v1 plan SHA-256 | `e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9` |

PR #175 is substrate, not successor proof. A later implementation must use a
fresh governed worktree at the then-authorized base and must not repurpose or
silently amend PR #175.

### 2.2 Evidence classes

| Class | Evidence used here | What it does not prove |
|---|---|---|
| Source / official | Cursor hook documentation and schemas; SQLite documented PRAGMAs, WAL, sync, and dbconfig behavior | Installed-version behavior, full tool inventory, or AWA implementation |
| Observed local | Cursor 3.22.7 responses; shared-child captures; Python SQLite 3.53.3; CLI SQLite 3.51.0 | Durable platform contract, other Cursor versions, isolated/cloud behavior |
| Bounded model | Nine scenarios, <=4 actors, 3 members, 2 requests/member, 2 boots; 105 complete schedules, 239 configurations, 144 summed abstract states; zero violations in bounds | Universal safety, liveness, or implementation equivalence |
| Temporary SQLite/filesystem | Process-kill, transaction, sidecar, and publication experiments | Hard power loss, hardware failure, APFS firmware behavior |
| Inference / proposal | This protocol, latency targets, rollout sequence, and rescue UX | Product proof or ADR/plan acceptance |

The prior model produced six counterexamples. The revised bounded model
removed those counterexamples inside its bounds by moving authority to
relational member state, adding the effect-intent barrier, making notices
separate, and delaying supersession of in-flight effects.

### 2.3 Cursor contract and observation facts

- Official invalid permission JSON fails open by default unless
  `failClosed:true`. Installed Cursor 3.22.7 was observed to block invalid or
  wrong-shape permission JSON with `failClosed:false`; production must not
  depend on that version-specific behavior.
- `session_id` is not a documented common hook field and cannot be required.
  It was observed as optional. `conversation_id` remains authoritative;
  absence is accepted, a present unequal value refuses as a contradiction,
  and no session value is synthesized.
- Official `preToolUse` documents `tool_name`, `tool_input`, `tool_use_id`,
  `cwd`, and allow/deny behavior. Official matcher examples include `Shell`,
  `Read`, `Write`, `Grep`, `Delete`, `Task`, and `MCP:<tool>` and are
  explicitly treated as non-exhaustive here.
- Exact `Glob`, `Edit`, browser/web, and internal names are fixture-gated.
  `beforeMCP` is server-aware. `beforeReadFile` occurs after local disk read
  but before model admission, so this plan does not claim to prevent that
  local read.
- Unknown surfaces may emit no event. Tab, manual, external, cloud-early, and
  already-running work remains unsupported.
- Four fresh shared-child launches produced 81 child `preToolUse` events.
  Each child had a distinct conversation from its parent and the same root
  set; when present, `session_id` equaled that child's conversation.
  `parent_tool_call` appeared in 73 events. Parent launch id did not equal
  child conversation. `subagentStart` carried no authoritative child root,
  isolation mode, or child conversation.

### 2.4 SQLite/filesystem facts

- The successor database is
  `${XDG_STATE_HOME}/awa/registration-v1/registration.db`, separate from
  legacy `state.db`; legacy connections use `synchronous=NORMAL` and
  checkpoint-on-close behavior.
- Initial support is local macOS APFS with SQLite `>=3.51.3`.
- The observed Python runtime embeds SQLite 3.53.3. The observed `sqlite3` CLI
  is 3.51.0 and must not write the successor database.
- Python stdlib does not expose `SQLITE_OPEN_NOFOLLOW`. Accepted C0-D1 retains
  the strong no-follow claim and requires a narrowly audited binding; a
  stdlib-only implementation is insufficient.

### 2.5 Stop and re-plan before implementation if

- ADR 0025 or this plan is not accepted;
- any remaining `C0-DESIGN` prerequisite in §3.2 is absent;
- the owner has not issued a separate exact implementation GO;
- live main changes registration, lifecycle/state transactions,
  current-session/heartbeat, integrity, finish, cleanup, hook ownership,
  installer, or host authority beyond a reviewed rebind;
- official Cursor or SQLite contracts invalidate a fact above;
- any claimed supported tool lacks a verified intercepting event;
- shared-child mode cannot be positively constrained before launch;
- the chosen SQLite binding/profile cannot prove its stated path and
  durability properties; or
- work would require global `failClosed:true`, cleanup authority,
  primary/no-touch mutation, release/install/host activation, or GitHub
  mutation before the named gate.

An unrelated baseline advance may be rebound only after recording its exact
OID and proving the protected-surface diff does not invalidate this plan.

## 3. C0-DESIGN and C1-SHIPPING graph

### 3.1 Owner decisions recorded 2026-09-26

| ID | Decision | Accepted owner choice — 2026-09-26 | Consequence / rationale |
|---|---|---|---|
| C0-D1 | SQLite no-follow | Use one narrowly audited binding exposing `SQLITE_OPEN_NOFOLLOW`; retain the strong no-follow claim | Python stdlib alone is insufficient |
| C0-D2 | WAL SHM unavailable | Treat environments without supported WAL shared memory as v1 **NO-GO**; do not activate `PERSIST+EXTRA` in v1 | `WAL+NORMAL` remains forbidden |
| C0-D3 | Rescue secrets | Reuse the existing private, local, unencrypted Retain secret policy; require exact `Preserve including secrets` | Local/no-network, owner-only, with explicit confidentiality risk |
| C0-D4 | Cursor handoff | Require the operator to open the returned rescue target manually in Cursor | No documented API safely moves the active conversation |
| C0-D5 | Git operations | Make every currently recognized Git operation family mandatory for v1 and preserve its administrative state | Partial family support would strand legitimate work unpredictably |
| C0-D6 | Submodules/LFS | Keep submodules/gitlinks and unproved LFS/filter state as v1 **NO-GO** | Restore proof is otherwise incomplete |
| C0-D7 | Artifact retention | Protect rescue artifacts until exact-ID deletion under existing authority; apply no automatic expiry | Automatic expiry would weaken recoverability |
| C0-D8 | Multi-agent | Enable only positively proved shared-child mode after UAT; deny ambiguous or isolated Task launches; keep isolated mode unsupported | No pre-spawn shared/isolated discriminator exists |

These eight records satisfy only the C0-DESIGN owner-choice component. They do
not accept or freeze either document, authorize implementation, or clear
C0-DESIGN.

### 3.2 One normative dependency graph

```text
R0 read-only refresh
        |
        v
C0-D1..C0-D8 owner-choice component: SATISFIED 2026-09-26
        +
exact draft hashes +
complete independent critical review +
all source-confirmed document findings disposed +
all verifier candidate adjudications resolved +
critical_coverage=true + probe_blind=true + revision=true +
explicitly accepted ADR + separately accepted/frozen plan +
exact implementation baseline + separate implementation GO
        |
        v
C0-DESIGN
        |
        +--> every M1/M2 implementation, schema, fixture, and proof task
        +--> every implementation Draft PR and exact-head review task
        |
        v
exact implementation head + implementation/test/disposable-UAT evidence +
no open protected findings + partial_rollout=false for named body +
verifier shipping_clearance=approved
        |
        v
C1-SHIPPING
        |
        +--> PR readiness                    + named owner gate
        +--> merge                           + named owner gate
        +--> release/tag                     + named owner gate
        +--> install/Skills binding          + named owner gate
        +--> ~/dev hook/local-jobs activation + named owner gate
        +--> live Desktop UAT/rollout        + named owner gate
```

R0 may only read source, official documentation, schemas, and live facts and
record evidence. It may not write product files, contracts, tests, database
state, hooks, jobs, runtime, or host state. No task may be relabeled research
to bypass C0-DESIGN or shipping to bypass C1-SHIPPING.

`C0-DESIGN` is pre-implementation and remains **UNSATISFIED** until all inputs
shown above exist. A document finding may be `resolved`, `false_positive`, or
`deferred_unsupported_platform_residual`; no other deferral clears C0-DESIGN.
The verifier's `shipping_clearance` is explicitly not a C0-DESIGN input and is
expected to be failed or not evaluated while no implementation exists.

`C1-SHIPPING` is post-implementation and exact-head. It cannot clear from plan
text, design review, or partial evidence. Every implementation task below
depends directly on C0-DESIGN. Every readiness, merge, release, install,
Skills, host, or live-UAT/rollout task depends on C1-SHIPPING plus its named
owner gate. The two nodes are not interchangeable.

## 4. Frozen successor contract

### 4.1 Canonical values, framing, and identifiers

Strict JSON input rejects duplicate keys, unknown keys, floats,
NaN/infinity, invalid Unicode, and values outside fixed byte/count/depth
bounds. Semantic bytes are RFC 8785 JCS with no LF. JSON files are
`JCS(object) || 0x0a`.

Every nanosecond value, device number, inode number, and other 64-bit JSON
value is an unsigned decimal string matching:

```text
0 | [1-9][0-9]{0,19}
```

and must be within the field's unsigned range. SQLite may use checked signed
integers for bounded protocol counters, but canonical objects use the decimal
string form.

Hash framing is:

```text
FRAME(part) = uint64be(length(part)) || part
D(label, parts...) =
  lowerhex(SHA-256(
    FRAME(UTF-8("awa-registration-domain/v1")) ||
    FRAME(UTF-8(label)) ||
    FRAME(part[0]) || ... || FRAME(part[n])
  ))
```

An object part is `JCS(object)`. No concatenation without framing is allowed.

Identifiers are:

```text
root_set_hash =
  D("root-set", JCS({conversation_id, boot_id,
                     root_set_incarnation, ordered_descriptors}))

member_id =
  D("physical-member", JCS({git_common_dev, git_common_ino,
                            git_worktree_private_id}))

episode_id =
  D("episode", JCS({conversation_id, boot_id, episode_incarnation,
                    root_set_incarnation, root_set_hash}))

request_key =
  D("request", JCS({episode_id, episode_incarnation, member_id,
                    member_version, admission_epoch, request_generation,
                    request_created_wall_ns}))

effect_id = D("effect", JCS({request_key}))

lease_id =
  D("lease", JCS({effect_id, request_key, member_id, member_version}))

certificate =
  D("certificate", JCS({effect_id, request_key, lease_hash,
                        attestation_hash, event_count, event_root_hash,
                        manifest_hash, completion_hash}))
```

`episode_incarnation`, `root_set_incarnation`, `claim_token`, and effect
`fence_token` are independently generated 256-bit values. Their randomness
does not replace deterministic request/effect binding.

Canonical member identity is independent of root-set membership. A member
version binds canonical root, root `dev/ino`, per-worktree Git directory,
common Git directory, policy/capability, current-session, heartbeat, and
structural basis. An add/remove/reorder of a root set does not by itself bump a
physical member version. A structural or authority change does.

Every request includes `request_created_wall_ns`; it is identity, not a
deadline. Claim expiry, retry, and backoff use boot-scoped monotonic
nanoseconds only. Persisted wall deadlines are display-only and never compared
for authority.

### 4.2 Store bootstrap and mandatory connection profile

The normative resolver starts from one trusted absolute base-directory file
descriptor. It accepts only absolute bounded input, walks every component with
`openat`/`O_NOFOLLOW` semantics, retains the directory and object descriptors,
and rechecks owner, regular/directory type, mode, device, and inode immediately
before each use. Policy inclusion/exclusion runs on those resolved objects,
never first on lexical spelling. Database, WAL, SHM, lease, rescue, and trash
operations remain descriptor-anchored; a later pathname re-resolution cannot
substitute another object.

The audited binding/VFS is responsible for applying
`SQLITE_OPEN_NOFOLLOW` to the main database and every sidecar open and for
binding SQLite's `xOpen` to the retained base/object identity. A stock
path-only open that validates once and then lets SQLite re-resolve the name is
not sufficient. Binding audit and alias/race tests are C0-D1 implementation
acceptance requirements, not evidence present in this draft.

Bootstrap must:

1. open and retain the trusted absolute base descriptor;
2. resolve or create `${XDG_STATE_HOME}/awa/registration-v1` as owned `0700`;
3. classify the pre-existing state through the closed matrix below;
4. create `registration.db` as owned regular `0600` only from `ABSENT`;
5. establish DB/WAL names through the audited VFS, full-sync DB/WAL and parent
   directories, and record a canonical schema fingerprint;
6. treat SHM as owner-checked `0600` rebuildable non-authority and never copy
   or use its bytes as proof;
7. close and reopen through retained/remeasured descriptor identity;
8. verify DB/WAL/SHM path, owner, type, mode, `st_dev`, and `st_ino`;
9. verify SQLite version `>=3.51.3`; and
10. verify schema fingerprint and the complete profile before any authority
    read or write.

| Pre-existing state | Required result |
|---|---|
| Directory/database absent | Create privately, full-sync file(s) then directory, close/reopen, verify |
| Owned empty regular DB | Initialize once, full-sync, close/reopen, fingerprint |
| Exact valid DB with valid/rebuildable sidecars | Reopen and verify; SHM may be discarded only by SQLite's supported recovery, never manually |
| Partial schema or wrong fingerprint | Refuse `UNAVAILABLE`; preserve bytes; no migration guess |
| Foreign SQLite/schema/application id | Refuse terminal bootstrap conflict; preserve |
| Wrong owner/mode/type/device or unexpected hard link | Refuse; preserve; RED |
| Symlinked/aliased DB, WAL, SHM, directory, lease, or trash component | Refuse before SQLite/file I/O; RED |
| WAL present without provable DB pairing, or DB/WAL identity drift | Refuse and preserve; no raw copy/delete |
| SHM absent/stale with exact DB/WAL | Let SQLite rebuild under audited VFS; SHM never grants authority |

The target settings are:

```text
PRAGMA journal_mode=WAL;             -- result must be "wal"
PRAGMA synchronous=FULL;             -- result must be 2
PRAGMA fullfsync=ON;                  -- Darwin
PRAGMA checkpoint_fullfsync=ON;
PRAGMA foreign_keys=ON;
PRAGMA trusted_schema=OFF;
PRAGMA locking_mode=NORMAL;
PRAGMA wal_autocheckpoint=1000;       -- PASSIVE auto-checkpoint policy
PRAGMA recursive_triggers=ON;
```

Bootstrap/writable connections set these values. Every connection, including
fresh resolver readback, queries and verifies every value without relying on
an implicit mode change. The binding must also set and read back
`SQLITE_DBCONFIG_DEFENSIVE`, `SQLITE_DBCONFIG_ENABLE_FKEY`,
`SQLITE_DBCONFIG_ENABLE_TRIGGER`, `SQLITE_DBCONFIG_TRUSTED_SCHEMA=0`, and
`SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE`. A mismatch is `UNAVAILABLE` for a read and
a hard write refusal. Writes use `BEGIN IMMEDIATE`, a bounded busy timeout,
and a stricter outer monotonic deadline.

Forbidden operations are `ATTACH`, manual `-wal`/`-shm` deletion, raw database
copy, `VACUUM`, and any connection that cannot prove the profile. The CLI
3.51.0 observed in the spike is read-only diagnostic at most and cannot open
the successor DB for write.

Under accepted C0-D2, an environment without supported WAL shared memory is
v1 **NO-GO**. `journal_mode=PERSIST` + `synchronous=EXTRA` is not activated
or supported in v1 and cannot substitute for WAL. `WAL + NORMAL` is always
rejected.

### 4.3 Normative strict schema

The implementation may add explanatory views and indexes, but the following
strict relations, keys, checks, and trigger effects are the minimum
executable authority. Hash/JCS recomputation remains application-side because
`trusted_schema=OFF`; triggers enforce relational closure and writer fencing,
not application-defined hash functions.

```sql
PRAGMA foreign_keys = ON;
PRAGMA trusted_schema = OFF;
PRAGMA recursive_triggers = ON;

CREATE TABLE registration_protocol_epoch (
  protocol_epoch INTEGER PRIMARY KEY CHECK (protocol_epoch > 0),
  schema_version INTEGER NOT NULL CHECK (schema_version = 1),
  reader_capability_hash TEXT NOT NULL CHECK (length(reader_capability_hash) = 64),
  writer_capability_hash TEXT NOT NULL CHECK (length(writer_capability_hash) = 64),
  db_profile_hash TEXT NOT NULL CHECK (length(db_profile_hash) = 64),
  writer_inventory_hash TEXT NOT NULL CHECK (length(writer_inventory_hash) = 64),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*')
) STRICT;

CREATE TABLE registration_protocol_writer (
  protocol_epoch INTEGER NOT NULL
    REFERENCES registration_protocol_epoch(protocol_epoch),
  writer_id TEXT NOT NULL,
  binary_hash TEXT NOT NULL CHECK (length(binary_hash) = 64),
  capability_hash TEXT NOT NULL CHECK (length(capability_hash) = 64),
  db_profile_hash TEXT NOT NULL CHECK (length(db_profile_hash) = 64),
  invocable INTEGER NOT NULL CHECK (invocable IN (0, 1)),
  PRIMARY KEY (protocol_epoch, writer_id)
) STRICT;

CREATE TABLE registration_protocol_current (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  protocol_epoch INTEGER NOT NULL
    REFERENCES registration_protocol_epoch(protocol_epoch),
  mode TEXT NOT NULL CHECK (mode IN ('DORMANT', 'WRITABLE', 'DRAINING')),
  write_generation INTEGER NOT NULL CHECK (write_generation >= 0),
  last_write_id TEXT,
  updated_wall_ns TEXT NOT NULL
    CHECK (updated_wall_ns <> '' AND updated_wall_ns NOT GLOB '*[^0-9]*')
) STRICT;

CREATE TABLE registration_writer_capability (
  protocol_epoch INTEGER NOT NULL,
  writer_id TEXT NOT NULL,
  operation_class TEXT NOT NULL
    CHECK (operation_class IN
      ('NORMAL', 'RECONCILE', 'GC', 'RESCUE', 'PROTOCOL')),
  target_table TEXT NOT NULL,
  transition_name TEXT NOT NULL,
  mutation_kind TEXT NOT NULL
    CHECK (mutation_kind IN ('INSERT', 'UPDATE', 'DELETE')),
  PRIMARY KEY
    (protocol_epoch, writer_id, operation_class, target_table,
     transition_name, mutation_kind),
  FOREIGN KEY (protocol_epoch, writer_id)
    REFERENCES registration_protocol_writer(protocol_epoch, writer_id)
) STRICT;

CREATE TABLE registration_mutation_authorization (
  authorization_id TEXT PRIMARY KEY CHECK (length(authorization_id) = 64),
  protocol_epoch INTEGER NOT NULL,
  writer_id TEXT NOT NULL,
  operation_class TEXT NOT NULL,
  target_table TEXT NOT NULL,
  transition_name TEXT NOT NULL,
  mutation_kind TEXT NOT NULL,
  target_key TEXT NOT NULL,
  nonce_hash TEXT NOT NULL CHECK (length(nonce_hash) = 64),
  issued_boot TEXT NOT NULL,
  expires_mono_ns TEXT NOT NULL
    CHECK (expires_mono_ns <> '' AND expires_mono_ns NOT GLOB '*[^0-9]*'),
  issued_wall_ns TEXT NOT NULL
    CHECK (issued_wall_ns <> '' AND issued_wall_ns NOT GLOB '*[^0-9]*'),
  FOREIGN KEY
    (protocol_epoch, writer_id, operation_class, target_table,
     transition_name, mutation_kind)
    REFERENCES registration_writer_capability
      (protocol_epoch, writer_id, operation_class, target_table,
       transition_name, mutation_kind)
) STRICT;

CREATE TABLE registration_write_receipt (
  write_id TEXT PRIMARY KEY CHECK (length(write_id) = 64),
  authorization_id TEXT NOT NULL UNIQUE
    REFERENCES registration_mutation_authorization(authorization_id),
  protocol_epoch INTEGER NOT NULL,
  write_generation INTEGER NOT NULL CHECK (write_generation > 0),
  operation_class TEXT NOT NULL
    CHECK (operation_class IN
      ('NORMAL', 'RECONCILE', 'GC', 'RESCUE', 'PROTOCOL')),
  target_table TEXT NOT NULL,
  transition_name TEXT NOT NULL,
  mutation_kind TEXT NOT NULL
    CHECK (mutation_kind IN ('INSERT', 'UPDATE', 'DELETE')),
  target_key TEXT NOT NULL,
  writer_id TEXT NOT NULL,
  binary_hash TEXT NOT NULL CHECK (length(binary_hash) = 64),
  capability_hash TEXT NOT NULL CHECK (length(capability_hash) = 64),
  db_profile_hash TEXT NOT NULL CHECK (length(db_profile_hash) = 64),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  FOREIGN KEY (protocol_epoch, writer_id)
    REFERENCES registration_protocol_writer(protocol_epoch, writer_id)
) STRICT;

CREATE TABLE registration_mutation_use (
  write_id TEXT PRIMARY KEY
    REFERENCES registration_write_receipt(write_id),
  target_table TEXT NOT NULL,
  transition_name TEXT NOT NULL,
  mutation_kind TEXT NOT NULL,
  target_key TEXT NOT NULL,
  used_wall_ns TEXT NOT NULL
    CHECK (used_wall_ns <> '' AND used_wall_ns NOT GLOB '*[^0-9]*')
) STRICT;

CREATE TRIGGER registration_protocol_epoch_append_only_update
BEFORE UPDATE ON registration_protocol_epoch
BEGIN SELECT RAISE(ABORT, 'protocol epoch is append-only'); END;
CREATE TRIGGER registration_protocol_epoch_append_only_delete
BEFORE DELETE ON registration_protocol_epoch
BEGIN SELECT RAISE(ABORT, 'protocol epoch is append-only'); END;
CREATE TRIGGER registration_protocol_writer_append_only_update
BEFORE UPDATE ON registration_protocol_writer
BEGIN SELECT RAISE(ABORT, 'writer declaration is append-only'); END;
CREATE TRIGGER registration_protocol_writer_append_only_delete
BEFORE DELETE ON registration_protocol_writer
BEGIN SELECT RAISE(ABORT, 'writer declaration is append-only'); END;
CREATE TRIGGER registration_writer_capability_append_only_update
BEFORE UPDATE ON registration_writer_capability
BEGIN SELECT RAISE(ABORT, 'writer capability is append-only'); END;
CREATE TRIGGER registration_writer_capability_append_only_delete
BEFORE DELETE ON registration_writer_capability
BEGIN SELECT RAISE(ABORT, 'writer capability is append-only'); END;
CREATE TRIGGER registration_mutation_authorization_append_only_update
BEFORE UPDATE ON registration_mutation_authorization
BEGIN SELECT RAISE(ABORT, 'mutation authorization is append-only'); END;
CREATE TRIGGER registration_mutation_authorization_append_only_delete
BEFORE DELETE ON registration_mutation_authorization
BEGIN SELECT RAISE(ABORT, 'mutation authorization is append-only'); END;
CREATE TRIGGER registration_write_receipt_append_only_update
BEFORE UPDATE ON registration_write_receipt
BEGIN SELECT RAISE(ABORT, 'write receipt is append-only'); END;
CREATE TRIGGER registration_write_receipt_append_only_delete
BEFORE DELETE ON registration_write_receipt
BEGIN SELECT RAISE(ABORT, 'write receipt is append-only'); END;
CREATE TRIGGER registration_mutation_use_append_only_update
BEFORE UPDATE ON registration_mutation_use
BEGIN SELECT RAISE(ABORT, 'mutation use is append-only'); END;
CREATE TRIGGER registration_mutation_use_append_only_delete
BEFORE DELETE ON registration_mutation_use
BEGIN SELECT RAISE(ABORT, 'mutation use is append-only'); END;

CREATE TRIGGER registration_write_receipt_fence
BEFORE INSERT ON registration_write_receipt
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_protocol_epoch AS e
        ON e.protocol_epoch = c.protocol_epoch
      JOIN registration_protocol_writer AS w
        ON w.protocol_epoch = c.protocol_epoch
       AND w.writer_id = NEW.writer_id
      JOIN registration_mutation_authorization AS a
        ON a.authorization_id = NEW.authorization_id
      JOIN registration_writer_capability AS cap
        ON cap.protocol_epoch = NEW.protocol_epoch
       AND cap.writer_id = NEW.writer_id
       AND cap.operation_class = NEW.operation_class
       AND cap.target_table = NEW.target_table
       AND cap.transition_name = NEW.transition_name
       AND cap.mutation_kind = NEW.mutation_kind
     WHERE c.singleton = 1
       AND c.protocol_epoch = NEW.protocol_epoch
       AND NEW.write_generation = c.write_generation + 1
       AND w.invocable = 1
       AND w.binary_hash = NEW.binary_hash
       AND w.capability_hash = NEW.capability_hash
       AND w.capability_hash = e.writer_capability_hash
       AND w.db_profile_hash = NEW.db_profile_hash
       AND w.db_profile_hash = e.db_profile_hash
       AND a.protocol_epoch = NEW.protocol_epoch
       AND a.writer_id = NEW.writer_id
       AND a.operation_class = NEW.operation_class
       AND a.target_table = NEW.target_table
       AND a.transition_name = NEW.transition_name
       AND a.mutation_kind = NEW.mutation_kind
       AND a.target_key = NEW.target_key
       AND (
         (c.mode = 'DORMANT' AND NEW.operation_class = 'PROTOCOL')
         OR
         (c.mode = 'WRITABLE')
         OR
         (c.mode = 'DRAINING'
          AND NEW.operation_class IN ('RECONCILE', 'GC', 'RESCUE', 'PROTOCOL'))
       )
  ) THEN RAISE(ABORT, 'registration writer fence') END;
END;

CREATE TRIGGER registration_write_receipt_advance
AFTER INSERT ON registration_write_receipt
BEGIN
  UPDATE registration_protocol_current
     SET write_generation = NEW.write_generation,
         last_write_id = NEW.write_id,
         updated_wall_ns = NEW.created_wall_ns
   WHERE singleton = 1;
END;

CREATE TABLE registration_reason (
  reason_code TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('GREEN', 'DEGRADED', 'RED', 'UNKNOWN')),
  wake_kind TEXT NOT NULL CHECK (wake_kind IN
    ('NONE', 'FRESH_IDENTITY', 'DUE', 'HELP', 'OPERATOR', 'HOST_RETRY',
     'REPAIR', 'UNSUPPORTED')),
  safe_action TEXT NOT NULL CHECK (safe_action IN
    ('NONE', 'WAIT', 'RESCUE', 'REOPEN_TARGET', 'REPAIR',
     'UPDATE_RUNTIME', 'REPORT_UNSUPPORTED', 'CANCEL_REPLAN')),
  consequence TEXT NOT NULL CHECK (consequence IN
    ('ALLOW', 'DENY', 'MAY_FAIL_OPEN', 'TERMINAL')),
  recovery_code TEXT NOT NULL
) STRICT;

INSERT INTO registration_reason
  (reason_code, status, wake_kind, safe_action, consequence, recovery_code)
VALUES
  ('registration_needed','DEGRADED','DUE','WAIT','DENY','claim_due'),
  ('wait_backoff','DEGRADED','DUE','WAIT','DENY','retry_due'),
  ('claim_active','DEGRADED','HELP','WAIT','DENY','help_or_expire'),
  ('identity_incomplete','UNKNOWN','FRESH_IDENTITY','WAIT','DENY','fresh_event'),
  ('identity_changed','DEGRADED','FRESH_IDENTITY','WAIT','DENY','successor'),
  ('heartbeat_stale','DEGRADED','FRESH_IDENTITY','WAIT','DENY','fresh_event'),
  ('basis_unstable','DEGRADED','FRESH_IDENTITY','WAIT','DENY','bounded_retry'),
  ('basis_timeout','RED','HOST_RETRY','WAIT','DENY','bounded_retry'),
  ('unknown_discriminator','RED','UNSUPPORTED','REPORT_UNSUPPORTED','DENY','contract_revision'),
  ('protocol_incompatible','RED','REPAIR','UPDATE_RUNTIME','DENY','upgrade_or_repair'),
  ('parser_reject','RED','FRESH_IDENTITY','CANCEL_REPLAN','DENY','valid_payload'),
  ('fallback_deny','RED','REPAIR','REPAIR','DENY','restore_serializer'),
  ('emergency_deny','RED','REPAIR','REPAIR','DENY','repair_protection'),
  ('initial_dirty','DEGRADED','OPERATOR','RESCUE','DENY','rescue'),
  ('git_operation_active','DEGRADED','OPERATOR','RESCUE','DENY','rescue'),
  ('intent_ready','DEGRADED','HELP','WAIT','DENY','execute_intent'),
  ('effect_in_flight','DEGRADED','HELP','WAIT','DENY','help_same_effect'),
  ('resolver_absent','DEGRADED','HELP','WAIT','DENY','retry_same_effect'),
  ('resolver_unavailable','RED','HOST_RETRY','WAIT','DENY','help_due'),
  ('effect_conflict','RED','NONE','REPAIR','TERMINAL','preserve_evidence'),
  ('lease_conflict','RED','NONE','REPAIR','TERMINAL','preserve_evidence'),
  ('lifecycle_conflict','RED','NONE','REPAIR','TERMINAL','preserve_evidence'),
  ('private_state_unsafe','RED','REPAIR','REPAIR','DENY','repair_private_state'),
  ('disk_full','RED','OPERATOR','REPAIR','DENY','free_space'),
  ('temporary_io_unavailable','DEGRADED','HOST_RETRY','WAIT','DENY','bounded_retry'),
  ('writer_skew','RED','REPAIR','UPDATE_RUNTIME','DENY','repair_writer_set'),
  ('rescue_required','DEGRADED','OPERATOR','RESCUE','DENY','rescue'),
  ('rescue_restoring','DEGRADED','OPERATOR','REOPEN_TARGET','DENY','resume_rescue'),
  ('registration_complete','GREEN','NONE','NONE','ALLOW','none'),
  ('superseded','DEGRADED','FRESH_IDENTITY','WAIT','DENY','successor'),
  ('terminal_preintent','RED','OPERATOR','CANCEL_REPLAN','TERMINAL','preserve_evidence'),
  ('hook_absent','RED','UNSUPPORTED','REPORT_UNSUPPORTED','MAY_FAIL_OPEN','restore_hook'),
  ('host_wake_stale','RED','REPAIR','REPAIR','DENY','restore_host_wake'),
  ('unsupported_platform','RED','UNSUPPORTED','REPORT_UNSUPPORTED','MAY_FAIL_OPEN','accepted_residual');

CREATE TABLE registration_canonical_member (
  member_id TEXT PRIMARY KEY CHECK (length(member_id) = 64),
  physical_key_json BLOB NOT NULL,
  physical_key_hash TEXT NOT NULL UNIQUE CHECK (length(physical_key_hash) = 64),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_canonical_member_version (
  member_id TEXT NOT NULL
    REFERENCES registration_canonical_member(member_id),
  member_version INTEGER NOT NULL CHECK (member_version > 0),
  admission_epoch INTEGER NOT NULL CHECK (admission_epoch > 0),
  basis_json BLOB NOT NULL,
  basis_hash TEXT NOT NULL CHECK (length(basis_hash) = 64),
  canonical_root TEXT NOT NULL,
  root_dev TEXT NOT NULL
    CHECK (root_dev <> '' AND root_dev NOT GLOB '*[^0-9]*'),
  root_ino TEXT NOT NULL
    CHECK (root_ino <> '' AND root_ino NOT GLOB '*[^0-9]*'),
  git_dir TEXT NOT NULL,
  git_common_dir TEXT NOT NULL,
  policy_digest TEXT NOT NULL CHECK (length(policy_digest) = 64),
  runtime_capability_digest TEXT NOT NULL
    CHECK (length(runtime_capability_digest) = 64),
  current_session_generation INTEGER NOT NULL
    CHECK (current_session_generation > 0),
  current_session_hash TEXT NOT NULL CHECK (length(current_session_hash) = 64),
  heartbeat_generation INTEGER NOT NULL CHECK (heartbeat_generation > 0),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (member_id, member_version),
  UNIQUE (member_id, admission_epoch),
  UNIQUE (member_id, member_version, admission_epoch)
) STRICT;

CREATE TABLE registration_episode (
  episode_id TEXT PRIMARY KEY CHECK (length(episode_id) = 64),
  episode_incarnation TEXT NOT NULL UNIQUE
    CHECK (length(episode_incarnation) = 64),
  conversation_id TEXT NOT NULL,
  boot_id TEXT NOT NULL,
  root_set_incarnation TEXT NOT NULL
    CHECK (length(root_set_incarnation) = 64),
  root_set_hash TEXT NOT NULL CHECK (length(root_set_hash) = 64),
  root_set_json BLOB NOT NULL,
  source_generation_id TEXT NOT NULL,
  request_created_wall_ns TEXT NOT NULL
    CHECK (request_created_wall_ns <> ''
       AND request_created_wall_ns NOT GLOB '*[^0-9]*'),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  UNIQUE (conversation_id, boot_id, root_set_incarnation)
) STRICT;

CREATE TABLE registration_root_event_evidence (
  event_evidence_id TEXT PRIMARY KEY CHECK (length(event_evidence_id) = 64),
  conversation_hash TEXT NOT NULL CHECK (length(conversation_hash) = 64),
  boot_id TEXT NOT NULL,
  generation_hash TEXT NOT NULL CHECK (length(generation_hash) = 64),
  root_set_incarnation TEXT NOT NULL CHECK (length(root_set_incarnation) = 64),
  root_set_hash TEXT NOT NULL CHECK (length(root_set_hash) = 64),
  descriptor_set_hash TEXT NOT NULL CHECK (length(descriptor_set_hash) = 64),
  evidence_json BLOB NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('CAPTURED', 'SEEDED', 'RESOLVED')),
  episode_id TEXT REFERENCES registration_episode(episode_id),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  CHECK ((state = 'CAPTURED' AND episode_id IS NULL)
      OR (state IN ('SEEDED', 'RESOLVED') AND episode_id IS NOT NULL))
) STRICT;

CREATE TABLE registration_episode_member (
  episode_id TEXT NOT NULL REFERENCES registration_episode(episode_id),
  member_ordinal INTEGER NOT NULL CHECK (member_ordinal >= 0),
  member_id TEXT NOT NULL
    REFERENCES registration_canonical_member(member_id),
  initial_member_version INTEGER NOT NULL CHECK (initial_member_version > 0),
  initial_admission_epoch INTEGER NOT NULL CHECK (initial_admission_epoch > 0),
  eligibility TEXT NOT NULL
    CHECK (eligibility IN ('ELIGIBLE', 'INELIGIBLE', 'EXTERNAL', 'UNKNOWN')),
  descriptor_json BLOB NOT NULL,
  descriptor_hash TEXT NOT NULL CHECK (length(descriptor_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (episode_id, member_id),
  UNIQUE (episode_id, member_ordinal),
  FOREIGN KEY (member_id, initial_member_version, initial_admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch)
) STRICT;

CREATE TABLE registration_request (
  request_key TEXT PRIMARY KEY CHECK (length(request_key) = 64),
  effect_id TEXT NOT NULL UNIQUE CHECK (length(effect_id) = 64),
  episode_id TEXT NOT NULL,
  member_id TEXT NOT NULL,
  member_version INTEGER NOT NULL CHECK (member_version > 0),
  admission_epoch INTEGER NOT NULL CHECK (admission_epoch > 0),
  request_generation INTEGER NOT NULL CHECK (request_generation > 0),
  request_created_wall_ns TEXT NOT NULL
    CHECK (request_created_wall_ns <> ''
       AND request_created_wall_ns NOT GLOB '*[^0-9]*'),
  request_json BLOB NOT NULL,
  request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  UNIQUE (request_key, effect_id),
  UNIQUE (episode_id, member_id, request_generation),
  UNIQUE (request_key, effect_id, episode_id, member_id,
          member_version, admission_epoch, request_generation),
  FOREIGN KEY (episode_id, member_id)
    REFERENCES registration_episode_member(episode_id, member_id),
  FOREIGN KEY (member_id, member_version, admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch)
) STRICT;

CREATE TABLE registration_member_current (
  episode_id TEXT NOT NULL,
  member_id TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK (state_version > 0),
  member_version INTEGER NOT NULL CHECK (member_version > 0),
  admission_epoch INTEGER NOT NULL CHECK (admission_epoch > 0),
  phase TEXT NOT NULL CHECK (phase IN
    ('REQUESTED', 'WAITING', 'CLAIMED', 'EFFECT_IN_FLIGHT',
     'REGISTERED', 'TERMINAL', 'SUPERSEDED')),
  reason TEXT NOT NULL REFERENCES registration_reason(reason_code),
  request_generation INTEGER NOT NULL CHECK (request_generation > 0),
  request_key TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  helper_generation INTEGER NOT NULL CHECK (helper_generation > 0),
  claim_window INTEGER CHECK (claim_window IS NULL OR claim_window >= 0),
  claim_token TEXT,
  claim_boot TEXT,
  claim_expires_mono_ns TEXT,
  next_due_mono_ns TEXT,
  wake_epoch INTEGER NOT NULL CHECK (wake_epoch >= 0),
  discontinuity_marker TEXT,
  supersede_pending INTEGER NOT NULL CHECK (supersede_pending IN (0, 1)),
  pending_member_version INTEGER,
  pending_admission_epoch INTEGER,
  pending_request_generation INTEGER,
  pending_basis_hash TEXT,
  pending_request_key TEXT,
  pending_effect_id TEXT,
  certificate TEXT,
  terminal_result_id TEXT,
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (episode_id, member_id),
  FOREIGN KEY (episode_id, member_id)
    REFERENCES registration_episode_member(episode_id, member_id),
  FOREIGN KEY (member_id, member_version, admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch),
  FOREIGN KEY (request_key, effect_id, episode_id, member_id,
               member_version, admission_epoch, request_generation)
    REFERENCES registration_request
      (request_key, effect_id, episode_id, member_id,
       member_version, admission_epoch, request_generation),
  FOREIGN KEY (pending_request_key, pending_effect_id, episode_id, member_id,
               pending_member_version, pending_admission_epoch,
               pending_request_generation)
    REFERENCES registration_request
      (request_key, effect_id, episode_id, member_id,
       member_version, admission_epoch, request_generation),
  FOREIGN KEY (terminal_result_id)
    REFERENCES registration_member_result_archive(result_id),
  CHECK (phase <> 'CLAIMED' OR
         (claim_window IS NOT NULL AND claim_token IS NOT NULL
          AND claim_boot IS NOT NULL AND claim_expires_mono_ns IS NOT NULL
          AND claim_expires_mono_ns <> ''
          AND claim_expires_mono_ns NOT GLOB '*[^0-9]*')),
  CHECK (phase = 'CLAIMED'
         OR (claim_token IS NULL
             AND claim_boot IS NULL
             AND claim_expires_mono_ns IS NULL)),
  CHECK (next_due_mono_ns IS NULL OR
         (next_due_mono_ns <> ''
          AND next_due_mono_ns NOT GLOB '*[^0-9]*')),
  CHECK (phase NOT IN ('REQUESTED', 'WAITING', 'CLAIMED')
         OR next_due_mono_ns IS NOT NULL),
  CHECK (phase <> 'REGISTERED' OR certificate IS NOT NULL),
  CHECK (phase NOT IN ('TERMINAL', 'SUPERSEDED')
         OR terminal_result_id IS NOT NULL),
  CHECK (supersede_pending = 0 OR
         (pending_member_version IS NOT NULL
          AND pending_admission_epoch IS NOT NULL
          AND pending_request_generation IS NOT NULL
          AND pending_basis_hash IS NOT NULL
          AND pending_request_key IS NOT NULL
          AND pending_effect_id IS NOT NULL)),
  CHECK (supersede_pending = 1 OR
         (pending_member_version IS NULL
          AND pending_admission_epoch IS NULL
          AND pending_request_generation IS NULL
          AND pending_basis_hash IS NULL
          AND pending_request_key IS NULL
          AND pending_effect_id IS NULL))
) STRICT;

CREATE TABLE registration_notice (
  episode_id TEXT NOT NULL,
  notice_epoch INTEGER NOT NULL CHECK (notice_epoch > 0),
  notice_version INTEGER NOT NULL CHECK (notice_version > 0),
  notice_cause TEXT NOT NULL REFERENCES registration_reason(reason_code),
  cause_hash TEXT NOT NULL CHECK (length(cause_hash) = 64),
  repeat_count INTEGER NOT NULL CHECK (repeat_count >= 0 AND repeat_count <= 3),
  progression TEXT NOT NULL
    CHECK (progression IN ('FULL', 'COMPACT1', 'COMPACT2', 'QUIESCENT')),
  stop_followup_consumed INTEGER NOT NULL CHECK (stop_followup_consumed IN (0, 1)),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  updated_wall_ns TEXT NOT NULL
    CHECK (updated_wall_ns <> '' AND updated_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (episode_id, notice_epoch),
  UNIQUE (episode_id, notice_version),
  FOREIGN KEY (episode_id) REFERENCES registration_episode(episode_id),
  CHECK ((repeat_count = 0 AND progression = 'FULL')
      OR (repeat_count = 1 AND progression = 'COMPACT1')
      OR (repeat_count = 2 AND progression = 'COMPACT2')
      OR (repeat_count = 3 AND progression = 'QUIESCENT'))
) STRICT;

CREATE TABLE registration_due_cursor (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  scan_generation INTEGER NOT NULL CHECK (scan_generation >= 0),
  cursor_boot TEXT NOT NULL,
  last_due_mono_ns TEXT
    CHECK (last_due_mono_ns IS NULL
       OR (last_due_mono_ns <> '' AND last_due_mono_ns NOT GLOB '*[^0-9]*')),
  last_request_created_wall_ns TEXT
    CHECK (last_request_created_wall_ns IS NULL
       OR (last_request_created_wall_ns <> ''
           AND last_request_created_wall_ns NOT GLOB '*[^0-9]*')),
  last_member_id TEXT,
  last_request_key TEXT,
  oldest_wait_ns TEXT NOT NULL
    CHECK (oldest_wait_ns <> '' AND oldest_wait_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  CHECK ((last_due_mono_ns IS NULL
          AND last_request_created_wall_ns IS NULL
          AND last_member_id IS NULL
          AND last_request_key IS NULL)
      OR (last_due_mono_ns IS NOT NULL
          AND last_request_created_wall_ns IS NOT NULL
          AND last_member_id IS NOT NULL
          AND last_request_key IS NOT NULL))
) STRICT;

CREATE TABLE registration_alert_component_current (
  component TEXT PRIMARY KEY,
  transition_generation INTEGER NOT NULL CHECK (transition_generation > 0),
  cause_fingerprint TEXT NOT NULL CHECK (length(cause_fingerprint) = 64),
  status TEXT NOT NULL CHECK (status IN ('GREEN', 'DEGRADED', 'RED', 'UNKNOWN')),
  notice_episode_id TEXT,
  notice_epoch INTEGER,
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (notice_episode_id, notice_epoch)
    REFERENCES registration_notice(episode_id, notice_epoch),
  CHECK ((notice_episode_id IS NULL) = (notice_epoch IS NULL))
) STRICT;

CREATE TABLE registration_alert_transition (
  component TEXT NOT NULL,
  transition_generation INTEGER NOT NULL CHECK (transition_generation > 0),
  cause_fingerprint TEXT NOT NULL CHECK (length(cause_fingerprint) = 64),
  status TEXT NOT NULL CHECK (status IN ('GREEN', 'DEGRADED', 'RED', 'UNKNOWN')),
  notice_episode_id TEXT,
  notice_epoch INTEGER,
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (component, transition_generation),
  FOREIGN KEY (notice_episode_id, notice_epoch)
    REFERENCES registration_notice(episode_id, notice_epoch),
  CHECK ((notice_episode_id IS NULL) = (notice_epoch IS NULL))
) STRICT;

CREATE TABLE registration_effect_parent (
  effect_id TEXT PRIMARY KEY CHECK (length(effect_id) = 64),
  request_key TEXT NOT NULL UNIQUE CHECK (length(request_key) = 64),
  episode_id TEXT NOT NULL,
  member_id TEXT NOT NULL,
  member_version INTEGER NOT NULL CHECK (member_version > 0),
  admission_epoch INTEGER NOT NULL CHECK (admission_epoch > 0),
  request_generation INTEGER NOT NULL CHECK (request_generation > 0),
  helper_generation INTEGER NOT NULL CHECK (helper_generation > 0),
  fence_token TEXT NOT NULL UNIQUE CHECK (length(fence_token) = 64),
  basis_hash TEXT NOT NULL CHECK (length(basis_hash) = 64),
  plan_hash TEXT NOT NULL CHECK (length(plan_hash) = 64),
  effect_intent_json BLOB NOT NULL,
  effect_intent_hash TEXT NOT NULL CHECK (length(effect_intent_hash) = 64),
  lease_bytes BLOB NOT NULL,
  lease_hash TEXT NOT NULL CHECK (length(lease_hash) = 64),
  expected_attestation_hash TEXT NOT NULL
    CHECK (length(expected_attestation_hash) = 64),
  expected_manifest_hash TEXT NOT NULL
    CHECK (length(expected_manifest_hash) = 64),
  expected_event_count INTEGER NOT NULL CHECK (expected_event_count >= 0),
  expected_event_root_hash TEXT NOT NULL
    CHECK (length(expected_event_root_hash) = 64),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (request_key, effect_id, episode_id, member_id,
               member_version, admission_epoch, request_generation)
    REFERENCES registration_request
      (request_key, effect_id, episode_id, member_id,
       member_version, admission_epoch, request_generation),
  FOREIGN KEY (episode_id, member_id)
    REFERENCES registration_episode_member(episode_id, member_id),
  FOREIGN KEY (member_id, member_version, admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch)
) STRICT;

CREATE TABLE registration_effect_stage (
  effect_id TEXT PRIMARY KEY
    REFERENCES registration_effect_parent(effect_id),
  stage TEXT NOT NULL CHECK (stage IN
    ('INTENT_DURABLE', 'LEASE_DURABLE', 'GRAPH_COMMITTED', 'CERTIFIED',
     'REFERENCED', 'ACTIVE_PUBLISHED', 'REGISTERED', 'TERMINAL')),
  resolution TEXT NOT NULL CHECK (resolution IN
    ('PENDING', 'COMMITTED', 'ABSENT', 'CONFLICT', 'UNAVAILABLE')),
  resolution_version INTEGER NOT NULL CHECK (resolution_version > 0),
  detail_code TEXT NOT NULL REFERENCES registration_reason(reason_code),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_action (
  effect_id TEXT NOT NULL
    REFERENCES registration_effect_parent(effect_id),
  action_ordinal INTEGER NOT NULL CHECK (action_ordinal >= 0),
  action_class TEXT NOT NULL CHECK (action_class IN
    ('LEASE_PUBLICATION', 'SQLITE_GRAPH', 'CERTIFICATE_PUBLICATION',
     'REFERENCE_PUBLICATION', 'POINTER_PUBLICATION', 'MEMBER_PUBLICATION')),
  action_key TEXT NOT NULL,
  postcondition_json BLOB NOT NULL,
  postcondition_hash TEXT NOT NULL CHECK (length(postcondition_hash) = 64),
  state TEXT NOT NULL CHECK (state IN
    ('PENDING', 'APPLYING', 'VERIFIED', 'CONFLICT')),
  acknowledgement_generation INTEGER NOT NULL
    CHECK (acknowledgement_generation >= 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (effect_id, action_ordinal),
  UNIQUE (effect_id, action_class, action_key)
) STRICT;

CREATE TABLE registration_member_result_archive (
  result_id TEXT PRIMARY KEY CHECK (length(result_id) = 64),
  episode_id TEXT NOT NULL,
  member_id TEXT NOT NULL,
  terminal_phase TEXT NOT NULL
    CHECK (terminal_phase IN ('REGISTERED', 'TERMINAL', 'SUPERSEDED')),
  state_version INTEGER NOT NULL CHECK (state_version > 0),
  member_version INTEGER NOT NULL CHECK (member_version > 0),
  admission_epoch INTEGER NOT NULL CHECK (admission_epoch > 0),
  request_generation INTEGER NOT NULL CHECK (request_generation > 0),
  helper_generation INTEGER NOT NULL CHECK (helper_generation > 0),
  request_key TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  certificate TEXT,
  supersede_pending INTEGER NOT NULL CHECK (supersede_pending IN (0, 1)),
  pending_member_version INTEGER,
  pending_admission_epoch INTEGER,
  pending_request_generation INTEGER,
  pending_basis_hash TEXT,
  pending_request_key TEXT,
  pending_effect_id TEXT,
  result_json BLOB NOT NULL,
  result_hash TEXT NOT NULL CHECK (length(result_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (episode_id, member_id)
    REFERENCES registration_episode_member(episode_id, member_id),
  FOREIGN KEY (member_id, member_version, admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch),
  FOREIGN KEY (request_key, effect_id, episode_id, member_id,
               member_version, admission_epoch, request_generation)
    REFERENCES registration_request
      (request_key, effect_id, episode_id, member_id,
       member_version, admission_epoch, request_generation),
  FOREIGN KEY (pending_request_key, pending_effect_id, episode_id, member_id,
               pending_member_version, pending_admission_epoch,
               pending_request_generation)
    REFERENCES registration_request
      (request_key, effect_id, episode_id, member_id,
       member_version, admission_epoch, request_generation),
  CHECK (supersede_pending = 0
         OR (pending_member_version IS NOT NULL
             AND pending_admission_epoch IS NOT NULL
             AND pending_request_generation IS NOT NULL
             AND pending_basis_hash IS NOT NULL
             AND pending_request_key IS NOT NULL
             AND pending_effect_id IS NOT NULL)),
  CHECK (supersede_pending = 1
         OR (pending_member_version IS NULL
             AND pending_admission_epoch IS NULL
             AND pending_request_generation IS NULL
             AND pending_basis_hash IS NULL
             AND pending_request_key IS NULL
             AND pending_effect_id IS NULL))
) STRICT;

CREATE TABLE registration_effect_lease (
  effect_id TEXT PRIMARY KEY
    REFERENCES registration_effect_parent(effect_id),
  lease_id TEXT NOT NULL UNIQUE CHECK (length(lease_id) = 64),
  relative_path TEXT NOT NULL,
  lease_bytes BLOB NOT NULL,
  lease_length INTEGER NOT NULL CHECK (lease_length >= 0),
  lease_hash TEXT NOT NULL CHECK (length(lease_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_attestation (
  effect_id TEXT PRIMARY KEY
    REFERENCES registration_effect_parent(effect_id),
  attestation_json BLOB NOT NULL,
  attestation_hash TEXT NOT NULL CHECK (length(attestation_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_event (
  effect_id TEXT NOT NULL
    REFERENCES registration_effect_parent(effect_id),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  event_type TEXT NOT NULL,
  event_json BLOB NOT NULL,
  event_hash TEXT NOT NULL CHECK (length(event_hash) = 64),
  chain_hash TEXT NOT NULL CHECK (length(chain_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (effect_id, ordinal)
) STRICT;

CREATE TABLE registration_effect_manifest (
  effect_id TEXT PRIMARY KEY
    REFERENCES registration_effect_parent(effect_id),
  manifest_json BLOB NOT NULL,
  manifest_hash TEXT NOT NULL CHECK (length(manifest_hash) = 64),
  lease_json BLOB NOT NULL,
  lease_encoding TEXT NOT NULL
    CHECK (lease_encoding = 'jcs-rfc8785/utf-8+lf/v1'),
  lease_length INTEGER NOT NULL CHECK (lease_length >= 0),
  lease_hash TEXT NOT NULL CHECK (length(lease_hash) = 64),
  attestation_hash TEXT NOT NULL CHECK (length(attestation_hash) = 64),
  event_count INTEGER NOT NULL CHECK (event_count >= 0),
  event_root_hash TEXT NOT NULL CHECK (length(event_root_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_completion (
  effect_id TEXT PRIMARY KEY
    REFERENCES registration_effect_parent(effect_id),
  completion_json BLOB NOT NULL,
  completion_hash TEXT NOT NULL CHECK (length(completion_hash) = 64),
  request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
  lease_hash TEXT NOT NULL CHECK (length(lease_hash) = 64),
  attestation_hash TEXT NOT NULL CHECK (length(attestation_hash) = 64),
  manifest_hash TEXT NOT NULL CHECK (length(manifest_hash) = 64),
  event_count INTEGER NOT NULL CHECK (event_count >= 0),
  event_root_hash TEXT NOT NULL CHECK (length(event_root_hash) = 64),
  closure_schema_version INTEGER NOT NULL CHECK (closure_schema_version = 1),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_certificate (
  effect_id TEXT PRIMARY KEY
    REFERENCES registration_effect_completion(effect_id),
  certificate TEXT NOT NULL UNIQUE CHECK (length(certificate) = 64),
  certificate_inputs_hash TEXT NOT NULL CHECK (length(certificate_inputs_hash) = 64),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_reference_clock (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  reference_generation INTEGER NOT NULL CHECK (reference_generation >= 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_reference (
  reference_id TEXT PRIMARY KEY CHECK (length(reference_id) = 64),
  effect_id TEXT NOT NULL
    REFERENCES registration_effect_parent(effect_id),
  reference_kind TEXT NOT NULL CHECK (reference_kind IN
    ('EPISODE', 'ACTIVE_POINTER', 'AUDIT', 'RECOVERY', 'RESCUE', 'INTEGRITY')),
  owner_hash TEXT NOT NULL CHECK (length(owner_hash) = 64),
  reference_generation INTEGER NOT NULL CHECK (reference_generation > 0),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  UNIQUE (effect_id, reference_kind, owner_hash)
) STRICT;

CREATE TABLE registration_rescue (
  rescue_id TEXT PRIMARY KEY CHECK (length(rescue_id) = 64),
  state_version INTEGER NOT NULL CHECK (state_version > 0),
  source_episode_id TEXT NOT NULL,
  source_member_id TEXT NOT NULL,
  source_member_version INTEGER NOT NULL CHECK (source_member_version > 0),
  source_admission_epoch INTEGER NOT NULL CHECK (source_admission_epoch > 0),
  source_incarnation_hash TEXT NOT NULL CHECK (length(source_incarnation_hash) = 64),
  state TEXT NOT NULL CHECK (state IN
    ('PLANNED', 'AUTHORIZED', 'PRESERVING', 'PRESERVED',
     'TARGET_PROVISIONING', 'AWAITING_TARGET_ENTRY',
     'TARGET_LIFECYCLE_COMMITTED', 'RESTORING', 'REGISTERED',
     'CANCELLED', 'SUPERSEDED', 'PRESERVED_ONLY',
     'AWAITING_OPERATOR', 'TERMINAL_CONFLICT')),
  handoff_id TEXT UNIQUE,
  failure_code TEXT CHECK (
    failure_code IS NULL OR failure_code IN
      ('R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R08', 'R09', 'R10',
       'R11', 'R12', 'R13', 'R14', 'R15', 'R16', 'R17', 'R18', 'R19', 'R20')
  ),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (source_episode_id, source_member_id)
    REFERENCES registration_episode_member(episode_id, member_id),
  FOREIGN KEY
    (source_member_id, source_member_version, source_admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch)
) STRICT;

CREATE TABLE registration_rescue_plan (
  plan_id TEXT PRIMARY KEY CHECK (length(plan_id) = 64),
  rescue_id TEXT NOT NULL UNIQUE REFERENCES registration_rescue(rescue_id),
  source_incarnation_hash TEXT NOT NULL CHECK (length(source_incarnation_hash) = 64),
  conversation_hash TEXT NOT NULL CHECK (length(conversation_hash) = 64),
  generation_hash TEXT NOT NULL CHECK (length(generation_hash) = 64),
  event_nonce_hash TEXT NOT NULL CHECK (length(event_nonce_hash) = 64),
  plan_json BLOB NOT NULL,
  plan_digest TEXT NOT NULL UNIQUE CHECK (length(plan_digest) = 64),
  item_count INTEGER NOT NULL CHECK (item_count >= 0),
  secret_item_count INTEGER NOT NULL
    CHECK (secret_item_count >= 0 AND secret_item_count <= item_count),
  expires_boot TEXT NOT NULL,
  expires_mono_ns TEXT NOT NULL
    CHECK (expires_mono_ns <> '' AND expires_mono_ns NOT GLOB '*[^0-9]*'),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_rescue_plan_item (
  plan_id TEXT NOT NULL REFERENCES registration_rescue_plan(plan_id),
  item_ordinal INTEGER NOT NULL CHECK (item_ordinal >= 0),
  item_kind TEXT NOT NULL CHECK (item_kind IN
    ('TRACKED', 'STAGED', 'CONFLICTED', 'UNTRACKED', 'IGNORED',
     'INDEX', 'OPERATION_STATE', 'REF', 'OBJECT_PACK')),
  opaque_item_id TEXT NOT NULL,
  item_digest TEXT NOT NULL CHECK (length(item_digest) = 64),
  secret_bearing INTEGER NOT NULL CHECK (secret_bearing IN (0, 1)),
  item_json BLOB NOT NULL,
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (plan_id, item_ordinal),
  UNIQUE (plan_id, opaque_item_id)
) STRICT;

CREATE TABLE registration_rescue_authorization (
  authorization_id TEXT PRIMARY KEY CHECK (length(authorization_id) = 64),
  rescue_id TEXT NOT NULL REFERENCES registration_rescue(rescue_id),
  plan_id TEXT NOT NULL REFERENCES registration_rescue_plan(plan_id),
  source_incarnation_hash TEXT NOT NULL CHECK (length(source_incarnation_hash) = 64),
  conversation_hash TEXT NOT NULL CHECK (length(conversation_hash) = 64),
  generation_hash TEXT NOT NULL CHECK (length(generation_hash) = 64),
  event_nonce_hash TEXT NOT NULL CHECK (length(event_nonce_hash) = 64),
  attachment_count INTEGER NOT NULL CHECK (attachment_count = 0),
  literal TEXT NOT NULL
    CHECK (literal IN ('Preserve', 'Preserve including secrets')),
  secret_scope TEXT NOT NULL CHECK (secret_scope IN ('EXCLUDE', 'INCLUDE')),
  plan_digest TEXT NOT NULL CHECK (length(plan_digest) = 64),
  expires_boot TEXT NOT NULL,
  expires_mono_ns TEXT NOT NULL
    CHECK (expires_mono_ns <> '' AND expires_mono_ns NOT GLOB '*[^0-9]*'),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  UNIQUE (rescue_id, authorization_id),
  CHECK ((literal = 'Preserve' AND secret_scope = 'EXCLUDE')
      OR (literal = 'Preserve including secrets' AND secret_scope = 'INCLUDE'))
) STRICT;

CREATE TABLE registration_rescue_authorization_use (
  authorization_id TEXT PRIMARY KEY
    REFERENCES registration_rescue_authorization(authorization_id),
  rescue_id TEXT NOT NULL UNIQUE REFERENCES registration_rescue(rescue_id),
  consumed_state_version INTEGER NOT NULL CHECK (consumed_state_version > 0),
  consumed_wall_ns TEXT NOT NULL
    CHECK (consumed_wall_ns <> '' AND consumed_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_rescue_artifact (
  artifact_id TEXT PRIMARY KEY CHECK (length(artifact_id) = 64),
  rescue_id TEXT NOT NULL UNIQUE REFERENCES registration_rescue(rescue_id),
  plan_id TEXT NOT NULL REFERENCES registration_rescue_plan(plan_id),
  artifact_hash TEXT NOT NULL UNIQUE CHECK (length(artifact_hash) = 64),
  proof_hash TEXT NOT NULL CHECK (length(proof_hash) = 64),
  publication_hash TEXT NOT NULL CHECK (length(publication_hash) = 64),
  source_dev TEXT NOT NULL
    CHECK (source_dev <> '' AND source_dev NOT GLOB '*[^0-9]*'),
  complete INTEGER NOT NULL CHECK (complete = 1),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_rescue_artifact_reference (
  reference_id TEXT PRIMARY KEY CHECK (length(reference_id) = 64),
  artifact_id TEXT NOT NULL REFERENCES registration_rescue_artifact(artifact_id),
  reference_kind TEXT NOT NULL CHECK (reference_kind IN
    ('RESCUE', 'AUDIT', 'RECOVERY', 'INTEGRITY', 'OPERATOR_RETENTION')),
  owner_hash TEXT NOT NULL CHECK (length(owner_hash) = 64),
  retention_generation INTEGER NOT NULL CHECK (retention_generation > 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  UNIQUE (artifact_id, reference_kind, owner_hash)
) STRICT;

CREATE TABLE registration_rescue_target_reservation (
  rescue_id TEXT PRIMARY KEY REFERENCES registration_rescue(rescue_id),
  source_member_id TEXT NOT NULL,
  target_member_id TEXT NOT NULL,
  target_member_version INTEGER NOT NULL CHECK (target_member_version > 0),
  target_admission_epoch INTEGER NOT NULL CHECK (target_admission_epoch > 0),
  target_root_hash TEXT NOT NULL CHECK (length(target_root_hash) = 64),
  handoff_id TEXT NOT NULL UNIQUE,
  reservation_version INTEGER NOT NULL CHECK (reservation_version > 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (target_member_id, target_member_version, target_admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch),
  CHECK (source_member_id <> target_member_id)
) STRICT;

CREATE TABLE registration_rescue_target_registration (
  rescue_id TEXT PRIMARY KEY
    REFERENCES registration_rescue_target_reservation(rescue_id),
  target_episode_id TEXT NOT NULL,
  target_member_id TEXT NOT NULL,
  target_member_version INTEGER NOT NULL,
  target_admission_epoch INTEGER NOT NULL,
  request_generation INTEGER NOT NULL CHECK (request_generation > 0),
  request_key TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  certificate TEXT NOT NULL,
  proof_hash TEXT NOT NULL CHECK (length(proof_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (target_episode_id, target_member_id)
    REFERENCES registration_episode_member(episode_id, member_id),
  FOREIGN KEY (target_member_id, target_member_version, target_admission_epoch)
    REFERENCES registration_canonical_member_version
      (member_id, member_version, admission_epoch),
  FOREIGN KEY (request_key, effect_id, target_episode_id, target_member_id,
               target_member_version, target_admission_epoch,
               request_generation)
    REFERENCES registration_request
      (request_key, effect_id, episode_id, member_id,
       member_version, admission_epoch, request_generation)
) STRICT;

CREATE TABLE registration_rescue_restore_proof (
  rescue_id TEXT PRIMARY KEY
    REFERENCES registration_rescue_target_registration(rescue_id),
  artifact_id TEXT NOT NULL REFERENCES registration_rescue_artifact(artifact_id),
  restore_hash TEXT NOT NULL CHECK (length(restore_hash) = 64),
  index_hash TEXT NOT NULL CHECK (length(index_hash) = 64),
  refs_hash TEXT NOT NULL CHECK (length(refs_hash) = 64),
  operation_state_hash TEXT NOT NULL CHECK (length(operation_state_hash) = 64),
  verified INTEGER NOT NULL CHECK (verified = 1),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_rescue_completion (
  rescue_id TEXT PRIMARY KEY
    REFERENCES registration_rescue_restore_proof(rescue_id),
  completion_hash TEXT NOT NULL CHECK (length(completion_hash) = 64),
  source_unchanged_hash TEXT NOT NULL CHECK (length(source_unchanged_hash) = 64),
  completed_wall_ns TEXT NOT NULL
    CHECK (completed_wall_ns <> '' AND completed_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_rescue_transition (
  rescue_id TEXT NOT NULL REFERENCES registration_rescue(rescue_id),
  state_version INTEGER NOT NULL CHECK (state_version > 0),
  from_state TEXT NOT NULL CHECK (from_state IN
    ('PLANNED', 'AUTHORIZED', 'PRESERVING', 'PRESERVED',
     'TARGET_PROVISIONING', 'AWAITING_TARGET_ENTRY',
     'TARGET_LIFECYCLE_COMMITTED', 'RESTORING', 'REGISTERED',
     'CANCELLED', 'SUPERSEDED', 'PRESERVED_ONLY',
     'AWAITING_OPERATOR', 'TERMINAL_CONFLICT')),
  to_state TEXT NOT NULL CHECK (to_state IN
    ('PLANNED', 'AUTHORIZED', 'PRESERVING', 'PRESERVED',
     'TARGET_PROVISIONING', 'AWAITING_TARGET_ENTRY',
     'TARGET_LIFECYCLE_COMMITTED', 'RESTORING', 'REGISTERED',
     'CANCELLED', 'SUPERSEDED', 'PRESERVED_ONLY',
     'AWAITING_OPERATOR', 'TERMINAL_CONFLICT')),
  transition_name TEXT NOT NULL,
  transition_hash TEXT NOT NULL CHECK (length(transition_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (rescue_id, state_version)
) STRICT;

CREATE TABLE registration_rescue_action (
  rescue_id TEXT NOT NULL REFERENCES registration_rescue(rescue_id),
  action_ordinal INTEGER NOT NULL CHECK (action_ordinal >= 0),
  action_class TEXT NOT NULL CHECK (action_class IN
    ('ARTIFACT_PUBLICATION', 'TARGET_PROVISION', 'RESTORE')),
  action_key TEXT NOT NULL,
  postcondition_json BLOB NOT NULL,
  postcondition_hash TEXT NOT NULL CHECK (length(postcondition_hash) = 64),
  state TEXT NOT NULL CHECK (state IN
    ('PENDING', 'APPLYING', 'VERIFIED', 'CONFLICT')),
  acknowledgement_generation INTEGER NOT NULL
    CHECK (acknowledgement_generation >= 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (rescue_id, action_ordinal),
  UNIQUE (rescue_id, action_class, action_key)
) STRICT;

CREATE TABLE registration_retention_clock (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  retention_generation INTEGER NOT NULL CHECK (retention_generation >= 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_effect_retention (
  effect_id TEXT PRIMARY KEY REFERENCES registration_effect_parent(effect_id),
  intent_generation INTEGER NOT NULL CHECK (intent_generation > 0),
  terminal_complete INTEGER NOT NULL CHECK (terminal_complete IN (0, 1)),
  collectible_marker_hash TEXT
    CHECK (collectible_marker_hash IS NULL OR length(collectible_marker_hash) = 64),
  collectible_generation INTEGER,
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  CHECK (terminal_complete = 0
         OR (collectible_marker_hash IS NOT NULL
             AND collectible_generation IS NOT NULL
             AND collectible_generation >= intent_generation))
) STRICT;

CREATE TABLE registration_effect_hold (
  effect_id TEXT NOT NULL REFERENCES registration_effect_parent(effect_id),
  hold_id TEXT NOT NULL CHECK (length(hold_id) = 64),
  hold_kind TEXT NOT NULL CHECK (hold_kind IN
    ('INTENT', 'MEMBER', 'CLAIM', 'POINTER', 'REFERENCE',
     'AUDIT', 'RECOVERY', 'INTEGRITY', 'RESCUE', 'EXPLICIT')),
  holder_hash TEXT NOT NULL CHECK (length(holder_hash) = 64),
  created_generation INTEGER NOT NULL CHECK (created_generation > 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (effect_id, hold_id)
) STRICT;

CREATE TABLE registration_effect_hold_release (
  effect_id TEXT NOT NULL,
  hold_id TEXT NOT NULL,
  released_generation INTEGER NOT NULL CHECK (released_generation > 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (effect_id, hold_id),
  FOREIGN KEY (effect_id, hold_id)
    REFERENCES registration_effect_hold(effect_id, hold_id)
) STRICT;

CREATE TABLE registration_artifact_retention (
  artifact_id TEXT PRIMARY KEY
    REFERENCES registration_rescue_artifact(artifact_id),
  intent_generation INTEGER NOT NULL CHECK (intent_generation > 0),
  terminal_complete INTEGER NOT NULL CHECK (terminal_complete IN (0, 1)),
  collectible_marker_hash TEXT
    CHECK (collectible_marker_hash IS NULL OR length(collectible_marker_hash) = 64),
  collectible_generation INTEGER,
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  CHECK (terminal_complete = 0
         OR (collectible_marker_hash IS NOT NULL
             AND collectible_generation IS NOT NULL
             AND collectible_generation >= intent_generation))
) STRICT;

CREATE TABLE registration_artifact_hold (
  artifact_id TEXT NOT NULL REFERENCES registration_rescue_artifact(artifact_id),
  hold_id TEXT NOT NULL CHECK (length(hold_id) = 64),
  hold_kind TEXT NOT NULL CHECK (hold_kind IN
    ('RESCUE', 'MEMBER', 'POINTER', 'REFERENCE',
     'AUDIT', 'RECOVERY', 'INTEGRITY', 'EXPLICIT')),
  holder_hash TEXT NOT NULL CHECK (length(holder_hash) = 64),
  created_generation INTEGER NOT NULL CHECK (created_generation > 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (artifact_id, hold_id)
) STRICT;

CREATE TABLE registration_artifact_hold_release (
  artifact_id TEXT NOT NULL,
  hold_id TEXT NOT NULL,
  released_generation INTEGER NOT NULL CHECK (released_generation > 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (artifact_id, hold_id),
  FOREIGN KEY (artifact_id, hold_id)
    REFERENCES registration_artifact_hold(artifact_id, hold_id)
) STRICT;

CREATE TABLE registration_gc_run (
  gc_run_id TEXT PRIMARY KEY CHECK (length(gc_run_id) = 64),
  reservation_generation INTEGER NOT NULL CHECK (reservation_generation > 0),
  state TEXT NOT NULL CHECK (state IN
    ('RESERVED', 'TRASHING', 'TRASHED', 'DELETING', 'COMPLETE', 'TERMINAL')),
  journal_hash TEXT NOT NULL CHECK (length(journal_hash) = 64),
  created_wall_ns TEXT NOT NULL
    CHECK (created_wall_ns <> '' AND created_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id)
) STRICT;

CREATE TABLE registration_gc_item (
  gc_run_id TEXT NOT NULL REFERENCES registration_gc_run(gc_run_id),
  effect_id TEXT NOT NULL REFERENCES registration_effect_parent(effect_id),
  reservation_generation INTEGER NOT NULL CHECK (reservation_generation > 0),
  state TEXT NOT NULL CHECK (state IN
    ('RESERVED', 'TRASHED', 'DELETING', 'DELETED',
     'TOMBSTONED', 'RETAINED', 'TERMINAL')),
  expected_lease_hash TEXT NOT NULL CHECK (length(expected_lease_hash) = 64),
  source_dev TEXT NOT NULL
    CHECK (source_dev <> '' AND source_dev NOT GLOB '*[^0-9]*'),
  trash_dev TEXT NOT NULL
    CHECK (trash_dev <> '' AND trash_dev NOT GLOB '*[^0-9]*'),
  trash_name TEXT NOT NULL,
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (gc_run_id, effect_id),
  UNIQUE (effect_id),
  CHECK (source_dev = trash_dev)
) STRICT;

CREATE TABLE registration_gc_artifact_item (
  gc_run_id TEXT NOT NULL REFERENCES registration_gc_run(gc_run_id),
  artifact_id TEXT NOT NULL REFERENCES registration_rescue_artifact(artifact_id),
  reservation_generation INTEGER NOT NULL CHECK (reservation_generation > 0),
  state TEXT NOT NULL CHECK (state IN
    ('RESERVED', 'TRASHED', 'DELETING', 'DELETED',
     'TOMBSTONED', 'RETAINED', 'TERMINAL')),
  expected_artifact_hash TEXT NOT NULL CHECK (length(expected_artifact_hash) = 64),
  move_kind TEXT NOT NULL
    CHECK (move_kind IN ('SAME_DEVICE_RENAME', 'CROSS_DEVICE_COPY')),
  source_dev TEXT NOT NULL
    CHECK (source_dev <> '' AND source_dev NOT GLOB '*[^0-9]*'),
  trash_dev TEXT NOT NULL
    CHECK (trash_dev <> '' AND trash_dev NOT GLOB '*[^0-9]*'),
  trash_name TEXT NOT NULL,
  copy_journal_hash TEXT
    CHECK (copy_journal_hash IS NULL OR length(copy_journal_hash) = 64),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (gc_run_id, artifact_id),
  UNIQUE (artifact_id),
  CHECK ((move_kind = 'SAME_DEVICE_RENAME' AND source_dev = trash_dev
          AND copy_journal_hash IS NULL)
      OR (move_kind = 'CROSS_DEVICE_COPY' AND source_dev <> trash_dev
          AND copy_journal_hash IS NOT NULL))
) STRICT;

CREATE TABLE registration_gc_action (
  gc_run_id TEXT NOT NULL REFERENCES registration_gc_run(gc_run_id),
  subject_kind TEXT NOT NULL CHECK (subject_kind IN ('EFFECT', 'ARTIFACT')),
  subject_id TEXT NOT NULL,
  action_ordinal INTEGER NOT NULL CHECK (action_ordinal >= 0),
  action_class TEXT NOT NULL CHECK (action_class IN
    ('TRASH_RENAME', 'COPY_FULLSYNC_VERIFY', 'SOURCE_UNLINK', 'GRAPH_DELETE',
     'TOMBSTONE')),
  postcondition_json BLOB NOT NULL,
  postcondition_hash TEXT NOT NULL CHECK (length(postcondition_hash) = 64),
  state TEXT NOT NULL CHECK (state IN
    ('PENDING', 'APPLYING', 'VERIFIED', 'CONFLICT')),
  acknowledgement_generation INTEGER NOT NULL
    CHECK (acknowledgement_generation >= 0),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  PRIMARY KEY (gc_run_id, subject_kind, subject_id, action_ordinal)
) STRICT;

CREATE TABLE registration_gc_tombstone (
  tombstone_id TEXT PRIMARY KEY CHECK (length(tombstone_id) = 64),
  gc_run_id TEXT NOT NULL,
  effect_id TEXT NOT NULL,
  retention_barrier_generation INTEGER NOT NULL
    CHECK (retention_barrier_generation > 0),
  deleted_graph_hash TEXT NOT NULL CHECK (length(deleted_graph_hash) = 64),
  deleted_lease_hash TEXT NOT NULL CHECK (length(deleted_lease_hash) = 64),
  completed_wall_ns TEXT NOT NULL
    CHECK (completed_wall_ns <> ''
       AND completed_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (gc_run_id, effect_id)
    REFERENCES registration_gc_item(gc_run_id, effect_id),
  UNIQUE (gc_run_id, effect_id)
) STRICT;

CREATE TABLE registration_gc_artifact_tombstone (
  tombstone_id TEXT PRIMARY KEY CHECK (length(tombstone_id) = 64),
  gc_run_id TEXT NOT NULL,
  artifact_id TEXT NOT NULL,
  retention_barrier_generation INTEGER NOT NULL
    CHECK (retention_barrier_generation > 0),
  deleted_artifact_hash TEXT NOT NULL CHECK (length(deleted_artifact_hash) = 64),
  completed_wall_ns TEXT NOT NULL
    CHECK (completed_wall_ns <> ''
       AND completed_wall_ns NOT GLOB '*[^0-9]*'),
  last_write_id TEXT NOT NULL REFERENCES registration_write_receipt(write_id),
  FOREIGN KEY (gc_run_id, artifact_id)
    REFERENCES registration_gc_artifact_item(gc_run_id, artifact_id),
  UNIQUE (gc_run_id, artifact_id)
) STRICT;

CREATE TRIGGER registration_effect_completion_validate
BEFORE INSERT ON registration_effect_completion
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_effect_parent AS p
      JOIN registration_request AS r
        ON r.request_key = p.request_key
       AND r.effect_id = p.effect_id
      JOIN registration_effect_stage AS s USING (effect_id)
      JOIN registration_effect_lease AS l USING (effect_id)
      JOIN registration_effect_attestation AS a USING (effect_id)
      JOIN registration_effect_manifest AS m USING (effect_id)
     WHERE p.effect_id = NEW.effect_id
       AND s.stage = 'LEASE_DURABLE'
       AND s.resolution IN ('PENDING', 'ABSENT')
       AND NEW.request_hash = r.request_hash
       AND p.lease_hash = l.lease_hash
       AND p.lease_hash = m.lease_hash
       AND m.lease_json = l.lease_bytes
       AND m.lease_length = l.lease_length
       AND m.lease_encoding = 'jcs-rfc8785/utf-8+lf/v1'
       AND p.expected_attestation_hash = a.attestation_hash
       AND p.expected_attestation_hash = m.attestation_hash
       AND p.expected_manifest_hash = m.manifest_hash
       AND p.expected_event_count = m.event_count
       AND p.expected_event_root_hash = m.event_root_hash
       AND NEW.lease_hash = l.lease_hash
       AND NEW.attestation_hash = a.attestation_hash
       AND NEW.manifest_hash = m.manifest_hash
       AND NEW.event_count = p.expected_event_count
       AND NEW.event_root_hash = p.expected_event_root_hash
       AND (SELECT COUNT(*) FROM registration_effect_event AS ev
             WHERE ev.effect_id = NEW.effect_id) = p.expected_event_count
       AND (
         p.expected_event_count = 0
         OR (
           (SELECT MIN(ordinal) FROM registration_effect_event AS ev
             WHERE ev.effect_id = NEW.effect_id) = 0
           AND
           (SELECT MAX(ordinal) FROM registration_effect_event AS ev
             WHERE ev.effect_id = NEW.effect_id) = p.expected_event_count - 1
         )
       )
  ) THEN RAISE(ABORT, 'registration effect graph is not closed') END;
END;

CREATE TRIGGER registration_effect_lease_insert_seal
BEFORE INSERT ON registration_effect_lease
WHEN EXISTS (
  SELECT 1 FROM registration_effect_completion WHERE effect_id = NEW.effect_id
)
BEGIN SELECT RAISE(ABORT, 'completion seals lease inserts'); END;
CREATE TRIGGER registration_effect_attestation_insert_seal
BEFORE INSERT ON registration_effect_attestation
WHEN EXISTS (
  SELECT 1 FROM registration_effect_completion WHERE effect_id = NEW.effect_id
)
BEGIN SELECT RAISE(ABORT, 'completion seals attestation inserts'); END;
CREATE TRIGGER registration_effect_event_insert_seal
BEFORE INSERT ON registration_effect_event
WHEN EXISTS (
  SELECT 1 FROM registration_effect_completion WHERE effect_id = NEW.effect_id
)
BEGIN SELECT RAISE(ABORT, 'completion seals event inserts'); END;
CREATE TRIGGER registration_effect_manifest_insert_seal
BEFORE INSERT ON registration_effect_manifest
WHEN EXISTS (
  SELECT 1 FROM registration_effect_completion WHERE effect_id = NEW.effect_id
)
BEGIN SELECT RAISE(ABORT, 'completion seals manifest inserts'); END;

CREATE TRIGGER registration_effect_parent_immutable_update
BEFORE UPDATE ON registration_effect_parent
BEGIN SELECT RAISE(ABORT, 'effect parent is immutable'); END;
CREATE TRIGGER registration_effect_parent_immutable_delete
BEFORE DELETE ON registration_effect_parent
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'effect parent delete requires GC reservation'); END;

CREATE TRIGGER registration_effect_completion_immutable_update
BEFORE UPDATE ON registration_effect_completion
BEGIN SELECT RAISE(ABORT, 'effect completion is immutable'); END;
CREATE TRIGGER registration_effect_completion_immutable_delete
BEFORE DELETE ON registration_effect_completion
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'effect completion delete requires GC reservation'); END;

CREATE TRIGGER registration_effect_certificate_immutable_update
BEFORE UPDATE ON registration_effect_certificate
BEGIN SELECT RAISE(ABORT, 'effect certificate is immutable'); END;
CREATE TRIGGER registration_effect_certificate_immutable_delete
BEFORE DELETE ON registration_effect_certificate
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'effect certificate delete requires GC reservation'); END;

CREATE TRIGGER registration_effect_lease_sealed_update
BEFORE UPDATE ON registration_effect_lease
BEGIN SELECT RAISE(ABORT, 'sealed effect lease'); END;
CREATE TRIGGER registration_effect_attestation_sealed_update
BEFORE UPDATE ON registration_effect_attestation
BEGIN SELECT RAISE(ABORT, 'sealed effect attestation'); END;
CREATE TRIGGER registration_effect_event_sealed_update
BEFORE UPDATE ON registration_effect_event
BEGIN SELECT RAISE(ABORT, 'sealed effect event'); END;
CREATE TRIGGER registration_effect_manifest_sealed_update
BEFORE UPDATE ON registration_effect_manifest
BEGIN SELECT RAISE(ABORT, 'sealed effect manifest'); END;

CREATE TRIGGER registration_effect_lease_sealed_delete
BEFORE DELETE ON registration_effect_lease
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'sealed effect lease delete'); END;
CREATE TRIGGER registration_effect_attestation_sealed_delete
BEFORE DELETE ON registration_effect_attestation
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'sealed effect attestation delete'); END;
CREATE TRIGGER registration_effect_event_sealed_delete
BEFORE DELETE ON registration_effect_event
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'sealed effect event delete'); END;
CREATE TRIGGER registration_effect_manifest_sealed_delete
BEFORE DELETE ON registration_effect_manifest
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = OLD.effect_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'sealed effect manifest delete'); END;

CREATE TRIGGER registration_reference_blocks_reserved_gc
BEFORE INSERT ON registration_effect_reference
WHEN EXISTS (
  SELECT 1 FROM registration_gc_item
   WHERE effect_id = NEW.effect_id
     AND state IN ('RESERVED', 'TRASHED', 'DELETED', 'TOMBSTONED')
)
BEGIN SELECT RAISE(ABORT, 'effect is reserved for GC'); END;

CREATE TRIGGER registration_artifact_reference_blocks_reserved_gc
BEFORE INSERT ON registration_rescue_artifact_reference
WHEN EXISTS (
  SELECT 1 FROM registration_gc_artifact_item
   WHERE artifact_id = NEW.artifact_id
     AND state IN ('RESERVED', 'TRASHED', 'DELETED', 'TOMBSTONED')
)
BEGIN SELECT RAISE(ABORT, 'artifact is reserved for GC'); END;

CREATE TRIGGER registration_gc_item_validate_reservation
BEFORE INSERT ON registration_gc_item
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_gc_run AS g
      JOIN registration_effect_retention AS r
        ON r.effect_id = NEW.effect_id
     WHERE g.gc_run_id = NEW.gc_run_id
       AND g.reservation_generation = NEW.reservation_generation
       AND r.terminal_complete = 1
       AND r.collectible_marker_hash IS NOT NULL
       AND r.collectible_generation IS NOT NULL
       AND r.collectible_generation < NEW.reservation_generation
  ) OR EXISTS (
    SELECT 1 FROM registration_effect_reference
     WHERE effect_id = NEW.effect_id
  ) OR EXISTS (
    SELECT 1
      FROM registration_effect_hold AS h
     WHERE h.effect_id = NEW.effect_id
       AND NOT EXISTS (
         SELECT 1 FROM registration_effect_hold_release AS x
          WHERE x.effect_id = h.effect_id AND x.hold_id = h.hold_id
       )
  ) OR EXISTS (
    SELECT 1 FROM registration_member_current
     WHERE effect_id = NEW.effect_id
       AND phase IN ('CLAIMED', 'EFFECT_IN_FLIGHT', 'REGISTERED')
  ) OR EXISTS (
    SELECT 1 FROM registration_rescue_target_registration
     WHERE effect_id = NEW.effect_id
  ) THEN RAISE(ABORT, 'effect has live retention or incomplete marker') END;
END;

CREATE TRIGGER registration_gc_artifact_validate_reservation
BEFORE INSERT ON registration_gc_artifact_item
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_gc_run AS g
      JOIN registration_artifact_retention AS r
        ON r.artifact_id = NEW.artifact_id
     WHERE g.gc_run_id = NEW.gc_run_id
       AND g.reservation_generation = NEW.reservation_generation
       AND r.terminal_complete = 1
       AND r.collectible_marker_hash IS NOT NULL
       AND r.collectible_generation IS NOT NULL
       AND r.collectible_generation < NEW.reservation_generation
  ) OR EXISTS (
    SELECT 1 FROM registration_rescue_artifact_reference
     WHERE artifact_id = NEW.artifact_id
  ) OR EXISTS (
    SELECT 1
      FROM registration_artifact_hold AS h
     WHERE h.artifact_id = NEW.artifact_id
       AND NOT EXISTS (
         SELECT 1 FROM registration_artifact_hold_release AS x
          WHERE x.artifact_id = h.artifact_id AND x.hold_id = h.hold_id
       )
  ) OR EXISTS (
    SELECT 1
      FROM registration_rescue AS r
      JOIN registration_rescue_artifact AS a
        ON a.rescue_id = r.rescue_id
     WHERE a.artifact_id = NEW.artifact_id
       AND r.state NOT IN ('CANCELLED', 'SUPERSEDED', 'REGISTERED',
                           'TERMINAL_CONFLICT')
  ) THEN RAISE(ABORT, 'artifact has live retention or incomplete marker') END;
END;

CREATE TRIGGER registration_member_inflight_requires_intent
BEFORE UPDATE OF phase ON registration_member_current
WHEN NEW.phase = 'EFFECT_IN_FLIGHT'
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_effect_parent AS p
     WHERE p.effect_id = NEW.effect_id
       AND p.request_key = NEW.request_key
       AND p.episode_id = NEW.episode_id
       AND p.member_id = NEW.member_id
       AND p.member_version = NEW.member_version
       AND p.admission_epoch = NEW.admission_epoch
       AND p.request_generation = NEW.request_generation
       AND p.helper_generation = NEW.helper_generation
       AND EXISTS (
         SELECT 1 FROM registration_effect_retention AS er
          WHERE er.effect_id = p.effect_id
       )
       AND EXISTS (
         SELECT 1 FROM registration_effect_hold AS eh
          WHERE eh.effect_id = p.effect_id AND eh.hold_kind = 'INTENT'
            AND NOT EXISTS (
              SELECT 1 FROM registration_effect_hold_release AS ex
               WHERE ex.effect_id = eh.effect_id AND ex.hold_id = eh.hold_id
            )
       )
  ) THEN RAISE(ABORT, 'in-flight transition lacks exact intent') END;
END;

CREATE TRIGGER registration_member_registered_requires_completion
BEFORE UPDATE OF phase ON registration_member_current
WHEN NEW.phase = 'REGISTERED'
BEGIN
  SELECT CASE WHEN NEW.certificate IS NULL OR NOT EXISTS (
    SELECT 1
      FROM registration_effect_completion AS c
      JOIN registration_effect_stage AS s USING (effect_id)
      JOIN registration_effect_certificate AS cert USING (effect_id)
     WHERE c.effect_id = NEW.effect_id
       AND s.resolution = 'COMMITTED'
       AND s.stage = 'ACTIVE_PUBLISHED'
       AND cert.certificate = NEW.certificate
       AND EXISTS (
         SELECT 1 FROM registration_effect_reference AS r
          WHERE r.effect_id = NEW.effect_id
            AND r.reference_kind = 'EPISODE'
       )
       AND EXISTS (
         SELECT 1 FROM registration_effect_reference AS r
          WHERE r.effect_id = NEW.effect_id
            AND r.reference_kind = 'ACTIVE_POINTER'
       )
  ) THEN RAISE(ABORT, 'registered transition lacks committed proof') END;
END;

CREATE TRIGGER registration_member_phase_transition
BEFORE UPDATE ON registration_member_current
BEGIN
  SELECT CASE
    WHEN NEW.state_version <> OLD.state_version + 1
      THEN RAISE(ABORT, 'member state version must advance once')
    WHEN NEW.helper_generation < OLD.helper_generation
      THEN RAISE(ABORT, 'helper generation cannot regress')
    WHEN OLD.phase IN ('TERMINAL', 'SUPERSEDED')
      THEN RAISE(ABORT, 'terminal member state is immutable')
    WHEN NOT (
      (OLD.phase = 'REQUESTED'
       AND NEW.phase IN ('REQUESTED','WAITING','CLAIMED','TERMINAL','SUPERSEDED'))
      OR
      (OLD.phase = 'WAITING'
       AND NEW.phase IN ('WAITING','CLAIMED','TERMINAL','SUPERSEDED'))
      OR
      (OLD.phase = 'CLAIMED'
       AND NEW.phase IN ('WAITING','EFFECT_IN_FLIGHT','TERMINAL','SUPERSEDED'))
      OR
      (OLD.phase = 'EFFECT_IN_FLIGHT'
       AND NEW.phase IN
         ('EFFECT_IN_FLIGHT','REGISTERED','TERMINAL','REQUESTED'))
      OR
      (OLD.phase = 'REGISTERED'
       AND NEW.phase IN ('REGISTERED','SUPERSEDED'))
    ) THEN RAISE(ABORT, 'illegal member phase transition')
  END;
END;

CREATE TRIGGER registration_member_terminal_fence
BEFORE UPDATE ON registration_member_current
WHEN OLD.phase = 'EFFECT_IN_FLIGHT'
 AND NEW.phase IN ('REGISTERED', 'TERMINAL', 'REQUESTED')
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_member_result_archive AS a
     WHERE a.result_id = NEW.terminal_result_id
       AND a.episode_id = OLD.episode_id
       AND a.member_id = OLD.member_id
       AND a.state_version = OLD.state_version
       AND a.member_version = OLD.member_version
       AND a.admission_epoch = OLD.admission_epoch
       AND a.request_generation = OLD.request_generation
       AND a.helper_generation = OLD.helper_generation + 1
       AND a.request_key = OLD.request_key
       AND a.effect_id = OLD.effect_id
       AND a.supersede_pending = OLD.supersede_pending
       AND a.pending_member_version IS OLD.pending_member_version
       AND a.pending_admission_epoch IS OLD.pending_admission_epoch
       AND a.pending_request_generation IS OLD.pending_request_generation
       AND a.pending_basis_hash IS OLD.pending_basis_hash
       AND a.pending_request_key IS OLD.pending_request_key
       AND a.pending_effect_id IS OLD.pending_effect_id
       AND (
         (a.terminal_phase = 'REGISTERED'
          AND a.certificate IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM registration_effect_certificate AS ec
             WHERE ec.effect_id = OLD.effect_id
               AND ec.certificate = a.certificate
          ))
         OR
         (a.terminal_phase = 'TERMINAL' AND a.certificate IS NULL)
       )
       AND (
         (OLD.supersede_pending = 0
          AND NEW.phase IN ('REGISTERED', 'TERMINAL')
          AND a.terminal_phase = NEW.phase
          AND NEW.request_key = OLD.request_key
          AND NEW.effect_id = OLD.effect_id
          AND NEW.member_version = OLD.member_version
          AND NEW.admission_epoch = OLD.admission_epoch
          AND NEW.request_generation = OLD.request_generation
          AND NEW.helper_generation = OLD.helper_generation + 1
          AND NEW.certificate IS a.certificate)
         OR
         (OLD.supersede_pending = 1
          AND NEW.phase = 'REQUESTED'
          AND NEW.request_key = OLD.pending_request_key
          AND NEW.effect_id = OLD.pending_effect_id
          AND NEW.member_version = OLD.pending_member_version
          AND NEW.admission_epoch = OLD.pending_admission_epoch
          AND NEW.request_generation = OLD.pending_request_generation
          AND NEW.supersede_pending = 0
          AND NEW.certificate IS NULL
          AND NEW.helper_generation = 1
          AND EXISTS (
            SELECT 1
              FROM registration_canonical_member_version AS mv
             WHERE mv.member_id = OLD.member_id
               AND mv.member_version = OLD.pending_member_version
               AND mv.admission_epoch = OLD.pending_admission_epoch
               AND mv.basis_hash = OLD.pending_basis_hash
          ))
       )
  ) THEN RAISE(ABORT, 'terminal/help fence mismatch') END;
END;

CREATE TRIGGER registration_member_preintent_archive_fence
BEFORE UPDATE ON registration_member_current
WHEN OLD.phase <> 'EFFECT_IN_FLIGHT'
 AND NEW.phase IN ('TERMINAL', 'SUPERSEDED')
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_member_result_archive AS a
     WHERE a.result_id = NEW.terminal_result_id
       AND a.episode_id = OLD.episode_id
       AND a.member_id = OLD.member_id
       AND a.terminal_phase = NEW.phase
       AND a.state_version = OLD.state_version
       AND a.member_version = OLD.member_version
       AND a.admission_epoch = OLD.admission_epoch
       AND a.request_generation = OLD.request_generation
       AND a.helper_generation = NEW.helper_generation
       AND a.request_key = OLD.request_key
       AND a.effect_id = OLD.effect_id
       AND a.certificate IS OLD.certificate
       AND a.supersede_pending = OLD.supersede_pending
       AND a.pending_member_version IS OLD.pending_member_version
       AND a.pending_admission_epoch IS OLD.pending_admission_epoch
       AND a.pending_request_generation IS OLD.pending_request_generation
       AND a.pending_basis_hash IS OLD.pending_basis_hash
       AND a.pending_request_key IS OLD.pending_request_key
       AND a.pending_effect_id IS OLD.pending_effect_id
  ) THEN RAISE(ABORT, 'pre-intent terminal archive mismatch') END;
END;

CREATE TRIGGER registration_effect_stage_transition
BEFORE UPDATE ON registration_effect_stage
BEGIN
  SELECT CASE
    WHEN OLD.stage = 'TERMINAL'
      THEN RAISE(ABORT, 'terminal effect stage is immutable')
    WHEN NEW.resolution_version <> OLD.resolution_version + 1
      THEN RAISE(ABORT, 'effect resolution version must advance once')
    WHEN NOT (
      (OLD.stage = NEW.stage
       AND NEW.resolution IN ('ABSENT','UNAVAILABLE','CONFLICT'))
      OR (OLD.stage = 'INTENT_DURABLE' AND NEW.stage = 'LEASE_DURABLE')
      OR (OLD.stage = 'LEASE_DURABLE' AND NEW.stage = 'GRAPH_COMMITTED')
      OR (OLD.stage = 'GRAPH_COMMITTED' AND NEW.stage = 'CERTIFIED')
      OR (OLD.stage = 'CERTIFIED' AND NEW.stage = 'REFERENCED')
      OR (OLD.stage = 'REFERENCED' AND NEW.stage = 'ACTIVE_PUBLISHED')
      OR (OLD.stage = 'ACTIVE_PUBLISHED' AND NEW.stage = 'REGISTERED')
      OR (NEW.stage = 'TERMINAL' AND NEW.resolution = 'CONFLICT')
    ) THEN RAISE(ABORT, 'illegal effect stage transition')
  END;
END;

CREATE TRIGGER registration_effect_action_transition
BEFORE UPDATE ON registration_effect_action
BEGIN
  SELECT CASE WHEN NOT (
    (OLD.state = 'PENDING' AND NEW.state IN ('APPLYING','VERIFIED','CONFLICT'))
    OR (OLD.state = 'APPLYING' AND NEW.state IN ('VERIFIED','CONFLICT'))
    OR (OLD.state = NEW.state AND NEW.state IN ('VERIFIED','CONFLICT'))
  ) OR NEW.effect_id <> OLD.effect_id
    OR NEW.action_ordinal <> OLD.action_ordinal
    OR NEW.action_class <> OLD.action_class
    OR NEW.action_key <> OLD.action_key
    OR NEW.postcondition_hash <> OLD.postcondition_hash
    OR NEW.acknowledgement_generation < OLD.acknowledgement_generation
  THEN RAISE(ABORT, 'effect action/postcondition transition invalid') END;
END;

CREATE TRIGGER registration_notice_transition
BEFORE UPDATE ON registration_notice
BEGIN
  SELECT CASE
    WHEN NEW.episode_id <> OLD.episode_id OR NEW.notice_epoch <> OLD.notice_epoch
      OR NEW.notice_cause <> OLD.notice_cause OR NEW.cause_hash <> OLD.cause_hash
      OR NEW.created_wall_ns <> OLD.created_wall_ns
      THEN RAISE(ABORT, 'notice identity is immutable')
    WHEN NEW.notice_version <> OLD.notice_version + 1
      THEN RAISE(ABORT, 'notice version must advance once')
    WHEN NOT (
      (OLD.progression = 'FULL'
       AND NEW.progression = 'COMPACT1' AND NEW.repeat_count = 1)
      OR (OLD.progression = 'COMPACT1'
       AND NEW.progression = 'COMPACT2' AND NEW.repeat_count = 2)
      OR (OLD.progression = 'COMPACT2'
       AND NEW.progression = 'QUIESCENT' AND NEW.repeat_count = 3)
      OR (OLD.progression = 'QUIESCENT'
       AND NEW.progression = 'QUIESCENT' AND NEW.repeat_count = 3
       AND OLD.stop_followup_consumed = 0
       AND NEW.stop_followup_consumed = 1)
    ) THEN RAISE(ABORT, 'notice repeat progression invalid')
  END;
END;

CREATE TRIGGER registration_alert_component_transition
BEFORE UPDATE ON registration_alert_component_current
BEGIN
  SELECT CASE WHEN NEW.transition_generation <> OLD.transition_generation + 1
    OR (NEW.cause_fingerprint = OLD.cause_fingerprint
        AND NEW.status = OLD.status)
    OR NOT EXISTS (
      SELECT 1 FROM registration_alert_transition AS t
       WHERE t.component = NEW.component
         AND t.transition_generation = NEW.transition_generation
         AND t.cause_fingerprint = NEW.cause_fingerprint
         AND t.status = NEW.status
         AND t.notice_episode_id IS NEW.notice_episode_id
         AND t.notice_epoch IS NEW.notice_epoch
    )
  THEN RAISE(ABORT, 'alert transition identity invalid') END;
END;

CREATE TRIGGER registration_rescue_transition_validate
BEFORE UPDATE OF state ON registration_rescue
BEGIN
  SELECT CASE
    WHEN NEW.state_version <> OLD.state_version + 1
      THEN RAISE(ABORT, 'rescue state version must advance once')
    WHEN OLD.state IN ('REGISTERED','CANCELLED','SUPERSEDED','TERMINAL_CONFLICT')
      THEN RAISE(ABORT, 'terminal rescue state is immutable')
    WHEN NOT (
      (OLD.state = 'PLANNED'
       AND NEW.state IN ('AUTHORIZED','AWAITING_OPERATOR','CANCELLED',
                         'SUPERSEDED','TERMINAL_CONFLICT'))
      OR (OLD.state = 'AUTHORIZED'
       AND NEW.state IN ('PRESERVING','AWAITING_OPERATOR','CANCELLED',
                         'SUPERSEDED','TERMINAL_CONFLICT'))
      OR (OLD.state = 'PRESERVING'
       AND NEW.state IN ('PRESERVED','PRESERVED_ONLY','TERMINAL_CONFLICT'))
      OR (OLD.state = 'PRESERVED'
       AND NEW.state IN ('TARGET_PROVISIONING','PRESERVED_ONLY',
                         'AWAITING_OPERATOR','TERMINAL_CONFLICT'))
      OR (OLD.state = 'TARGET_PROVISIONING'
       AND NEW.state IN ('AWAITING_TARGET_ENTRY','PRESERVED_ONLY',
                         'TERMINAL_CONFLICT'))
      OR (OLD.state = 'AWAITING_TARGET_ENTRY'
       AND NEW.state IN ('TARGET_LIFECYCLE_COMMITTED','PRESERVED_ONLY',
                         'AWAITING_OPERATOR','TERMINAL_CONFLICT'))
      OR (OLD.state = 'TARGET_LIFECYCLE_COMMITTED'
       AND NEW.state IN ('RESTORING','AWAITING_OPERATOR','TERMINAL_CONFLICT'))
      OR (OLD.state = 'RESTORING'
       AND NEW.state IN ('REGISTERED','AWAITING_OPERATOR','TERMINAL_CONFLICT'))
      OR (OLD.state = 'PRESERVED_ONLY'
       AND NEW.state IN ('TARGET_PROVISIONING','AWAITING_OPERATOR',
                         'TERMINAL_CONFLICT'))
      OR (OLD.state = 'AWAITING_OPERATOR'
       AND NEW.state IN ('AUTHORIZED','TARGET_PROVISIONING',
                         'AWAITING_TARGET_ENTRY','RESTORING','CANCELLED',
                         'TERMINAL_CONFLICT'))
    ) THEN RAISE(ABORT, 'illegal rescue transition')
  END;

  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM registration_rescue_transition AS t
     WHERE t.rescue_id = NEW.rescue_id
       AND t.state_version = NEW.state_version
       AND t.from_state = OLD.state
       AND t.to_state = NEW.state
       AND t.last_write_id = NEW.last_write_id
  ) THEN RAISE(ABORT, 'rescue transition proof missing') END;

  SELECT CASE WHEN NEW.state IN
    ('AUTHORIZED','PRESERVING','PRESERVED','TARGET_PROVISIONING',
     'AWAITING_TARGET_ENTRY','TARGET_LIFECYCLE_COMMITTED','RESTORING',
     'REGISTERED','PRESERVED_ONLY')
    AND NOT EXISTS (
      SELECT 1
        FROM registration_rescue_plan AS p
        JOIN registration_rescue_authorization AS a
          ON a.plan_id = p.plan_id AND a.rescue_id = p.rescue_id
        JOIN registration_rescue_authorization_use AS u
          ON u.authorization_id = a.authorization_id
         AND u.rescue_id = a.rescue_id
       WHERE p.rescue_id = NEW.rescue_id
         AND p.source_incarnation_hash = NEW.source_incarnation_hash
         AND a.source_incarnation_hash = NEW.source_incarnation_hash
         AND a.plan_digest = p.plan_digest
         AND a.conversation_hash = p.conversation_hash
         AND a.generation_hash = p.generation_hash
         AND a.event_nonce_hash = p.event_nonce_hash
         AND a.attachment_count = 0
         AND (
           (NEW.state = 'AUTHORIZED'
            AND u.consumed_state_version = NEW.state_version)
           OR
           (NEW.state <> 'AUTHORIZED'
            AND u.consumed_state_version < NEW.state_version)
         )
         AND (SELECT COUNT(*) FROM registration_rescue_plan_item AS i
               WHERE i.plan_id = p.plan_id) = p.item_count
         AND (SELECT COUNT(*) FROM registration_rescue_plan_item AS i
               WHERE i.plan_id = p.plan_id AND i.secret_bearing = 1)
             = p.secret_item_count
         AND (p.secret_item_count = 0 OR a.secret_scope = 'INCLUDE')
    ) THEN RAISE(ABORT, 'rescue authorization closure missing') END;

  SELECT CASE WHEN NEW.state IN
    ('PRESERVED','TARGET_PROVISIONING','AWAITING_TARGET_ENTRY',
     'TARGET_LIFECYCLE_COMMITTED','RESTORING','REGISTERED','PRESERVED_ONLY')
    AND NOT EXISTS (
      SELECT 1 FROM registration_rescue_artifact
       WHERE rescue_id = NEW.rescue_id AND complete = 1
    ) THEN RAISE(ABORT, 'rescue artifact proof missing') END;

  SELECT CASE WHEN NEW.state IN
    ('TARGET_PROVISIONING','AWAITING_TARGET_ENTRY',
     'TARGET_LIFECYCLE_COMMITTED','RESTORING','REGISTERED')
    AND NOT EXISTS (
      SELECT 1 FROM registration_rescue_target_reservation
       WHERE rescue_id = NEW.rescue_id
         AND source_member_id = NEW.source_member_id
         AND source_member_id <> target_member_id
         AND handoff_id = NEW.handoff_id
    ) THEN RAISE(ABORT, 'rescue target reservation missing') END;

  SELECT CASE WHEN NEW.state IN
    ('TARGET_LIFECYCLE_COMMITTED','RESTORING','REGISTERED')
    AND NOT EXISTS (
      SELECT 1 FROM registration_rescue_target_registration
       WHERE rescue_id = NEW.rescue_id
    ) THEN RAISE(ABORT, 'target registration proof missing') END;

  SELECT CASE WHEN NEW.state = 'REGISTERED' AND NOT EXISTS (
    SELECT 1
      FROM registration_rescue_artifact AS a
      JOIN registration_rescue_target_reservation AS tr
        ON tr.rescue_id = a.rescue_id
      JOIN registration_rescue_target_registration AS rg
        ON rg.rescue_id = tr.rescue_id
       AND rg.target_member_id = tr.target_member_id
       AND rg.target_member_version = tr.target_member_version
       AND rg.target_admission_epoch = tr.target_admission_epoch
      JOIN registration_member_current AS mc
        ON mc.episode_id = rg.target_episode_id
       AND mc.member_id = rg.target_member_id
       AND mc.member_version = rg.target_member_version
       AND mc.admission_epoch = rg.target_admission_epoch
       AND mc.request_generation = rg.request_generation
       AND mc.request_key = rg.request_key
       AND mc.effect_id = rg.effect_id
       AND mc.certificate = rg.certificate
       AND mc.phase = 'REGISTERED'
      JOIN registration_rescue_restore_proof AS rp
        ON rp.rescue_id = rg.rescue_id
       AND rp.artifact_id = a.artifact_id
       AND rp.verified = 1
      JOIN registration_rescue_completion AS rc
        ON rc.rescue_id = rp.rescue_id
     WHERE a.rescue_id = NEW.rescue_id
       AND a.complete = 1
       AND tr.source_member_id = NEW.source_member_id
       AND tr.source_member_id <> tr.target_member_id
  ) THEN RAISE(ABORT, 'registered rescue lacks complete restore proof') END;
END;

CREATE TRIGGER registration_rescue_action_transition
BEFORE UPDATE ON registration_rescue_action
BEGIN
  SELECT CASE WHEN NOT (
    (OLD.state = 'PENDING' AND NEW.state IN ('APPLYING','VERIFIED','CONFLICT'))
    OR (OLD.state = 'APPLYING' AND NEW.state IN ('VERIFIED','CONFLICT'))
    OR (OLD.state = NEW.state AND NEW.state IN ('VERIFIED','CONFLICT'))
  ) OR NEW.rescue_id <> OLD.rescue_id
    OR NEW.action_ordinal <> OLD.action_ordinal
    OR NEW.action_class <> OLD.action_class
    OR NEW.action_key <> OLD.action_key
    OR NEW.postcondition_hash <> OLD.postcondition_hash
    OR NEW.acknowledgement_generation < OLD.acknowledgement_generation
  THEN RAISE(ABORT, 'rescue action/postcondition transition invalid') END;
END;

CREATE TRIGGER registration_gc_tombstone_validate
BEFORE INSERT ON registration_gc_tombstone
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM registration_gc_item AS i
     WHERE i.gc_run_id = NEW.gc_run_id
       AND i.effect_id = NEW.effect_id
       AND i.state = 'DELETED'
       AND NEW.retention_barrier_generation > i.reservation_generation
  ) THEN RAISE(ABORT, 'effect tombstone lacks delete and barrier') END;
END;

CREATE TRIGGER registration_gc_artifact_tombstone_validate
BEFORE INSERT ON registration_gc_artifact_tombstone
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM registration_gc_artifact_item AS i
     WHERE i.gc_run_id = NEW.gc_run_id
       AND i.artifact_id = NEW.artifact_id
       AND i.state = 'DELETED'
       AND NEW.retention_barrier_generation > i.reservation_generation
  ) THEN RAISE(ABORT, 'artifact tombstone lacks delete and barrier') END;
END;

CREATE TRIGGER registration_gc_action_transition
BEFORE UPDATE ON registration_gc_action
BEGIN
  SELECT CASE WHEN NOT (
    (OLD.state = 'PENDING' AND NEW.state IN ('APPLYING','VERIFIED','CONFLICT'))
    OR (OLD.state = 'APPLYING' AND NEW.state IN ('VERIFIED','CONFLICT'))
    OR (OLD.state = NEW.state AND NEW.state IN ('VERIFIED','CONFLICT'))
  ) OR NEW.postcondition_hash <> OLD.postcondition_hash
    OR NEW.acknowledgement_generation < OLD.acknowledgement_generation
  THEN RAISE(ABORT, 'GC action/postcondition transition invalid') END;
END;

CREATE TRIGGER registration_root_event_evidence_transition
BEFORE UPDATE ON registration_root_event_evidence
BEGIN
  SELECT CASE WHEN NEW.event_evidence_id <> OLD.event_evidence_id
    OR NEW.conversation_hash <> OLD.conversation_hash
    OR NEW.boot_id <> OLD.boot_id
    OR NEW.generation_hash <> OLD.generation_hash
    OR NEW.root_set_incarnation <> OLD.root_set_incarnation
    OR NEW.root_set_hash <> OLD.root_set_hash
    OR NEW.descriptor_set_hash <> OLD.descriptor_set_hash
    OR NEW.evidence_json <> OLD.evidence_json
    OR NEW.created_wall_ns <> OLD.created_wall_ns
    OR NOT (
      (OLD.state = 'CAPTURED' AND NEW.state = 'SEEDED')
      OR (OLD.state = 'SEEDED' AND NEW.state = 'RESOLVED')
    )
  THEN RAISE(ABORT, 'root event evidence transition invalid') END;
END;

CREATE TRIGGER registration_due_cursor_transition
BEFORE UPDATE ON registration_due_cursor
BEGIN
  SELECT CASE
    WHEN NEW.scan_generation <> OLD.scan_generation + 1
      THEN RAISE(ABORT, 'due cursor generation must advance once')
    WHEN NEW.cursor_boot <> OLD.cursor_boot
      AND NOT (NEW.last_due_mono_ns IS NULL
               AND NEW.last_request_created_wall_ns IS NULL
               AND NEW.last_member_id IS NULL
               AND NEW.last_request_key IS NULL
               AND NEW.oldest_wait_ns = '0')
      THEN RAISE(ABORT, 'reboot must reset due cursor')
  END;
END;

CREATE TRIGGER registration_effect_stage_predicate
BEFORE UPDATE ON registration_effect_stage
BEGIN
  SELECT CASE
    WHEN NEW.stage = 'GRAPH_COMMITTED' AND NOT EXISTS (
      SELECT 1 FROM registration_effect_completion
       WHERE effect_id = NEW.effect_id
    ) THEN RAISE(ABORT, 'graph stage lacks completion')
    WHEN NEW.stage = 'CERTIFIED' AND NOT EXISTS (
      SELECT 1 FROM registration_effect_certificate
       WHERE effect_id = NEW.effect_id
    ) THEN RAISE(ABORT, 'certified stage lacks certificate')
    WHEN NEW.stage = 'REFERENCED' AND NOT EXISTS (
      SELECT 1 FROM registration_effect_reference
       WHERE effect_id = NEW.effect_id AND reference_kind = 'EPISODE'
    ) THEN RAISE(ABORT, 'referenced stage lacks episode reference')
    WHEN NEW.stage = 'ACTIVE_PUBLISHED' AND NOT EXISTS (
      SELECT 1 FROM registration_effect_reference
       WHERE effect_id = NEW.effect_id AND reference_kind = 'ACTIVE_POINTER'
    ) THEN RAISE(ABORT, 'active stage lacks pointer reference')
  END;
END;

CREATE TRIGGER registration_gc_run_transition
BEFORE UPDATE ON registration_gc_run
BEGIN
  SELECT CASE WHEN NOT (
    (OLD.state = 'RESERVED' AND NEW.state IN ('TRASHING','TERMINAL'))
    OR (OLD.state = 'TRASHING' AND NEW.state IN ('TRASHED','TERMINAL'))
    OR (OLD.state = 'TRASHED' AND NEW.state IN ('DELETING','TERMINAL'))
    OR (OLD.state = 'DELETING' AND NEW.state IN ('COMPLETE','TERMINAL'))
  ) THEN RAISE(ABORT, 'illegal GC run transition') END;
END;

CREATE TRIGGER registration_gc_item_transition
BEFORE UPDATE ON registration_gc_item
BEGIN
  SELECT CASE WHEN NOT (
    (OLD.state = 'RESERVED' AND NEW.state IN ('TRASHED','RETAINED','TERMINAL'))
    OR (OLD.state = 'TRASHED' AND NEW.state IN ('DELETING','RETAINED','TERMINAL'))
    OR (OLD.state = 'DELETING' AND NEW.state IN ('DELETED','TERMINAL'))
    OR (OLD.state = 'DELETED' AND NEW.state IN ('TOMBSTONED','TERMINAL'))
  ) THEN RAISE(ABORT, 'illegal GC effect transition') END;
END;

CREATE TRIGGER registration_gc_artifact_item_transition
BEFORE UPDATE ON registration_gc_artifact_item
BEGIN
  SELECT CASE WHEN NOT (
    (OLD.state = 'RESERVED' AND NEW.state IN ('TRASHED','RETAINED','TERMINAL'))
    OR (OLD.state = 'TRASHED' AND NEW.state IN ('DELETING','RETAINED','TERMINAL'))
    OR (OLD.state = 'DELETING' AND NEW.state IN ('DELETED','TERMINAL'))
    OR (OLD.state = 'DELETED' AND NEW.state IN ('TOMBSTONED','TERMINAL'))
  ) THEN RAISE(ABORT, 'illegal GC artifact transition') END;
END;

CREATE TRIGGER registration_effect_retention_transition
BEFORE UPDATE ON registration_effect_retention
BEGIN
  SELECT CASE WHEN NEW.effect_id <> OLD.effect_id
    OR NEW.intent_generation <> OLD.intent_generation
    OR OLD.terminal_complete = 1
    OR NEW.terminal_complete <> 1
  THEN RAISE(ABORT, 'effect retention marker transition invalid') END;
END;

CREATE TRIGGER registration_artifact_retention_transition
BEFORE UPDATE ON registration_artifact_retention
BEGIN
  SELECT CASE WHEN NEW.artifact_id <> OLD.artifact_id
    OR NEW.intent_generation <> OLD.intent_generation
    OR OLD.terminal_complete = 1
    OR NEW.terminal_complete <> 1
  THEN RAISE(ABORT, 'artifact retention marker transition invalid') END;
END;

CREATE TRIGGER registration_member_result_archive_immutable_update
BEFORE UPDATE ON registration_member_result_archive
BEGIN SELECT RAISE(ABORT, 'member result archive is immutable'); END;
CREATE TRIGGER registration_member_result_archive_immutable_delete
BEFORE DELETE ON registration_member_result_archive
BEGIN SELECT RAISE(ABORT, 'member result archive is retained'); END;
CREATE TRIGGER registration_alert_transition_immutable_update
BEFORE UPDATE ON registration_alert_transition
BEGIN SELECT RAISE(ABORT, 'alert transition is immutable'); END;
CREATE TRIGGER registration_alert_transition_immutable_delete
BEFORE DELETE ON registration_alert_transition
BEGIN SELECT RAISE(ABORT, 'alert transition is retained'); END;
CREATE TRIGGER registration_gc_tombstone_immutable_update
BEFORE UPDATE ON registration_gc_tombstone
BEGIN SELECT RAISE(ABORT, 'GC tombstone is immutable'); END;
CREATE TRIGGER registration_gc_tombstone_immutable_delete
BEFORE DELETE ON registration_gc_tombstone
BEGIN SELECT RAISE(ABORT, 'GC tombstone is retained'); END;
CREATE TRIGGER registration_gc_artifact_tombstone_immutable_update
BEFORE UPDATE ON registration_gc_artifact_tombstone
BEGIN SELECT RAISE(ABORT, 'GC artifact tombstone is immutable'); END;
CREATE TRIGGER registration_gc_artifact_tombstone_immutable_delete
BEFORE DELETE ON registration_gc_artifact_tombstone
BEGIN SELECT RAISE(ABORT, 'GC artifact tombstone is retained'); END;

CREATE TRIGGER registration_rescue_plan_immutable_update
BEFORE UPDATE ON registration_rescue_plan
BEGIN SELECT RAISE(ABORT, 'rescue plan is immutable'); END;
CREATE TRIGGER registration_rescue_plan_immutable_delete
BEFORE DELETE ON registration_rescue_plan
BEGIN SELECT RAISE(ABORT, 'rescue plan is retained'); END;
CREATE TRIGGER registration_rescue_plan_item_immutable_update
BEFORE UPDATE ON registration_rescue_plan_item
BEGIN SELECT RAISE(ABORT, 'rescue plan item is immutable'); END;
CREATE TRIGGER registration_rescue_plan_item_immutable_delete
BEFORE DELETE ON registration_rescue_plan_item
BEGIN SELECT RAISE(ABORT, 'rescue plan item is retained'); END;
CREATE TRIGGER registration_rescue_authorization_immutable_update
BEFORE UPDATE ON registration_rescue_authorization
BEGIN SELECT RAISE(ABORT, 'rescue authorization is immutable'); END;
CREATE TRIGGER registration_rescue_authorization_immutable_delete
BEFORE DELETE ON registration_rescue_authorization
BEGIN SELECT RAISE(ABORT, 'rescue authorization is retained'); END;
CREATE TRIGGER registration_rescue_authorization_use_immutable_update
BEFORE UPDATE ON registration_rescue_authorization_use
BEGIN SELECT RAISE(ABORT, 'rescue authorization use is immutable'); END;
CREATE TRIGGER registration_rescue_authorization_use_immutable_delete
BEFORE DELETE ON registration_rescue_authorization_use
BEGIN SELECT RAISE(ABORT, 'rescue authorization use is retained'); END;
CREATE TRIGGER registration_rescue_artifact_immutable_update
BEFORE UPDATE ON registration_rescue_artifact
BEGIN SELECT RAISE(ABORT, 'rescue artifact proof is immutable'); END;
CREATE TRIGGER registration_rescue_artifact_immutable_delete
BEFORE DELETE ON registration_rescue_artifact
WHEN NOT EXISTS (
  SELECT 1 FROM registration_gc_artifact_item
   WHERE artifact_id = OLD.artifact_id AND state = 'DELETING'
)
BEGIN SELECT RAISE(ABORT, 'rescue artifact delete requires GC'); END;
CREATE TRIGGER registration_rescue_target_reservation_immutable_update
BEFORE UPDATE ON registration_rescue_target_reservation
BEGIN SELECT RAISE(ABORT, 'target reservation is immutable'); END;
CREATE TRIGGER registration_rescue_target_reservation_immutable_delete
BEFORE DELETE ON registration_rescue_target_reservation
BEGIN SELECT RAISE(ABORT, 'target reservation is retained'); END;
CREATE TRIGGER registration_rescue_target_registration_immutable_update
BEFORE UPDATE ON registration_rescue_target_registration
BEGIN SELECT RAISE(ABORT, 'target registration proof is immutable'); END;
CREATE TRIGGER registration_rescue_target_registration_immutable_delete
BEFORE DELETE ON registration_rescue_target_registration
BEGIN SELECT RAISE(ABORT, 'target registration proof is retained'); END;
CREATE TRIGGER registration_rescue_restore_proof_immutable_update
BEFORE UPDATE ON registration_rescue_restore_proof
BEGIN SELECT RAISE(ABORT, 'restore proof is immutable'); END;
CREATE TRIGGER registration_rescue_restore_proof_immutable_delete
BEFORE DELETE ON registration_rescue_restore_proof
BEGIN SELECT RAISE(ABORT, 'restore proof is retained'); END;
CREATE TRIGGER registration_rescue_completion_immutable_update
BEFORE UPDATE ON registration_rescue_completion
BEGIN SELECT RAISE(ABORT, 'rescue completion is immutable'); END;
CREATE TRIGGER registration_rescue_completion_immutable_delete
BEFORE DELETE ON registration_rescue_completion
BEGIN SELECT RAISE(ABORT, 'rescue completion is retained'); END;

CREATE TRIGGER registration_canonical_member_immutable_update
BEFORE UPDATE ON registration_canonical_member
BEGIN SELECT RAISE(ABORT, 'canonical member is immutable'); END;
CREATE TRIGGER registration_canonical_member_immutable_delete
BEFORE DELETE ON registration_canonical_member
BEGIN SELECT RAISE(ABORT, 'canonical member is retained'); END;
CREATE TRIGGER registration_member_version_immutable_update
BEFORE UPDATE ON registration_canonical_member_version
BEGIN SELECT RAISE(ABORT, 'member version is immutable'); END;
CREATE TRIGGER registration_member_version_immutable_delete
BEFORE DELETE ON registration_canonical_member_version
BEGIN SELECT RAISE(ABORT, 'member version is retained'); END;
CREATE TRIGGER registration_episode_immutable_update
BEFORE UPDATE ON registration_episode
BEGIN SELECT RAISE(ABORT, 'episode is immutable'); END;
CREATE TRIGGER registration_episode_immutable_delete
BEFORE DELETE ON registration_episode
BEGIN SELECT RAISE(ABORT, 'episode is retained'); END;
CREATE TRIGGER registration_episode_member_immutable_update
BEFORE UPDATE ON registration_episode_member
BEGIN SELECT RAISE(ABORT, 'episode membership is immutable'); END;
CREATE TRIGGER registration_episode_member_immutable_delete
BEFORE DELETE ON registration_episode_member
BEGIN SELECT RAISE(ABORT, 'episode membership is retained'); END;
CREATE TRIGGER registration_request_immutable_update
BEFORE UPDATE ON registration_request
BEGIN SELECT RAISE(ABORT, 'request is immutable'); END;
CREATE TRIGGER registration_request_immutable_delete
BEFORE DELETE ON registration_request
BEGIN SELECT RAISE(ABORT, 'request is retained'); END;

CREATE TRIGGER registration_member_current_write_scope
BEFORE UPDATE ON registration_member_current
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_write_receipt AS w ON w.write_id = c.last_write_id
     WHERE c.singleton = 1
       AND NEW.last_write_id = w.write_id
       AND w.target_table = 'registration_member_current'
       AND w.mutation_kind = 'UPDATE'
       AND w.target_key = NEW.episode_id || ':' || NEW.member_id
       AND w.transition_name = OLD.phase || '_TO_' || NEW.phase
  ) THEN RAISE(ABORT, 'member current write is unscoped') END;
END;
CREATE TRIGGER registration_member_current_consume
AFTER UPDATE ON registration_member_current
BEGIN
  INSERT INTO registration_mutation_use
    (write_id, target_table, transition_name, mutation_kind,
     target_key, used_wall_ns)
  SELECT write_id, target_table, transition_name, mutation_kind,
         target_key, created_wall_ns
    FROM registration_write_receipt
   WHERE write_id = NEW.last_write_id;
END;

CREATE TRIGGER registration_effect_stage_write_scope
BEFORE UPDATE ON registration_effect_stage
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_write_receipt AS w ON w.write_id = c.last_write_id
     WHERE c.singleton = 1
       AND NEW.last_write_id = w.write_id
       AND w.target_table = 'registration_effect_stage'
       AND w.mutation_kind = 'UPDATE'
       AND w.target_key = NEW.effect_id
       AND w.transition_name = OLD.stage || '_TO_' || NEW.stage
  ) THEN RAISE(ABORT, 'effect stage write is unscoped') END;
END;
CREATE TRIGGER registration_effect_stage_consume
AFTER UPDATE ON registration_effect_stage
BEGIN
  INSERT INTO registration_mutation_use
    (write_id, target_table, transition_name, mutation_kind,
     target_key, used_wall_ns)
  SELECT write_id, target_table, transition_name, mutation_kind,
         target_key, created_wall_ns
    FROM registration_write_receipt
   WHERE write_id = NEW.last_write_id;
END;

CREATE TRIGGER registration_notice_write_scope
BEFORE UPDATE ON registration_notice
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_write_receipt AS w ON w.write_id = c.last_write_id
     WHERE c.singleton = 1
       AND NEW.last_write_id = w.write_id
       AND w.target_table = 'registration_notice'
       AND w.mutation_kind = 'UPDATE'
       AND w.target_key = NEW.episode_id || ':' || NEW.notice_epoch
       AND w.transition_name = OLD.progression || '_TO_' || NEW.progression
  ) THEN RAISE(ABORT, 'notice write is unscoped') END;
END;
CREATE TRIGGER registration_notice_consume
AFTER UPDATE ON registration_notice
BEGIN
  INSERT INTO registration_mutation_use
    (write_id, target_table, transition_name, mutation_kind,
     target_key, used_wall_ns)
  SELECT write_id, target_table, transition_name, mutation_kind,
         target_key, created_wall_ns
    FROM registration_write_receipt
   WHERE write_id = NEW.last_write_id;
END;

CREATE TRIGGER registration_rescue_write_scope
BEFORE UPDATE ON registration_rescue
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_write_receipt AS w ON w.write_id = c.last_write_id
     WHERE c.singleton = 1
       AND NEW.last_write_id = w.write_id
       AND w.operation_class = 'RESCUE'
       AND w.target_table = 'registration_rescue'
       AND w.mutation_kind = 'UPDATE'
       AND w.target_key = NEW.rescue_id
       AND w.transition_name = OLD.state || '_TO_' || NEW.state
  ) THEN RAISE(ABORT, 'rescue write is unscoped') END;
END;
CREATE TRIGGER registration_rescue_consume
AFTER UPDATE ON registration_rescue
BEGIN
  INSERT INTO registration_mutation_use
    (write_id, target_table, transition_name, mutation_kind,
     target_key, used_wall_ns)
  SELECT write_id, target_table, transition_name, mutation_kind,
         target_key, created_wall_ns
    FROM registration_write_receipt
   WHERE write_id = NEW.last_write_id;
END;

CREATE TRIGGER registration_gc_item_write_scope
BEFORE UPDATE ON registration_gc_item
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_write_receipt AS w ON w.write_id = c.last_write_id
     WHERE c.singleton = 1
       AND NEW.last_write_id = w.write_id
       AND w.operation_class = 'GC'
       AND w.target_table = 'registration_gc_item'
       AND w.mutation_kind = 'UPDATE'
       AND w.target_key = NEW.gc_run_id || ':' || NEW.effect_id
       AND w.transition_name = OLD.state || '_TO_' || NEW.state
  ) THEN RAISE(ABORT, 'GC effect write is unscoped') END;
END;
CREATE TRIGGER registration_gc_item_consume
AFTER UPDATE ON registration_gc_item
BEGIN
  INSERT INTO registration_mutation_use
    (write_id, target_table, transition_name, mutation_kind,
     target_key, used_wall_ns)
  SELECT write_id, target_table, transition_name, mutation_kind,
         target_key, created_wall_ns
    FROM registration_write_receipt
   WHERE write_id = NEW.last_write_id;
END;

CREATE TRIGGER registration_gc_artifact_write_scope
BEFORE UPDATE ON registration_gc_artifact_item
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
      FROM registration_protocol_current AS c
      JOIN registration_write_receipt AS w ON w.write_id = c.last_write_id
     WHERE c.singleton = 1
       AND NEW.last_write_id = w.write_id
       AND w.operation_class = 'GC'
       AND w.target_table = 'registration_gc_artifact_item'
       AND w.mutation_kind = 'UPDATE'
       AND w.target_key = NEW.gc_run_id || ':' || NEW.artifact_id
       AND w.transition_name = OLD.state || '_TO_' || NEW.state
  ) THEN RAISE(ABORT, 'GC artifact write is unscoped') END;
END;
CREATE TRIGGER registration_gc_artifact_consume
AFTER UPDATE ON registration_gc_artifact_item
BEGIN
  INSERT INTO registration_mutation_use
    (write_id, target_table, transition_name, mutation_kind,
     target_key, used_wall_ns)
  SELECT write_id, target_table, transition_name, mutation_kind,
         target_key, created_wall_ns
    FROM registration_write_receipt
   WHERE write_id = NEW.last_write_id;
END;
```

Every authority-table insert/update carries the receipt created in the same
`BEGIN IMMEDIATE` transaction. The connection-scoped SQLite authorizer denies
every table/operation/transition not present in
`registration_writer_capability`, denies direct writes to protocol and
mutation-use tables, and allows internal writes only when SQLite reports the
exact frozen trigger source. Before admitting a receipt it also verifies the
authorization's exact boot and current monotonic time is strictly before
`expires_mono_ns`; persisted wall time is never consulted. The transaction
hook refuses COMMIT unless the
one receipt has exactly one matching `registration_mutation_use`; rollback
burns no authorization. The explicit triggers above duplicate the mutable
phase/effect/notice/rescue/GC fences. Immutable relations reject updates and
deletes directly. GC deletion additionally requires operation class `GC`, an
exact `DELETING` reservation, and a table-specific one-use receipt; the
authorizer denies ad hoc SQL even from a declared writer.

The closed operation matrix is:

| Operation class | Permitted authority mutations |
|---|---|
| `NORMAL` | New episode/member/request; claim/wait/intent; effect action progression; certificate/reference/pointer/member publication |
| `RECONCILE` | Same-effect help, bounded `UNAVAILABLE` help-due, startup exact-evidence seed/resolve, notice/alert progression; no new effect after intent |
| `RESCUE` | Immutable plan/items/auth/use, rescue actions, artifact/target/restore proofs, rescue transitions and holds only |
| `GC` | Reservation, GC actions, trash/delete/tombstone, and hold release only; no episode/request/rescue retarget |
| `PROTOCOL` | Epoch/writer/capability declarations, DORMANT/WRITABLE/DRAINING mode transitions, schema bootstrap only |

Protocol epoch/writer/capability/authorization/receipt/use rows and immutable
episode, member-version, request, plan/item/proof, result-archive, and effect
parent rows are append-only. No `UPDATE` or `DELETE` is permitted by caller
convention alone.

The direct-SQL negative matrix executes every writer id x operation class x
table x transition x mutation kind, including stale epoch/binary/capability/
profile, reused/expired/wrong-target authorization, missing receipt, two
mutations per receipt, receipt-only COMMIT, trigger-source spoof, direct
terminal rewrite, rescue retarget, hold/reference insertion after GC
reservation, and non-GC delete. Every disallowed cross-product must abort and
leave `PRAGMA integrity_check`, `foreign_key_check`, write generation, and all
authority rows unchanged.

### 4.4 Episode, member, request, and phase rules

An event's exact `workspace_roots` is authoritative for that event. AWA:

1. requires absolute lexical paths without cwd fallback;
2. resolves each bounded candidate from the trusted base with the fd-anchored
   no-follow resolver before inclusion/exclusion classification;
3. retains and rechecks owner/type/device/inode descriptors;
4. classifies the resolved physical object and derives canonical
   `member_id`; lexical spelling never grants exclusion or inclusion;
5. sorts descriptors by canonical JCS bytes and rejects ambiguous aliases;
6. creates or reuses the exact root-set incarnation/hash; and
7. inserts one immutable episode and ordered membership set.

The only registration phases are:

```text
REQUESTED | WAITING | CLAIMED | EFFECT_IN_FLIGHT |
REGISTERED | TERMINAL | SUPERSEDED
```

`RESTORING` is a rescue workflow state, not an eighth registration phase.
A target may have a registration member in `REGISTERED` while aggregate
admission remains non-green because its linked rescue row is `RESTORING`.

The resolution precedence is:

1. immutable effect-graph conflict;
2. help the exact `EFFECT_IN_FLIGHT` effect;
3. record/apply invalidation and `supersede_pending`;
4. terminal pre-intent failure;
5. fresh identity or satisfied wait condition;
6. due/expiry/retry bookkeeping; and
7. notice publication.

Codes below are `K` unchanged, `C` claim, `F` intent barrier,
`W` wait, `G` registered, `T` terminal, `S` superseded/successor,
`H` help same effect, `P` record pending supersession, `N` notice-only, and
`A` absorbing.

| Event \ phase | REQUESTED | WAITING | CLAIMED | EFFECT_IN_FLIGHT | REGISTERED | TERMINAL | SUPERSEDED |
|---|---|---|---|---|---|---|---|
| due claim | C | C if exact wake due, else K | K | H | K | A | A |
| claim expiry/transient | K | K | W | H | K | A | A |
| exact intent CAS | K | K | F | H | K | A | A |
| wait condition | W | W | W if exact token | H | K | A | A |
| terminal pre-intent failure | T | T | T if exact token | H | K | A | A |
| invalidation | S | S | S | P then H | S | A + new episode | A + new episode |
| resolver `COMMITTED` | K | K | conflict unless stale audit | G | exact G or conflict | A | A |
| resolver `ABSENT` | K | K | same-effect retry only | W same effect | K | A | A |
| resolver `CONFLICT` | T | T | T | T | T | A | A |
| resolver `UNAVAILABLE` within budget | K | K | W read-only | H/read-only | K | A | A |
| resolver `UNAVAILABLE` budget exhausted | K | K | W + help due + release lock | W + help due + release lock | K | A | A |
| helper terminal, no pending successor | K | K | K | fenced G/T + archive | K | A | A |
| helper terminal, pending successor | K | K | K | archive old + consume exact pending into REQUESTED | K | A | A |
| reboot | S after fresh identity | S after fresh identity | S after fresh identity | H same effect | S after fresh identity | A | A |
| startup exact dead-event evidence | seed/resolve exact | seed/resolve exact | help exact | help exact | audit exact | A | A |
| startup without exact source evidence | K; await fresh identity | K; await fresh identity | K; await fresh identity | help only durable effect | K | A | A |
| denial/notice | N | N | N | N | N | N | N |

Closed interpretations:

- `C` is one full-tuple CAS that writes claim window, token, boot, expiry,
  `next_due`, and wake epoch together.
- `F` is one transaction that inserts immutable effect parent/intent and
  intent-time retention object/hold and changes exact
  `CLAIMED -> EFFECT_IN_FLIGHT`. It is the lifecycle-I/O authorization point.
- `P` increments canonical `member_version` and `admission_epoch` and records
  the newest exact pending successor without changing the in-flight effect.
- `H` resolves only the existing effect. CAS losers reread, inspect the frozen
  postcondition, and help/return.
- `G/T` compares effect, member version, admission epoch, helper generation,
  request, certificate, and the complete pending-successor tuple. The same
  transaction archives the old result and either leaves its terminal result
  current or consumes the exact pending successor into `REQUESTED`.
- `S` absorbs the old row and creates a separate immutable successor episode
  or membership state. It never rewrites episode identity.
- `N` changes only `registration_notice`.
- `TERMINAL` and `SUPERSEDED` are absorbing. New work uses a new request or
  episode; it never resurrects an absorbed row.

### 4.5 Exact transition pseudocode and lock graph

```text
claim_due(episode_id, member_id, observed_now, boot):
  BEGIN IMMEDIATE within outer monotonic deadline
  verify writer receipt and exact REQUESTED|WAITING row
  verify wake due, same boot, no live claim, no in-flight effect
  if sleep/discontinuity:
      coalesce every missed window into one window
      discontinuity_marker = D("sleep-discontinuity", observed facts)
      next_due = observed_now + capped_backoff
      never extend or reuse the prior deadline
  CAS full old tuple -> CLAIMED with
      claim_window, claim_token, claim_boot, claim_expiry,
      next_due, wake_epoch, discontinuity_marker
  COMMIT
  loser rereads; performs no registration-effect I/O

execute_claim(exact_claim):
  acquire exactly one member common-directory lock
  B1 = collect uncached global basis + ordered canonical vector V1
  E  = read relational episode/member/request/effect/rescue snapshot
  B2 = collect uncached global basis + ordered canonical vector V2
  if B1 != B2 or V1 != V2:
      release; move exact claim to WAITING if still owned
  BEGIN IMMEDIATE
  reread exact claim, member_version, admission_epoch, wake_epoch
  require carried B2/V2 and root-set/member vector still exact
  insert complete immutable effect parent/intent
  insert registration_effect_retention + live INTENT hold
  insert frozen registration_effect_action rows/postconditions
  CAS exact CLAIMED -> EFFECT_IN_FLIGHT in same transaction
  COMMIT
  if CAS lost:
      rollback inserted intent; reread and help/return

  # Only now is lifecycle I/O authorized.
  for each frozen action in ordinal order:
      inspect_postcondition(action) using retained descriptors
      if EXACT:
          CAS same action -> VERIFIED; do not replay
      if ABSENT:
          CAS same action -> APPLYING
          apply immutable bytes/transaction
          inspect_postcondition(action)
          require EXACT; CAS -> VERIFIED
      if PARTIAL_OR_CONFLICT:
          CAS same action -> CONFLICT
          terminalize same effect; preserve evidence
  close writer connection

  resolution = fresh_open_resolve(effect_id, bounded_attempts, mono_deadline)
  if UNAVAILABLE before budget: retry read only
  if UNAVAILABLE at budget:
      persist same-effect help_due; create no effect
      release common-directory lock
      wait for root-bearing event/startup/host retry
  if ABSENT: retain same effect; return to precommit retry
  if CONFLICT: helper terminalizes exact effect; preserve evidence
  if COMMITTED:
      record GRAPH_COMMITTED/COMMITTED in a short exact stage transaction
      reread graph + lease; create certificate
      record CERTIFIED
      add DB reference before any external durable reference
      record REFERENCED
      publish postcommit active.json
      record ACTIVE_PUBLISHED
      BEGIN IMMEDIATE
      reread exact effect/member/admission/helper/request/certificate/
          pending-successor tuple
      insert immutable member result archive
      if supersede_pending:
          CAS exact EFFECT_IN_FLIGHT -> REQUESTED for exact pending successor;
          clear pending tuple atomically
      else:
          CAS exact EFFECT_IN_FLIGHT -> REGISTERED with certificate
          record effect stage REGISTERED
      COMMIT
  release common-directory lock

invalidate(member_id, observed_basis):
  BEGIN IMMEDIATE
  append member_version+1 and admission_epoch+1
  for each current row:
      if EFFECT_IN_FLIGHT:
          set/replace supersede_pending and pending basis
      else:
          CAS old row -> SUPERSEDED and create successor
  COMMIT

publish_notice(episode_id, cause):
  BEGIN IMMEDIATE
  insert/CAS notice_epoch, version, cause, repeat_count, progression only
  COMMIT

startup_reconcile(dead_event_evidence):
  if exact durable root-bearing source evidence binds conversation, boot,
     generation, root-set and descriptors:
      seed or resolve only that episode/request/effect
  else:
      await a fresh root-bearing identity; infer nothing
```

The lock graph is fixed:

```text
short DB claim / notice / invalidation; release
-> one common-directory lock
-> B1 / E / B2
-> short DB intent barrier
-> disk lease
-> effect transaction
-> close/reopen resolver
-> certificate/reference/active pointer
-> short helper/registration transaction
-> release common-directory lock

rescue/GC order:
short protocol/read transaction; release
-> at most one common-directory or artifact lock
-> inspect frozen postcondition
-> short RESCUE or GC transaction at one retention generation
-> release filesystem lock
```

Prohibitions:

- never hold a database writer while waiting for a common-directory lock;
- never hold two common-directory locks;
- never acquire a common-directory lock from a notice, integrity, or GC lock;
- never hold a DB writer while waiting for rescue/GC filesystem locks;
- never reserve an effect/artifact while any unreleased hold/reference exists;
- never use an episode/display-file lock as authority; and
- never perform lifecycle disk/graph I/O before the exact intent CAS.

### 4.6 Immutable lease and active pointer

The effect intent contains the exact canonical bytes for:

```text
<root>/.awa/registration-v1/leases/<effect_id>.json
```

The lease object contains exactly:

```text
schema = "awa-registration-lease/v1"
encoding = "jcs-rfc8785/utf-8+lf/v1"
lease_id
effect_id
request_key
episode_id
episode_incarnation
member_id
member_version
admission_epoch
request_generation
request_created_wall_ns
fence_token
root
root_dev
root_ino
git_dir
git_common_dir
conversation_id_hash
boot_id
root_set_incarnation
root_set_hash
basis_hash
plan_hash
policy_digest
runtime_capability_digest
current_session_generation
current_session_hash
heartbeat_generation
created_wall_ns
```

All nanosecond/device/inode values use unsigned decimal strings. Bytes are
`JCS(object) || LF`; `lease_hash` hashes those exact file bytes.

Publication through the already validated directory fd is:

1. create an unpredictable same-directory temp with
   `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0600`;
2. retry `EINTR`, advance on positive short writes, and treat zero write as
   `EIO` until all bytes are written;
3. `fchmod(0600)`, `fsync`, and Darwin `F_FULLFSYNC`, then close;
4. no-follow verify that the exact final name is absent;
5. `linkat` temp to the exact final basename, so publication cannot replace;
6. reopen final no-follow and prove bytes/hash/owner/mode;
7. `fsync` plus `F_FULLFSYNC` the parent directory;
8. unlink temp and sync the directory again.

If the final already exists, it is accepted only after exact
bytes/hash/owner/mode proof. Conflicting evidence is preserved and terminal.
An interrupted temp is never authority and is collected only through bounded
temp cleanup plus directory sync.

`active.json` is a mutable JCS+LF pointer containing only the exact committed
effect id, lease id/hash, certificate, and pointer generation. It is published
after `COMMITTED`, certificate, and database reference. No pre-COMMIT effect
may occupy this name. Its loss is recoverable from referenced committed proof;
its conflict is RED. Publication uses a same-directory no-follow `O_EXCL`
temporary, complete write, mode/file full sync, exact expected prior pointer
generation, atomic replace, readback, and directory full sync.

The manifest contains the complete lease object, encoding, exact byte length,
and file-byte hash in addition to its effect commitments. Recovery therefore
does not reconstruct lease bytes from live root state.

### 4.7 Effect transaction and four-way resolver

The effect graph transaction uses `BEGIN IMMEDIATE` and:

1. requires and exact-compares the immutable effect parent already committed
   by the intent barrier;
2. exact-CASes the stage from `INTENT_DURABLE` or resolver `ABSENT` to
   `LEASE_DURABLE` and records durable lease proof;
3. inserts one attestation;
4. inserts ordered event ordinals `0..N-1`;
5. inserts one manifest committing lease, attestation, event count/root, and
   all expected identities;
6. verifies relational closure and application JCS/SHA commitments; and
7. inserts completion last, then COMMITs.

No required graph row is written outside that graph transaction. Certificate,
reference, pointer, member-publication, and retention-release rows remain
separate named actions with frozen postconditions. A successful COMMIT return
is not proof. The writer closes; a newly opened, profile-verified connection
resolves:

```text
EFFECT_COMMITTED(effect_id) ->
  COMMITTED | ABSENT | CONFLICT | UNAVAILABLE
```

`COMMITTED` requires one exact parent/intent, stage-compatible completion, one
lease/attestation/manifest, exact contiguous events, exact request and
identity bindings, and every JCS/hash/commitment recomputed from fresh rows.
`ABSENT` means no completion and no graph row other than the immutable intent
parent/stage; it alone permits same-effect precommit retry. Any partial,
extra, gapped, divergent, misbound, or hash-invalid graph is `CONFLICT`.
Open/profile/busy/I/O failure before a trustworthy read is `UNAVAILABLE`;
that branch retries only the read.

The certificate is created only from the fresh `COMMITTED` read plus exact
immutable lease bytes. Writer memory and `active.json` are not certificate
inputs. After a `COMMITTED` read, a short exact transaction advances the stage
from `LEASE_DURABLE` to `GRAPH_COMMITTED` and resolution to `COMMITTED`;
completion remains the last graph insert. Exact later transactions advance
`CERTIFIED`, `REFERENCED`, `ACTIVE_PUBLISHED`, and `REGISTERED` only after
their named durable predicate; helpers may recompute but never skip a stage.
`UNAVAILABLE` never changes the effect. The resolver uses a frozen attempt
count and monotonic budget. Exhaustion releases the common-directory lock and
persists only same-effect help-due scheduling under `RECONCILE`; a later
root-bearing event, startup pass, or host tick resumes it.

The inspect-before-apply postcondition matrix is normative:

| Action class | Exact postcondition inspected before apply | `ABSENT` action | Conflict / acknowledgement-loss convergence |
|---|---|---|---|
| Lease publication | Retained lease-directory fd names exact owned `0600` bytes/hash and synced parent generation | Publish immutable no-replace bytes | Exact means verify/advance; partial or different final is terminal; never overwrite |
| SQLite graph | Fresh profile-verified resolver returns exact sealed graph/completion | Execute same completion-last graph transaction | `COMMITTED` advances, `ABSENT` retries same effect, `CONFLICT` terminal, `UNAVAILABLE` help-due |
| Certificate | Fresh graph + exact immutable lease derive expected certificate | Insert exact certificate action result | Existing exact converges; mismatch terminal |
| Reference | Exact DB reference/retention generation exists before external reference | Insert DB reference, then external durable reference | DB-only resumes external publication; external-only is conflict/RED |
| Active pointer | Descriptor-bound pointer has expected prior generation and exact new bytes/hash | Publish same-directory temp + atomic replace + readback | Exact new pointer converges; unexpected generation/content is conflict |
| Member publication | Current tuple and archive match effect/member/epoch/helper/request/certificate/pending successor | Exact terminal/help CAS | CAS loss rereads archive/current and helps; never chooses a new effect |
| Rescue artifact | Artifact/proof/reference and retention rows match immutable plan/inventory | Preserve and publish same artifact | Exact converges; partial/conflict preserves source and evidence |
| Rescue target provision | Target reservation/member/handoff and clean target proof match | Provision exact target under no-exec profile | Exact converges; collision/conflict becomes `PRESERVED_ONLY`/terminal |
| Rescue restore | Target registration, artifact, restore plan and pre-restore target proof match | Restore then verify all predicates | Exact completion converges; mismatch stays non-green and preserves artifact |
| GC trash move | Reservation generation, object hash, source/trash descriptors and journal match | Same-device no-replace rename | Exact trash converges; `EXDEV` is not retried as rename |
| GC central copy | Cross-device journal and source hash exact; destination absent | Copy, full-sync, hash-verify, sync destination dir | Exact destination resumes source unlink; mismatch retains source/RED |
| GC delete | Trash/object and graph reservation exact; no hold/reference can be inserted | Delete exact reserved object/graph and sync | Exact absence advances; ambiguity re-inspects, never scans |
| GC tombstone | Exact deletion plus crossed retention barrier, no prior tombstone | Insert immutable terminal tombstone last | Existing exact converges; mismatch terminal |

Every helper test kills or loses acknowledgement immediately before and after
the inspect, apply, sync/COMMIT, verify, and action-state CAS for each row.
Convergence must reach the same postcondition without duplicate effects,
retargeting, or inferred success.

### 4.8 Crash and recovery matrix

| Crash/fault boundary | Durable observation | Required recovery |
|---|---|---|
| Before claim COMMIT | No claim | Another event/tick may claim |
| After claim COMMIT, before common lock | Exact `CLAIMED` | Same request waits/takes over after exact expiry |
| During B1/E/B2 | No effect intent | Claim returns to `WAITING`; no lifecycle I/O |
| After B2, before intent CAS | Claim may remain | Invalidation makes CAS lose; no lifecycle I/O |
| Intent transaction rolls back | No effect parent, phase not in-flight | Same request may claim again |
| Intent COMMIT ambiguous | Fresh state read plus retention row/hold | Exact parent + in-flight helps; absence retries; divergence terminal |
| `EFFECT_IN_FLIGHT`, no lease | Intent contains exact bytes | Republish same immutable lease |
| Temp lease only | Temp is non-authoritative | Remove exact owned temp, sync dir, republish |
| Final exact lease, graph absent | Stage/intent exact, active absent | Reuse final; retry same-effect graph |
| Final conflicting lease | Mismatch | `CONFLICT`; preserve evidence |
| Graph transaction before COMMIT | SQLite rollback | Resolver `ABSENT`; retry same effect |
| COMMIT return ambiguous | Unknown | Close/reopen; only four-way resolver decides |
| Graph complete, lease missing | Manifest/intent exact | Republish exact immutable lease, then continue |
| Graph complete, lease conflicts | Immutable mismatch | `CONFLICT`; never overwrite or roll back |
| `COMMITTED`, certificate absent | Fresh graph + lease | Recreate certificate; no lifecycle replay |
| Certificate/reference absent | Committed graph | Add DB reference, then external reference |
| DB reference exists, active absent | Retained proof | Publish exact `active.json` |
| Active exact, member not registered | All proof exact | Fenced helper archives exact result and converges |
| Invalidation during in-flight | New member version + complete `supersede_pending` tuple | Fenced helper archives old result and atomically consumes pending successor |
| Ack lost after any lifecycle/rescue/GC effect | Frozen action + postcondition | Inspect first; exact converges, absent reapplies same action, conflict terminal |
| Resolver budget exhausted | Same effect + help-due state | Release common lock; later event/startup/host retries same effect |
| Reboot with `CLAIMED` | Old boot claim | Supersede claim after fresh identity |
| Reboot with in-flight effect | Exact intent/graph state | Reconcile same effect; never allocate another |
| Root-bearing event died before due index | Exact durable source evidence, or none | Seed/resolve exact episode only with evidence; otherwise await fresh identity |
| Stale precommit lease, newer request | Immutable unreferenced file | Coexists; stage/reference-aware GC later |
| GC reserved, before trash | Reservation generation blocks all holds/references/helpers | Resume or release reservation |
| In trash, before graph delete | Journal + exact trash proof | Resume; never scan/guess |
| Cross-device copy interrupted | Journal + source/destination hashes | Resume copy/verify; source remains until destination dir synced |
| Graph/file deleted, no tombstone | Journal says deleting | Reconcile exact absence, cross retention barrier, write tombstone last |
| Rescue preservation committed only | Protected artifact exact | `PRESERVED_ONLY` or resume target provisioning |
| Rescue target made, before entry | Clean target exact | `AWAITING_TARGET_ENTRY`; operator opens manually |
| Target registration committed, before restore | Rescue relation non-green | Resume `RESTORING` from protected artifact |
| Restore interrupted | Source untouched, target non-green | Recreate clean target or resume only from exact proof |

Stale immutable precommit leases do not wedge active selection because
`active.json` is postcommit only. Stage resolution and references decide their
retention.

### 4.9 Admission snapshot and aggregate green

Every functioning admission performs:

```text
B1 = {
  boot, conversation, root_set_incarnation/hash,
  policy/capability/current-session/heartbeat basis,
  ordered canonical-member vector V1:
    (member_id, member_version, admission_epoch, physical basis hash)
}

E = one read transaction over:
  episode + episode membership + member current rows +
  requests + effects/stages/completions + references + rescue rows

B2 = same uncached collection with ordered vector V2
```

Allow requires:

1. `B1 == B2` and `V1 == V2`;
2. `E` binds the exact episode/root-set and every canonical vector element;
3. each positively eligible member is `REGISTERED`;
4. each member's request/effect/certificate and required references resolve
   exact and `supersede_pending=0`;
5. no linked rescue row is nonterminal (`RESTORING` and every predecessor
   state are non-green);
6. protocol writer/wake/wiring capability is exact; and
7. the event surface and discriminator are in the frozen supported registry.

One full retry is allowed within the total admission deadline. A second
mismatch, timeout, unknown member, unknown tool, missing event, or unavailable
authority denies when the hook functions. Successful `B2` is the invocation's
admission linearization point. A later invalidation affects the next
invocation; an already-running tool cannot be revoked.

No admission/member reservation survives that linearization point. The
implementation must include a negative structural and behavioral proof that
no lock, row, lease, status, copy, or operator message claims protection for
tool duration. An admitted invocation may finish; only later calls observe
later invalidation/effects. Duration protection is rejected, not deferred.

The database read transaction, not a JSON episode file, is `E`. An optional
private episode projection can show status but cannot grant, retry, recover,
or publish success.

Multi-root registration is per canonical member, not cross-root atomic. At
most one common-directory lock is held. Completed members are not replayed.
Aggregate green is the exact all-member fold above. Two overlapping root sets
share `member_id/member_version` and therefore cannot carry inconsistent
physical-member truth.

### 4.10 Retry claims, sleep, reboot, and notice

Registration/reconciliation opportunities are exact root-bearing
`sessionStart`, `beforeSubmitPrompt`, and `preToolUse`, startup reconciliation,
and one bounded `stop` follow-up. A separately supervised 15-second host tick
is the no-new-prompt backstop. Every opportunity uses the same claim CAS; an
optional detached worker may accelerate but is never liveness authority, and
no daemon or prompt loop is introduced.

Startup reconciliation may seed or resolve an episode whose root-bearing event
died before due-index publication only when durable source evidence exactly
binds conversation, boot, generation, root-set incarnation/hash, and resolved
member descriptors. Without that evidence it publishes no episode/request and
waits for a fresh root-bearing identity.

The claim CAS key is:

```text
(episode_id, member_id, state_version, member_version, admission_epoch,
 phase, request_generation, request_key, effect_id, claim_window,
 prior_claim_token, wake_epoch)
```

The winner atomically writes:

```text
phase=CLAIMED
claim_window=N
claim_token
claim_boot
claim_expires_mono_ns
next_due_mono_ns
wake_epoch
discontinuity_marker|null
```

No field is installed separately. Losers reread and perform no Git, lease,
effect, certificate, reference, pointer, or registration I/O.

Scheduling and claim expiry use boot-scoped monotonic nanoseconds only within
`claim_boot`. Persisted wall deadlines are display-only and are never
converted back into scheduling authority. After sleep or delayed wake, one CAS
coalesces all missed windows, writes the
discontinuity marker, and sets:

```text
next_due_mono_ns = observed_now_mono_ns + capped_backoff
```

There is no catch-up loop and no extension of the prior deadline. Reboot
supersedes ordinary claims and recomputes deadlines only after fresh identity.
`EFFECT_IN_FLIGHT` always reconciles the same effect across reboot.

Frozen initial parameters, subject to measured M2 evidence, are:

```text
event registration outer deadline       2.0 seconds
tool admission outer deadline            250 milliseconds
claim expiry                              5 seconds
backoff                                   0,1,2,4,8,16,30 seconds
deterministic jitter                      0-20% from request_key
host retry cadence                        15 seconds
maximum members per tick                  8
host DEGRADED threshold                   45 seconds
host RED threshold                        90 seconds
resolver UNAVAILABLE attempts             3
resolver UNAVAILABLE outer deadline       2.0 seconds
unknown classification probe             1
stop follow-up per notice epoch           1
```

The host queue is deterministic oldest-due first by
`(next_due_mono_ns, request_created_wall_ns, member_id, request_key)` with a
persisted cursor for equal due groups. Every scan records oldest wait. Wait
beyond 45 seconds is DEGRADED and beyond 90 seconds or any detected starvation
is RED. A continuous queue of more than eight members must prove bounded
rotation and maximum wait across restart; an eight-item batch limit may not
starve later keys.

Notice is a separate relation keyed by episode plus
`notice_epoch/notice_version/notice_cause`. The persisted CAS progression is
exactly `FULL(0) -> COMPACT1(1) -> COMPACT2(2) -> QUIESCENT(3)`. Later
attempts read the stable quiescent row and do no write. Notice writes never
touch member state, request, claim, token, deadline, wake epoch, generation,
effect, rescue, alert identity, or certificate.

The full message uses only closed labels: why the action did not run, that
current work remains in place, the current DEGRADED/RED status, the exact
automatic wake/repair condition, and one safe action. A repeat for the same
epoch performs no registration-effect I/O and returns only the stable epoch,
reason, status, next wake, and safe action. After `COMPACT2`, quiescent
guidance says the agent should stop protected attempts, report from the denial
response, and not switch tools, change cwd, manufacture a prompt, disable
hooks, reset/clean, or invoke cleanup. That guidance is non-authoritative:
safety remains the hook's deny on every later intercepted non-green tool. One
`stop` follow-up may be consumed for the epoch. Restart, transcript
compaction, and arbitrary attempts cannot create unbounded work or messages.

Every partial-runtime and gate denial uses the DDL reason catalog. In
particular, basis instability, basis timeout, unknown discriminator,
protocol incompatibility, parser rejection, serializer fallback deny, and
emergency deny each have one closed status, wake, safe action, consequence,
and recovery. Unknown codes cannot be emitted.

### 4.11 Tool-event and child contract

The normative gate matrix is:

| Surface | Required seam | Supported basis | Non-green behavior | Limit |
|---|---|---|---|---|
| Shell | `preToolUse` / `Shell` | Official + fixture | Valid deny JSON or exit 2 | Existing shell guard remains separate |
| Read | `preToolUse` / `Read`; `beforeReadFile` where emitted | Official + fixture | Deny model admission | Local file read may precede `beforeReadFile` |
| Write/Delete | `preToolUse` exact names | Official names + fixtures | Deny | `afterFileEdit` is not a gate |
| Grep | `preToolUse` / `Grep` | Official + fixture | Deny | No diagnostic exception |
| Glob/Edit | Exact captured discriminator | Fixture/UAT only | Unknown denies while event exists | Name not assumed from docs |
| MCP | `preToolUse` `MCP:<tool>` plus server-aware `beforeMCP` | Official + fixture | Either deny blocks | Unknown/no-event MCP remains unsupported |
| Browser/web/internal | Exact captured discriminator | Fixture/UAT only | Unknown denies while event exists | No inferred alias/provenance |
| Task | Parent `preToolUse` plus `subagentStart` | Parent episode only | Deny unless supported shared mode positively established | No pre-spawn mode field |
| Unknown event discriminator | `preToolUse` | Event exists | Deny | Add only through contract revision |
| No hook event | None | None | Cannot intentionally deny | RED when later observed |

Production serializer behavior is:

- emit one complete valid allow or deny JSON object plus LF;
- use only closed reason/action strings and bounded identifiers;
- retry short writes and treat broken stdout as failure;
- use exit 2 as the only fallback when valid deny JSON cannot be emitted;
- never rely on malformed, truncated, duplicate, or wrong-shape JSON; and
- keep `failClosed:false` globally.

The common official schema is authority. Optional observed `session_id` and
`parent_tool_call` may detect contradiction but cannot be required.
`subagent_id`, `tool_call_id`, parent launch id, branch, cwd, and task text do
not create child identity.

Parent green authorizes at most a supported launch. A shared child receives no
copied authority and uses its own distinct conversation plus root-bearing
`preToolUse` to create/resolve its episode and gate its first tool. Parent
green never means child green.

Because there is no pre-spawn shared/isolated discriminator, Task remains
denied unless a versioned capability can positively constrain the requested
launch to the shared path already proved by Desktop UAT. Isolated mode remains
unsupported in v1. Any future revision proposing isolated support must first
prove pre-spawn mode, root identity, and first-tool timing through separate
UAT. No post-spawn observation retroactively authorizes a launch.

Required later Desktop UAT:

1. shared parent launch allowed only from exact parent green;
2. shared child first tool denies, creates/resolves its own episode, then a
   later exact tool allows;
3. missing child root or conversation denies without inference;
4. isolated launch denial when mode cannot be known pre-spawn;
5. no isolated allow exists in v1; any future revision first proves pre-spawn
   mode, root timing, own episode, and first-tool interception;
6. valid deny JSON, exit 2, malformed JSON, wrong-shape JSON, timeout, signal,
   and no-process behavior on installed Desktop;
7. complete exact discriminator inventory for every supported Agent tool; and
8. cloud behavior tested separately and never generalized from Desktop.

### 4.12 Hook-owned dirty/in-progress rescue

There is no Agent-tool exception. A non-green dirty or recognized in-progress
member still denies every intercepted Agent tool.

The operator flow is exact:

1. The first denial says the action did not run, work remains in place, and
   the only safe action is `Reply exactly: Rescue`.
2. An exact attachment-free `Rescue` submission is intercepted by the
   `beforeSubmitPrompt` hook and invokes
   `registration rescue plan`. It is read-only and returns a digest-bound
   complete plan with every selected row.
3. The next accepted literals are exactly `Preserve`,
   `Preserve including secrets`, or `Cancel`, with no aliases, extra words,
   booleans, clicks, agent commands, or attachments.
4. `Cancel` closes the pending workflow as `CANCELLED`; it performs no plan
   apply, preservation, lifecycle, repository, workspace, ref, or artifact
   effect.
5. A preserve literal invokes hook-owned `registration rescue apply` against
   the exact unexpired plan/digest. `Preserve` refuses if secret-bearing rows
   exist; `Preserve including secrets` is required for those rows.
6. Apply preserves all rows, creates and proves the target, then tells the
   operator to open the new root manually through the local OS/Cursor folder
   picker. AWA output never prints the root. It never claims Cursor moved.

Secret-bearing preservation follows the accepted existing private, local,
unencrypted Retain policy. It is owner-only, uses no network, requires exact
`Preserve including secrets`, and carries an explicit confidentiality risk.

Hook-owner v4 places this control handler before the unchanged finish
consumer. A non-rescue submission reaches finish with byte-equivalent payload,
stdout/stderr, exit behavior, warning publication, and exact-`Close`
semantics. An exact rescue control turn is consumed by the hook-owned workflow
and never becomes an Agent prompt. The immutable canonical plan/inventory and
one-use authorization relation bind source incarnation, conversation,
generation, event nonce, attachment absence, boot-scoped expiry, exact
literal, secret scope, complete row inventory, and plan digest. Apply consumes
that authorization by exact CAS in the same `RESCUE` transaction. Retarget,
replay, stale generation, changed inventory, attachment, and second consume
all fail without mutation. Rescue selects every row; there is no partial row
picker.

The extracted router-free Retain core must preserve:

- all at-risk tracked, staged, conflicted, untracked, and ignored content;
- raw Git index bytes and mode/stage metadata;
- administrative state for every currently recognized Git operation family;
- refs and reachable object closure;
- a local-history object pack sufficient without fetch;
- no-follow ownership/mode/path proofs;
- file and directory full-sync durability;
- disposable restore and byte/graph proof; and
- a protected publication marker.

The finish dialogue is not reused. No router selects or authorizes rescue.

The Git execution profile is closed and plumbing-only:

- the pinned Git binary may execute only `rev-parse`, `for-each-ref`,
  `show-ref`, `ls-files`, `cat-file`, `pack-objects`, `index-pack`,
  `hash-object --no-filters`, `update-index`, `read-tree`,
  `checkout-index`, and `update-ref`, with frozen argument grammars;
- no porcelain, alias, shell, pager, editor, diff/textconv, hook, maintenance,
  submodule, remote, fetch, credential, or custom helper command is permitted;
- repository/global/system hooks are neutralized with an empty owned
  `core.hooksPath`; config includes, aliases, URL rewrites, credential/remote
  helpers, and any filter/process driver are rejected before execution;
- `GIT_CONFIG_NOSYSTEM=1`, an empty owned HOME/global config,
  `GIT_TERMINAL_PROMPT=0`, failing askpass/SSH helpers, no pager/editor, and a
  file-only protocol allowlist are fixed; inherited Git/environment variables
  are discarded rather than filtered;
- an OS sandbox denies network and child execution except the pinned Git
  binary under the exact profile; repository scripts are never executable;
  and
- if materialization or proof requires a hook, filter, process driver, config
  include, helper, prompt, URL rewrite, network transport, script, or command
  outside that list, rescue stops with R08/R11/R15.

Qualification includes malicious repositories for every hook location,
filter/process form, config include depth, alias, credential/remote helper,
URL rewrite, prompt, pager/editor, textconv, external diff, submodule, and
script path. The sandbox must prove no process or network escape.

Source invariants:

- never modify/adopt/reset/stash/abort/clean the source;
- never run repository scripts or network access;
- never remove a lock or infer an unknown Git operation;
- preserve the artifact before provisioning a target;
- protect every rescue artifact until exact-ID deletion under the existing
  authority, with no automatic expiry;
- create an exact fresh clean local rescue ref/worktree at captured HEAD;
- leave the original worktree in its existing registration state and
  untouched; and
- leave original cleanup to the existing separate explicit authority.

All rescue plan/control/error/notice/log/stdout/stderr/projection output uses
one bounded opaque schema:

```text
schema = "awa-registration-rescue-output/v1"
kind = PLAN | CONTROL | STATUS | ERROR | NOTICE
state = one closed rescue state
reason = one R01..R20 or closed success code
guidance = NONE | CONFIRM | WAIT | OPEN_TARGET | RESUME | CANCEL | REPAIR
repeat = FULL | COMPACT1 | COMPACT2 | QUIESCENT
```

Unknown fields are rejected. No branch emits a root, path, identifier,
filename, secret classification/metadata, plan inventory, prompt, tool input,
environment value, command line, or unbounded exception text. Internal
handoff identity stays relational. The OS/Cursor picker—not hook output—shows
the local folder to the operator. A negative leak corpus covers ordinary,
malicious, crash, duplicate, timeout, and compaction paths.

Target sequence:

```text
PLAN_CURRENT
-> PRESERVATION_COMMITTED
-> TARGET_PROVISIONED
-> operator manually opens target
-> normal TARGET_REGISTRATION_COMMITTED
-> rescue state RESTORING keeps aggregate non-green
-> RESTORE_COMMITTED
-> RESCUE_COMPLETE
-> rescue REGISTERED; aggregate may become green
```

Workflow states are:

```text
PLANNED | AUTHORIZED | PRESERVING | PRESERVED |
TARGET_PROVISIONING | AWAITING_TARGET_ENTRY |
TARGET_LIFECYCLE_COMMITTED | RESTORING | REGISTERED |
CANCELLED | SUPERSEDED | PRESERVED_ONLY | AWAITING_OPERATOR |
TERMINAL_CONFLICT
```

Crash recovery resumes only from durable predicates. If target registration
committed but restore did not, registration phase may be `REGISTERED` while
the linked rescue `RESTORING` state keeps effective admission non-green.
Restore must be independently verified before rescue `REGISTERED`.

Each target reservation has one durable `handoff_id`, but that value never
leaves the store. While rescue dialogue is pending, exact attachment-free
`Rescue` is also the status/resume verb: it rereads the current rescue row and
returns only the bounded output above. Lost instructions, restart, and a target
never opened remain `AWAITING_TARGET_ENTRY`; no target or source mutation is
repeated, status/alert remains active, and the operator may retry the manual
open or choose the state's one safe rollback action.

#### Exhaustive rescue state/event/predicate/crash matrix

| Current state | Accepted event / exact CAS target | Required durable predicate before CAS | Duplicate, restart, or crash result | Bounded output |
|---|---|---|---|---|
| `PLANNED` | exact preserve auth -> `AUTHORIZED`; `Cancel` -> `CANCELLED`; drift -> `SUPERSEDED` | Immutable plan/items exact and current; auth unused/unexpired | Duplicate auth refuses; restart rereads plan | `CONFIRM`, `CANCEL`, or R16/R17 |
| `AUTHORIZED` | apply -> `PRESERVING`; invalid auth -> `AWAITING_OPERATOR` | One-use auth consumed in same transaction | Ack loss sees consumed auth and same state; never consumes twice | `WAIT` or R17 |
| `PRESERVING` | artifact action -> `PRESERVED`; proof failure -> `TERMINAL_CONFLICT` | Frozen artifact postcondition/action | Restart inspects artifact first; exact helps, partial preserves source | `WAIT` or R18 |
| `PRESERVED` | target action -> `TARGET_PROVISIONING`; pause -> `PRESERVED_ONLY` | Exact artifact/proof/reference and artifact hold | Duplicate target request reuses same reservation | `WAIT` |
| `TARGET_PROVISIONING` | proved target -> `AWAITING_TARGET_ENTRY`; failure -> `PRESERVED_ONLY` | Source != target; exact canonical target reservation/member | Crash inspects target postcondition; collision never retargets | `OPEN_TARGET` or R19 |
| `AWAITING_TARGET_ENTRY` | exact target event -> `TARGET_LIFECYCLE_COMMITTED`; status stays same | Durable handoff + target root event + target registration proof | Never-opened/restart remains; duplicate event helps same proof | `OPEN_TARGET` or `WAIT` |
| `TARGET_LIFECYCLE_COMMITTED` | restore start -> `RESTORING` | Exact target registration request/effect/certificate | Duplicate start uses same restore action | `WAIT` |
| `RESTORING` | verified completion -> `REGISTERED`; recoverable stop -> `AWAITING_OPERATOR`; conflict -> `TERMINAL_CONFLICT` | Artifact + target registration + restore proof + source unchanged | Restart inspects restore postcondition; no partial green | `WAIT`, `RESUME`, or R20 |
| `PRESERVED_ONLY` | exact resume -> `TARGET_PROVISIONING`; repair decision -> `AWAITING_OPERATOR` | Artifact/proof/reference/hold remain exact | Arbitrary status calls are read-only | `RESUME` |
| `AWAITING_OPERATOR` | state-specific exact resume/cancel -> declared predecessor/terminal | Prior proofs retained; new auth if required | Near-miss/duplicate leaves row unchanged | `RESUME`, `CANCEL`, or `REPAIR` |
| `REGISTERED` | status only | Every plan/auth/artifact/target/registration/restore/completion predicate | Absorbing across restart | closed success status |
| `CANCELLED` | status only | No apply effect; any prior proof retained | Absorbing; no deletion | closed cancelled status |
| `SUPERSEDED` | status/re-plan only | Old plan immutable; successor separate | Absorbing; no retarget | R16 |
| `TERMINAL_CONFLICT` | status/repair only | Conflict evidence + artifact/source holds retained | Absorbing; no deletion | R18/R20 |

Every matrix edge is exercised with the CAS winner, loser, duplicate,
acknowledgement loss, process restart, power boundary, missing/corrupt
artifact, target collision, target registration mismatch, restore mismatch,
and every output branch. No unspecified edge mutates.

#### Proof-preserving rescue rollback

| State | One operator action | Drain/retention result |
|---|---|---|
| `PRESERVED_ONLY` | exact `Rescue` then `Cancel` future continuation | Keep artifact/proof/reference; close continuation only |
| `AWAITING_TARGET_ENTRY` | exact `Rescue` then `Cancel` future continuation | Keep artifact and clean target reservation; no source/target delete |
| `RESTORING` | exact `Rescue` then `Wait` | Stop new restore steps, retain target/artifact/proofs, remain non-green |
| `AWAITING_OPERATOR` | exact `Rescue` then `Cancel` where matrix permits | Close pending dialogue; retain every durable predicate |
| `TERMINAL_CONFLICT` | exact `Rescue` then `Repair` | Preserve all evidence and holds; no deletion or automatic repair |

Rollback never deletes an artifact, target, ref, proof, or source. Later
exact-ID deletion remains under the existing separate authority.

#### Closed rescue failure/UAT taxonomy

| ID | Condition | Required outcome |
|---|---|---|
| R01 | Source is primary | No-go; source unchanged |
| R02 | Policy-excluded source | No-go; source unchanged |
| R03 | Detached or unborn HEAD | No-go |
| R04 | Nonlocal/cloud root | No-go |
| R05 | Multi-root or ambiguous physical identity | No-go |
| R06 | Another live session owns/touches source | No-go; no takeover |
| R07 | Genuine lock or unknown Git operation | No-go; never remove/abort |
| R08 | Malformed index, missing object, or fetch required | No-go; no network |
| R09 | Symlink, mount boundary, special file, or nested repository | No-go |
| R10 | Submodule or gitlink present | V1 no-go under accepted C0-D6 |
| R11 | LFS/filter state not locally and byte-exactly proved | V1 no-go |
| R12 | Unsafe private state, owner, mode, or no-follow proof | No-go |
| R13 | Insufficient local storage for artifact + disposable proof + target | No-go |
| R14 | Artifact/ref/worktree/target collision | No-go; preserve both facts |
| R15 | Script execution or network would be required | No-go |
| R16 | Root/member/HEAD/index/plan incarnation drifts | Plan superseded; re-plan |
| R17 | Authorization literal, secret scope, attachment, or digest mismatches | `AWAITING_OPERATOR` or cancel; no mutation |
| R18 | Preservation publication or disposable restore proof fails | `TERMINAL_CONFLICT`; source unchanged |
| R19 | Target provisioning or normal registration cannot commit exactly | `PRESERVED_ONLY` or `AWAITING_TARGET_ENTRY`; no restore |
| R20 | Restore or post-restore byte/index/ref/operation proof fails | Target stays `RESTORING`/terminal; source + artifact protected |

UAT injects each R01-R20 condition, every crash between workflow predicates,
every exact/near-miss operator literal, secret/non-secret plans, every
currently recognized operation family, manual-open delay/restart, target
collision, and artifact exact-ID deletion protection.

### 4.13 References, active publication, and garbage collection

The reference relation is authoritative:

- add a database reference before publishing the matching external durable
  reference;
- remove and full-sync the external durable reference before deleting its
  database reference; and
- never infer absence or deletion permission from a scan.

Effect intent inserts `registration_effect_retention` and its live `INTENT`
hold in the same transaction as the effect parent and in-flight phase. Rescue
artifact intent does the equivalent before artifact I/O. Member, claim,
rescue, active-pointer, generic reference, audit, recovery, integrity, and
operator-retention owners have explicit holds or references. Release is an
append-only relation; holds are never updated or deleted.

Collectibility requires all of:

1. terminal and complete object closure;
2. an immutable collectible marker and generation;
3. no current member/claim/rescue linkage;
4. no pointer/reference/audit/recovery/integrity/operator hold;
5. every explicit hold has an exact release; and
6. GC reservation generation strictly exceeds the collectible generation.

GC runs:

1. acquire no filesystem lock; `BEGIN IMMEDIATE`; advance the one retention
   clock; prove every predicate above; reserve exact effects/artifacts and
   insert run/items/actions at that generation; COMMIT.
2. Reservation triggers reject every new hold/reference/helper for the
   reserved object. Rescue and GC use the §4.5 lock order.
3. Journal and full-sync the exact run.
4. For each per-root lease/artifact, open that root's private `0700` trash by
   retained descriptor, prove source/trash `st_dev` equal, and perform a
   no-replace rename plus both directory syncs.
5. For an explicitly central artifact whose devices differ, use only:
   journal -> copy complete bytes -> file `fsync` + `F_FULLFSYNC` -> hash and
   metadata verify -> destination-directory full sync -> source unlink ->
   source-directory full sync. `EXDEV` on a rename enters this named copy
   action; it never becomes an implicit fallback.
6. Mark exact item `TRASHED`; then `DELETING`; delete sealed graph/object only
   with operation class `GC`, a table-specific one-use authorization, and the
   exact reservation.
7. Reinspect exact absence, full-sync database/filesystem results, cross a new
   retention barrier, insert immutable terminal tombstone last, and mark item
   then run complete.

Startup resumes any nonterminal run. An unreadable journal, unknown
reference, mismatch, or ambiguous deletion conservatively retains and reports
RED. Crash qualification covers every copy, sync, hash, directory sync,
unlink, delete, barrier, and tombstone boundary plus `EXDEV`. No GC path scans
and decides that an unreferenced-looking file is safe.

### 4.14 Writer fencing, activation, and rollback

Every write receipt binds:

```text
write_generation
protocol_epoch
writer_id
binary_hash
capability_hash
db_profile_hash
operation_class = NORMAL | RECONCILE | GC | RESCUE | PROTOCOL
target_table
transition_name
mutation_kind
target_key
one-use authorization_id
```

The possible-writer inventory includes hook roles, startup reconciler, host
retry executable, rescue plan/apply, CLI lifecycle paths, installer/migrator,
effect helpers, reference publisher, recovery, and GC. Each writer receives
only the exact operation/table/transition rows in §4.3. The SQLite authorizer
and triggers enforce the matrix; neither writer identity nor an application
call path grants ambient database write access. Epochs, writer declarations,
capabilities, authorizations, receipts, and uses are append-only.

Activation is:

1. install successor readers/runtime while the successor database is absent;
2. make historical binaries that lack successor refusal operationally
   uninvocable;
3. bootstrap/validate schema in `DORMANT`;
4. enumerate every invocable writer and commit exact hashes plus the full
   writer x operation x table x transition matrix;
5. verify every connection profile and no-follow choice;
6. transition to `WRITABLE` in one `BEGIN IMMEDIATE`; and
7. project hook-owner v4 rows last, in a separately authorized host change.

`DRAINING` is entered by `BEGIN IMMEDIATE`. The committed mode prevents later
compliant `NORMAL` receipts. Rollback then:

1. denies new admission/claims;
2. resolves every ambiguous or in-flight effect;
3. rolls each committed effect forward to registered/terminal;
4. applies the state-specific proof-preserving rescue drains in §4.12 and
   closes external-reference, GC, and active-pointer obligations;
5. preserves every proof/reference;
6. transitions/removes v4 rows only after closure;
7. keeps v4/runtime readers installed while any successor row/reference
   remains; and
8. ordinarily leaves the dedicated database and proof in place.

There is no down-migration or proof deletion in ordinary rollback. A failed
drain halts rollback. Same-user tampering is residual and cannot be eliminated
by writer advertisement.

### 4.15 Integrity, privacy, and partial-runtime truth

Integrity observes but never grants admission. Add
`registration_admission`:

- GREEN only when every eligible active member is relationally registered,
  no rescue is active, and v4/writer/wake/wiring health is current;
- DEGRADED when the functioning gate safely denies a recoverable state;
- RED for absent/incompatible protection, terminal conflict, unadmitted
  effect, writer skew, dead-man expiry, unsafe private state, or all configured
  alerts failed; and
- UNKNOWN for incomplete evidence, never green.

The display projection may include bounded counts and age but no raw roots,
conversation ids, effect ids, task/tool inputs, prompt, content, credentials,
or arbitrary environment. Projection files are views, not authority.

Partial-runtime outcomes:

| Condition | Honest result |
|---|---|
| Compatible wrapper/engine/profile | Exact green allows; any non-green/unknown intercepted event emits valid deny |
| Basis differs across B1/E/B2 | `basis_unstable`; bounded retry then valid deny; DEGRADED |
| Basis collection exceeds admission budget | `basis_timeout`; valid deny; RED and host retry |
| Event exists but discriminator is unknown | `unknown_discriminator`; valid deny; RED; contract revision required |
| Protocol/schema/profile incompatible | `protocol_incompatible`; valid deny/exit 2; RED; update/repair |
| Strict parser rejects payload | `parser_reject`; valid deny if positive eligibility is known; otherwise honest platform fail-open residual |
| Serializer cannot emit valid JSON after eligibility proof | `fallback_deny`; exit 2 only; RED; never malformed output |
| Closed emergency protection branch | `emergency_deny`; valid deny/exit 2; RED; repair before retry |
| Engine missing after wrapper positively proves eligible root | Literal valid fallback deny or exit 2; RED |
| Engine missing before eligibility proof | Official fail-open may occur; later observer RED |
| Hook timeout/kill/transport loss | May fail open; never claim blocked |
| Host tick stale/missing, admission hook healthy | Intercepted tools still deny; DEGRADED then RED |
| Hook row/process absent | Cannot deny; later observer reports RED |

Native and optional alerts retain ADR 0020's accepted-not-seen semantics.
Alert delivery and host wake freshness are separate from registration
authority and notice epochs. Alert identity is
`(component, transition_generation, cause_fingerprint)`. A notice epoch may be
stored only as optional correlation; it cannot deduplicate, suppress, merge,
or identify an alert transition.

## 5. Future implementation milestones — all currently NO-GO

Every M1-M3 item that creates, changes, executes, or reviews implementation has
a direct dependency on C0-DESIGN, even where ordinary milestone sequencing
also applies. No item depends on C1-SHIPPING until PR readiness or delivery.

### Milestone 0: Resolve C0-DESIGN

#### R0: read-only refresh

- [ ] Re-read both governance indexes, ADRs 0020/0023/0024, frozen v1,
  draft/accepted ADR 0025, and this exact v2.
- [ ] Refresh official Cursor/SQLite documentation and source topology.
- [ ] Record the then-live base, clean implementation worktree, PR #175
  disposition, writer inventory, exact tool inventory, and SQLite binding
  options.
- [ ] Stop on any §2.5 condition.

#### C0-DESIGN: owner and independent design clearance

- [x] Record explicit owner acceptance of C0-D1 through C0-D8 — satisfied
  2026-09-26.
- [ ] Record both exact draft hashes in external review evidence (never
  self-hash either document).
- [ ] Obtain a complete independent critical review over both exact drafts.
- [ ] Resolve every source-confirmed document finding as `resolved`,
  `false_positive`, or `deferred_unsupported_platform_residual`.
- [ ] Resolve every verifier candidate adjudication and record
  `critical_coverage=true`, `probe_blind=true`, and
  `revision=true`.
- [ ] Explicitly accept ADR 0025 against its exact hash.
- [ ] Separately accept and freeze this exact plan against its exact hash.
- [ ] Record an exact refreshed baseline.
- [ ] Obtain separate owner implementation GO naming baseline and
  C0-DESIGN evidence.

**Definition of done:** all items are present and mutually consistent.
Bounded-model success, document self-assessment, silence, budget exhaustion,
partial review, or generic approval does not satisfy C0-DESIGN. Verifier
`shipping_clearance` is not required here and, because there is no
implementation, is expected to be failed or not evaluated.

### Milestone 1: Minimum complete end-to-end system

Every task directly requires C0-DESIGN. M1 is incomplete if rescue, admission,
recovery, references, fencing, or compatibility is a stub.

#### Task 1: Bootstrap the dedicated store and canonical contracts

- [ ] Implement the fd-anchored resolver, audited no-follow SQLite binding/VFS,
  exact create/reopen/sidecar matrix, schema fingerprint, and connection
  profile.
- [ ] Install the strict DDL, full trigger inventory, profile/readback checks,
  direct-SQL negative matrix, JCS parser, framing, identifiers, and golden
  vectors.
- [ ] Implement append-only epochs/writers/capabilities/authorizations/
  receipts/uses plus the SQLite authorizer; make ambient, legacy, or CLI
  writes impossible.
- [ ] Keep legacy `state.db` and native-entry v1/v2 bytes/semantics unchanged.

#### Task 2: Implement episode/member/request authority

- [ ] Build canonical physical member identity/versioning independent of root
  sets.
- [ ] Build immutable episodes/membership and mutable current phases through
  exact CAS.
- [ ] Implement invalidation, `admission_epoch`, `supersede_pending`, and the
  terminal archive/fence plus closed matrix/pseudocode.
- [ ] Implement startup exact-evidence episode seed/resolve; otherwise await
  fresh identity.
- [ ] Generate only display projections; structural tests prove no authority
  reader consumes them.

#### Task 3: Implement intent, lease, effect, and helpers

- [ ] Implement the fixed lock graph and
  `CLAIMED -> EFFECT_IN_FLIGHT` intent transaction including retention
  object/hold and frozen action postconditions.
- [ ] Publish immutable per-effect leases and postcommit-only `active.json`.
- [ ] Write completion-last effect graphs and close/reopen four-way resolver.
- [ ] Produce fresh certificates, inspect-before-apply helper convergence,
  bounded `UNAVAILABLE` help-due recovery, and atomic pending-successor
  archive/consumption.

#### Task 4: Implement admission and event coverage

- [ ] Implement `B1(V1) / E / B2(V2)` from lightweight basis plus one database
  read transaction.
- [ ] Deny all non-green intercepted tools; add no diagnostic exception.
- [ ] Gate MCP at both required seams and Task at parent seams.
- [ ] Implement total valid serializer plus exit-2 fallback; never malformed
  output.
- [ ] Prove invocation-start-only admission and the absence of any
  duration-long reservation or revocation claim.

#### Task 5: Implement retry, notice, and host backstop

- [ ] Implement full-tuple claims, bounded deadlines, one-window sleep clamp,
  boot-scoped monotonic clock mapping, reboot behavior, and same-effect
  in-flight recovery without deadline extension.
- [ ] Keep notice progression and alert component transition identity
  separate; implement the closed reason/status/wake/action/consequence/
  recovery catalog.
- [ ] Ship the bounded retry-due executable and health protocol; no plist,
  activation, daemon, or host edit; implement oldest-due fairness and
  persistent cursor.

#### Task 6: Implement hook-owned rescue

- [ ] Extract the router-free Retain preservation core without its finish
  dialogue.
- [ ] Implement exact `Rescue` -> plan -> `Preserve` /
  `Preserve including secrets` / `Cancel` hook flow.
- [ ] Implement predicates/states, protected artifact, fresh clean target,
  durable manual-open handoff/status, target registration barrier, non-green
  restore, and exact restore proof.
- [ ] Implement immutable plan/items, one-use consent relation, closed
  plumbing/no-exec/no-network profile, bounded opaque egress, all R01-R20,
  the exhaustive state/event/predicate/crash matrix, and state-specific
  proof-preserving rollback.

#### Task 7: Implement references, GC, integrity, and fencing

- [ ] Implement reference-before-external publication and external-before-
  reference removal.
- [ ] Implement intent-time retention holds, one shared retention generation,
  helper/reference fencing, same-device per-root trash, explicit cross-device
  copy protocol, deletion, terminal tombstone, and barrier-last GC.
- [ ] Add independent status/projection/alerts without admission authority.
- [ ] Implement dormant/writable/draining activation and proof-preserving
  rollback.

#### Task 8: Add immutable hook-owner v4 in throwaway direct mode

- [ ] Define v4 roles for all-tool admission, MCP, parent launch, episode
  events, stop, retry health, and rescue conversation handling.
- [ ] Preserve v1-v3 compatibility and external zero-access.
- [ ] Test runtime-first, writer-fenced, rows-last install/doctor/staging in
  throwaway homes only.
- [ ] Do not release, install live, project external rows, activate jobs,
  mutate GitHub, or touch PR #175.

**M1 definition of done:** a hermetic local APFS fixture proves one clean root
from event to canonical member/episode/request, claim, intent barrier,
immutable lease, committed graph, fresh certificate/reference/active pointer,
member registration, and successful admission. It also proves a dirty root
through exact rescue to a separately registered/restored target, while the
source stays byte-identical. Restart, invalidation, overlap, child denial,
writer drain, and GC all use the same authority.

### Milestone 2: Fault, concurrency, power, and latency proof

- [ ] Inject crashes before/after every DB transaction, CAS, lease operation,
  graph statement, COMMIT return, resolver read, certificate/reference/pointer,
  helper transition, rescue predicate, and GC step.
- [ ] Model-check the complete phase/event matrix and invariants beyond the
  bounded spike, including overlapping episodes/member versions.
- [ ] Run high-contention same-request, invalidation, helper, sleep/reboot,
  notice, event/tick, rescue authorization, rescue/GC hold, and terminal-fence
  schedules.
- [ ] Use a custom SQLite VFS to inject short writes, reordered/failed syncs,
  torn sectors, WAL/SHM faults, ENOSPC/EDQUOT/EIO, busy, and ambiguous COMMIT.
- [ ] Run disposable macOS VM hard-power tests at every named durability
  boundary. Process kill is not accepted as power-loss evidence.
- [ ] Measure p50/p95/p99 admission and registration latency on the accepted
  WAL/FULL profile, battery/tick cost, database/lease/GC growth, and recovery;
  confirm unsupported WAL-shared-memory environments remain v1 no-go.
- [ ] Prove every effect-action acknowledgement-loss postcondition, every
  R01-R20/state-matrix case, malicious Git fixture, negative egress corpus,
  direct-SQL writer cross-product, continuous queue above eight, source-byte
  preservation, and negative admission-duration claim.

**Definition of done:** every acceptance row passes with injected evidence;
latency bounds are measured rather than assumed; custom-VFS and VM power tests
match the crash matrix; no race creates a second effect, false green, source
mutation, lost reference, or premature delete.

### Milestone 3: Product docs and governed Draft PR review

- [ ] Update product/operator docs only after behavior is proven.
- [ ] Run focused, full, install, kernel-off, finish, guard, cleanup,
  compatibility, migration, power-evidence, and performance gates.
- [ ] Open new governed Draft/unarmed PRs for approved implementation bodies;
  do not modify PR #175.
- [ ] Run Bugbot until no valid finding remains.
- [ ] Run fresh security, concurrency/authority, durability, and operator-
  rescue reviews plus protected-axis verification over the complete body.
- [ ] Run exact-head disposable/local Desktop UAT for supported tool
  discriminators, shared child, rescue, restart, and recovery; this is
  shipping evidence, not live host rollout.
- [ ] Keep every PR Draft/unarmed. Do not arm auto-merge, mark ready, merge,
  release, bind, install, activate, or run live UAT.

### C1-SHIPPING checkpoint

- [ ] Bind the exact implementation head and complete implementation, test,
  fault, power, performance, and disposable-UAT evidence.
- [ ] Resolve every protected review/verifier finding; no protected finding
  remains open.
- [ ] Record `partial_rollout=false` for the named complete body.
- [ ] Obtain verifier `shipping_clearance=approved` for that exact head.

Design acceptance, C0-DESIGN, green tests alone, a partial body, or a verifier
result from another head cannot satisfy C1-SHIPPING.

### Milestone 4: Separately gated delivery

Every node requires C1-SHIPPING for the exact head plus its own named owner
checkpoint:

```text
PR readiness authorization
-> merge authorization
-> AWA release/tag authorization
-> AWA install authorization
-> Skills Flavor-2 pin if then-required
-> separate ~/dev v4 hook/local-jobs PR authorization
-> rows-last activation
-> live Desktop shared-child/tool/rescue/power-recovery UAT authorization
-> rollout acceptance
```

Rollback follows §4.14. No cross-repository step is represented as atomic.
The reviewer App alone may arm native auto-merge where repository governance
assigns it that role.

## 6. Failure-mode registry

| Domain / failure | Detection | Closed result | Recovery / residual |
|---|---|---|---|
| JSON/key/type/size invalid | Strict parser/JCS vectors | Refuse; non-green | No defaults or partial persistence |
| Root alias/incarnation ambiguity | Fd-anchored no-follow descriptor + recheck | WAITING or TERMINAL by closed cause | Never lexically exclude or merge uncertain roots |
| DB/WAL/SHM bootstrap ambiguity | Closed absent/empty/valid/partial/foreign/symlink matrix + fingerprint | No authority open/write; RED | Preserve bytes; rebuild only non-authoritative SHM |
| Overlapping root sets | Canonical `member_id/version` | Shared member truth | No cross-root atomic claim |
| Conversation/boot mismatch | Exact official fields and boot | Successor/non-green | No cwd/env/session synthesis |
| Current-session/heartbeat stale | Basis generations/hash | WAITING | Fresh exact event only |
| Initial dirty/operation | Clean/idle gate | Deny; offer Rescue if eligible | Source remains untouched |
| Request/effect acknowledgement loss | Deterministic key/effect + frozen action postcondition | Inspect then help same action/effect | Never allocate replacement or replay exact postcondition |
| Claim storm/expiry | Full-tuple CAS | One winner | Losers no effect I/O |
| Sleep/clock discontinuity | Boot-scoped monotonic + marker | One coalesced window from observed now | No catch-up or deadline extension; wall is display-only |
| Rebooted ordinary claim | Boot mismatch + fresh identity | Supersede and recompute | In-flight same effect reconciles |
| Invalidation before intent | Intent CAS predicate | No lifecycle I/O | Successor request |
| Invalidation after intent | In-flight phase | Complete `supersede_pending` + fenced help | Archive same effect; atomically consume exact successor |
| Lease temp/final fault | Exact publication proof | Retry same effect or terminal conflict | No active pointer precommit |
| Graph partial/ambiguous | Four-way fresh resolver | ABSENT/CONFLICT/UNAVAILABLE | Only ABSENT writes |
| Resolver remains `UNAVAILABLE` | Attempt + monotonic budget | Persist same-effect help due; release common lock | Event/startup/host retry; no new effect |
| Certificate mismatch | Fresh graph + lease recomputation | TERMINAL/RED | No rollback claim |
| Reference publication crash | DB-before-external order | Conservative retention | Exact resume |
| Active pointer loss/conflict | Reference + committed proof | Rebuild exact / RED conflict | Pointer never commit proof |
| Notice race/repeat storm | Separate notice CAS + persisted progression | FULL -> COMPACT1 -> COMPACT2 -> QUIESCENT; bounded work | Guidance is non-authoritative; delivery not claimed |
| Host queue starvation | Oldest-due wait + persisted cursor | RED at threshold; no skipped tail | Stable tie-break; >8 continuous queue qualification |
| Dead root-bearing event before due index | Exact durable source evidence | Seed/resolve exact episode only | Without evidence await fresh identity |
| Unknown/no-event tool | Registry/event inventory | Deny if event; unsupported if none | Rollout blocked for claimed surface |
| False duration-protection claim | Structural/message corpus | Test failure; no shipping | Invocation-start only; admitted tool may finish |
| `beforeReadFile` pre-read | Official timing | Deny model admission only | Local read residual stated |
| Shared child identity missing | Child root-bearing event | Deny | Never inherit parent |
| Ambiguous Task mode | No pre-spawn discriminator | Deny | Shared capability/UAT only |
| Malformed permission response | Contract/fixtures | Never emitted intentionally | Valid deny or exit 2 |
| Hook/runtime absent | Dead-man observer | Platform may fail open; RED later | Cannot self-report in real time |
| DB profile/version mismatch | Every-connection readback | No write; UNAVAILABLE read | Repair binding/profile |
| No-follow unavailable | C0-D1/bootstrap proof | NO-GO | Audited binding required; stdlib-only and a weaker v1 claim are rejected |
| Writer skew/scope violation | Append-only epoch/capability/auth/receipt + authorizer/triggers | Transaction abort; DORMANT/DRAINING/RED | Make old binary uninvocable; no ambient SQL |
| Rescue authorization mismatch/replay | Immutable plan/items + one-use bound consent | No mutation | Re-plan or Cancel; no retarget/second use |
| Rescue preservation/restore failure | Durable predicates/proofs | Protected artifact; non-green target | Source preserved |
| Rescue Git escape | Closed command/config/env/sandbox malicious fixtures | Stop before materialization | No hooks/filters/helpers/prompts/network/scripts |
| Rescue egress leak | Closed serializer + negative corpus | Suppress bounded branch; RED | No roots/IDs/files/secret metadata/prompt/tool/env |
| Rescue handoff lost/never opened | Durable internal handoff + exact `Rescue` status | `AWAITING_TARGET_ENTRY`; no replay/delete | Manual retry or one state-specific safe action |
| Rescue rollback | State-specific drain/hold matrix | Proof/artifact/target retained | No deletion in any rescue state |
| GC/retention race | Shared generation + reservation/hold/reference triggers | Live owner or GC wins, never both | Journal resume; terminal marker/barrier required |
| GC cross-device move | `st_dev`, `EXDEV`, copy journal | Explicit copy/fullsync/hash/dir-sync/unlink flow | Source retained until destination durable |
| Alert/notice conflation | Component transition generation + cause fingerprint | Independent alert event | Notice epoch correlation only |
| Unknown gate reason | Closed reason FK/catalog | Refuse emission; RED | Add through reviewed protocol revision |
| Hard power loss | Custom VFS + disposable VM | Must match crash matrix | No claim before proof |
| Same-user tampering | Ownership/hash/integrity observation | RED when detected | Residual |

## 7. Acceptance-test ledger

| ID | Requirement | Required proof | Milestone |
|---|---|---|---|
| A01 | Canonical encoding/framing | Golden RFC8785/no-LF semantic and +LF file vectors; duplicate/float/NaN/unknown/oversize/Unicode/decimal64 rejection | M1/M2 |
| A02 | Identifier definitions | Golden root-set/member/episode/request/effect/lease/certificate vectors; one-bit changes bite | M1 |
| A03 | Dedicated store/profile | Closed absent/empty/valid/partial/foreign/symlink create/reopen matrix; schema fingerprint; DB/WAL bootstrap full-sync; SHM rebuildable-only; 0700/0600; CLI/legacy cannot write | M1/M2 |
| A04 | Atomic no-follow resolution | Fd-anchored resolver and audited SQLite binding/VFS survive alias/symlink/swap/sidecar races with owner/type/dev/inode recheck; no lexical pre-exclusion | M1/M2 |
| A05 | Strict DDL/writer control | Executable STRICT DDL on minimum SQLite; every composite member/version/epoch FK, phase/rescue/notice/terminal/completion trigger; authorizer + direct-SQL writer x operation x table x transition matrix; one-use same-transaction auth | M1/M2 |
| A06 | Canonical member authority | Overlapping/reordered root sets share member id/version; root-set changes do not clone physical truth | M1/M2 |
| A07 | Immutable episodes/requests | Identity rows never update; successor creation preserves history; display projection cannot grant authority | M1/M2 |
| A08 | Deterministic request/effect/action | Lost ack/retry/reboot/helper storms yield one request/effect and every lifecycle/rescue/GC action converges from frozen inspect-before-apply postcondition | M1/M2 |
| A09 | Claim atomicity | Window/token/boot/expiry/next_due/wake write together; losers perform zero effect I/O | M1/M2 |
| A10 | Clock/sleep/reboot | Boot-scoped monotonic expiry/backoff; wall display-only; missed windows coalesce once at `observed_now+backoff` without extension; reboot fresh identity; in-flight same effect | M1/M2 |
| A11 | Intent barrier/retention | Fault every point around B2/CAS; effect parent, action postconditions, retention object and live hold commit together; no disk/graph I/O before exact intent | M1/M2 |
| A12 | Invalidation/terminal fence | Before-intent invalidation denies I/O; after-intent sets complete pending tuple; terminal CAS compares all fences, archives old result, atomically preserves/consumes successor | M1/M2 |
| A13 | Lock/retention graph | Instrumented lifecycle/rescue/GC order proves no DB writer waits on filesystem locks, no two common-dir locks, and reservation cannot cross any live hold/reference | M1/M2 |
| A14 | Immutable lease publication | EINTR/short/zero write, chmod, fsync/fullsync, link, existing exact/conflict, temp cleanup, directory sync | M1/M2 |
| A15 | Postcommit active pointer | No precommit active name; exact committed recovery rebuilds; conflict never overwritten | M1/M2 |
| A16 | Relational closure | Missing/extra/gapped/divergent graph, completion seal, phase, terminal archive, rescue plan/auth/artifact/target/restore proof, notice/retry, and wrong writer/direct SQL all fail | M1/M2 |
| A17 | Four-way resolver | COMMITTED/ABSENT/CONFLICT/UNAVAILABLE exhaustive; only ABSENT writes; ambiguous COMMIT close/reopen; budget exhaustion releases lock and schedules same-effect help | M1/M2 |
| A18 | Certificate/helper/postconditions | Certificate derives only from fresh graph + lease; every effect-class helper converges after CAS/ack loss without duplicate apply or replacement effect | M1/M2 |
| A19 | Crash/recovery matrix | Every §4.8 and postcondition boundary, startup dead-event branch, GC EXDEV/copy/tombstone, and rescue state edge reaches exactly its result across restart | M2 |
| A20 | Admission vector/duration | Model invalidation before/between/after B1/E/B2; allow only exact V1=V2 relational proof; negative proof rejects any duration reservation/revocation claim | M1/M2 |
| A21 | Aggregate/overlap | Every eligible member exact, no rescue active; partial/conflict/unknown overlap remains non-green | M1/M2 |
| A22 | All-tool deny | Every official, observed, fixture, renamed, unknown, and no-event surface classified honestly; no diagnostic exception | M1/M2/M4 |
| A23 | MCP/read timing | Both MCP seams gate; `beforeReadFile` tests prove only model admission claim | M1/M2/M4 |
| A24 | Serializer/reason catalog | Valid JSON/exit-2 only; invalid/wrong-shape never relied on; basis unstable/timeout, unknown discriminator, protocol/parser/fallback/emergency reasons each map status/wake/action/consequence/recovery | M1/M2/M4 |
| A25 | Shared child | Parent launch gate; child distinct identity and own episode; optional fields absent; first tool deny then exact allow | M1/M2/M4 |
| A26 | Isolated/ambiguous Task | No pre-spawn mode means deny; v1 has no isolated allow; any future revision requires complete separate UAT | M1/M4 |
| A27 | Notice/fairness/startup | Notice CAS progresses FULL/COMPACT1/COMPACT2/QUIESCENT with bounded restart/compaction work; non-authoritative stop guidance; oldest-due persistent cursor prevents starvation above eight; exact-evidence startup seed only | M1/M2 |
| A28 | Rescue consent/egress | Exact literals and attachment absence; immutable canonical plan/items; auth binds incarnation/conversation/generation/event/expiry/secret scope/digest and consumes once; negative bounded-output leak corpus | M1/M2/M4 |
| A29 | Rescue preservation/security | All at-risk content/index/op state/refs/objects retained and source byte-identical; closed plumbing/config/env/sandbox profile defeats malicious hooks/filters/helpers/includes/prompts/rewrites/network/scripts | M1/M2 |
| A30 | Rescue target/handoff | Source != canonical reserved target; durable internal handoff; exact `Rescue` status handles lost instruction/restart/never-opened; registration before restore; RESTORING non-green; final proof exact | M1/M2/M4 |
| A31 | Rescue exhaustive matrix/rollback | Every state x event x predicate/crash edge, CAS loser/duplicate/restart and R01-R20 output exact; one safe rollback action for five named states; no deletion | M1/M2 |
| A32 | References/retention/GC | Intent-time holds; terminal collectible marker; all live holds block reservation; same-device per-root trash; journaled cross-device copy/fullsync/hash/dir-sync/unlink; barrier+tombstone last; no scan-delete | M1/M2 |
| A33 | Writer drain/rollback | Closed writer x operation x table x transition cross-product; no ambient/direct SQL or post-drain NORMAL commit; rescue-state drain and all proof/runtime retained | M1/M2 |
| A34 | Integrity/alerts | Observer never grants admission; alert identity uses independent component generation/cause fingerprint, notice only correlation; accepted-not-seen; all-alert-fail RED | M1/M2 |
| A35 | Guard/finish/cleanup parity | Exact behavior/bytes unchanged with every registration/rescue/protocol state and engine on/off | M2 |
| A36 | Custom VFS faults | Sync/order/torn/WAL/SHM/ENOSPC/EIO/busy/ambiguous-COMMIT injections match resolver/matrix | M2 |
| A37 | Hard-power durability | Disposable-VM power cuts at every durable boundary match retained state and recovery | M2 |
| A38 | Latency/resources/liveness | p50/p95/p99 admission/registration/resolver, maximum queue wait/starvation, tick/battery, DB/lease/artifact/GC growth measured against accepted bounds | M2 |
| A39 | Evidence labeling | Reports distinguish official, observed, bounded-model, temporary, inferred, and unproved claims | M1-M4 |
| A40 | Scope and governance | C0-DESIGN uses exact hashes/review/finding dispositions/verifier adjudications+coverage/acceptance/baseline/GO but not shipping clearance; C1-SHIPPING exact-head evidence/no findings/partial_rollout=false/shipping approval; every downstream owner gate enforced; protected artifacts unchanged | M0-M4 |

No test may pass by weakening a parser, skipping a race/crash/sync, sleeping
past contention, treating missing evidence as green, using malformed output as
the expected block, inferring child identity, mutating the rescue source,
claiming duration-long admission, leaking rescue identifiers, allowing
repository execution/network, scanning to authorize delete, starving a queue,
or changing accepted guard/finish/cleanup behavior.

## 8. Review provenance and C0-DESIGN protected axes

The source-confirmed findings that caused this documentation revision have the
following draft dispositions. `resolved_in_draft_text` means only that the
normative documents now state a closed design and tests; it does not mean
implemented, proved, independently reviewed, verifier-adjudicated, accepted,
or shipping-cleared.

| ID | Finding | Draft disposition | Normative closure |
|---|---|---|---|
| F01 | Effect replay postcondition | `resolved_in_draft_text` | §4.3 action relations, §4.5 inspect/apply loop, §4.7 class matrix, A08/A18/A19 |
| F02 | Rescue/GC coordination | `resolved_in_draft_text` | One retention generation, explicit holds/releases, shared lock order, terminal marker/barrier, §4.13, A13/A32 |
| F03 | Admission-duration reservation | `resolved_in_draft_text` by explicit rejection | Invocation-start B2 only; admitted tool may finish; negative proof A20 |
| F04 | Supersede terminal fence | `resolved_in_draft_text` | Full-tuple helper CAS, immutable result archive, atomic pending-successor consume, A12 |
| F05 | Clock mapping | `resolved_in_draft_text` | Boot monotonic only, wall display-only, discontinuity coalescing, reboot/fresh identity, no extension, A10 |
| F06 | GC live effects | `resolved_in_draft_text` | Intent-time retention hold; complete terminal marker; all live holds fence reservation, A11/A32 |
| F07 | Writer control plane | `resolved_in_draft_text` | Append-only declarations/capabilities/auth/receipts/use; operation matrix; same-transaction one use, A05/A33 |
| F08 | DDL closure | `resolved_in_draft_text` | Executable STRICT schema/triggers/composite FKs and direct-SQL matrix, §4.3/A05/A16 |
| F09 | Rescue relational closure | `resolved_in_draft_text` | Immutable plan/items/auth/use/artifact/target/registration/restore/completion + transition trigger, A16/A28-A31 |
| F10 | Bootstrap/sidecars | `resolved_in_draft_text` | Create/reopen matrix, fingerprint, DB/WAL sync, SHM non-authority, §4.2/A03 |
| F11 | GC trash | `resolved_in_draft_text` | Same-device per-root trash; explicit journaled cross-device copy/verify/unlink, §4.13/A32 |
| F12 | Atomic path resolution | `resolved_in_draft_text` | Trusted-base fd walk, retained descriptors/recheck, post-resolution policy, audited SQLite binding/VFS, §4.2/A04 |
| F13 | Writer operation scopes | `resolved_in_draft_text` | Closed writer x operation x table x transition authorizer+trigger matrix, A05/A33 |
| F14 | Rescue consent | `resolved_in_draft_text` | Canonical plan/inventory; source/conversation/generation/nonce/attachment/expiry/literal/secret/digest binding; one-use CAS, A28 |
| F15 | Rescue state closure | `resolved_in_draft_text` | Source != target; canonical target reservation; complete predicates for `REGISTERED`, §4.3/§4.12/A30-A31 |
| F16 | Rescue no-exec/no-network | `resolved_in_draft_text` | Closed plumbing command/config/env/sandbox profile and malicious fixtures, §4.12/A29 |
| F17 | Rescue egress | `resolved_in_draft_text` | Closed bounded opaque schema and negative leak corpus, §4.12/A28 |
| F18 | `UNAVAILABLE` resolver | `resolved_in_draft_text` | Bounded attempts/time; release lock; same-effect help due; event/startup/host retry, §4.7/A17 |
| F19 | Rescue matrix | `resolved_in_draft_text` | Exhaustive state/event/predicate/crash table with CAS/duplicate/restart/artifact/target/registration/restore/output tests, §4.12/A31 |
| F20 | Manual handoff | `resolved_in_draft_text` | Durable internal handoff; exact `Rescue` status; lost/restart/never-opened non-destructive state/alert, A30 |
| F21 | Rescue rollback | `resolved_in_draft_text` | Five-state proof-preserving one-action table; no deletion, §4.12/A31/A33 |
| F22 | Host fairness | `resolved_in_draft_text` | Oldest-due stable key, persistent cursor, maximum wait/RED, continuous >8 test, §4.10/A27/A38 |
| F23 | Notice repeat | `resolved_in_draft_text` | Persisted FULL/COMPACT1/COMPACT2/QUIESCENT CAS; bounded attempts/restart/compaction; non-authoritative guidance, A27 |
| G01 | C0/C1 split | `resolved_in_draft_text` | §3, Milestone 0, C1 checkpoint, §9, A40 |

The fresh independent review must cover the complete ADR and plan, not only
the diff or spike summaries:

| Axis | Required adjudication |
|---|---|
| Authority/linearization | Relational source of truth, intent barrier, action postconditions, terminal fence, aggregate vector, invocation-start-only admission |
| Concurrency | Claim/invalidation/helper/overlap/notice/fairness/rescue/GC schedules, retention generation, and lock graph |
| Durability | SQLite/bootstrap/sidecars, no-follow binding, lease, resolver budget, retention/GC copy, custom VFS, hard power |
| Security/privacy | Atomic path ownership, writer operation scopes, JCS parser, rescue consent/no-exec/egress, same-user residual |
| Cursor platform | Exact schemas, fail modes, tool inventory, MCP/read ordering, shared/isolated children |
| Operator safety | Exact rescue dialogue, source immutability, artifacts, manual handoff, no-go taxonomy |
| Migration/rollback | Writer inventory, old binaries, drain closure, no down-migration/proof loss |
| Independent boundaries | Guard, finish, cleanup, kernel-off, integrity, host ownership |

The verifier must receive the exact-hash review evidence, independently
adjudicate every candidate finding, reproduce disputed/high-risk claims, and
record `critical_coverage=true`, `probe_blind=true`, and
`revision=true`. C0-DESIGN consumes those findings, adjudications,
and coverage fields. It does not consume `shipping_clearance`; before
implementation that field is expected failed or not evaluated. Silence,
unavailable evidence, bounded-model success, this ledger, or author
self-review is NO-GO.

## 9. Owner gates

### Documentation acceptance

The 2026-09-26 owner record satisfies C0-D1 through C0-D8 only. The owner must
still explicitly accept ADR 0025 and separately accept this exact v2 by their
externally recorded hashes after the complete independent critical review,
source-confirmed finding dispositions, verifier candidate adjudications, and
required coverage flags are complete. Acceptance freezes v2 and records frozen
v1 as superseded in the plan index only; v1 bytes never change.

### Implementation GO

After every other C0-DESIGN element is satisfied, a qualifying instruction is:

```text
GO to implement ADR 0025 using native-entry-durable-registration-v2
from <exact-authorized-base-oid>; C0-DESIGN evidence is <evidence-id>.
```

Generic approval, this drafting authorization, a PR action/comment, green
checks, or document acceptance is not implementation GO.

### Delivery hold

Implementation GO authorizes only approved implementation bodies, local
verification, disposable/local pre-shipping UAT, and new Draft/unarmed PRs.
PR readiness, merge, release, tag, Skills binding, installation, Dev host
rows, local-jobs activation, live state, live Desktop UAT, and rollout each
require exact-head C1-SHIPPING plus that action's separate named owner gate.

### Current NO-GO

While this plan is draft or any C0-DESIGN element is absent, leave source,
contracts, tests, versions, runtime, hooks, jobs, host wiring, state, PR #175,
GitHub metadata, release/install surfaces, Dev, Skills, primary, no-touch
roots, accepted ADRs, and frozen v1 unchanged. After implementation begins but
before C1-SHIPPING, keep every implementation PR Draft/unarmed and every
delivery/live-rollout surface unchanged.

## 10. Unsupported residuals and non-goals

Unsupported even after successful implementation:

- total hook/runtime plus host-supervisor absence;
- an unknown surface that emits no hook event;
- `beforeReadFile` local disk read before model gate;
- isolated children in v1; any future support requires a separate accepted
  revision and proof;
- cloud early turns and environments without user hooks;
- no documented exactly-once event, ordering, timer, detached lifetime, or
  pre-spawn Task mode;
- no duration-long reservation and inability to revoke or stop an
  already-admitted tool (accepted invocation-start invariant, not an
  implementation gap);
- Tab/manual/external/unhooked work;
- same-user tampering;
- proof that a notification was seen; and
- hardware/storage behavior beyond the exact tested envelope.

Non-goals:

- Global `failClosed:true`, malformed-output reliance, daemon dependency,
  network admission, paid GitHub Actions runners, or integrity as a gate.
- Registration of primary, excluded, detached, ambiguous, nonlocal/cloud, or
  unsupported submodule/gitlink/LFS/filter roots.
- Treating ordinary admitted branch/HEAD/content work as structural
  invalidation.
- Child identity inferred from parent/task/session/call/branch metadata.
- Cleanup authority, autonomous deletion, destructive source repair, guard
  relaxation, or finish authorization changes.
- Release, install, host wiring, Skills binding, live UAT, PR #175 mutation,
  or any GitHub mutation during this documentation task.

## 11. Review provenance and remaining risk

This rewrite integrates:

- the revised bounded linearization model;
- the dedicated SQLite/APFS durability spike;
- official and observed Cursor event/child evidence; and
- the dirty/in-progress rescue design; and
- the 23 source-confirmed concurrency, durability, authorization, security,
  reliability, and operator findings dispositioned in §8.

It removes the old mutable aggregate authority, paired-CAS clauses,
diagnostic reads, contractual malformed-JSON claim, mutable active lease, and
indefinite dirty stop. It does not claim those replacements are independently
cleared. It also replaces circular C0 language with pre-implementation
C0-DESIGN and post-implementation exact-head C1-SHIPPING.

No implementation, custom-VFS, hard-power, complete-tool, isolated-child, or
live rescue proof exists. The owner choices now require an audited no-follow
binding, no v1 `PERSIST+EXTRA` fallback, the explicit accepted rescue policy,
and only positively proved shared-child support after UAT. Fresh independent
review and verifier candidate adjudication/coverage remain mandatory;
ADR/plan acceptance, an exact refreshed baseline, and separate implementation
GO remain absent. The verifier's shipping clearance is not a design gate and
is expected failed/not evaluated until an implementation exists. Every new
closure in this draft remains unimplemented and unproved. Implementation
remains **NO-GO**.
