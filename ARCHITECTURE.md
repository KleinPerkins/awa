# AWA — architecture: one generic product, kernel-first, engine off the safety path

> The design invariant for Agent Worktree Automation (AWA). The machine-checkable BEHAVIOR
> surface is pinned in `contracts/awa-contract.v1.json`; this document is the prose record of
> the principle those pins defend.

## The re-founded principle

**AWA ships as ONE self-contained product — a generic KERNEL and a generic ENGINE, BOTH in
`KleinPerkins/awa`, BOTH zero-link.** Every org/host-specific literal (which repos are governed,
which paths are read-only, where worktrees live) lives ONLY in a host-supplied **policy overlay**
(`AWA_POLICY`), never in the product. A host adopts AWA by cloning + `bash ./install.sh`, then pointing
`AWA_POLICY` / `AWA_GOVERNED_ROOT` at its own machine-local policy. The product itself names no
organization, ever.

This replaces the earlier "kernel = host layer, never in this engine" framing. The kernel is not a
host artifact you re-implement per machine — it is generic, ships here, and is installed verbatim.
The only thing the host provides is data (a policy file).

## The kernel-first invariant (unchanged)

**The kernel delivers the full safety guarantee standalone; the engine only observes, bookkeeps,
and eases.** Detection, recovery, cleanup-refusal, and safe lifecycle decisions MUST hold with the
daemon/engine/watcher **OFF**. Nothing the engine adds may become load-bearing for the core
guarantee. The behavior contract is frozen so the engine can be layered *behind* the kernel without
ever regressing a green verifier.

### Root-bound finish: kernel authority, consumer ergonomics

`kernel/lib/awa_finish.py` and `kernel/bin/dev-worktree.sh clean --finish-current` own inventory,
challenge, literal-`Close`, lock, final proof, session, removal, reconciliation, and local
branch-disposition decisions. The private full proof covers every physical object (encoded raw path,
type, mode, size, regular-file hash, link target, grouped-directory descendants, and exact Git
status/index evidence), plus the root and per-worktree Git-admin physical incarnations, with
no-follow before/after identity checks. The challenge also carries a path-granularity proof that
keeps ordered displayed deletion scopes, each row-root type/mode/link target, directory and symlink
descendants, all structure outside displayed directory scopes, Git path/mode/stage structure,
operation state, target identity, and session membership exact. Regular files below an already
displayed directory are opaque contents of that displayed scope; their
creation/removal/rename/mode/bytes and ordinary index blob ids are omitted. Operator output remains
one escaped row per Git item and
exposes none of either private proof. That path imports no consumer/router/engine code and invokes
no network.

Inventory starts with a finish-only index-visibility preflight, before any Git status or physical
tree scan and before challenge creation. It reads SHA-1/SHA-256 index structure and NUL-delimited
`ls-files` tags with fsmonitor disabled, optional locks disabled, and lazy fetch forbidden. Any
assume-unchanged, skip-worktree/sparse, fsmonitor, malformed, ambiguous, or unreadable state maps to
the one generic `index_visibility_flags` refusal; no flagged path or private Git value enters a
projection. Ordinary `clean --path` does not call this preflight and retains its v1 behavior.
The inventory then canonicalizes every supported per-worktree Git operation (merge, sequencer,
rebase-merge/apply, am, bisect, and notes merge). Under the shared lock it descriptor-scans the
selected admin roots twice, recursively and no-follow, and requires byte-identical raw-name-sorted
type/mode/size/SHA-256 records. Git APIs supply `refs/bisect`/`refs/rewritten`; pseudo refs, exact raw
index bytes, conflict stages, worktree dependencies, original branch identity, and operation-rooted
object closure complete the private manifest. Unknown/ambiguous state or any link, special file,
mount, live git lockfile, path escape, or read drift refuses; a foreign non-git top-level `.lock`
(e.g. the ~/dev host `cursor-session.lock` one-writer session marker) is not a git operation and is
ignored, so it never blocks finish. The public projection is only fixed synthetic
operation copy. Recognized detached rebase/bisect binds the original branch and forces retention.
Every finish-local Git child—from the first discovery probe through Retain, reconciliation,
worktree removal, and ref cleanup—drops all inherited `GIT_*` variables, fixes locale and the
no-lock/no-lazy-fetch/no-prompt profile, then uses a no-follow-validated Git-dir/worktree/real-index
binding. Only Commit's contained temporary-index operation may substitute its validated index path.

`consumer/finish_current.py` is a production stdlib conversational adapter:

1. A versioned pure matcher recognizes high-signal direct closeout wording before generic router
   normalization and rejects negated/quoted/meta/hypothetical uses.
2. Preview resolves exactly one local linked-worktree root, calls the Phase-1 inventory/challenge,
   renders immutable warning copy plus Phase-1 escaped rows, and stores `awa_finish_dialogue/v1`
   state keyed by stable conversation id.
