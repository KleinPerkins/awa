## Learned User Preferences

- Use a plan-first workflow for AWA features: draft a rigorous plan, run multi-perspective review swarms, fold feedback into v2/v3, then implement.
- When executing an approved plan, do not edit the plan file; plan todos are the authoritative worklist.
- Work autonomously through obstacles to implemented, verified, and merged state; distinguish true blockers from approval-grantable actions.
- Large AWA builds and pre-merge work: use multitask mode with parallel subagents; monitor and close subagents actively, not passively.
- Before merge, run code-review and hardening swarms; iterate when the operator requests another pass.
- Verify reported failures are true positives before acting or reporting; confirm built-vs-gaps against disk and gates.

## Learned Workspace Facts

- KleinPerkins/awa is the SSP product (kernel + engine + dashboard + contract); KleinPerkins/dev is the thin host overlay (_ops delegators, `worktree-policy.yml`, `worktree-modes.yml`).
- Runtime installs to `~/.local/share/awa/current`; GCB shelf at KleinPerkins/skills `global/tools/awa` (Flavor-2 standalone-release pointer).
- Per-repo ON/ASK_ON/OFF modes live in a tool-owned `awa-modes/v1` file; host policy references it via `modes_file:` (LD overlay uses `default_mode: ask_on` for new eligible repos).
- Kernel-first invariant: never weaken engine-off safety; `make verify` is the repo gate (contract-freeze, zero-link, parity, guard tests).
- Product repo mutations use `_ops/bin/dev-worktree.sh ensure` + linked worktree; ~/dev is worktree-excluded — edit host overlay in place on a branch.
- MCP mode tools mutate only the host modes file — never repos, git state, or primary checkouts.
- Documented guard residual: cross-cwd `git -C <primary>` from a linked worktree is not classified by payload cwd (see SECURITY.md shell-gate scope).
