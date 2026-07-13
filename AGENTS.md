## Learned User Preferences

- Use a plan-first workflow for AWA features: draft a rigorous plan, run multi-perspective review swarms, fold feedback into v2/v3, then implement.
- When executing an approved plan, do not edit the plan file; plan todos are the authoritative worklist.
- Work autonomously through obstacles to implemented, verified, and merged state; distinguish true blockers from approval-grantable actions.
- Large AWA builds and pre-merge work: use multitask mode with parallel subagents on disjoint work; monitor and close them actively, with one writer per working tree.
- Before merge, run code-review and hardening swarms; iterate when the operator requests another pass.
- Verify reported failures are true positives before acting or reporting; confirm built-vs-gaps against disk and gates, then lock accepted fixes with biting regressions.
- For AWA, prioritize determinism, reliability, and consistency over convenience; destructive-path uncertainty must preserve the workspace.
- Do not claim live Desktop proof from tests or agent rehearsal; require the operator's real prompt and inspect the resulting metadata.
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
- Root-bound finish is kernel-authorized: finish wording only previews; `consumer/finish_current.py` and `beforeSubmitPrompt` are convenience surfaces and never authorize removal.
- `Commit`/`Retain`/`Mixed`/`Cancel` normalize case and surrounding whitespace; exact standalone attachment-free `Close` remains case-sensitive, one-use, and the sole removal authorization.
- Commit requires an exact-head merge-commit PR incorporated into the live default branch with passing checks; Retain creates a protected restore-proven local artifact; ignored rows are Retain-only; removal is zero-network.
- After hook-mode Commit/Retain/Mixed, the next prompt only publishes a fresh hook-owned warning; even `Close` is discarded there, so a second exact `Close` is required.
- Finish CLIs reject option abbreviations and expose only fixed closed JSON; removed-state and branch truth come from durable index/journal evidence, never invented fallbacks.
- `dev-worktree.sh clean --force` only overrides the ignored-files gate (`--bundle` archives first); it does not bypass commit-safety (`branch_is_cleanup_safe`) — branches with unrecognized-unshared commits still refuse.
- Recovery archives from `clean --bundle` live under `${XDG_STATE_HOME:-~/.local/state}/awa/recovery` (outside git); no built-in TTL/prune verb today.