3. `sessionStart` eagerly writes an atomic root-bound current identity; the
   first `beforeSubmitPrompt` can bind the same exact payload conversation when
   eager ordering or workspace movement missed it. The guard reuses that
   identity rather than minting an `unattributed` member.
4. The user-level `beforeSubmitPrompt` command hook returns `{continue:false,user_message:...}` only
   after complete preview/index publication. Its private invocation ticket binds the post-output
   publication transition to the exact emitted conversation/session/root/generation/nonce/warning
   digest. Hook challenges start inactive. After a hook-mode Commit/Retain/Mixed action, the action
   CLI persists only `action_complete_refresh_pending`; the next prompt is discarded before
   recognition and used to create the fresh warning, while only the hook's post-output transition
   makes that generation choice-accepting. Thus an exact Close used as the refresh trigger cannot
   act; a second exact Close is required. A later choice candidate creates one atomic envelope
   carrying the submitted bytes, attachment provenance, and additive canonical decision.
   Commit/Retain/Mixed/Cancel canonicalize case-insensitively; Close canonicalizes only from exact
   bytes.
5. `dispatch --current` resolves exactly one root/session/generation, consumes exactly one envelope,
   and activates that same challenge by nonce/generation CAS. Partial/timeout state, reconstruction,
   attachment, replay, ambiguity, and target/row/path/type/mode/link/Git-structure drift cannot
   activate it. For Retain only, regular files below an unselected displayed directory may be
   created, removed, renamed, have modes changed, or be rewritten when the displayed scope and
   non-content structure remain exact and every selected row's content proof still matches. A Close
   casing/trim variant returns a correction without activation. Only exact activated Close invokes the kernel CLI with literal
   authorization plus the envelope's complete expected nonce/generation pair. That pair can name
   only the exact still-current hook challenge; a direct replacement cannot inherit it. Before any shared-lock or destructive
   attempt, the kernel exclusive-creates a nonce/generation-bound `awa_finish_generation_state/v1`
   `close_claimed` record. Every outcome after that claim is one-use; retry requires a fresh preview
   and envelope. One closed typed builder projects every dispatcher result after authorization
   handling: it emits fixed copy and validated outcome/reason/branch values only, never child
   output, exceptions, kernel messages, paths, object ids, hashes, prompt bytes, or extra fields.
   Known inventory drift reasons add only fixed plain-language recovery copy; arbitrary exception
   text remains generic.
   The clean child emits one exact machine-mode JSON shape; extra, malformed, oversized, or
   exit-status-contradictory output is treated as uncertainty rather than parsed heuristically.
   Proven removal reports removal plus agent stop/chat-open truth; proven refusal reports
   preservation; any post-invocation ambiguity reports unknown removal and stops.
   At exact Close, the under-lock full proof may differ only when the under-lock structural proof
   still byte-matches the warning-time proof. This permits a normal hook to create, remove, rename,
   change modes on, or rewrite regular files below an already displayed directory without changing
   the deletion scope that the path-granularity warning authorizes. Every displayed-row
   insertion/removal/reorder/path/root-type/root-mode/root-link change, directory or symlink
   descendant change, structure change outside such a scope, Git path/mode/stage change,
   operation-state change, target/incarnation change, or session-membership change refuses. Legacy
   challenges without the additive structural proof remain full-proof-only. The prepared removal
   journal binds both warning-time and execution-time full proofs so failed-removal recovery
   compares the actual pre-execution tree, not stale warning bytes.
6. Commit's GitHub delivery adapter is the only network-bearing finish component. Retain writes a
   typed protected artifact outside the worktree and verifies a disposable restore under the same
   per-common-dir lock. Its kernel-owned selected snapshot is reused for exact source suppression,
   including complete recursive directory descendants and status/index bytes. Both require a fresh
   preview afterward. Retain infers the source SHA-1/SHA-256 object format, installs proof blobs with
   filters disabled, fsyncs payloads/blobs/directories, restore-proves while unpublished, writes and
   syncs the true manifest while still hidden, then publishes through a content-addressed pending
   marker, staging→final/root-sync barrier, and atomic pending→committed trust latch. Readers and
   kernel suppression independently require the committed marker's artifact id and exact
   true-manifest digest. Markerless legacy artifacts remain listable/restorable/deletable but never
   suppress source rows. Deletion similarly uses a durable, resumable tombstone before recursive
   removal. Every visible Git-ignored row, including directories and secret-named files, is
   deterministically Retain-only; Commit and the Mixed commit partition reject it before claiming
   the dialogue or mutating Git/artifacts, and finish never invokes `git add -f`.
   An operation row additionally captures its exact admin tree, logical/pseudo/original refs, raw
   index, indexed/worktree dependencies, and a local pack for the manifest's reachable closure.
   Disposable proof restores the same object format, verifies the complete operation digest and
   bytes/modes/stages/reachability, then runs only operation-specific abort/reset on a second copy.
   Exact digest equality plus the committed publication latch is required for suppression; legacy
   file-only artifacts retain their existing read lifecycle.
