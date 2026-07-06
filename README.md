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

### Per-repo mode (ON / ASK_ON / OFF)

Each governed repo has an explicit AWA **mode** you can set and inspect:

- **ON** — AWA asks before a mutating command on your main checkout and steers work into a Safe
  Workspace. Full protection; the only mode that may run a repo's committed worktree-setup.
- **ASK_ON** — same ask-and-steer nudge as ON, but the repo shows in its own dashboard bucket and
  will **not** run repo-committed setup. A good "protect but don't auto-run anything" default.
- **OFF** — AWA leaves the repo alone (no ask, no Safe Workspace).

Modes live in a tool-owned, source-tracked modes file (schema `awa-modes/v1`) that your policy
points at via `modes_file:`. You never hand-edit it — set and inspect modes through the CLI or the
MCP tools:

```bash
dev-worktree.sh mode list                 # show every configured repo + the default
dev-worktree.sh mode get   projects/foo    # show the explicit entry (exact key) for one repo
dev-worktree.sh mode set   projects/foo on # set a repo to on | ask_on | off
dev-worktree.sh mode remove projects/foo   # drop the explicit entry (fall back to the default)
dev-worktree.sh mode sync                  # ensure-exists + normalize the modes file (idempotent)
```

`sync`/`repair` do **not** scan the filesystem, materialize per-repo entries, or prune stale
repos — they ensure the file exists and normalize/repair its own contents; the runtime
`default_mode` is what protects a new eligible repo. `policy-check` **WARNs** (never hard-fails) on
an invalid/broad-off/legacy/dangling-pointer config.

The same operations are exposed as MCP tools for plain-language use: `awa_mode_list` / `awa_mode_get`
(read) and `awa_mode_set` / `awa_mode_remove` / `awa_mode_repair` / `awa_mode_sync` (write, scoped to
the modes file only — they never touch a repo, git, or your primary checkout; `sync`/`repair`
normalize the file's own contents, they do not scan the filesystem).

**Default posture.** A repo with no explicit entry falls back to `default_mode`. The shipped default
is `on` (byte-for-byte back-compatible). A host may set `default_mode: ask_on` so eligible repos are
protected-and-asked by default without opting any of them into setup execution.

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
[Per-repo mode](#per-repo-mode-on--ask_on--off)).

The engine (`awa-engine <verb>`, launched by `bin/awa-engine.sh`): `doctor`, lifecycle
(`adopt`/`attest`/`apply-back`/`publish`/`retire`/`lease-read`), recovery
(`recover patch|bundle|restore-patch|list`), guard (`guard shell`/`guard can-clean` — the
engine-off kernel guarantee), `daemon` (`status`/`run-once`), `events`, and `mcp-serve` (a stdio
JSON-RPC MCP server exposing read-only tools).

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
