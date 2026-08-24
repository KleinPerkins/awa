# ADR 0020: AWA integrity surveillance and lifecycle — fix entry/lifecycle/observability, never the guard
Status: draft — 2026-08-24

*Plain-language summary: the 2026-08-24 incident proved the shell guard is doing its job — a
mutating command on a protected primary was correctly denied, even the `cd <worktree> && …`
bypass. The real gaps are (1) getting an agent *into* a Safe Workspace when Cursor's external mover
breaks, and (2) that nothing watches AWA's own lifecycle — orphaned worktrees, unreconciled leases,
dangling sessions, and a latent recovery-scan error all accumulated silently. This ADR decides to
add one honest, runnerless integrity evaluator + a single machine-local status of record + loud
alerts + a thin static console, and to fix the entry/lifecycle root causes — while leaving the
guard's safety contract untouched.*

## Context

On 2026-08-24 an agent on `pr-automation-controller` could not commit because Cursor's external
`cursor-app-control.move_agent_to_root` (not an AWA capability) aborted twice, leaving the agent
rooted at the protected primary. AWA then correctly denied `cd <worktree> && git commit`. A
read-only forensic pass (recorded in
[`docs/incidents/awa-integrity-incident-20260824.md`](../incidents/awa-integrity-incident-20260824.md))
found the guard, kernel/engine parity, hook fail-open, MCP/engine adapter parity, and
installed-release identity all **HOLDING**, but found the Safe-Workspace *entry* handshake, the
orphan/lease/session *lifecycle*, *surveillance*, and *alerting* invariants **VIOLATED**: 64
leaseless worktrees, 2 `active` leases whose roots are absent on disk but which are *not* thereby
removal-authorized (pid/boot are diagnostic only — `engine/lease.py:10,49`), 12 dangling in-namespace
session records, and a legacy bare recovery archive whose missing sidecar manifest made
`recover status` report `errors`. The recovery error was cleared by a reversible move into
`recovery/.trash` — which is the deletion-journal namespace, not a durable quarantine (M2 owns a real
quarantine). Overall integrity remains **DEGRADED**.

Cross-repo authority for AWA product statements is ADR 0002 (AWA owns the product; `~/dev` is a host
overlay that points here). Kernel-first safety (engine off the critical path) is the standing
invariant. No paid CI runners are permitted anywhere in the fleet.

## Decision

### 1. The guard's safety contract does not change — fix entry, lifecycle, and observability instead

Guard behavior is **correct** and stays byte-for-byte as-is: a mutating command on an INCLUDED
PRIMARY denies; linked/leased/cloud allow; classification is against the Cursor session root, and an
in-command `cd` never moves it. This ADR introduces **no** lease-aware relaxation, **no** path-pattern
allowance, **no** `cd`-into-worktree carve-out, and nothing that could downgrade a protected-primary
deny. Kernel-first is preserved: everything added here is **engine-side** and never sits on the
kernel guard's critical path; the guard keeps working with the engine OFF.

### 2. One evaluator, one trigger interface, one commit per evaluation

Add a single integrity subsystem backed by **exactly one** evaluator (`engine/integrity.py`) with a
**single registry + reducer** mapping invariant → check. Every consumer runs it through **one CLI
execution interface**:

```
awa-engine integrity verify --profile fast|deep --trigger cli|beforeShell|stop|launchd
```

**One evaluation produces exactly one *evaluation* commit** (§3) that carries that trigger's
`attempt/success/error` **and** the result — there is **no** separate trigger-only commit. (A later
alert *receipt* is a distinct typed **bookkeeping** commit under the same transition id, §6 — it
re-evaluates nothing and raises no new alert.) The default CLI profile may
be `deep`; the `beforeShellExecution`/`stop` hook wrappers pass `--profile fast` explicitly and the
launchd sweep passes `--profile deep`. An **unexpected evaluator crash propagates**; the expected
`0/1/2` severities are normalized to a successful job **only by the `~/dev` local-jobs wrapper**,
never by AWA.

**Two result profiles.** `fast` = bounded local surfaces only: read current status, hook-row
presence + fail-open, the last alert-delivery result, and read-time freshness; it may **coalesce and
schedule (debounced) a requested deep sweep** but never performs one. `deep` = the exhaustive work:
classifier/parity corpus, lifecycle topology + recovery scan, installed-release provenance, and entry
history. **The `deep` profile never runs on a per-shell hook path.**

