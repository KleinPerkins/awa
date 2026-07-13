# AWA operator entrypoint

This installed agent entrypoint routes operator language through `consumer/operator_loop.py`.
Root-bound finish dialogue is implemented by the production stdlib CLI
`consumer/finish_current.py`; the intent router remains optional and never authorizes removal.

## When to use

Use it for protecting, checking, resuming, saving, old-copy cleanup, or finishing the current
temporary workspace. Direct closeout wording is matched before generic routing.

## Current-workspace finish

1. Direct phrases such as “I'm done”, “remove worktree”, “can we close”, “end session”, “finish”,
   and “finalize” start preview only. Negated, quoted, hypothetical, documentation, examples,
   feature requests, and discussion do not.
2. The installed `beforeSubmitPrompt` hook may perform that preview and block the initiating prompt
   with the fixed warning. The hook is convenience only and fails open; unsupported Cloud,
   background, primary, absent, and multi-root contexts create no challenge.
3. A standalone `Commit`, `Retain`, `Mixed`, or `Cancel` is case-insensitive (and may have
   surrounding whitespace normalized). Exact `Close` remains case-sensitive with no surrounding
   whitespace. The hook captures submitted text and its canonical non-destructive choice in a
   one-use root/session/generation-bound envelope, then dispatches without reconstructing the
   user's answer:

   ```text
   python3 "$AWA_HOME/consumer/finish_current.py" dispatch --current
   ```

4. Reject attachments, extra words, booleans, “yes”, and approval clicks as choices. A case or trim
   variant of Close returns `For safety, reply exactly: Close`, keeps the pending dialogue live, and
   never activates or invokes kernel authorization. `Cancel` deletes pending state and changes no
   repository/workspace content. Exact `Close` is the only dispatcher path that passes literal
   `Close` to the Phase-1 kernel.
5. `Commit`, `Retain`, and `Mixed` require explicit displayed row selections. Retain uses
   `retain --rows 1,3` and creates a protected, restore-proven local artifact; secrets additionally
   require `--allow-secrets`. List/restore/delete use `retain-list`, `retain-restore`, and
   `retain-delete` (delete requires the exact artifact id again).
6. Commit delivery is not a local-commit assertion: it requires one GitHub repository with merge
   commits enabled, an exact-head merge-commit PR incorporated into the live default branch, and
   complete passing checks. Squash/rebase-only repositories are unsupported by this action. Network is
   allowed only in Commit/Mixed. After Commit/Retain/Mixed, run fresh reconnaissance and show the
   full warning again; never infer or auto-run Close.
7. After a successful Close, report workspace removal, branch retained/deleted result, that the
   agent is stopping, and that the chat remains open. Issue no further task tools.

## The loop (never skip a step, never reorder)

1. **hear** — take the operator's exact words. Do not paraphrase into a verb yourself.
2. **map** — `OperatorLoop.map(utterance)` asks the router to PROPOSE (read-only). The router never
   executes and never authorizes.
   - If the router is not installed, `map` returns `None` and the loop DEGRADES to ask + the
     secondary explicit path (the six plain options). Never guess a destructive action.
3. **confirm-consequence** — the confirmation is sourced from the KERNEL consequence descriptor
   `{destroys_unshared_work, irreversible, affects_shared_ref}`, computed from the LIVE target, never
   from the router and never from a static verb list. A safe-looking verb with a destructive
   consequence MUST confirm; a benign verb MUST NOT nag.
   - **CR9 is router-independent.** The destructive-class confirmation gate is derived from the
     CONSUMER CATALOG (an entry's `safety_class == "destructive"` or a required literal `confirm`
     slot), NOT from the router's `missing_params`. A lying router (`missing_params=[]`,
     `verdict=strong`) therefore cannot suppress the confirmation on a destructive verb.
   - **`affects_shared_ref` is live.** When a verb's catalog entry declares
     `removes_shared_reference: true` (optional; default false), the loop passes that to the kernel so
     the "changes something other people rely on" reason surfaces. No current AWA verb sets it — it is
     wired defensively and covered by a simulated-verb regression test.
