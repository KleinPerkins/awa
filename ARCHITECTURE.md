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
| `mcp_server` | stdio newline-delimited JSON-RPC MCP server exposing read-only tools (`awa_status`, `awa_lease_read`, `awa_guard_shell`) |
| `remote` | Apply-back execute adapter: read/write token split (S3), SHA-drift refusal, preview→confirm gating (live push is an operator step) |
| `redact` | S5 secret/PII redaction pass; every persisted audit/command string is piped through it |
| `cli` / `__main__` | `awa-engine` command surface (launched by `bin/awa-engine.sh`) |

## Per-repo mode (ON / ASK_ON / OFF)

A repo's AWA behavior is a first-class, explicitly-settable **mode** with three states, resolved
inside the same generic zero-link classifier the shell kernel and the engine share:

- **ON** → `include`: the guard **asks** before a mutating command on the primary checkout,
  `ensure` creates a Safe Workspace, and the repo is the only mode eligible for repo-committed
  worktree-setup execution.
- **ASK_ON** → `ask_on`: the guard still **asks** and `ensure` still creates a Safe Workspace (so
  the nudge is coherent), but the repo is surfaced in its own dashboard bucket and is **not**
  setup-exec eligible. This is the one genuinely new runtime behavior.
- **OFF** → `exclude`: AWA leaves the repo alone — the guard allows, `ensure` is a no-op.

For a mutating command on a primary checkout the guard asks under ON and ASK_ON and allows under
OFF; read-only commands, linked worktrees, and adopted leases always allow in every mode.
`afterFileEdit` stays **observation-only** in every mode (it can only write a metadata-only
detection receipt, never pre-block).

### Storage — a tool-owned, source-tracked modes file

Modes are recorded in a dedicated, machine-owned file (schema `awa-modes/v1`) referenced from the
host policy via a single `modes_file:` pointer (resolved relative to the policy file's directory;
`~`/absolute allowed). The file has no hand-authored content, so the tools can rewrite it atomically
without clobbering a hand-authored policy:

```
schema: awa-modes/v1
default_mode: ask_on
modes:
  projects/foo: on
  projects/bar: off
  projects/baz: ask_on
```

Keys are repo paths relative to the governed root (exact or glob, first-match by file order, exact
preferred), values `on|off|ask_on` (case-normalized). `default_mode` governs eligible repos with no
explicit entry. The file is intended to be **source-tracked** in the host overlay and rewritten only
by the tools — never hand-edited. A repo-local mode marker is deliberately rejected: a cloned repo
could ship `off` to silence the guard (a repo-controlled safety downgrade), so modes are host-owned
only.

### Resolution precedence (classifier, first-match-wins)

1. not a git repo → `not-git`
2. explicit **OFF** → `exclude` (absolute opt-out, top precedence)
3. legacy `overrides.exclude` / `overrides.include`
4. **SAFETY excludes** — umbrella root, governed-marker, foreign-hook framework, read-only path
   (these sit **above** the explicit ON/ASK_ON step, so an explicit ON/ASK_ON/invalid may not
   override a safety-exclude)
5. explicit **ON** → `include`; explicit **ASK_ON** → `ask_on`; **invalid** value → `ask_on`
   (safe fallback, and `policy-check` fails)
6. exclude glob → `exclude`
7. no origin → `advisory`
8. eligibility (include glob / `default: include`) mapped through **`default_mode`**:
   `on`→`include`, `ask_on`→`ask_on`, `off`→`exclude`

`default_mode: on` reproduces the pre-mode classification byte-for-byte. The classifier's 4-field
tab output is unchanged; a separate `mode-for` CLI exposes the resolved explicit mode for
shell/status/dashboard plumbing. `kernel/lib/awa_policy.py` and `engine/policy.py` implement this
identically, and their parity (including `modes_file` load and invalid handling) is tested.

### Default posture (product vs host)

The shipped template keeps `default_mode: on` for byte-for-byte back-compat: a host with no
`modes_file`/`modes` behaves exactly as before. Opting eligible repos into **ASK_ON by default** is a
host-overlay choice (`default_mode: ask_on`), a safety tightening — same guard-ask + ensure, but
eligible repos are no longer setup-exec eligible and surface in the `ask_on` bucket.

### Tools — generalized verbs (view / add / update / delete / repair / sync)

Modes are managed only through generalized verbs over the modes file — never by hand:

- Engine: `python3 -m engine mode {list,get,set,remove,repair,sync,doctor}` (via `engine/modes.py`).
- Kernel CLI: `dev-worktree.sh mode <verb>` delegates to the engine module.
- MCP: read tools `awa_mode_list`/`awa_mode_get` plus mutating, path-scoped config tools
  `awa_mode_set`/`awa_mode_remove` (write) and `awa_mode_repair`/`awa_mode_sync` (materialize /
  reconcile eligible repos to the default, idempotent and non-destructive of explicit entries).

Writes are schema-validated, atomic, and backup-before-write, and are **path-scoped to the host
modes file** — they never touch a repo, git, or a primary checkout. The MCP server's read-only
invariant is amended to "read-only for safety state; config mutations are path-scoped to the host
modes file." `repair`/`sync` are how a new eligible repo is materialized to the host default and how
stale entries are reported (pruning only under an explicit opt-in). These make modes changeable in
plain language by a non-technical owner, with the CLI verbs as the parity mechanism.

## The contract is BEHAVIOR-only (location is informational)

`contracts/awa-contract.v1.json` freezes the kernel's public **behavior**: the CLI verbs/flags, the
`awa-worktree/v1` dashboard JSON shape, the guard permission schema, and the `.awa/lease.json`
shape. These are the interface; the engine may only BACK them, never silently change them. A
removal/rename of a required verb/flag/key — or a changed schema string — is a breaking change that
requires a versioned bump (`awa-contract.v2.json`). Additive, backward-compatible OPTIONAL fields
are allowed within v1.

The per-repo mode work is **additive within v1 — no v2**. The contract freezes keys and `schema`
literals, not value sets, so the new `ask_on` classification/reason value lives in the open-vocabulary
`classification`/`reason` fields; the new optional `summary.ask_on`, `repo.mode`, and `repo.mode_error`
dashboard fields, the new `mode` CLI verb, and the new `awa_mode_*` MCP tools are all additive (the
freeze checker asserts frozen verbs/flags/keys/shapes exist, not that none are added). The frozen
guard `ask`/`allow` shapes are unchanged — ASK_ON reuses the same `ask` permission shape as ON.

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
