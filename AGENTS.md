## Learned User Preferences

- Use a plan-first workflow for AWA features: draft a rigorous plan, run multi-perspective review swarms, fold feedback into v2/v3, then implement.
- When executing an approved plan, do not edit the plan file; plan todos are the authoritative worklist.
- Work autonomously through obstacles to implemented, verified, and merged state; distinguish true blockers from approval-grantable actions.
- Large AWA builds and pre-merge work: use multitask mode with parallel subagents; monitor and close subagents actively, not passively.
- Before merge, run code-review and hardening swarms; iterate when the operator requests another pass.
- Verify reported failures are true positives before acting or reporting; confirm built-vs-gaps against disk and gates.
- Prefer the simplest root-bound, proof-checked AWA mechanism; reject identity or lineage designs that depend on unstable Cursor chat IDs or complex actor/session control planes.
- AWA implementation/refactor sessions: launch with project root = KleinPerkins/awa product repo, not disposable UAT fixtures or the ~/dev host overlay.

## Learned Workspace Facts

- KleinPerkins/awa is the SSP product (kernel + engine + dashboard + contract); KleinPerkins/dev is the thin host overlay (_ops delegators, `worktree-policy.yml`, `worktree-modes.yml`).
- Runtime installs to `~/.local/share/awa/current`; GCB shelf at KleinPerkins/skills `global/tools/awa` (Flavor-2 standalone-release pointer).
- Per-repo ON/OFF modes live in a tool-owned `awa-modes/v1` file; host policy references it via `modes_file:` (LD overlay uses `default_mode: on`). ON = a confirmed mutating command on an included primary returns an enforced hook `deny` (Cursor enforces `deny`, treats `ask` as non-blocking — L4); one fail-safe rule (only exact `off` disables; any other value => ON); Cloud/background agent degrades to allow; `mode repair` migrates a legacy `ask_on` forward to `on`.
- Kernel-first invariant: never weaken engine-off safety; `make verify` is the repo gate (contract-freeze, zero-link, parity, guard tests).
- Product repo mutations use `_ops/bin/dev-worktree.sh ensure` + linked worktree; ~/dev is worktree-excluded — edit host overlay in place on a branch.
- MCP mode tools mutate only the host modes file — never repos, git state, or primary checkouts.
- Documented guard residual: cross-cwd `git -C <primary>` from a linked worktree is not classified by payload cwd (see SECURITY.md shell-gate scope).
- `dev-worktree.sh clean --force` only overrides the ignored-files gate (`--bundle` archives first); it does not bypass commit-safety (`branch_is_cleanup_safe`) — branches with unrecognized-unshared commits still refuse.
- Recovery archives from `clean --bundle` live under `${XDG_STATE_HOME:-~/.local/state}/awa/recovery` (outside git); no built-in TTL/prune verb today.