4. **execute AWA's OWN verb** — only after the confirmation gate passes. The loop runs an AWA verb;
   it NEVER runs anything from the router's output.
5. **verify-real-outcome** — check the verb actually did what it claimed.
6. **narrate** — report what ACTUALLY happened in plain language, with honest confidence ("what I
   checked and what I couldn't"), zero banned terms — never a bare green pill.
7. **record-feedback** — emit an `intent-feedback/v1`-shaped record (not persisted in A0).

## Hard rules

- The router PROPOSES; AWA verbs EXECUTE; the KERNEL sources every consequence confirmation.
- Kernel-first / off-switch: everything here degrades safely when the router is uninstalled, and the
  kernel guard/refuse/audit path is never on the router's critical path.
- Every operator-facing string is jargon-free (zero Tier A/B/C banned terms) and honest about
  confidence. The egress gate (`consumer/egress.py`) and its tests enforce this.

## Programmatic entry

```python
from consumer.operator_loop import OperatorLoop, pm_view
loop = OperatorLoop(catalog)              # router resolved lazily; degrades to ask if uninstalled
result = loop.handle(utterance, target=resolved_target, facts=kernel_facts, confirm=None)
# result["decision"] in {execute, awaiting_confirmation, need_more_info, degraded_to_ask, not_understood}
pm = pm_view(result)   # PM-FACING subset ONLY. The raw router envelope (tool_path/why[]/safety_class),
                       # the verb token, the kernel consequence, and the feedback record stay INTERNAL
                       # (under result["_internal"] / result["feedback"]) — never render them to the PM.
```

`confirm=True` remains compatibility behavior for old-copy `cleanup`. It is never accepted for
`finish_current`; finish authorization is a separate exact `Close` consumed by the kernel.

## A0 fix-pass hardening (review-swarm close-out)

A0 is **implemented** but **not yet "proven"** — the single remaining gate is a real non-technical
PM driving the loop end-to-end (an agent-driven rehearsal stands in for it; a human trial does not).
The pre-merge review swarm's fixes are each locked by a biting regression test (fails pre-fix, passes
post-fix), all wired into `make verify`:

| Fix | Guard test |
|-----|------------|
| CR9 literal-confirm from the catalog (not the router) | `test_consumer_loop.TestOperatorLoop.test_lying_router_cannot_suppress_destructive_confirm_cr9` |
| `render_block` never leaks raw kernel guard text | `test_consumer_translators.TestTranslators.test_render_block_never_leaks_real_kernel_guard_text` |
| `_plain_param` never echoes an unknown/banned slot | `test_consumer_translators.TestTranslators.test_plain_param_never_echoes_unknown_or_banned_slot` |
| `affects_shared_ref` live on the product path | `test_consumer_loop.TestOperatorLoop.test_affects_shared_ref_is_live_on_the_product_path` |
| Raw router envelope stays out of PM output (`pm_view`) | `test_consumer_loop.TestOperatorLoop.test_raw_router_envelope_stays_out_of_pm_facing_output` |
| Engine imports neither consumer nor router (forever) | `test_consumer_contamination_structural.TestStructuralContamination.test_engine_imports_neither_consumer_nor_router` |
| Kernel router-usage scan covers the whole kernel surface | `test_kernel_off_matrix.KernelOffMatrixTest.test_kernel_has_no_router_import_or_read` |
| Seam runs non-skipped in CI (drift bites) | `test_consumer_seam.TestSeamRouterPresence.test_router_present_when_required` + the `router-seam` CI job |

The router pin (`consumer/router-pin.json`) tracks router `main` at `f44dbadd` (the merge that froze
`intent-proposal/v1`). `make verify` stays GREEN with the router UNINSTALLED (kernel-first).
