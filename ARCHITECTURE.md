# AWA — architecture: one generic product, kernel-first, engine off the safety path

> The design invariant for Agent Worktree Automation (AWA). The machine-checkable BEHAVIOR
> surface is pinned in `contracts/awa-contract.v1.json`; this document is the prose record of
> the principle those pins defend.

## The re-founded principle

**AWA ships as ONE self-contained product — a generic KERNEL and a generic ENGINE, BOTH in
`KleinPerkins/awa`, BOTH zero-link.** Every org/host-specific literal (which repos are governed,
which paths are read-only, where worktrees live) lives ONLY in a host-supplied **policy overlay**
(`AWA_POLICY`), never in the product. A host adopts AWA by cloning + `./install.sh`, then pointing
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
challenge, literal-`Close`, lock, final fingerprint, session, removal, reconciliation, and local
branch-disposition decisions. The private proof covers every physical object (encoded raw path,
type, mode, size, regular-file hash, link target, grouped-directory descendants, and exact Git
status/index evidence), plus the root and per-worktree Git-admin physical incarnations, with
no-follow before/after identity checks; operator output remains one
escaped row per Git item and exposes none of that private proof. That path imports no
consumer/router/engine code and invokes no network.

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
mount, live lock, path escape, or read drift refuses. The public projection is only fixed synthetic
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
3. `sessionStart` writes an atomic root-bound current identity with the real payload
   session/conversation plus exact branch/common-dir. The guard reuses that identity rather than
   minting an `unattributed` member.
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
   attachment, replay, ambiguity, and drift cannot activate it. A Close casing/trim variant returns
   a correction without activation. Only exact activated Close invokes the kernel CLI with literal
   authorization plus the envelope's complete expected nonce/generation pair. That pair can name
   only the exact still-current hook challenge; a direct replacement cannot inherit it. Before any shared-lock or destructive
   attempt, the kernel exclusive-creates a nonce/generation-bound `awa_finish_generation_state/v1`
   `close_claimed` record. Every outcome after that claim is one-use; retry requires a fresh preview
   and envelope. One closed typed builder projects every dispatcher result after authorization
   handling: it emits fixed copy and validated outcome/reason/branch values only, never child
   output, exceptions, kernel messages, paths, object ids, hashes, prompt bytes, or extra fields.
   The clean child emits one exact machine-mode JSON shape; extra, malformed, oversized, or
   exit-status-contradictory output is treated as uncertainty rather than parsed heuristically.
   Proven removal reports removal plus agent stop/chat-open truth; proven refusal reports
   preservation; any post-invocation ambiguity reports unknown removal and stops.
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
| `state` | SQLite (WAL) store: leases, append-only **redacted** audit events, detections, quarantine refs, recovery artifacts |
| `lease` | `.awa/lease.json` read/write + attest; native-window adopt (no push) |
| `lifecycle` | Adopt → attest → apply-back **preview** (SHA-bound, recovery-before-mutation) → retire |
| `recovery` | Patch round-trip + bundle (secret-skip S1, symlink-escape drop S2) + restore + list |
| `daemon` | Single-instance (flock'd pidfile) bounded maintenance loop + quarantine-ref cleanup/retention |
| `guard` | Adversary-aware mutating-shell classifier + engine-OFF decision + cleanup-refusal (`can_clean`); reads ONLY policy + `.awa/lease.json` |
| `mcp_server` | stdio newline-delimited JSON-RPC MCP server exposing three read-only diagnostic tools plus six path-scoped mode tools; inline instructions are the primary agent-routing surface |
| `mcp_resources` | Pure fixed-resource registry/renderer for the secondary `awa://assistant/operator-guide/v1`; consumes in-memory advertised tool descriptions and reads no environment, filesystem, policy, contract, database, or live state |
| `remote` | Apply-back execute adapter: read/write token split (S3), SHA-drift refusal, preview→confirm gating (live push is an operator step) |
| `redact` | S5 secret/PII redaction pass; every persisted audit/command string is piped through it |
| `cli` / `__main__` | `awa-engine` command surface (launched by `bin/awa-engine.sh`) |

## Per-repo mode (ON / OFF)

A repo's AWA behavior is a first-class, explicitly-settable **mode** with two states, resolved
inside the same generic zero-link classifier the shell kernel and the engine share:

- **ON** → `include`: a confirmed mutating command on the primary checkout returns an enforced hook
  **`deny`**, `ensure` creates a Safe Workspace, and the repo is eligible for repo-committed
  worktree-setup execution.
- **OFF** → `exclude`: AWA leaves the repo alone — the guard allows, `ensure` is a no-op.

**Why `deny`, not `ask` (L4).** Cursor's agent enforces a `beforeShellExecution` hook that returns
`deny` (the command is blocked) but treats `ask` as **non-blocking** on the agent path, and
`afterFileEdit` ignores the permission field entirely. So on the one case where prevention must
actually happen — a confirmed mutating command on an included **primary** checkout (mode ON) — the
guard returns an enforced `deny`. `ask` is retained only as an honest no-op on the genuine-uncertainty
path (an included-looking checkout whose command payload the hook could not parse): AWA emits `ask`
there knowing Cursor won't block, so it never *silently* downgrades an uncertain case to allow.
See [SECURITY.md](SECURITY.md) for the platform-limitation writeup.

For a mutating command on a primary checkout the guard **denies** under ON and allows under OFF;
read-only commands, linked worktrees, and adopted leases always allow in every mode. A Cursor Cloud
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
`$XDG_DATA_HOME/awa/current`, writes a config env (`AWA_HOME`, `AWA_POLICY`, optional
`AWA_GOVERNED_ROOT`), merges the Cursor hooks (soft backstop, fail-open), registers an add-only
`awa` MCP server, ensures the local-disk state dir, and writes a self-describing release pointer.
It is idempotent and backup-before-write, with `--repair`, `--doctor`, `--check`, and
`--uninstall [--keep-state]` verbs. No sibling-repo dependency: a fresh clone installs on its own.

## Security

See `SECURITY.md` for the Cluster-D security ledger (S1–S6) and the threat model. Each closable row
is backed by an automated test in this repo's suite.