### 3. Status of record: a status-last, generation-validated commit protocol

The single source of truth is the operator-fixed path **`~/.local/state/awa/integrity/status.json`**
(private `0600`, in a `0700` dir). It is the **one atomic commit point and the full current
authority**. It is **not** written with `engine.paths.write_private()` (which `O_TRUNC`-truncates in
place — `paths.py:105-117`, neither atomic nor crash-safe). The commit protocol, under a **dedicated
integrity lock** (`fcntl.flock` on `~/.local/state/awa/integrity/.lock`; **never** the shared
`state_root_lock` and **never** any recovery lock — only `_commit()` acquires it):

1. Compute generation `N = prev+1` (and a `transition_id` iff overall severity changed).
2. Build every derived artifact **first** as an **immutable, generation-tagged** private file in its
   own child dir — `history/<N>.json`, `public/<N>.json` (the closed redacted projection),
   `console/<N>.html`, `outbox/<N>.json` — each: `O_EXCL` temp in the same child dir → write all bytes
   → `fchmod 0600` (BEFORE the file fsync) → `fsync(fd)` → `os.replace` to its `<N>` name →
   **`fsync` that artifact's immediate parent child dir** (`history/`, `public/`, `console/`,
   `outbox/`). Any child dir created this pass is `fsync`ed by also `fsync`ing the **integrity root**
   after creation. A later prune/unlink of a superseded generation file likewise `fsync`s that child
   dir after the unlink.
3. Build `status.json` bytes = the full status **plus** `generation`, `transition_id`, and the
   **sha256 + relative path of each committed derived artifact**.
4. **Atomically replace `status.json` LAST**: `O_EXCL` temp in the same dir → write all bytes →
   **`fchmod 0600` BEFORE the final `fsync`** → `fsync(fd)` → `os.replace(tmp, status.json)` →
   **`fsync` the parent dir**.
5. Release the lock, then dispatch alerts (§6, outside the lock).

**Readers ignore any derived artifact whose generation/hash is not referenced by the current
`status.json`.** A crash before step 4 leaves the previous `status.json` valid and merely orphans
generation files (harmless; GC-able later). This is **not** a fictional multi-file atomic
transaction — it is an explicit **status-last + generation-validation** commit. Each committed status
carries a monotonic generation; a non-increasing generation is refused. Schema is versioned
(`awa-integrity-status/v1`).

**Live-SQLite read path.** The evaluator reads AWA's durable SQLite **live** through
`sqlite3.connect("file:{db}?mode=ro", uri=True)` + `PRAGMA query_only=ON` + an explicit read
transaction, so **rows present only in the WAL are visible** and writes are refused. It does **not**
use `immutable=1` (that would hide live WAL commits) and does **not** instantiate the mutating
`engine.state.State()` (whose `__init__` runs `PRAGMA journal_mode=WAL` + `executescript(_DDL)` —
`state.py:132-148`). If a frozen point-in-time snapshot is ever required, use the **SQLite online
backup API**, never `immutable=1`.

### 4. Deterministic invariant → severity mapping, including UNKNOWN

Every invariant resolves to exactly one of `green | degraded | red | unknown`; overall severity is a
deterministic reduction:

- **GREEN** overall ⟺ **all required invariants `green`** **and all required triggers fresh** (§5.1).
- **DEGRADED** = safety intact but an operational issue/action is required; a non-safety-critical
  `unknown` maps to at least `degraded`.
