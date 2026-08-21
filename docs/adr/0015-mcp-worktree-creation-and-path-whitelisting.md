# ADR 0015: MCP worktree creation + path whitelisting — fused ensure-reuse and disposable scratch dir
Status: draft — 2026-08-06

## Decision

Expose MCP worktree provisioning as a **fused** capability: (PRIMARY) an MCP tool that invokes
`dev-worktree.sh ensure`, reusing the kernel's sole creation path — classify → managed location →
lease → `move_agent_to_root` hand-off; and (SECONDARY) the option to create and whitelist a
disposable, managed scratch directory handed to the agent. A **hard** constraint governs both:
whitelisting must **never** downgrade an included primary checkout's protection — mirroring the FG3
mode-off restriction, only an exact `off` disables protection, and the MCP boundary rejects any
glob-metachar `mode='off'` key.

## Why

- **Reinvent worktree creation in MCP (rejected).** `ensure_worktree()` is the single creation path
  (`kernel/bin/dev-worktree.sh:227`): it reads the classification (`classify_repo` at `:242`),
  proceeds only when `class == include` (`if [ "$class" != "include" ]` at `:246`), places the
  worktree under the managed location (`MANAGED_LOCATION=…/awa/worktrees`, `:44`), and prints the
  `move_agent_to_root` hand-off (`:307`–`313`). A parallel MCP creator would duplicate classify,
  managed-location, and lease logic and risk divergence. Rejected in favor of reuse.
- **Disposable-dir only (rejected as the sole mechanism).** A throwaway whitelisted scratch dir is
  useful for ephemeral agent work, but it does not give the agent a real linked Safe Workspace with
  a lease keyed by `hash(worktree_path + branch + git_common_dir + boot_id)`
  (`contracts/awa-contract.v1.json:67`). So it is the *secondary*, not primary, mechanism.
- **Fused: `ensure` (primary) + disposable scratch dir (secondary) (chosen).** Reuse the kernel
  creation path for real protected worktrees, and offer a disposable managed scratch dir as an
  advisory-scoped add for ephemeral work. The non-downgrade floor mirrors FG3: only exact `off`
  disables protection (`kernel/lib/awa_policy.py:49`–`51`, `:266`), and `_reject_broad_off` today
  passes partial globs like `vendor/*` (`engine/modes.py:66`, `_is_pure_glob` at `:133`–`134`,
  `_reject_broad_off` at `:138` checking `rel in _BROAD_OFF_RELS or _is_pure_glob(rel)` at `:142`,
  invoked from `set_mode` at `:363`) — so any whitelist emitted through MCP must reject a
  glob-metachar `off` key and can only ever add advisory/standalone scope, never write `off` onto an
  included primary.

## Consequences

- Enables: MCP-initiated Safe Workspace creation that reuses classify + managed location + lease,
  plus an optional disposable scratch dir for ephemeral agent work.
- Forecloses: any whitelist that lowers an included primary checkout's protection. The MCP boundary
  rejects glob-metachar `mode='off'` keys (FG3); a disposable-dir whitelist is additive/advisory
  only.
- Must stay true: `ensure` remains the sole creation path and runs only on `class == include`; the
  disposable dir is managed (bundle-able / recoverable) and never a primary; the exact-`off`-only
  rule holds at the MCP boundary.
- Defers/creates: the MCP worktree-create tool and the disposable-dir provisioning are plan work
  items (M3), plus an M6 safety test that whitelisting-never-downgrades-primary. Cross-links: ADR
  0012 (route surfaces `ensure`), ADR 0014 (same kernel-gated, non-self-authorizing discipline),
  plan §M3/§M6.
