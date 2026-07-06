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
`doctor`, `policy-check`, `dashboard-data`.

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
