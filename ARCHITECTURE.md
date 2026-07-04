# AWA — architecture: kernel-first, engine off the safety-critical path (frozen)

> Frozen architectural principle for Agent Worktree Automation (AWA). This is the in-repo
> record of the design invariant; the machine-checkable surface pins live in
> `contracts/awa-contract.v1.json`.

## The invariant (frozen)

**The kernel delivers the full safety guarantee standalone; the engine only observes,
bookkeeps, and eases.** The safety guarantee — detection, recovery, cleanup-refusal, and
safe lifecycle decisions — MUST hold with the daemon/engine/watcher **OFF**. Nothing the
engine adds may become load-bearing for the core guarantee. The kernel contract is frozen so
the engine can be layered *behind* it without ever regressing a green verifier.

AWA is a two-layer system:

- **Kernel (host layer).** A small set of host-installed shims (a `git worktree` adapter/CLI,
  a `beforeShellExecution` gate, an `afterFileEdit` detector, a policy resolver, a render-only
  status dashboard). The kernel carries the safety guarantee on its own and is where any
  host/organization-specific policy literals live — never in this engine.
- **Engine (this repo).** A Python package (`engine`, stdlib + `sqlite3` only) that BACKS the
  kernel surfaces with durable state, recovery, a single-instance daemon, an MCP server, and a
  preview-first apply-back adapter. Every engine layer is gated; none is on the safety-critical
  path.

## Engine module map

| Module | Responsibility |
|---|---|
| `paths` | XDG state/recovery/detection/lock dirs; `700`/`600` perms (S4); local-disk-only assertion (WAL safety, H6) |
| `identity` | Stable worktree identity = hash(path + branch + common-dir + boot-id); **never** a bare pid |
| `gitutil` | Thin, testable `git` wrapper (no shelling pitfalls) |
| `policy` | Generic repo classifier: include/exclude globs + governed-marker & foreign-hook detectors, all supplied by a host policy file |
| `lock` | Per-common-dir advisory flock — the real write-serialization/collision boundary |
| `state` | SQLite (WAL) store: leases, append-only **redacted** audit events, detections, quarantine refs, recovery artifacts |
| `lease` | `.awa/lease.json` read/write + attest; native-window adopt (no push) |
| `lifecycle` | Adopt → attest → apply-back **preview** (SHA-bound, recovery-before-mutation) → retire |
| `recovery` | Patch round-trip + bundle (secret-skip S1, symlink-escape drop S2) + restore + list |
| `daemon` | Single-instance (flock'd pidfile) bounded maintenance loop + quarantine-ref cleanup/retention |
| `guard` | Adversary-aware mutating-shell classifier + engine-OFF decision + cleanup-refusal (`can_clean`); reads ONLY policy + `.awa/lease.json` |
| `mcp_server` | stdio newline-delimited JSON-RPC MCP server exposing read-only tools (`awa_status`, `awa_lease_read`, `awa_guard_shell`) |
| `remote` | Apply-back execute adapter: read/write token split (S3), SHA-drift refusal, preview→confirm gating (live push is an operator step) |
| `redact` | S5 secret/PII redaction pass; every persisted audit/command string is piped through it |
| `cli` / `__main__` | `awa-engine` command surface (launched by `bin/awa-engine.sh`) |

## Contract freeze

`contracts/awa-contract.v1.json` pins the kernel's public interface (CLI verbs/flags, the
`awa-worktree/v1` dashboard JSON shape, the guard permission schema, the `.awa/lease.json`
shape). The engine may only BACK these surfaces; a removal/rename is a breaking change that
requires a versioned bump (`awa-contract.v2.json`). Additive OPTIONAL fields are allowed within
v1. The host wires this contract into its own freeze check against the live kernel shims.

## Zero-link (host-agnostic master)

This engine is designed to be installed into any host and to be publishable on a global
capability shelf. It therefore carries **zero** host/organization-specific literals. Repo
classification — including *excluding a self-governed sibling repo* — is decided **generically**
via the governed-marker detector (a repo that ships its own `_ops/POLICY.md` / integrity-engine
marker is treated as self-governed and left alone) and the foreign-hook detector, never by a
hard-coded org/vendor literal. Any such literals live only in the host's machine-local policy
file. `engine/tests/test_zero_link.py` is the in-repo pre-flight for this invariant.

## Security

See `SECURITY.md` for the Cluster-D security ledger (S1–S6) and the threat model. Each
closable row is backed by an automated test in this repo's suite.
