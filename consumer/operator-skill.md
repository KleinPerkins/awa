# AWA operator entrypoint

Guidance for AWA verbs in `consumer/operator_loop.py` and root-bound finish in
`consumer/finish_current.py`. Use for protecting, checking, resuming, saving,
old-copy cleanup, or finishing the temporary workspace. Match direct
closeout wording before generic routing.

## Current-workspace finish

1. Direct phrases such as "I'm done", "remove worktree", "can we close", "end session",
   "finish", and "finalize" start preview only. Negated, quoted, hypothetical,
   documentation, examples, feature requests, and discussion do not.
2. `beforeSubmitPrompt` may preview/block with the fixed warning, but it is only a
   convenience hook: it fails open; unsupported Cloud, background, primary, absent,
   and multi-root contexts create no challenge.
3. Standalone `Commit`, `Retain`, `Mixed`, or `Cancel` are case-insensitive and may
   have whitespace normalized. Exact `Close` is case-sensitive with no surrounding
   whitespace. The hook stores submitted text and canonical non-destructive choice in
   a one-use root/session/generation-bound envelope, then dispatches without rebuilding it:

   ```text
   python3 "$AWA_HOME/consumer/finish_current.py" dispatch --current
   ```

4. Reject attachments, extra words, booleans, "yes", and approval clicks. A case/trim
   Close variant returns `For safety, reply exactly: Close`, keeps pending dialogue
   live, and never reaches kernel authorization. `Cancel` deletes pending state and
   changes no repo/workspace content. Exact `Close` alone passes literal `Close` to the
   Phase-1 kernel.
5. `Commit`, `Retain`, and `Mixed` require explicit displayed row selections. Retain
   uses `retain --rows 1,3` and creates a protected, restore-proven local artifact;
   secrets require `--allow-secrets`. List/restore/delete are `retain-list`,
   `retain-restore`, and `retain-delete`; delete needs the exact artifact id again.
6. Commit delivery is not a local-commit claim: it requires one GitHub repo with merge
   commits enabled, an exact-head merge-commit PR merged into live default branch, and
   complete passing checks. Squash/rebase-only repos are unsupported. Network only in
   Commit/Mixed. After Commit/Retain/Mixed, rerun reconnaissance, show the full warning,
   and never infer or auto-run Close.
7. After successful Close, report workspace removal, branch retained/deleted result,
   agent stopping, and chat remaining open. Issue no further task tools.

## Operator loop

Never skip or reorder:

1. **hear**: take the operator's exact words; do not paraphrase them into a verb.
2. **map**: `OperatorLoop.map(utterance)` asks the optional router to PROPOSE only.
   The router never executes or authorizes. If absent, degrade to ask plus the six plain
   explicit options; never guess a destructive action.
3. **confirm-consequence**: the KERNEL descriptor
   `{destroys_unshared_work, irreversible, affects_shared_ref}` is computed from the
   LIVE target, never the router or a static verb list. Destructive consequences confirm;
   benign ones do not nag. CR9 is catalog-derived (`safety_class == "destructive"` or
   literal `confirm`), so a lying router cannot suppress confirmation.
   `affects_shared_ref` is live when `removes_shared_reference: true`; no current verb
   sets it, but the simulated-verb regression keeps biting.
4. **execute AWA's own verb** only after confirmation; never run router output.
5. **verify-real-outcome**.
6. **narrate** in plain language with honest confidence ("what I checked and what I
   couldn't"), zero Tier A/B/C banned terms, and no bare green pill.
7. **record-feedback** as an `intent-feedback/v1`-shaped record (not persisted in A0).

## Hard boundaries

- Router PROPOSES; AWA verbs EXECUTE; KERNEL sources consequence confirmation.
- Kernel-first/off-switch: the flow degrades safely with the router uninstalled, and the
  kernel guard/refuse/audit path never depends on router output.
- PM output is `pm_view(result)` only. Keep raw router fields (`tool_path`, `why[]`,
  `safety_class`), verb token, kernel consequence, and feedback internal under
  `result["_internal"]`/`result["feedback"]`.
- `confirm=True` is compatibility only for old-copy `cleanup`; it is never accepted for
  `finish_current`. Finish authorization is exact `Close` consumed by the kernel.
- Operator-facing strings are jargon-free and honest; `consumer/egress.py` enforces this.

Programmatic shape: `OperatorLoop(catalog)`, `loop.handle(..., confirm=None)`, then
`pm_view(result)`.

## A0 hardening status

A0 is implemented but not yet proven; the remaining gate is a non-technical PM
driving the loop end to end. `make verify` locks:
`test_consumer_loop.TestOperatorLoop.test_lying_router_cannot_suppress_destructive_confirm_cr9`,
`test_consumer_translators.TestTranslators.test_render_block_never_leaks_real_kernel_guard_text`,
`test_consumer_translators.TestTranslators.test_plain_param_never_echoes_unknown_or_banned_slot`,
`test_consumer_loop.TestOperatorLoop.test_affects_shared_ref_is_live_on_the_product_path`,
`test_consumer_loop.TestOperatorLoop.test_raw_router_envelope_stays_out_of_pm_facing_output`,
`test_consumer_contamination_structural.TestStructuralContamination.test_engine_imports_neither_consumer_nor_router`,
`test_kernel_off_matrix.KernelOffMatrixTest.test_kernel_has_no_router_import_or_read`, and
`test_consumer_seam.TestSeamRouterPresence.test_router_present_when_required` plus the
`router-seam` CI job.

The router pin (`consumer/router-pin.json`) tracks router `main` at `f44dbadd`, the
merge freezing `intent-proposal/v1`. `make verify` stays GREEN with the router
UNINSTALLED.
