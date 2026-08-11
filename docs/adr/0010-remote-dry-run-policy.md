# ADR 0010: Remote Git dry-runs remain mutating on protected primaries
Status: draft — 2026-08-11

## Decision

1. AWA classifies every `git fetch` and `git push` invocation as potentially mutating on an
   included primary checkout. `--dry-run`, push `-n`, `--no-verify`, and recursive variants do
   not create a read-only exception.
2. AWA's existing outer context decision remains unchanged: linked Safe Workspaces, adopted
   leases, standalone/advisory repositories, Cloud agents, and explicit operator overrides allow
   before command-family enforcement. An operator who needs a remote preflight uses a linked Safe
   Workspace or standalone scratch repository instead of weakening a protected primary.
3. A future remote-command exception requires behavior proof across supported Git versions of:
   zero Git-managed persistent writes, zero remote updates, and zero arbitrary hook/helper
   execution. A `--dry-run` token alone is never sufficient evidence.

## Why

`fetch --dry-run` and `push --dry-run` suppress their ordinary headline mutation, but neither
creates a deterministic read-only boundary:

- `fetch --dry-run` suppresses normal destination-ref and `FETCH_HEAD` updates, yet still enters
  object transport. Upstream Git paths can write objects, shallow metadata, partial-clone or
  bundle configuration, bundle/remote-HEAD refs, commit graphs, and maintenance state.
- `push --dry-run` suppresses stock local/remote ref updates, yet the normal `pre-push` hook runs
  unless `--no-verify` is supplied. Transport, credential, SSH, and remote helpers start; recursive
  child pushes and `push.negotiate` can invoke additional Git operations.
- Hooks and helpers are arbitrary executables. Their possible writes are not bounded by the
  repository or by Git's dry-run flag.

Alternatives considered:

- **Allow exact `--dry-run`/push `-n` forms on protected primaries — rejected.** Token shape cannot
  prove the absence of object/config/shallow writes or arbitrary hook/helper effects.
- **Deny remote dry-runs in every context — rejected.** AWA's existing Safe Workspace and
  standalone-repository boundary already isolates work from a protected primary; adding a second
  global network prohibition would exceed the product's mutation-protection purpose.
- **Build a remote-operation sandbox — rejected.** A credential/helper/network sandbox is a
  separate product surface and is unnecessary to close this classifier gap. The existing linked
  worktree or standalone scratch path is sufficient.

AWA is not a general network sandbox. This stronger proof bar applies when carving an exception
out of a command family already known to mutate local or remote state; it does not retroactively
redefine every existing local query command.

## Consequences

- Protected primaries continue to deny all fetch/push forms, including dry-runs.
- Linked Safe Workspaces and standalone scratch repositories remain the supported place for remote
  preflights.
- The classifier must test fetch/push dry-run denials explicitly so later flag-based allowlisting
  cannot weaken the policy accidentally.
- The engine and kernel hook must preserve the same outcome without introducing an engine import
  into the kernel path.
- This decision does not promise that commands run from a Safe Workspace are side-effect-free; it
  protects the primary-checkout boundary.
- A future exception requires a higher-numbered ADR that supersedes this record and includes new
  cross-version behavior proof.

## Live-state verification record

Verified 2026-08-11 against:

- AWA `origin/main` at `5be9e68`, where `_GITMUT` already treats `fetch` and `push` as mutating and
  PR #95 deliberately deferred dry-run exceptions.
- Apple Git `2.50.1` (`Apple Git-155`) on the operator host.
- Git documentation for fetch dry-run, push dry-run, recursive push, `--no-verify`, `pre-push`,
  and `push.negotiate`.
- Upstream Git source behavior in `builtin/fetch.c`, `fetch-pack.c`, `bundle-uri.c`,
  `transport.c`, `send-pack.c`, and `transport-helper.c`.

The implementation plan requires two offline regression proofs:

1. A local bare-remote fetch dry-run downloads a previously absent object while destination refs
   and `FETCH_HEAD` remain unchanged.
2. A local bare-remote push dry-run runs a sentinel `pre-push` hook while the proposed remote ref
   remains absent.
