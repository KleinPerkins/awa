# ADR 0010: Remote Git commands remain mutating; one upstream-fetch maintenance exception
Status: accepted — 2026-08-23 (owner sign-off; design PR #120)

## Context

AWA classifies `git fetch` and `git push` as mutating because both enter transport and may write
Git state or invoke configured helpers. A `--dry-run` token does not make either command read-only.

The original decision therefore denied every fetch and push on an included primary and directed
agents to fetch from a linked Safe Workspace. Fresh verification established that this location
boundary does not protect the affected Git state: a primary checkout and its linked worktrees share
the same common directory, object database, remote-tracking refs, and fetch bookkeeping.

The product boundary is protection of unshared work—not a transport, credential-helper, hook, or
network sandbox. The useful distinction is therefore between a tightly bounded upstream refresh
performed on a clean primary and an arbitrary remote operation.

## Decision

1. **Classification remains honest.** Every `git fetch` and `git push` remains mutating in both the
   engine and kernel classifiers. Neither family is reclassified as read-only, including dry-runs.

2. **One decision-layer fetch exception is authorized.** ADR 0019 may convert the included-primary
   deny into allow only for exact `git fetch` or `git fetch <configured-upstream-remote>` on a clean,
   attached, idle checkout with exactly one remote-tracking upstream and safe configured fetch
   destinations.

3. **The exception is state- and target-bound.** The guard rejects Git global options, fetch
   options, URLs, explicit refspecs, additional operands, wrappers, command chaining, repository
   retargeting/config injection, local upstreams, unsafe refspec destinations, dirty state, and
   in-progress Git operations. Any inspection uncertainty falls through to the existing deny.

4. **Normal configured fetch behavior is accepted.** The bounded fetch may write objects,
   `FETCH_HEAD`, configured remote-tracking refs, shallow/partial-clone metadata, reachable tags,
   and ordinary maintenance state, and may invoke configured transport, credential, and hook
   behavior. The caller checks clean status after the command before continuing.

5. **Every other remote form remains denied on a protected primary.** This includes fetch dry-run,
   fetch with any option, arbitrary remote/URL/refspec fetch, `git pull`, every push form (including
   dry-run and `--no-verify`), recursive push, remote update/prune, and explicit tag/submodule
   maintenance.

6. **Outer context behavior is unchanged.** Linked Safe Workspaces, adopted leases,
   standalone/advisory repositories, Cloud agents, and explicit operator overrides continue to
   resolve before this included-primary exception.

## Why

- **Relocating fetch is not isolation.** Linked worktrees share precisely the common Git state that
  fetch updates, so requiring a worktree detour adds friction without protecting unshared work.
- **Clean state plus upstream binding separates maintenance from work.** The exception cannot
  author local history, switch branches, target an arbitrary ref, resolve divergence, or push.
- **Dry-run remains an invalid proof.** Fetch and push dry-runs can still enter transport, invoke
  helpers/hooks, and write local state; neither qualifies for the exact no-option fetch grammar.
- **A helper sandbox is out of scope.** Configured Git behavior is trusted equally in the primary
  and linked worktrees. AWA protects worktree state; it does not attest every executable Git may
  invoke.

Alternatives considered:

- **Keep every primary fetch denied — rejected.** It preserves no additional common-repository
  isolation and perpetuates the maintenance failure this decision is intended to remove.
- **Allow `git pull --ff-only` — rejected.** Separating refresh from branch advancement gives each
  operation its own state check and failure report.
- **Allow remote dry-runs — rejected.** Their option-bearing grammar and non-zero side-effect
  surface do not match the bounded maintenance operation.
- **Build a remote-operation sandbox — rejected.** That is a separate product with materially
  different authority and complexity.

## Consequences

- A clean protected primary may refresh only its configured upstream through ADR 0019's exact
  decision-layer exception.
- Fetch and push remain mutating everywhere; no consumer can mistake the exception for a read-only
  classification.
- Push, pull, dry-run, arbitrary fetch, and unnecessary remote-maintenance forms remain denied.
- Engine, source-hook, and installed-hook behavior must stay identical without adding an engine
  dependency to the kernel path.
- Plain-language refusal copy directs configuration repair or work reconciliation to a Safe
  Workspace and never recommends a blanket primary override for routine maintenance.
- Any broader remote allowance requires a new ADR and successor plan.

## Live-state verification record

Verified 2026-08-21 and revalidated 2026-08-23 against:

- AWA `origin/main` at `01053f6`; `engine/guard.py` and
  `kernel/hooks/worktree-guard.sh` still classify fetch/push as mutating and deny confirmed
  included-primary mutations.
- Apple Git `2.50.1` (`Apple Git-155`) on the operator host.
- AWA primary and linked-worktree `git rev-parse --git-common-dir` /
  `git rev-parse --git-path refs/remotes/origin/main`, which resolve to the same common Git state.
- Git documentation for fetch destinations and `FETCH_HEAD`, fetch/push dry-run, configured hooks,
  helpers, automatic maintenance, recursive behavior, and push negotiation.
- The accepted companion plan
  `docs/plans/guard-fast-forward-primary-carve-out-v1.md`, which requires offline behavior proof,
  closed command/state corpora, engine/kernel parity, installed-hook UAT, and caller postconditions.
