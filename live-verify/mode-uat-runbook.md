# Live verification — per-repo mode (Desktop)

**Goal:** prove ON / OFF change live guard behavior and dashboard surfacing after the ASK_ON
removal (2026-07-07): mode ON returns an enforced **`deny`** on an included-primary mutation (Cursor
enforces `deny`, treats `ask` as non-blocking — L4), mode OFF allows, and the one fail-safe rule
holds (only `off` disables; any other value → ON).

## Prereqs

- Host overlay with `modes_file: worktree-modes.yml` and `default_mode: on`
- Eligible fixture: `bash live-verify/bootstrap-eligible-uat.sh`

## Drive steps

1. **Default ON (no explicit entry):** a mutating command on the fixture's primary → **hard deny**
   (the command does not run; the agent gets the deny recovery message). Dashboard → repo in the
   **Included** bucket, `mode ""`.
2. **Explicit ON:** `dev-worktree.sh mode set <rel> on` (or `awa_mode_set` via MCP) → mutating
   primary still **denies**; `mode on` on the row.
3. **OFF:** `mode set <rel> off` → mutating primary → **allow** (no block). Dashboard → **Excluded**,
   `mode off`.
4. **Fail-safe (legacy/typo value):** hand-seed a modes file with `proj: ask_on` (or any non-off
   token) then `mode repair` → the value migrates to `on`; a mutating primary **denies**. A dashboard
   row for an un-repaired legacy value shows `mode "invalid"` but still classifies **Included**.
5. **Broad-off rejected:** `mode set . off` or MCP `awa_mode_set rel="." mode="off"` → error.
6. **Legacy value on `set` rejected:** `mode set <rel> ask_on` → error (only `on|off` accepted); the
   sanctioned migration for a pre-existing legacy value is `mode repair`.

## Headless smoke (before live)

```bash
POLICY=~/dev/_ops/policy/worktree-policy.yml ROOT=~/dev
REL=personal/awa-uat-<ts>
AWA_POLICY=$POLICY AWA_GOVERNED_ROOT=$ROOT awa-engine guard shell \
  --policy "$POLICY" --cwd "$ROOT/$REL" --command "git commit -m x"
# expect permission: deny  (mode ON / default_mode on)
# then: mode set $REL off  → re-run → expect permission: allow
```

## Evidence

Record in `live-verify/RESULTS-e2e-uat-20260707.md` and the `SECURITY.md` live ledger.