7. Heartbeat membership and current-session reads/merges/writes share the per-common-dir lock.
   Existing same-boot legacy state and structurally valid prior-boot projections are migrated only
   after live target recheck; malformed bytes are preserved. Every dual timestamp is derived from
   one epoch sample, with only the old one-second writer skew eligible for locked normalization.
   The writer revalidates linked-root/common-dir/branch identity inside the lock.
8. Preview, final recheck, operation identity, and the removal journal bind the install id plus
   root/Git-admin device/inode/incarnation evidence. Before physical removal the kernel fsyncs
   `awa_finish_removal/v1` in `prepared`. Recovery uses both root existence and local Git worktree
   registration. Every returned remove result is reclassified under the lock: absence plus
   unregistration finalizes even after a nonzero Git result, while a still-present original is
   called intact only after the complete operation fingerprint byte-matches. Partial deletion,
   inspection failure, signal disagreement, or a same-path replacement remains uncertain and
   preserves the journal. It durably records the actual removed-phase branch result before emitting
   its idempotent operation-bound receipt, then exception-contains challenge/root/session cleanup
   and completes `finalized`; no retained fallback is invented. The shell invokes this recovery
   immediately when a child disappears after removal. The conversation index remains the exact
   journal-bound terminal recovery anchor after dialogue/envelope cleanup and through complete
   removed/uncertain stdout flush, then is exact-CAS deleted. Output interruption or failed deletion
   therefore leaves duplicate truthful recovery available, never a false surviving-workspace
   projection, and superseding generations are untouched.
9. `kernel/lib/awa_durability.py` is the shared stdlib physical-durability ABI for finish and root
   state: complete write, private atomic replace/exclusive create, durable unlink/adoption, and
   component-wise private directory creation. `_sync_fd` retries `EINTR`, always calls `fsync`, and
   on Darwin also requires successful `F_FULLFSYNC` for regular files and directories. After Git's
   logical worktree removal the kernel full-syncs the surviving root-parent and Git-admin-parent
   namespaces before branch handling. A branch delete uses explicit Git ref-fsync settings, then
   syncs loose refs/reflogs/packed-refs or reftable list/files/directories. Failed post-remove sync
   keeps the prepared/removed journal unfinalized and branch truth empty until reconciliation
   explicitly re-adopts and syncs the exact visible state.

Cancel uses the same terminal-generation authority: it writes `cancelled` first, then performs
bounded challenge/dialogue/index/envelope projection cleanup. Readers ignore terminal projections,
and any cleanup fault is reported rather than converting partial cleanup into success.

This layering means removing every Phase-2 file or disabling every hook reduces recall but leaves the
Phase-1 refusal unchanged. Successful removal makes the workspace unavailable and the agent must
stop; the Cursor chat remains open because no chat-close API exists.

## Two layers, one repo

- **Kernel** (`kernel/`) — the generic safety layer, installed verbatim onto a host:
  - `kernel/bin/dev-worktree.sh` — the `git worktree` adapter/CLI (frozen verbs/flags).
  - `kernel/hooks/worktree-guard.sh` — the `beforeShellExecution` gate + `afterFileEdit` detector.
  - `kernel/hooks/worktree-session.sh` — the `sessionStart` context provider.
  - `kernel/hooks/before-submit-prompt-with-entry.sh` — the fail-open
    first-prompt recovery composite that relays the unchanged finish hook.
  - `kernel/lib/awa_policy.py` — the single kernel-layer generic policy resolver/classifier.
  - `kernel/policy/default-worktree-policy.yml` — the **generic** default overlay (zero literals).
  - `kernel/checks/awa-contract-freeze.sh` — the role-resolved behavior-freeze checker.
  - The kernel carries the safety guarantee on its own; it reads org facts only from `AWA_POLICY`.
- **Engine** (`engine/`) — a Python package (stdlib + `sqlite3` only) that BACKS the kernel
  surfaces with durable state, recovery, a single-instance daemon, an MCP server, and a
  preview-first apply-back adapter. Every engine layer is gated; none is on the safety-critical
  path. `engine/policy.py` mirrors `kernel/lib/awa_policy.py` so the classification the engine
  reasons about is identical to the one the shell kernel enforces engine-off (parity is tested).

## Engine module map