- **RED** = a safety-critical invariant (`guard_safety`, `parity`) is `red`/`unknown`; **or** the
  status is malformed/missing/**stale beyond its freshness bound**; **or** the evaluator crashed;
  **or**, while the state is non-green, **all configured alert paths failed** (§6).

A missing/malformed/stale status is itself non-green; a silent all-paths alert failure while
non-green is RED. **Lifecycle classification uses root existence, Git registration, the canonical
`awa_roots.disposition` (`active|stale|dead|untracked|absent`), the lease file, and pending
journal/recovery ambiguity — PID/boot are diagnostic only.** The `entry_handshake` invariant is
derived **only** from explicit handoff metadata: until M2 handoff receipts exist, entry capability is
`absent | pending | unknown` — **never an invented retry history**. The invariant set is the
incident's verified starter set (guard safety; entry handshake; recovery; lifecycle; parity; hooks;
mcp/engine parity; release identity; surveillance freshness; alert delivery); it grows only by a
superseding ADR.

### 5. Defense in depth: fast fail-open hook triggers + a periodic deep sweep, all runnerless

Two complementary trigger classes drive the one commit (§2), and neither uses any CI runner:

- **Fast, fail-open, observation-only** checks fired from Cursor `beforeShellExecution` and `stop`
  hooks (`--profile fast`). They are debounced/coalesced, never block, never gate safety, and on
  doubt degrade to allow. The `beforeShellExecution` observer runs **fully detached** so it adds no
  latency; the guard continues to own the deny decision and its output is preserved byte-for-byte.
- A **periodic deep sweep** (`--profile deep --trigger launchd`) that runs with no session present.
  **AWA ships the sweep/verify executable and the label/schedule *contract requirements* only — no
  plist template. `~/dev`'s `local-jobs` is the sole desired-state writer/activation owner** of the
  launchd job `com.kleinperkins.awa-integrity` (§8).

**5.1 Freshness** is computed at read time from per-trigger `last_attempt/last_success/last_error`
+ profile + generation. `launchd` (deep) is the required trigger (fresh ⟺ within `DEEP_BOUND`, default
24h); fast triggers are advisory. A stale/absent required trigger ⇒ `surveillance_freshness`
non-green ⇒ overall non-green.

### 6. Loud alerts: always *attempted*, honest about delivery, RED when all configured paths fail

Alerting is transactional and honest:

- On a severity change the evaluation commit publishes the authoritative status transition + an
  **immutable pending `outbox`** entry (the `transition_id`). **Dispatch happens outside the lock.**
- **Delivery is persisted by a separate typed CAS bookkeeping commit**,
  `commit_alert_receipt(expected_generation, transition_id, outcomes)`: it reacquires the integrity
  lock, **CAS-verifies** the current status generation + transition still match, then writes a NEW
  immutable **delivery-receipt** artifact + regenerated projection/console and advances `status.json`
  **status-last** to a **bookkeeping generation under the SAME `transition_id`** with per-channel
  `accepted | failed`. It performs **no re-evaluation, emits no new alert/outbox, and cannot recurse**.
  If the CAS fails (a newer evaluation superseded it) the receipt is **stale/audited and never
  overwrites the newer status**. A transition already `accepted` never re-fires (dedupe by
  `transition_id`); reminders for continued non-green are bounded; no alert about the alert subsystem.
- **The canonical rule: while non-green, failure of ALL CONFIGURED paths is RED.** Native is always
  a configured path and is **always *attempted*** on a flip-to-worse (not "always delivered").
  **If Slack is opted out, native is the sole configured path, so a native failure is RED.**
  `osascript`/Slack exit-ok = **accepted**, never "seen"/"delivered".
- **Fallback is trigger-specific:** a synchronous CLI run additionally writes a **stderr** line;
  local-jobs persists **durable job logs/status**; a **detached hook cannot promise visible stderr**
  — so a hook-triggered all-paths-failed non-green is still recorded RED in the status and surfaced
  by the next CLI/launchd read.
- **Slack transport (opt-in):** a Keychain bot token + a `0600`-config operator Slack user id →
  `conversations.open` → `chat.postMessage` a closed redacted payload → record `accepted|failed`,
  with a **bounded total connect+read timeout**, a **bounded retry count with backoff**, a **capped
  honoring of `429 Retry-After`**, and **no unbounded waits**.

### 7. A lightweight, non-canvas operator interface — a private static HTML console (M1)

The interface is a **private (`0600`), deterministic, self-contained static local HTML console**,
**atomically regenerated as the `console/<N>.html` derived artifact tied to the referenced generation
(§3)**; the in-page reload re-reads the file. The renderer consumes a **closed, redacted public
projection** (overall verdict, per-invariant `{id, severity, redacted_reason}`, bounded recent
history, counts, `last_checked_age`, and a `fresh_until` timestamp) with **no raw evidence, no
absolute host paths, no secrets**. Serialization is script-safe (HTML-escape + JSON-embedding that
escapes `<`, `>`, `&`, U+2028, U+2029); a strict **CSP** with **no remote assets**. The page carries
**one tiny CSP-hashed CLOCK-ONLY inline script** whose sole job is to recompute age from `fresh_until`
and force a **STALE/RED presentation after expiry even if the file was not regenerated** — it embeds
**no other evaluator logic**. **No arbitrary export exists in M1** (M4 owns share-safe export). Not a
Cursor Canvas.

### 8. Cross-repo authority and ownership boundary: AWA owns the product; `~/dev` owns the live host

Per ADR 0002:

- **AWA owns the product contract** — the evaluator, the status/public-projection **schemas and
  contract**, the **sweep/verify executable**, the **hook-compatible product scripts** (the composite
  guard-with-integrity script, the stop/observer script, the session-handoff script, and the Python
  detacher), the **launchd label/schedule contract requirements** (not a plist), and the **console
  renderer**. The AWA installer ships and validates these, but **must NOT `launchctl bootstrap`/
  `bootout` the live host job and must NOT read/stat/write external hook rows** (external mode is
  zero-access — `contracts/awa-contract.v1.json` `external_real_hook_file_writes:false`).
- **`~/dev` is the sole live host projection/owner** — it writes the external `beforeShellExecution`/
  `stop`/`sessionStart` hook rows (as host-policy-delegators calling the installed AWA roles), holds
  machine config/secrets, and uses **`local-jobs`** as the sole desired-state writer that
  registers/activates `com.kleinperkins.awa-integrity`. It **points here** for the product contract.

**Hook-owner successor is a concrete, separate product artifact.** A new file
**`contracts/awa-hook-owner.v2.json`** (schema `awa-hook-owner/v2`) adds the composite-guard,
stop-observer, and session-handoff roles; **the existing `awa-contract.v1.json` bytes remain
untouched** (its embedded `awa-hook-owner/v1` block still describes the five frozen roles). The
updated product installer/checks **prefer and validate v2 when shipped** while **retaining explicit
v1 compatibility tests**. The **direct** installer may project v2 rows; **external** mode stays
zero-access and only exposes/validates product role metadata.

**Release/wiring sequence (independent governed PRs, never atomic):** AWA product release/tag → AWA
install → **Skills Flavor-2 pin at `global/tools/awa` only if the current ecosystem requires it for
install** (it is discoverability-only, WF1-enrolled, no cpp-sync — confirm at release time; update
for catalog accuracy via its own `KleinPerkins/skills` PR if needed) → `~/dev` host PR(s) → activation
+ UAT.

**Cross-repo profile is PROPOSED, not live.** `awa-integrity` **is not registered** in
`~/dev/_ops/doc-warden/cross-repo-profiles.yml` (verified: only `poc3d` exists, and its topics do
not include the integrity topics, so `poc3d` cannot be reused). The trailer below declares the
intended id `awa-integrity`, but it has **no enforcement** until a separate `~/dev` Docs PR registers
the profile and adds the dependent-side pointer. No duplicate authority.

### 9. Lifecycle is read-only reconciliation, never boot/pid GC

Because durable leases survive process/boot by design (`engine/lease.py:10,49`), the M2 lifecycle fix
is a **read-only classify/report** module **`engine/lifecycle_reconcile.py`** (distinct from the
existing `engine/lifecycle.py`, which does adopt/attest/publish/retire). It consumes the canonical
`awa_roots.disposition` (`kernel/lib/awa_roots.py`: `active|stale|dead|untracked|absent`), emits only
`retire_candidate` / `adopt_candidate` classifications across separate dimensions (topology, content
safety, activity, cached-remote redundancy), and **never mutates the DB or worktrees**. Any actual
mutation is a **separate, explicitly operator-authorized, digest-bound** `integrity repair plan|apply`
with exactly two action kinds: **`retire-bookkeeping`** (for a fully-proven absent + Git-unregistered
lease row: re-checks the exact evidence, holds the **stored `git_common_dir` lock**, updates the
SQLite lease status **only** with audit/rollback metadata — it does **not** call
`engine.lifecycle.retire()`, which no-ops without an on-disk lease, and it **never removes a
path/ref**) and **`remove-worktree`** (routes through the existing `clean --path` active-root /
content / recovery / kernel gates). A durable row is a `retire_candidate` only when root **absent** AND
unregistered AND non-`active` disposition AND no live session AND no pending journal/recovery
ambiguity AND no on-disk lease/worktree path;
`chaos-scheduler` is a hard no-touch via a **generic** predicate (host config supplies the path).
**No autonomous deletion.** The periodic path stays zero-network.

## Why

- **Weakening the guard (rejected — evidence-refuted).** The incident shows the guard *correctly*
  denied a real mutate-the-primary attempt via `cd <worktree> && git commit` (C1–C3). The problem was
  *entry* and *observability*, not the guard; relaxing it would re-open the mutation class AWA exists
  to prevent.
- **`immutable=1` on the read snapshot (rejected — source-checked).** `immutable=1` tells SQLite the
  file cannot change and to ignore the WAL, so a row committed only to the live WAL would be **invisible**
  to the evaluator — it could read a stale DB and mis-score green. `mode=ro` + `query_only=ON` + a read
  transaction reads the live database correctly and refuses writes.
- **A fictional multi-file atomic transaction (rejected).** POSIX gives one atomic `rename`, not an
  N-file transaction. The honest design is status-last: derived artifacts are written first and only
  become authoritative when the single atomic `status.json` replace references their generation+hash;
  a crash just orphans harmless generation files.
- **Reusing `engine.paths.write_private()` or `state_root_lock` for the status store (rejected —
  source-checked).** `write_private` truncates in place (`O_TRUNC`, no fsync/rename); `state_root_lock`
  serializes a different subsystem (leases/recovery), so sharing it would couple integrity liveness to
  recovery contention and risk recursive-lock deadlock when the evaluator reads recovery state. A
  dedicated store + dedicated lock owned **only** by `_commit()` is the minimum honest design.
- **A second trigger-only commit / wrappers taking the lock (rejected).** Two commits per evaluation
  or a wrapper acquiring the integrity lock invites lost updates and recursive-lock deadlock. One
  evaluation → one commit; only `_commit()` locks.
- **Instantiating `State()` from the read path (rejected — source-checked).** `State.__init__` runs
  DDL + WAL PRAGMas (`state.py:144-148`); a "read-only" evaluator that constructed it would mutate the
  DB it audits.
- **AWA shipping a launchd plist template / activating the job (rejected — ownership).** Per ADR 0002
  the live host projection belongs to `~/dev`; AWA shipping/activating a plist would duplicate host
  authority and could stomp the operator's launchd/hook state. AWA ships the executable + a label/
  schedule contract; `local-jobs` owns desired state.
- **`install-hooks` rendering external rows (rejected — source-checked).** `awa-hook-owner/v1`
  mandates `external_real_hook_file_writes:false`; external mode performs zero reads/writes of the
  hook file. `~/dev` alone writes external rows; the direct installer projects v2.
- **"Always delivered" alert language (rejected).** `osascript`/Slack success means the request was
  *accepted*, not seen. The honest contract is "always attempted", per-channel `accepted|failed`, and
  RED when all configured paths fail while non-green — with Slack opt-out making native the sole
  configured path.
- **Interface: `chaos-scheduler` reuse / menu-bar / Tauri / a persistent M1 server (rejected).**
  `chaos-scheduler` is a permanent no-touch; a tray/Tauri app or a standing server is unnecessary
  runtime/attack surface for a rendered snapshot. A self-contained static HTML file with a tiny
  clock-only script gives an honest, self-staling view with zero runtime. An **ephemeral on-demand
  loopback server is a deliberate M3 increment** (random per-launch capability token, exact
  `Host`/`Origin`, no CORS, POST-only re-run of the same evaluator, idle shutdown).
- **Boot/pid lifecycle GC or classify/report that mutates (rejected — source-checked).** Durable
  leases survive boot (`lease.py:10,49`); disposition is canonical (`awa_roots.disposition`).
  Reconciliation classifies read-only; mutation is a separate operator-authorized verb through kernel
  gates.
- **GitHub Actions / any paid runner (rejected — hard constraint).** Local `local-jobs` launchd +
  fail-open hooks cover the machine-local reality with no runner.
- **A new framework / speculative second-consumer generality (rejected — YAGNI).**

## Consequences

- **Enables:** an honest, fresh, machine-local integrity verdict written by one status-last commit;
  a correct **live-WAL** read path; loud native (and opt-in Slack) alerts that are always *attempted*
  with recorded results and RED-on-all-fail; a zero-runtime self-staling private static console; a
  `view/verify/console`(+`sweep`) verb family; a read-only lifecycle reconciliation path; and a clean
  hand-off of host wiring to `~/dev`.
- **Forecloses:** any guard relaxation; `immutable=1` reads; `write_private`/`state_root_lock` for the
  status store; any lock acquisition outside `_commit()`; a second trigger-only commit; reuse of
  `chaos-scheduler`; any paid runner; any auto-deletion of a worktree/lease on pid/boot evidence; any
  AWA-installer activation of the host job or access to external hook rows; any AWA plist template; any
  consumer treating stale/missing/malformed status as green; "always delivered" alert claims.
- **Must stay true:** kernel-first; one evaluator + one trigger interface + one *evaluation* commit
  per evaluation (a delivery receipt is a separate typed CAS bookkeeping commit under the same
  transition id, never a re-evaluation); status-last + generation validation; live-WAL `mode=ro`+`query_only` reads that never construct
  `State()`; only `_commit()` holds the dedicated integrity lock; the `deep` profile never runs
  per-shell; while non-green, all-configured-paths-failed ⇒ RED; every destructive lifecycle action
  goes through existing kernel gates; AWA owns the product, `~/dev` owns live host wiring.
- **Verb hygiene:** M1 registers **only** `integrity view`, `integrity verify`, `integrity console`
  (render/open), and `integrity sweep` **iff** local-jobs needs a dedicated entry (otherwise local-jobs
  calls `verify --profile deep --trigger launchd`). Both `view` and `verify` return exact **0/1/2 =
  green/degraded/red** (missing/malformed/stale ⇒ 2). `repair`/`export` are **prose-reserved and NOT
  registered** (a stub exiting 2 collides with RED). M2 defines `integrity repair plan|apply`; M4 owns
  `export`.
- **Defers/creates (to the plan):** milestone sequencing, exact schema/projection fields, the
  invariant→check matrix, the `awa-hook-owner.v2.json` roles + composite/detacher scripts, the
  read-only `lifecycle_reconcile` module, the digest-bound recovery **quarantine** verb + `.trash`
  migration, the session-handoff role/script, biting fault injection, the exact **two** `~/dev` PRs,
  and release/bind/install verification — all in
  [`docs/plans/awa-integrity-surveillance-and-lifecycle-v1.md`](../plans/awa-integrity-surveillance-and-lifecycle-v1.md).
  Cross-links: ADR 0001 (guard doctrine, unchanged), ADR 0002 (authority), and the incident record.

## Live-state verification record

Verified 2026-08-24 against installed AWA `v1.5.2` `a2b13f7e` (release-identity, not a drift proof):

- Guard verdicts (`awa_guard_shell`): primary + `git commit` → `deny/include`; primary +
  `cd <worktree> && git commit` → `deny/include`; linked worktree + `git commit` → `allow/worktree`
  (`engine/guard.py:918-967`, `kernel/hooks/worktree-guard.sh:1142-1204`).
- Store/State facts (§3): `engine/paths.py:105-117` (`write_private` `O_TRUNC`, non-atomic);
  `engine/state.py:132-148` (`State.__init__` runs DDL + WAL PRAGMas). Lock ABI: `engine/lock.py`
  (`state_root_lock`/`lockfile_for` — the shared recovery-maintenance lock; the integrity store uses a
  separate dedicated lock).
- Recovery/quarantine facts (§9 / plan M2): `engine/retention.py` (`_TRASH_DIRNAME=".trash"`, reconcile
  globs only `*.deletion.json`, maintenance under `state_root_lock`), `engine/recovery.py:353`
  (`list_artifacts` skips `.trash`), `contracts/awa-contract.v1.json:367` (`.trash` = transient
  deletion-journal).
- Disposition (§9): `kernel/lib/awa_roots.py` (`awa_roots.disposition`: `active|stale|dead|untracked|
  absent`), `contracts/awa-contract.v1.json:339` (ONE source of truth). `engine/lifecycle.py` already
  exists (adopt/attest/publish/retire) → the new module is `engine/lifecycle_reconcile.py`.
- Hook-owner facts (§8): `contracts/awa-contract.v1.json` `hook_ownership` = `awa-hook-owner/v1`, five
  roles, `external_real_hook_file_writes:false`, `external_rule` (external mode never touches the hook
  file); `kernel/hooks/install-hooks.sh:29-41` (external early-exit, zero-access).
- Cross-repo profile (§8): `~/dev/_ops/doc-warden/cross-repo-profiles.yml` = only `poc3d` (no
  `awa-integrity`). Interface non-goal: no Cursor Canvas; `chaos-scheduler` permanent hard no-touch.

**Cross-repo profile:** awa-integrity
**Dependent repo:** dev
**Topic ids:** integrity-sot,integrity-invariants,runnerless-surveillance,host-trigger-wiring,safe-workspace-entry,operator-interface
