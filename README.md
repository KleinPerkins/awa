# AWA — Agent Worktree Automation (engine)

**AWA keeps agent work off your main checkout.** When an agent (or you) starts mutating a
repository, AWA steers the work into an isolated `git` worktree ("Safe Workspace"), detects
native edits to the primary checkout, refuses unsafe cleanups, and can recover uncommitted work
— so your main branch stays clean and nothing gets silently lost.

This repository is the **AWA engine**: the durable, testable software home for the system. It is
the pinned artifact that the global `tools/awa` capability shelf points at, and that a host
installs alongside its own machine-local kernel shims.

> Kernel-first (frozen): the safety guarantee holds with the engine/daemon **OFF**. The engine
> only observes, bookkeeps, and eases. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## What's in here

```
engine/                 Python package (stdlib + sqlite3 only) — the kernel core + engine layers
  paths identity gitutil policy lock state lease lifecycle recovery daemon guard mcp_server remote
  redact                S5 secret/PII redaction pass for the audit/command log
  cli __main__          the `awa-engine` command surface
  tests/                the full test suite (unittest; local-only, no network)
bin/awa-engine.sh       launcher — puts the repo root on PYTHONPATH and runs `python3 -m engine`
contracts/              the FROZEN kernel contract (awa-contract.v1.json)
hook-probe/             operator harness for empirically probing live editor hooks
ARCHITECTURE.md         the kernel-first design invariant + engine module map
SECURITY.md             the Cluster-D security ledger (S1–S6) + threat model
```

## Requirements

- Python **3.9+** (standard library + `sqlite3` only — no third-party dependencies).
- `git` on `PATH`.

## Quick start

```bash
# Run the engine CLI (JSON on stdout; human notes on stderr):
bin/awa-engine.sh doctor
bin/awa-engine.sh --help

# Run the test suite:
make test           # or: bash engine/tests/run-tests.sh
```

The engine reads its repo-classification policy from the **host**. Point it at a host policy
file with `AWA_POLICY=/path/to/worktree-policy.yml` (or the `--policy` flag on the guard verb);
absent a policy, the resolver degrades to a safe default. The engine ships **no** policy of its
own and carries **zero** host/organization-specific literals (see `ARCHITECTURE.md` §zero-link).

## Command surface (backs the frozen kernel)

`awa-engine <verb>` — grouped verbs: `doctor`, lifecycle (`adopt`/`attest`/`apply-back`/
`publish`/`retire`/`lease-read`), recovery (`recover patch|bundle|restore-patch|list`), guard
(`guard shell`/`guard can-clean` — the engine-off kernel guarantee), `daemon` (`status`/
`run-once`), `events`, and `mcp-serve` (a stdio JSON-RPC MCP server exposing read-only tools).

## Versioning & the frozen contract

`engine/__init__.py:__version__` is the engine version; releases are tagged (`vX.Y.Z`). The
kernel contract in `contracts/awa-contract.v1.json` is frozen — the engine may only BACK those
surfaces. A removal/rename is a breaking change requiring `awa-contract.v2.json`.

## License

Proprietary — © KleinPerkins. All rights reserved. See [`LICENSE`](LICENSE).
