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
self-describing release pointer. There is **no** sibling-repo dependency — a fresh clone installs on
its own. `bootstrap.sh` is a one-command "clone + install" convenience.

To put AWA on your `PATH`, source the generated env (or add it to your shell profile):

```bash
source "${XDG_CONFIG_HOME:-$HOME/.config}/awa/env"
```

### Point AWA at your repos (the policy overlay)

AWA ships a **generic** default policy with zero governed roots. To govern your repos, set
`AWA_GOVERNED_ROOT` (or supply a full policy file via `AWA_POLICY`) that names your governed
root(s), include/exclude globs, and detectors. The product stays generic; your policy is the only
place org/host literals live, and it is never vendored or published.

### Per-repo mode (ON / OFF)

Each governed repo has an explicit AWA **mode** you can set and inspect:

- **ON** — a matching non-`off` mode classifies a repo as included unless a higher-priority safety
  exclusion applies; `default_mode: on` applies only to repos that reach the final eligibility
  step. A confirmed mutating command on a resulting included **primary** checkout returns an
  enforced hook **`deny`** (Cursor enforces `deny`; it treats `ask` as non-blocking — see
  [SECURITY.md](SECURITY.md#platform-limitation--cursor-enforces-hook-deny-not-ask-l4)), steering
  work into a Safe Workspace. A Cursor Cloud / background agent (already an isolated own-branch
  `/workspace` clone) degrades to allow, and afterFileEdit is observation-only.
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

## Command surface

The kernel worktree CLI (`dev-worktree.sh`, frozen verbs): `status`, `ensure`, `list`, `clean`,
`doctor`, `policy-check`, `dashboard-data`, plus the additive `mode` verb (see
[Per-repo mode](#per-repo-mode-on--off)).

The engine (`awa-engine <verb>`, launched by `bin/awa-engine.sh`): `doctor`, lifecycle
(`adopt`/`attest`/`apply-back`/`publish`/`retire`/`lease-read`), recovery
(`recover patch|bundle|restore-patch|list`), guard (`guard shell`/`guard can-clean` — engine-off
advisory; `guard can-clean` may refuse when kernel `clean` succeeds after squash-merge detection
because engine cleanup remains ancestry-stricter until fast-follow B), `daemon` (`status`/`run-once`),
`events`, and `mcp-serve` (a stdio JSON-RPC MCP server exposing nine tools plus the fixed advisory
operator guide).

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
