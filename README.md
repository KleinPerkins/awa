# AWA — Agent Worktree Automation

**AWA keeps agent work off your main checkout.** When an agent (or you) starts mutating a
repository, AWA steers the work into an isolated `git` worktree ("Safe Workspace"), detects native
edits to the primary checkout, refuses unsafe cleanups, and can recover uncommitted work — so your
main branch stays clean and nothing gets silently lost.

AWA is **one self-contained product**: a generic **kernel** (the safety layer — a `git worktree`
CLI, a `beforeShellExecution` guard, an `afterFileEdit` detector, a policy resolver, a render-only
status dashboard) and a generic **engine** (durable state, recovery, a single-instance daemon, an
MCP server). Both ship here and both are **zero-link** — they name no organization. Every
host/org-specific fact lives only in a machine-local **policy overlay** (`AWA_POLICY`).

> Kernel-first (frozen): the safety guarantee holds with the engine/daemon **OFF**. The engine only
> observes, bookkeeps, and eases. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Requirements

- Python **3.9+** (standard library + `sqlite3` only — no third-party dependencies).
- `git` on `PATH`.

## Clone and install

```bash
git clone git@github.com:KleinPerkins/awa.git
cd awa
./install.sh            # idempotent, backup-before-write; installs into your XDG dirs
./install.sh --doctor   # read-only health check of the install
make verify             # tests + contract freeze + zero-link + install --check
```

`install.sh` copies a self-contained runtime into `$XDG_DATA_HOME/awa/current`, writes a config env
(`$XDG_CONFIG_HOME/awa/env`), merges the Cursor hooks (a fail-open soft backstop) into
`~/.cursor/hooks.json`, registers an add-only `awa` MCP server in `~/.cursor/mcp.json`, and writes a
self-describing release pointer. When `AWA_GOVERNED_ROOT` is configured it also publishes the
product-owned dashboard seed into Cursor's machine-local Canvas directory. There is **no required**
sibling-repo dependency — a fresh clone installs on its own. `bootstrap.sh` is a one-command
"clone + install" convenience.

To put AWA on your `PATH`, source the generated env (or add it to your shell profile):

```bash
source "${XDG_CONFIG_HOME:-$HOME/.config}/awa/env"
```

### Point AWA at your repos (the policy overlay)

AWA ships a **generic** default policy with zero governed roots. To govern your repos, set
`AWA_GOVERNED_ROOT` (or supply a full policy file via `AWA_POLICY`) that names your governed
root(s), include/exclude globs, and detectors. The product stays generic; your policy is the only
place org/host literals live, and it is never vendored or published.

### Dashboard refresh

The dashboard's **Refresh** button never opens a chat. It writes a closed
`awa-dashboard-refresh` request to the Canvas sidecar. If the machine has already adopted the
optional `local-jobs` Canvas bridge, install/repair registers that fixed job (disabled for
scheduling) and the existing bridge runs the read-only renderer in the background. The renderer
accepts only its fixed root/policy arguments, reads repo status, and writes the derived Canvas plus
one validated same-directory sidecar alias; it never writes in a governed repo. A dedicated marker
binds the fixed job to AWA: install/repair and uninstall refuse to replace or remove a same-named
job whose ownership is not proven.

AWA does not silently opt a machine into the shared bridge. An agent can explicitly enable and
register it with:

```bash
AWA_GOVERNED_ROOT=/path/to/root AWA_POLICY=/path/to/policy \
  dashboard/install_actions.sh --enable-bridge
```

Without that optional bridge, refresh from the CLI with
`dashboard/render.py --root /path/to/root --policy /path/to/policy`.

Every worktree row includes its allocated on-disk size in adaptive KB, MB, or GB units. The
read-only measurement uses the same bounded timeout posture as repo inspection and reports
`not available` instead of delaying the whole dashboard when a directory cannot be measured.

### Per-repo mode (ON / OFF)

Each governed repo has an explicit AWA **mode** you can set and inspect:

- **ON** — a matching non-`off` mode classifies a repo as included unless a higher-priority safety
  exclusion applies; `default_mode: on` applies only to repos that reach the final eligibility
  step. A confirmed mutating command on a resulting included **primary** checkout returns an
  enforced hook **`deny`** (Cursor enforces `deny`; it treats `ask` as non-blocking — see
  [SECURITY.md](SECURITY.md#platform-limitation--cursor-enforces-hook-deny-not-ask-l4)), steering
  work into a Safe Workspace. This decision is target-path-aware: when every path the command
  actually resolves to is confidently outside any protected primary checkout (e.g. `rm -f /tmp/x`
  run from inside an included repo), the guard allows instead of denying; any uncertainty keeps the
  enforced deny (see [ADR 0001](docs/adr/0001-target-path-aware-mutation-scope.md)). A Cursor Cloud
  / background agent (already an isolated own-branch `/workspace` clone) degrades to allow, and
  afterFileEdit is observation-only.
- **OFF** — AWA leaves the repo alone (no block, no Safe Workspace).

One **fail-safe rule** governs both the classifier and the modes writer: only an exact `off`
disables protection; **any other value** — a typo, a removed legacy value — resolves to ON.

The runtime merges compatibility settings written inline in the host policy with the tool-owned,
source-tracked modes file (schema `awa-modes/v1`) named by `modes_file:`; the referenced file wins
an identical key/default. Exact keys then win over globs, matching globs follow file order, and
`default_mode` applies only at final eligibility when neither matches. The CLI and MCP tools manage
only the referenced file, not inline settings. Never hand-edit the referenced file:

```bash
dev-worktree.sh mode list                 # show every configured repo + the default
dev-worktree.sh mode get   projects/foo    # show the explicit entry (exact key) for one repo
dev-worktree.sh mode set   projects/foo on # set a repo to on | off
dev-worktree.sh mode remove projects/foo   # remove this file key; inline/glob/default may emerge
dev-worktree.sh mode sync                  # ensure-exists + normalize the modes file (idempotent)
```

`sync`/`repair` do **not** scan the filesystem, materialize per-repo entries, or prune stale repos.
`repair` requires an existing referenced file; `sync` creates one when missing. Both coerce invalid
values to fail-safe `on`, drop unsafe/empty keys, and normalize an invalid default. A present but
unreadable/non-regular referenced file forces runtime mode/default values to `on`, including over
lower-priority inline `off` values. `policy-check` **WARNs** (never hard-fails) on an
invalid/broad-off/legacy/dangling-pointer config.

The same operations are exposed as MCP tools for plain-language use: `awa_mode_list` / `awa_mode_get`
(read) and `awa_mode_set` / `awa_mode_remove` / `awa_mode_repair` / `awa_mode_sync` (write, scoped to
the modes file only — they never touch a repo, git, or your primary checkout; `sync`/`repair`
normalize the file's own contents, they do not scan the filesystem). `awa_mode_list`/`get` expose
only referenced-file storage, not effective runtime mode. Runtime first merges inline policy and
file settings, then prefers an exact combined key and the first matching combined glob.
`default_mode` applies only at the final eligibility step when neither matches. Removing a file key
can therefore reveal an inline exact key or another inline/file glob rather than the default.
Supplying `default_mode=off` to `awa_mode_sync` seeds only a missing or invalid file default, but
when it does, each eligible repo with no combined exact or matching glob entry is excluded.

The MCP server puts routing and safety guidance directly in each tool description and in
`initialize.instructions`. It also advertises one secondary, fixed on-demand document at
`awa://assistant/operator-guide/v1` (`text/markdown`). Cursor decides whether and when to list/read
that resource; AWA does not assume it is automatically injected. The guide is advisory and contains
no live status, modes, leases, paths, history, recovery data, raw contracts, or lifecycle actions.
Use `dev-worktree.sh status` for current-repo classification/root/worktree state, `ensure` to
create/select a Safe Workspace, `doctor` for policy/worktree health, and `clean` for
bundle-or-refuse removal. Use `awa-engine` for adopt/attest/apply-back/publish/retire/recovery.
Engine status is not full health, guard output is diagnostic, and lease reads check only contract
fields/hash; cleanup uses the active-root heartbeat plus git/content checks. The kernel guarantee
continues with the engine off.

Adoption's in-worktree `.awa/lease.json` does not make an otherwise removable worktree permanently
dirty. Ordinary `clean --path` tolerates and removes that file only after proving `.awa/` contains
exactly one private, regular lease whose identity matches the live worktree path, branch, and Git
common directory. A malformed/mismatched lease, link, permission drift, tracked `.awa` path, sibling
file, or any unrelated untracked content retains the existing refuse/preserve behavior. Ignored
operator content still follows the independent bundle-or-refuse gate.

**Live evidence: RETAIN, narrowly.** A real Cursor Desktop explicit on-demand read returned the
fixed guide; that read alone satisfies the plan's explicit-utility alternative. The resource added
no metadata routing coverage beyond inline guidance, and no authenticated model-output matrix ran;
no model-routing benefit is claimed. See
[`RESULTS-MCP-GUIDANCE-BASELINE-20260709.md`](live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md).
`consent_prompt()` remains contract-only candidate copy for a future host integration: the AWA
stdio server neither renders nor enforces it, so it is not a production consent control.

**Default posture.** A repo with no combined inline/file exact or matching glob entry uses
`default_mode` only if it reaches the final eligibility step. The shipped default is `on`. A host
may set `default_mode: off` to exclude otherwise eligible unmatched repos; any non-`off` default
(including a stale legacy value) fails safe to ON, and `mode repair` normalizes a legacy default in
the referenced file forward to `on`.

## Install verbs

| Command | Effect |
|---|---|
| `./install.sh` | Install / reconcile (idempotent) |
| `./install.sh --repair` | Force re-copy the runtime + re-wire hooks/mcp |
| `./install.sh --doctor` | Read-only health check of the install |
| `./install.sh --check` | CI-safe static preflight (writes nothing to `$HOME`) |
| `./install.sh --uninstall [--keep-state]` | Remove the install (`--keep-state` preserves recovery state) |

Equivalent `make` targets exist (`make install|repair|doctor|check|uninstall`); `make help` lists
them. `make verify-install` exercises the whole install lifecycle in a throwaway `HOME`.

## Finish the current Safe Workspace

Direct closeout language (“I'm done”, “remove worktree”, “can we close”, “end session”, “finish”,
“finalize”) starts a deterministic local preview before generic intent routing. It never removes
anything. A user-level `beforeSubmitPrompt` hook may block that initiating prompt and display the
fixed warning, but the hook is convenience only and fails open globally.

The warning offers exactly five standalone choices:

- **Commit / Retain / Mixed / Cancel input** — case-insensitive; surrounding whitespace is
  normalized to the canonical title-case choice. Attachments and extra words still reject.
- **Commit** — select only the displayed items to deliver. A local commit is not delivery proof:
  AWA requires one GitHub repository with merge commits enabled, the exact preserved head in a
  merge-commit PR and live default branch, and complete passing checks. A stable repeated empty
  check rollup proves a genuine zero-check repository; the first empty result never does.
  Squash/rebase-only repositories are unsupported. Network calls exist only in Commit/Mixed.
- **Retain** — select displayed items for a typed, protected artifact under AWA local state.
  Creation is crash-durable and restore-proven before publication; unproven/tombstoned artifacts
  remain invisible, and interrupted deletion resumes safely. SHA-1 and SHA-256 sources are
  preserved without running configured filters over raw proof blobs. Artifacts are
  listed/restored/deleted explicitly, excluded from automatic pruning, and survive normal
  uninstall. Every displayed Git-ignored file/directory is Retain-only; secret-named items require
  an additional explicit selection flag.
- **Mixed** — choose Commit or Retain for each selected row. Its Commit partition rejects
  Retain-only rows before dialogue claim, Git mutation, artifact creation, or delivery; ignored
  rows can be retained while ordinary rows are committed. AWA never force-adds ignored paths.
- **Cancel** — make the selected generation inert, then clear pending dialogue/challenge/index/envelope
  state; no repository, archive, or workspace change. Incomplete local-state cleanup is reported.
- **Close** — the only choice routed to the Phase-1 kernel authorization. It must be exact,
  case-sensitive, standalone `Close` with no surrounding whitespace; casing/trim variants receive
  a non-destructive correction and leave the dialogue live. Yes, booleans, approval clicks,
  attachments, and extra words do not substitute.

Commit/Retain/Mixed always require full fresh reconnaissance and a fresh warning. In hook mode the
completed action stores a retry-safe latch but creates no replacement challenge itself: the next
submitted prompt is discarded before choice/intent recognition and used only to show that warning,
whose exact generation is published after complete output. Even if that trigger is `Close`, a
second exact `Close` is required. They never auto-close. The later Close is content-addressed to the
current root, branch/HEAD, complete visible and hidden inventory, session membership, warning
version, install identity, and root/Git-admin physical incarnations; the private proof includes
every filesystem object and grouped-directory descendant, while warnings never expose content or
hashes.
Any read, metadata, link, nested-repository, or membership drift preserves the workspace.
Before finish runs Git status or scans the tree, a read-only NUL-safe preflight refuses any
assume-unchanged, skip-worktree/sparse, or fsmonitor-hidden index state—including unchanged flagged
entries—with one generic `index_visibility_flags` reason. It also refuses malformed or unavailable
inspection, creates no challenge/dialogue, leaves the index and workspace unchanged, and reveals no
flagged path or private value. This check is finish-only; ordinary `clean --path` uses its separate
active-root, commit-safety, dirty/ignored-state, and validated AWA-lease checks.
Active merge, cherry-pick/revert sequence, rebase (merge/apply), `git am`, bisect, and notes-merge
state is represented by one content-safe synthetic row per logical operation. Privately, AWA scans
the complete per-worktree operation administration twice without following links and binds its
content-addressed manifest, Git logical refs, exact raw index, worktree dependencies, and reachable
object closure into the challenge. Unknown, ambiguous, changing, linked, special-file, mounted, or
live-lock state refuses preview. Recognized detached rebase/bisect state is bound to its validated
original local branch and forces branch retention; an otherwise detached HEAD still refuses.
Finish strips ambient `GIT_*` variables from the first target probe through removal/ref cleanup,
then explicitly binds the validated Git dir, worktree, and real index. It retains normal
`HOME`/XDG/PATH configuration; only Commit's contained selected-path flow may bind its own validated
temporary index.
Desktop choices use `dispatch --current`: `sessionStart` binds the physical root to the actual
session/conversation, while `beforeSubmitPrompt` records the exact one-use choice and attachment
provenance. An activated Close generation is claimed before the shared-lock attempt, so every
kernel attempt—including contention or refusal—is one-use and a retry requires a fresh preview and
envelope. Expected nonce/generation fields must be a complete exact pair naming the current hook
challenge; they can never authorize a replacement direct challenge. A partial/timed-out hook
preview remains inert and cannot confirm Close. All dispatcher outcomes pass through one typed
public builder after authorization: fixed messages and validated outcome/reason/branch values only,
with no child output, exception/kernel text, local paths, object ids, hashes, prompt bytes, or extra
child fields. Its clean child emits one exact machine JSON shape; malformed, extra, oversized, or
exit-status-contradictory output becomes uncertainty. Proven removal stops the agent while the chat
remains open; proven refusal reports preservation; post-invocation ambiguity reports unknown
removal and stops.
Removal and local branch disposition remain zero-network. Local-only commits retain the branch;
uncertainty also retains it. A successful Close removes the workspace and stops the agent, but
Cursor provides no API for AWA to close the chat, so the chat remains open.
The kernel fsyncs a local removal journal before Git removal and reconciles every Git result from
both physical root existence and local Git registration. Complete absence finalizes even after a
nonzero Git return. A present original clears the prepared journal only when its complete
operation-bound fingerprint still byte-matches; partial deletion, unreadable inspection, signal
disagreement, or a same-path replacement is uncertain and preserves the journal and branch.
One shared stdlib durability primitive complete-writes and syncs every critical file and containing
namespace; Darwin additionally requires successful `F_FULLFSYNC` for files and directories. After
Git removes a worktree, AWA syncs the surviving worktree-parent and Git-admin-parent namespaces
before branch handling. Branch deletion asks Git to fsync ref updates and then syncs the actual
files or reftable backend. Any failure after logical removal leaves the journal retryable and reports
unknown/uncertain removal or branch truth until reconciliation explicitly re-adopts those visible
namespaces; it never invents retained/deleted.
If the finish child exits immediately after removal,
the shell repairs and reports that removed outcome; later invocation can idempotently finish
branch/state/receipt cleanup. The branch result comes from the validated durable journal or the
actual closed in-memory finalization result, never a prefilled retained default. Dialogue/envelopes
may be cleaned first, but the exact current index stays through complete removed/uncertain output
as the journal-bound recovery anchor and is CAS-deleted only after stdout flush; interruption or
deletion failure can repeat a truthful result, while a superseding generation is untouched. A crash
before removal never reports success.

New Retain artifacts publish through an explicit durable trust latch. Payloads, proof blobs, and the
final `restore_proven:true` manifest are fully synced in hidden staging; a pending marker binds the
artifact id to that exact manifest digest; staging is renamed to final and the Retain root synced;
then pending is atomically renamed committed. List, restore, and finish-row suppression trust a new
artifact only when the committed marker and manifest digest match. Markerless older artifacts remain
discoverable, restorable, and explicitly deletable with `legacy_unlatched` status, but do not hide
source rows. A failure before the latch remains hidden/untrusted and is safely resumed; a failure
after the latch returns success with a bounded cleanup warning.
Selecting an operation row is atomic with its raw index, conflict stages, required worktree
dependencies, recursive admin state, logical refs, and a local object pack. Secret or ignored
dependencies require their explicit flags. Proof restores a standalone repository in the same
object format, compares exact bytes/modes/refs/reachability and the operation digest, then proves the
operation-specific abort/reset on a separate copy without running continue, hooks, merge drivers,
or rebase exec. Only a committed artifact with the exact current operation digest suppresses that
row; older file-only artifacts remain readable.

Cloud/background, primary-checkout, absent, and multi-root contexts mint no local challenge.
Empty or explicit false/0/no/off Cloud fields remain normal Desktop context; any other non-empty
top-level or nested broker/background handle is unsupported. Raw terminal
`git worktree remove`/`rm`, aliases that evade classification, and Cursor-managed external
cleanup remain outside this conversational guarantee. Live Desktop proof that the current Cursor
build displays and blocks the exact `beforeSubmitPrompt` `user_message` is a release UAT item; the
kernel's literal-Close refusal is already hook-independent.

## Command surface

The kernel worktree CLI (`dev-worktree.sh`, frozen verbs): `status`, `ensure`, `list`, `clean`,
`doctor`, `policy-check`, `dashboard-data`, plus the additive `mode` verb (see
[Per-repo mode](#per-repo-mode-on--off)).

The engine (`awa-engine <verb>`, launched by `bin/awa-engine.sh`): `doctor`, lifecycle
(`adopt`/`attest`/`apply-back`/`publish`/`retire`/`lease-read`), recovery
(`recover patch|bundle|archive|restore-patch|restore-bundle|list|prune|status`), guard
(`guard shell`/`guard can-clean` — engine-off advisory; `guard can-clean` may refuse when kernel
`clean` succeeds after squash-merge detection because engine cleanup remains ancestry-stricter until
fast-follow B), `daemon` (`status`/`run-once`), `events`, and `mcp-serve` (a stdio JSON-RPC MCP
server exposing nine tools plus the fixed advisory operator guide).

## Recovery retention

Recovery artifacts (git-ignored bundles, patches, and protected whole-worktree archives) are kept in
the engine state dir and pruned by ONE evaluator: ordinary artifacts expire at a **7-day TTL**, with
a **1-GiB / 24-hour** soft-watermark pressure policy; **protected** archives are never auto-removed
and survive uninstall. Pruning runs off the finish/removal path — deterministically **on every
artifact write**, plus opportunistic (throttled ≤1/24h, non-blocking) passes from a fail-open
sessionStart hook and `daemon run-once`. Inspect with `awa-engine recover status`; force a canonical
pass with `awa-engine recover prune --maintenance`.

## Layout

```
kernel/       generic safety layer — dev-worktree CLI, guard/session/install hooks,
              awa_policy resolver, default policy template, role-resolved freeze checker
engine/       Python package (stdlib + sqlite3) that BACKS the kernel; tests/ is the full suite
dashboard/    generic, data-free status dashboard (emitter.py + seed.canvas.tsx)
contracts/    the FROZEN, behavior-only kernel contract (awa-contract.v1.json)
bin/          awa-engine.sh launcher
install.sh    Standalone System Package installer; bootstrap.sh = clone + install
ARCHITECTURE.md / SECURITY.md   the design invariant + the Cluster-D security ledger
```

## Versioning & the frozen contract

`engine/__init__.py:__version__` is the engine version; releases are tagged (`vX.Y.Z`). The kernel
contract in `contracts/awa-contract.v1.json` freezes **behavior** (verbs/flags, the `awa-worktree/v1`
shape, the guard permission schema, the lease shape) — not file locations, which are informational
and resolved by role. A removal/rename is a breaking change requiring `awa-contract.v2.json`.

## License

Proprietary — © KleinPerkins. All rights reserved. See [`LICENSE`](LICENSE).