| Module | Responsibility |
|---|---|
| `paths` | XDG state/recovery/detection/lock dirs; `700`/`600` perms (S4); local-disk-only assertion (WAL safety, H6) |
| `identity` | Stable worktree identity = hash(path + branch + common-dir + boot-id); **never** a bare pid |
| `gitutil` | Thin, testable `git` wrapper (no shelling pitfalls) |
| `policy` | Generic repo classifier: include/exclude globs + governed-marker & foreign-hook detectors + per-repo mode resolution (`default_mode` + a `modes_file`), all supplied by a host policy file (mirror of `kernel/lib/awa_policy.py`) |
| `modes` | Generic mode-management verbs (`list`/`get`/`set`/`remove`/`repair`/`sync`/`doctor`) over the tool-owned `awa-modes/v1` modes file; atomic + schema-validated + path-scoped (never touches a repo, git, or a primary checkout) |
| `lock` | Per-common-dir advisory flock — the real write-serialization/collision boundary |
| `state` | SQLite (WAL) store: leases, append-only **redacted** audit events, detections, quarantine refs, recovery artifacts (+ Phase-3 `recovery_source_deleted` age clock, `recovery_tombstones`, maintenance meta) |
| `lease` | `.awa/lease.json` read/write + attest; native-window adopt (no push) |
| `lifecycle` | Adopt → attest → apply-back **preview** (SHA-bound, recovery-before-mutation) → retire |
| `native_entry` | Event-aware fail-open registrar for eager `sessionStart` and first-prompt `beforeSubmitPrompt`: payload-only conversation identity, exact current-session/policy/Git/content/lifecycle revalidation, monotonic private per-root/session `awa-native-entry/v2` evidence, and strict v1/v2 read-only evidence/discovery readers; never `workspaceOpen` or cleanup authority |
| `native_entry_prompt_adapter` | Quiet 2-second total-deadline process supervisor for prompt recovery; bounded stdin only, closed FDs, isolated process group, suppressed output, and terminate/kill cleanup before the unchanged finish hook runs |
| `recovery` | Patch round-trip + bundle (secret-skip S1, symlink-escape drop S2) + whole-worktree archive + restore + list; emits the ONE unified `awa_recovery_artifact/v1` manifest and runs prune-on-creation |
| `retention` | The canonical recovery-retention evaluator + crash-resumable, tombstoned deletion transaction (7-day TTL, 1-GiB/24h pressure, source-deleted age clock) under the shared state-root lock; the ONE implementation every trigger calls |
| `daemon` | Single-instance (flock'd pidfile) bounded maintenance loop + quarantine-ref cleanup/retention + throttled opportunistic recovery-retention pass |
| `guard` | Adversary-aware mutating-shell classifier + state-aware primary-maintenance decision + engine-OFF decision + cleanup-refusal (`can_clean`) |
| `mcp_server` | stdio newline-delimited JSON-RPC MCP server exposing three read-only diagnostic tools plus six path-scoped mode tools; inline instructions are the primary agent-routing surface |
| `mcp_resources` | Pure fixed-resource registry/renderer for the secondary `awa://assistant/operator-guide/v1`; consumes in-memory advertised tool descriptions and reads no environment, filesystem, policy, contract, database, or live state |
| `integrity` | One observational evaluator plus the dedicated status-last store, closed public projection, immutable transition outbox, and typed CAS delivery-receipt bookkeeping commit |
| `integrity_alert` | Bounded native notification dispatcher for a new worsening or the authoritative current pending outbox; records `accepted|failed` and turns all-configured-path failure while non-green into RED |
| `integrity_console` | Deterministic private static HTML renderer with a strict CSP and one clock-only script that forces a stale snapshot's presentation to RED |
| `remote` | Apply-back execute adapter: read/write token split (S3), SHA-drift refusal, preview→confirm gating (live push is an operator step) |
| `redact` | S5 secret/PII redaction pass; every persisted audit/command string is piped through it |
| `cli` / `__main__` | `awa-engine` command surface (launched by `bin/awa-engine.sh`) |

### Integrity surveillance commit boundary (M1-B)

Integrity remains behind the kernel. One `verify --profile fast|deep --trigger ...` evaluation
publishes generation-tagged `history/public/console/outbox` artifacts first and atomically replaces
private `status.json` last under a dedicated integrity lock. Readers validate each referenced
artifact's relative path, generation, and SHA-256. Alert dispatch runs after that lock is released.
Its result is a separate compare-and-swap bookkeeping generation under the same transition id:
`receipt/public/console` are written first, then `status.json` last; it does not re-evaluate, create
another outbox, or recurse. A stale receipt is privately audited and cannot overwrite a newer
evaluation.

A separate private dispatch lock serializes status/outbox revalidation, native invocation, and the
receipt CAS across competing evaluators. Each evaluation carries forward an undelivered current
transition as pending and retries it even when severity did not worsen again; a superseded transition
is audited and never invoked. Failed delivery remains pending and non-green. The receipt/current-
generation advance is exactly once, but the OS notification boundary is deliberately **at least
once**: a crash after macOS accepts the notification and before receipt commit can produce one retry.

The session-independent `kernel/bin/awa-integrity-sweep.sh` calls the same deep/launchd interface
and preserves every exit code and signal. The product's schedule contract bounds the interval and
label, but AWA ships no plist and performs no host activation; `local-jobs` owns that projection.
M1-C hook observers, M1-D Slack transport, and all M2 lifecycle mutations are deliberately absent.

## Per-repo mode (ON / OFF)

A repo's AWA behavior is a first-class, explicitly-settable **mode** with two states, resolved
inside the same generic zero-link classifier the shell kernel and the engine share:

- **ON** → `include`: a confirmed mutating command on the primary checkout returns an enforced hook
  **`deny`** unless it affirmatively satisfies the exact upstream-maintenance exception below, or
  every path the command resolves to is confidently outside every protected primary checkout
  (target-path-aware narrowing, see
  [ADR 0001](docs/adr/0001-target-path-aware-mutation-scope.md)). `ensure` creates a Safe Workspace,
  and the repo is eligible for repo-committed worktree-setup execution.
- **OFF** → `exclude`: AWA leaves the repo alone — the guard allows, `ensure` is a no-op.

### State-aware primary-maintenance decision

Fetch and merge remain mutating in both classifiers. Inside the included-primary mutating branch,
before ADR 0001 target narrowing, one closed recognizer may convert the existing deny to allow:

- `git fetch`, optionally followed by the current branch's configured upstream remote;
- `git merge --ff-only --no-overwrite-ignore`, optionally followed by `@{u}`, `@{upstream}`, or
  the exact configured `<remote>/<branch>` upstream short name.

The recognizer accepts only a single bare-`git` shell segment. It rejects assignments, wrappers,
path-qualified executables, Git global options, redirects, substitutions, control operators, extra
flags, and arbitrary remotes, URLs, refs, or refspecs. Its bounded local inspector requires an
attached branch, exactly one remote-tracking upstream, safe configured fetch destinations, no
repository-retargeting or config-injection `GIT_*` environment, no in-progress Git operation, and a
clean index/worktree including untracked files. It independently rejects `skip-worktree` and
`assume-unchanged` index bits because either can hide tracked-file edits from status. Merge also
proves that `HEAD` is equal to or an ancestor of the live upstream. Any missing, malformed, non-zero,
timed-out, or ambiguous evidence falls through to the existing deny; merge also denies local-ahead
or divergent history.

The kernel hook carries an independent Python 3.9-compatible mirror and does not import the engine
or daemon. A shared command/state corpus exercises the engine, source hook, and installed
role-resolved hook; the contract-freeze UAT holds canonical fetch and fast-forward allows plus
representative denials. Predicate uncertainty denies, while a genuine hook-internal crash retains
the product-wide fail-open behavior.

Allowed commands retain configured Git semantics. Fetch may update common-repository objects,
`FETCH_HEAD`, configured remote-tracking refs, reachable tags, shallow/partial-clone metadata, and
ordinary bookkeeping, and may invoke configured helpers, hooks, and automatic maintenance. Merge
may advance only the current branch and update `HEAD`, index, worktree, reflogs, and `ORIG_HEAD`;
configured hooks, filters, fsmonitor, and submodule behavior remain active. The caller must check
`git status --short` after each command. A non-clean result is preserved and diagnosed from a Safe
Workspace; it does not authorize reset or further primary mutation.

`pull`, `push`, explicit prune, remote update, ordinary merge, branch mutation, cleanup,
commit/rewrite, and every other development operation retain the primary deny.

**Why `deny`, not `ask` (L4).** Cursor's agent enforces a `beforeShellExecution` hook that returns
`deny` (the command is blocked) but treats `ask` as **non-blocking** on the agent path, and
`afterFileEdit` ignores the permission field entirely. So on the one case where prevention must
actually happen — a confirmed mutating command on an included **primary** checkout (mode ON) — the
guard returns an enforced `deny`. `ask` is retained only as an honest no-op on the genuine-uncertainty
path (an included-looking checkout whose command payload the hook could not parse): AWA emits `ask`
there knowing Cursor won't block, so it never *silently* downgrades an uncertain case to allow.
See [SECURITY.md](SECURITY.md) for the platform-limitation writeup.

For a mutating command on a primary checkout the guard **denies** under ON unless the exact
state-aware maintenance lane allows it or every target resolves confidently outside any protected
primary (ADR 0001), and allows under OFF; read-only commands, linked worktrees, and adopted leases
always allow in every mode. A Cursor Cloud
/ background agent runs in an already-isolated, own-branch `/workspace` clone; the guard detects that
and **degrades to allow before the deny branch**, so a cloud VM is never hard-blocked. Hook-infra
failure (crash / timeout / missing interpreter) also degrades to allow (anti-brick). `afterFileEdit`
stays **observation-only** in every mode (it can only write a metadata-only detection receipt, never
pre-block).

### Storage — a tool-owned, source-tracked modes file

Modes are recorded in a dedicated, machine-owned file (schema `awa-modes/v1`) referenced from the
host policy via a single `modes_file:` pointer (resolved relative to the policy file's directory;
`~`/absolute allowed). The file has no hand-authored content, so the tools can rewrite it atomically
without clobbering a hand-authored policy:

```
schema: awa-modes/v1
default_mode: on
modes:
  projects/foo: on
  projects/bar: off
```

Keys are repo paths relative to the governed root (exact or glob), values `on|off`
(case-normalized). Runtime merges compatibility entries/default from the inline host policy with
the referenced modes file; the file wins identical keys/default. Resolution then prefers an exact
combined key, then the first matching combined glob. `default_mode` applies only at the final
eligibility step when neither matches. One **fail-safe rule** governs the classifier and writer:
only an exact `off` disables; any other value — a typo or removed legacy value — resolves to `on`.
A present but unreadable/non-regular referenced file forces combined modes/default to `on` rather
than trusting lower-priority inline `off` settings. The file is intended to be **source-tracked** in
the host overlay and rewritten only by tools — never hand-edited. A repo-local mode marker is
deliberately rejected: a cloned repo could ship `off` to silence the guard, so modes are host-owned.

### Resolution precedence (classifier, first-match-wins)

1. not a git repo → `not-git`
2. explicit **OFF** → `exclude` (absolute opt-out, top precedence)
3. legacy `overrides.exclude` / `overrides.include`
4. **SAFETY excludes** — umbrella root, governed-marker, foreign-hook framework, read-only path
   (these sit **above** the explicit mode step, so a non-off explicit value may not override a
   safety-exclude)
5. any explicit **non-off** value → `include` (the fail-safe: a removed legacy value or a typo is
   not `off`, so it protects; `policy-check` **WARNs** on an unknown value, never hard-fails)
6. exclude glob → `exclude`
7. no origin → `advisory`
8. eligibility (include glob / `default: include`) mapped through **`default_mode`**:
   non-`off` (e.g. `on`)→`include`, `off`→`exclude`

`default_mode: on` reproduces the pre-mode classification byte-for-byte. The classifier's 4-field
tab output is unchanged; a separate `mode-for` CLI exposes the resolved explicit mode for
shell/status/dashboard plumbing. `kernel/lib/awa_policy.py` and `engine/policy.py` implement this
identically, and their parity (including `modes_file` load and invalid handling) is tested.

### Default posture (product vs host)

The shipped template keeps `default_mode: on` for byte-for-byte back-compat: a host with no
`modes_file`/`modes` behaves exactly as before. A host may set `default_mode: off` to exclude
otherwise eligible repos with no combined exact/glob match; it does not govern safety-excluded,
no-origin, or otherwise ineligible repos. Any non-`off` default (including a stale legacy value)
fails safe to ON, and `mode repair` normalizes a legacy referenced-file `default_mode` forward to
`on` (the sanctioned migration path).

### Tools — generalized verbs (view / add / update / delete / repair / sync)

Modes are managed only through generalized verbs over the modes file — never by hand:

- Engine: `python3 -m engine mode {list,get,set,remove,repair,sync}` (via `engine/modes.py`).
- Kernel CLI: `dev-worktree.sh mode <verb>` delegates to the engine module.
- MCP: read tools `awa_mode_list`/`awa_mode_get` plus mutating, path-scoped config tools
  `awa_mode_set`/`awa_mode_remove` (write) and `awa_mode_repair`/`awa_mode_sync` (ensure-exists +
  normalize/repair the file's own contents, idempotent and non-destructive of explicit entries).

Writes are schema-validated and atomic (same-directory temporary file, `fsync`, then `os.replace`);
mode writes do not create backup copies. They are **path-scoped to the host modes file** — they never
touch a repo, git, or a primary checkout. The MCP server's read-only invariant is amended to
"read-only for safety state; config mutations are path-scoped to the host modes file."
`sync`/`repair` do **not** scan the filesystem, materialize per-repo entries, prune, report stale
repos, or inspect inline policy settings. `repair` requires an existing referenced file; `sync`
creates it when absent. They normalize only that file (preserving invalid/legacy value keys as
protected `on`, dropping unsafe/empty keys, and normalizing an invalid file `default_mode`).
`sync(default_mode=off)` can seed a missing or invalid file default, excluding each eligible repo
with no combined inline/file exact or matching glob entry. `sync` is additionally a no-op write
when the file is already canonical (so an install/overlay run leaves a source-tracked file
byte-stable). These make
modes changeable in plain language by a non-technical owner, with the CLI verbs as the parity
mechanism.

### MCP guidance is advisory and secondary to the kernel

Correct routing must work from the nine tool descriptions and `initialize.instructions`; resources
are not a safety or routing dependency. The server remains on MCP `2024-11-05`, advertises
`capabilities.resources: {}`, and implements deterministic `resources/list`, exact-match
`resources/read`, and an empty `resources/templates/list`. Its sole resource is a fixed
`text/markdown` operator guide of at most 500 words rendered from the advertised descriptions inside
the existing tool catalog. Independent semantic tests bind those descriptions to exact-before-glob
mode resolution, default fallback, CLI routing, and safety boundaries.

Resource consumption is host-driven: Cursor may list/read the guide when asked, but AWA does not
assume automatic injection. The guide contains no live status, mode values, lease records, paths,
SQLite history, recovery artifacts, raw kernel contract, templates, subscriptions, or lifecycle
actions. It routes current-repo state, Safe Workspace creation/selection, policy/worktree health,
and removal to the corresponding kernel CLI verbs; other lifecycle/recovery intents route to
`awa-engine`. It states that engine status is not full health, guard output is diagnostic, lease
reads validate contract fields/hash only, cleanup uses active-root/git/content checks, inline and
file modes merge before exact/glob resolution, `default_mode` applies only at final eligibility,
and safety exclusions still outrank `on`. None of these surfaces is load-bearing: kernel safety and
cleanup refusal still hold with the engine off.

The resource is retained solely because a real Cursor Desktop explicit on-demand read proved the
plan's alternative utility criterion. Catalog discovery supports that read but is not evidence of
model routing. The resource added no routing coverage beyond inline metadata; the model-output
matrix was blocked by authentication and was not fabricated, so no model-routing benefit is proven.
Evidence:
[`RESULTS-MCP-GUIDANCE-BASELINE-20260709.md`](live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md).
`consent_prompt()` is contract-only candidate host copy; the stdio server does not render or
enforce it, and no production consent wiring is claimed.

## Recovery retention lifecycle (Phase 3)

AWA never silently deletes at-risk work, but recovery artifacts cannot grow without bound. Phase 3
adds a retention lifecycle that runs **entirely in the engine, off the kernel safety path** — the
finish authorization + removal path contains **no** retention logic, and worktree cleanup stays
correct with the engine absent.

- **One artifact format.** Both the kernel bundler (`dev-worktree.sh clean --bundle`) and the engine
  writers (`recovery.py`) emit the ONE `awa_recovery_artifact/v1` manifest: collision-resistant
  `artifact_id`, `kind` (`bundle | patch | worktree-archive`), `protected`, `source`, `size`,
  `sha256`, and a creation timestamp. Legacy pairs are normalized + permission-repaired on read.
- **One evaluator, one deletion transaction.** `retention.run_maintenance` is the single evaluator;
  every trigger calls it. Ordinary artifacts expire at a **7-day TTL**; a **1-GiB** soft watermark
  prunes the oldest ordinary artifacts after a **24-hour** minimum age. The age clock starts when the
  **source work is deleted** (recorded once in `recovery_source_deleted`), not at archive creation.
  **Protected** whole-worktree archives and kernel Retain artifacts are **never** auto-removed and
  **survive uninstall**.
- **Triggers.** The deterministic PRIMARY trigger is **prune-on-creation** (every artifact write runs
  the bounded pass, so storage self-limits with no schedule). The SEPARATE fail-open sessionStart
  hook (`kernel/hooks/awa-recovery-maintenance.sh`, installed beside — and never changing — the
  kernel worktree-context hook) and `daemon run-once` are OPPORTUNISTIC secondary triggers: quiet on
  success, throttled to ≤1/24h, non-blocking. The hook contains no retention logic and never unlinks.
- **Crash-resumable + contained.** Each deletion writes a transient `recovery/.trash` journal before
  any unlink, records a durable `awa_recovery_tombstone/v1` (so a recovery row never implies a
  restorable archive), then removes the journal; an interrupted deletion is completed idempotently on
  the next pass. Every target must be a non-symlink file resolving beneath the physical recovery root;
  a failed unlink is an honest ERROR that PRESERVES the artifact.
- **One lock ABI.** Maintenance serializes on the single global state-root lock
  (`locks/recovery-maintenance.lock`) using the same advisory-flock ABI as the per-common-dir
  finish/clean/Retain lock; an opportunistic trigger acquires non-blocking and skips when a pass runs.
- **Visibility.** Failed maintenance, protected-storage growth, and watermark overage surface in the
  dashboard (`environment.recovery`, additive) and a bounded sessionStart context warning.

## The contract is BEHAVIOR-only (location is informational)

`contracts/awa-contract.v1.json` freezes the kernel's public **behavior**: the CLI verbs/flags, the
`awa-worktree/v1` dashboard JSON shape, the guard permission schema, and the `.awa/lease.json`
shape. These are the interface; the engine may only BACK them, never silently change them. A
removal/rename of a required verb/flag/key — or a changed schema string — is a breaking change that
requires a versioned bump (`awa-contract.v2.json`). Additive, backward-compatible OPTIONAL fields
are allowed within v1.

The per-repo mode surface stays **within v1 — no v2**. The contract freezes keys and `schema`
literals, not value sets: `classify()` now emits only `include | exclude | advisory | not-git` (the
`ask_on` classification value was removed with ASK_ON), and the `repo.mode`/`repo.mode_error`
dashboard fields, the `mode` CLI verb, and the `awa_mode_*` MCP tools remain additive (the freeze
checker asserts frozen verbs/flags/keys/shapes exist, not that none are added). The guard now returns
an enforced **`deny`** on a confirmed included-primary mutation; the contract keeps `ask` in
`permission_values` (retained for the uncertainty path) and **adds** an additive `deny_shape`
(`permission` + `user_message` + `agent_message`). The freeze checker asserts the included-primary
mutation denies with `deny_shape` present and that `afterFileEdit` allows (observation-only).

**File locations are NOT frozen.** The shim/hook/emitter paths recorded in the contract are
`informational` and resolved by **role** (`AWA_HOME` / the installed release path). Re-homing the
generic kernel — e.g. from a host's `_ops/` into `KleinPerkins/awa/kernel/` — needs no contract
bump, because location was never the interface. `kernel/checks/awa-contract-freeze.sh` enforces the
behavior floor against the live shims *wherever they are installed* (role-resolved via `AWA_HOME`).

## Zero-link (the product names no organization)

Because the kernel AND engine ship here and are installed verbatim, BOTH carry **zero**
host/organization-specific literals. Repo classification — including *excluding a self-governed
sibling repo* — is decided **generically**: the governed-marker detector treats any repo that ships
its own `_ops/POLICY.md` (or other configured marker) as self-governed and leaves it alone WITHOUT
naming it, and the foreign-hook detector defers to husky/lefthook/pre-commit repos. Org/vendor
literals live ONLY in the machine-local policy overlay, which is never vendored or published.

`engine/tests/test_zero_link.py` is the SOLE in-repo pre-flight for the orchestrator's
`zero-link --mode global` gate (which greps the whole payload). It scans the entire shipped surface
(kernel + engine + dashboard + contracts + bin + shipped top-level files) and is at least as strict
as that gate. `engine/tests/test_kernel_policy_parity.py` guards against drift between the two
classifier mirrors.

## Install & standalone shape

`install.sh` is the Standalone-System-Package (SSP) entry point: it copies the runtime into
`$XDG_DATA_HOME/awa/current`, writes a config env (`AWA_HOME`, `AWA_POLICY`, `AWA_HOOK_OWNER`,
optional `AWA_GOVERNED_ROOT`), registers an add-only `awa` MCP server, ensures the local-disk state
dir, and writes a self-describing release pointer. It is idempotent and backup-before-write, with
`--repair`, `--doctor`, `--check`, and `--uninstall [--keep-state]` verbs. No sibling-repo
dependency: a fresh clone installs on its own.

Hook-file ownership starts with the additive `awa-hook-owner/v1` block in the
canonical behavior contract. Direct product projection prefers
`awa-hook-owner/v3`, composing the frozen v1 roles, v2 guard/observer/handoff
roles, and the v3 prompt-recovery composite after explicit role supersession;
v1/v2 remain validated compatibility inputs.
The strict machine-local selection at `$XDG_CONFIG_HOME/awa/hook-owner.json` resolves from an
explicit `AWA_HOOK_OWNER=direct|external`, then persisted selection, then a compatible release
pointer, with `direct` only as the fresh/legacy default. Invalid or ambiguous state refuses before
hook or selection mutation; only a valid explicit value repairs malformed state.

In `direct`, AWA reconciles the exact seven-role effective composition into the selected user hook file. In
`external`, the host owns the entire file transaction and AWA performs zero selected-hook-file
reads or writes on install, repair, doctor, and uninstall. A host-policy delegator may inject only
policy/root data before executing an installed product role. The v3
`beforeSubmitPrompt` role runs bounded native-entry recovery and then delegates
to the byte-identical finish hook; the finish consumer remains unchanged. The
role ID plus event—not command spelling—is identity, and this composition does
not move guard, recovery, heartbeat, cleanup, or literal-`Close` authority off
the kernel-first path.

The release pointer advertises the selected mode, `awa-hook-owner/v1`, and the installed canonical
contract SHA-256. Doctor requires selection/pointer/runtime/contract agreement. A direct projection
can be built and checked against an explicit non-live `AWA_HOOKS_JSON` staging path while external
remains persisted; making that complete owner live atomically is the host's rollback transaction,
not an AWA lifecycle side effect.

## Security

See `SECURITY.md` for the Cluster-D security ledger (S1–S6) and the threat model. Each closable row
is backed by an automated test in this repo's suite.
