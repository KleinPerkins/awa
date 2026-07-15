# Post-UAT items 2–3 — Phase 3 Step 3.6 dashboard

Status: **implemented and executable paths verified; fresh live Canvas click remains operator-bound**

## Direct evidence and code path

Preserved bundle:
`${XDG_STATE_HOME:-$HOME/.local/state}/awa/uat-evidence/phase-3-step-3.6-20260715/`

The operator observed that **Refresh via agent** opened a new foreground agent chat and requested
adaptive KB/MB/GB size labels. The sealed collection-time source snapshot directly shows the refresh
handler dispatching `newComposerChat`; the captured SDK declaration defines that action as opening a
new local agent chat. This is the exact pre-fix code path, not an inferred platform cause.

## Fix

- The seed now writes one closed `dash.runRequest` for the fixed `awa-dashboard-refresh` command.
  It contains no prompt and never calls `newComposerChat`.
- Install/repair publishes the product seed and registers that command only when the machine has
  already enabled the shared `local-jobs` Canvas bridge. A dedicated environment marker proves job
  ownership; install/repair and uninstall refuse to replace or remove a same-named unowned job.
- The fixed command runs the read-only renderer, which regenerates the machine-local Canvas and its
  narrowly validated same-directory bridge alias.
- The emitter measures each worktree with bounded `du -sk`, emits `size_bytes`, and renders an
  adaptive `plain_size` label in KB, MB, or GB. Timeout/failure becomes `not available`.

## Biting regressions

`TestCanvasRefreshBridge.test_seed_uses_background_request_and_never_opens_chat` was run against
pre-item-2 commit `39815a7` and failed because `"dash.runRequest"` was absent and
`newComposerChat` remained.

`TestWorktreeDiskSize.test_seed_displays_size_on_every_worktree_row` was run against pre-item-3
commit `d5f3a22` and failed because the size header and row value were absent.

The ownership-collision regression was run against pre-hardening commit `403841c` and failed because
the installer returned success after updating the same-named unowned job. Current focused tests pass.

## Verification

Focused commands:

```text
bash -n dashboard/install_actions.sh install.sh
python3 dashboard/test_emitter.py TestCanvasRefreshBridge TestWorktreeDiskSize
```

Result: **PASS** (11 focused tests)

Final repository gate:

```text
make verify
```

Result: **PASS** — 772 Python tests passed (15 skipped), all 17 dashboard tests passed, and the
contract freeze, static installer preflight, and live-verification artifact checks passed.

No unit test or agent rehearsal is represented as a fresh live Cursor Canvas click. The preserved
operator observation proves the original defect; the executable source/tests prove the replacement
path and output shape. A new operator click is the remaining platform-bound confirmation.
