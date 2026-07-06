# Live verification — per-repo mode (Desktop)

**Goal:** prove ON / ASK_ON / OFF change live guard behavior and dashboard surfacing after the
2026-07-06 mode feature + round-2 hardening.

## Prereqs

- Host overlay with `modes_file: worktree-modes.yml` and `default_mode: ask_on`
- Eligible fixture: `bash live-verify/bootstrap-eligible-uat.sh`

## Drive steps

1. **Explicit ASK_ON:** `dev-worktree.sh mode set <rel> ask_on` (or `awa_mode_set` via MCP).
   Mutating command on primary → **ask**. Dashboard → repo in **Ask-on** bucket.
2. **OFF:** `mode set <rel> off` → mutating primary → **allow** (no prompt).
3. **default_mode:** second fixture with no explicit entry → **ask** (inherits `ask_on`).
4. **Broad-off rejected:** `mode set . off` or MCP `awa_mode_set rel="." mode="off"` → error.

## Headless smoke (before live)

```bash
POLICY=~/dev/_ops/policy/worktree-policy.yml ROOT=~/dev
REL=personal/awa-uat-<ts>
AWA_POLICY=$POLICY AWA_GOVERNED_ROOT=$ROOT awa-engine guard shell \
  --policy "$POLICY" --cwd "$ROOT/$REL" --command "git commit -m x"
# expect permission: ask when ask_on
```

## Evidence

Record in `live-verify/RESULTS-mode-<date>.md` and `SECURITY.md` live ledger.
