# AWA Root-Bound Worktree Finish — Final-Rollout source-side coverage audit — 2026-07-12

> **Superseded by [`RESULTS-finish-all-transitions-trial-20260712.md`](RESULTS-finish-all-transitions-trial-20260712.md)** (this audit is kept as history). This doc is the **static, source-side** audit: it maps each plan scenario to the existing `module::Class::test` that proves it, but did **not** execute anything end-to-end. The canonical coverage artifact is now the **executed** transition matrix, which drives all 13 plan scenarios end-to-end through the production surfaces (75 headless transitions, 0 gaps). This audit's per-scenario source-test citations have been **carried forward** into that matrix (see its *"Source-test citations carried forward from the superseded audit"* section) so no traceability is lost.

**Feature under audit:** Root-Bound Worktree Finish (kernel-authorized closeout + hook/consumer
convenience surfaces). This is the **pre-ship coverage gate**. Per the plan's hard rule *"Do not
claim any live proof that did not occur"*, coverage is established **headlessly** (source test
suites run under `make verify`) plus an **honest** ledger of what remains **live-Desktop-only** and
cannot be exercised without an operator's real prompt/UI.

**Method:** SOURCE-SIDE audit only. This session did **not** drive live Desktop. For each plan
scenario the matrix cites the exact `module::Class::test` that proves it; where a sub-aspect is
inherently non-headless (Cursor UI rendering, live operator submission, live agent runtime
cessation) it is classified **DEFERRED (live-Desktop-only)** with the honest reason.

**Source pin:** branch `cursor/worktree/awa-20260711033524` @ HEAD `06b237e` (tree clean at audit
start). Router **UNINSTALLED** (kernel-first): `make verify` is green with the router absent; the
router-seam tests skip by design.

> Convention: topic-scoped `RESULTS-<topic>-<date>.md` (cf. `RESULTS-finish-phase2-uat-20260712.md`,
> `RESULTS-e2e-uat-20260707.md`). **No screenshots.** Machine-side evidence is the named headless
> tests, each of which is wired into `make verify` via `engine/tests/run-tests.sh`.

---

## Live-Desktop proof to date (unchanged by this audit)

Live-Desktop proof exists **only** for:

- **`I'm done`** → hook renders the fixed "WARNING: Finish workspace requested" block, five options
  each on its own line, `continue:false` / `decision:block_warning` (operator screenshot + metadata-
  only hook observation), and
- **`Cancel`** (lowercase `cancel`) → dispatch → `state:cancelled`, `mutated_repo:false`.

Both are recorded in **[`RESULTS-finish-phase2-uat-20260712.md`](RESULTS-finish-phase2-uat-20260712.md)**
on runtime `e0f3ae4`. `Close` / `Commit` / `Retain` / `Mixed` were **not** driven live and are **not**
claimed as live-proven here; their behavior is covered headlessly below.

---

## Coverage matrix (one row per plan scenario)

| # | Scenario (from the plan) | Status | Proving headless test(s) / honest reason |
|---|--------------------------|--------|------------------------------------------|
| 1 | Representative finish phrases ("I'm done", "remove worktree", "can we close", "end session", "finish", "finalize") → preview/block only | **PROVEN (headless)** | `test_finish_conversation::RecognizerTest::test_all_approved_phrases_and_paraphrases` (all six + paraphrases + uppercase recognize); `::test_high_signal_match_runs_before_router`; `HookAndDispatcherTest::test_hook_preview_blocks_with_exact_warning_and_bare_choice_handoff`; `::test_hook_script_uses_current_block_schema_and_exact_message`; `WarningSnapshotTest::test_static_warning_byte_snapshot` |
| 2 | Metalinguistic negatives (negated, quoted, hypothetical, documentation, examples, feature-requests, discussion) must NOT trigger | **PROVEN (headless)** | `test_finish_conversation::RecognizerTest::test_negated_quoted_documentation_feature_hypothetical_and_meta_rejected` (all seven negative categories, incl. uppercase) |
| 3 | All choices + casing: `Commit`/`Retain`/`Mixed`/`Cancel` case-insensitive + trim; exact `Close` case-sensitive, one-use, attachment-free; case/trim `Close` → `For safety, reply exactly: Close`, dialogue stays live, no removal | **PROVEN (headless)** | `test_finish_conversation::HookAndDispatcherTest::test_choice_canonicalizer_casing_trimming_and_reasons`; `test_finish_hardening::CurrentEnvelopeAdversarialTest::test_non_destructive_casing_matrix_through_hook_envelope_and_current`; `::test_close_variants_correct_without_activation_or_mutation` (asserts `user_message == CLOSE_CORRECTION`, `hook_activated=False`, executor never called, then exact `Close` removes); `HookAndDispatcherTest::test_close_routes_only_literal_close_to_kernel_executor`; `test_finish_kernel::AuthorizeChallengeTest::test_is_literal_close_exact_only`; `IdenticalRefusalGateTest::test_non_close_variants_all_refuse`, `::test_replay_once_challenge_consumed_on_removal` (one-use); `test_finish_phase2_final_blockers::HookOwnedActionRefreshTest::test_exact_close_trigger_only_publishes_then_second_close_invokes_once` |
| 4 | Attachment rejection (choice with attachments / extra words / booleans / "yes" / approval-click rejected) | **PROVEN (headless)** | `test_finish_hardening::CurrentEnvelopeAdversarialTest::test_attachment_provenance_refuses_every_choice`; `test_finish_conversation::HookAndDispatcherTest::test_choice_canonicalizer_casing_trimming_and_reasons` ("Close please"/"yes" → `choice_not_standalone`; `True`/`False` → `boolean_not_allowed`; attachments → `attachments_present`); `RecognizerTest::test_finish_ignores_trusted_boolean_bypass` (a trusted `confirm=True`/approval never authorizes finish) |
| 5 | Retain: explicit displayed-row selection; protected restore-proven artifact; secrets require `--allow-secrets`; retain-list/restore/delete (delete requires exact artifact id) | **PROVEN (headless)** | `test_finish_conversation::RetainArtifactTest::test_typed_artifact_restore_proof_permissions_lifecycle_and_secret` (row indices; `protected`+`restore_proven`; `create_retain` without `allow_secrets` raises, with `allow_secrets=True` succeeds; `list_retained`/`restore_retain`; `delete_retain(id,"yes")` raises, `delete_retain(id,id)` deletes); `::test_retain_action_requires_fresh_preview_and_separate_close`; `::test_deleted_ignored_and_conflicted_types_are_manifested`; `::test_retain_lock_contention_refuses_and_preserves_source`; `test_finish_final_hardening::DurableRetainPublicationTest::*` |
| 6 | Mixed (row-partitioned commit + retain) | **PROVEN (headless)** | `test_finish_hardening::StateMachineAdversarialTest::test_mixed_requires_exact_disjoint_complete_partition`; `test_finish_phase2_final_blockers::ActionCompletionLatchTest::test_mixed_is_complete_when_both_actions_finish_even_if_refresh_fails`; `IgnoredRowsRetainOnlyTest::test_mixed_retains_ignored_commits_ordinary_and_restore_proves_ignore_intent` |
| 7 | Commit delivery boundaries: ONE GitHub repo, merge-commits enabled, exact-head merge-commit PR incorporated into live default branch w/ complete passing checks; squash/rebase-only unsupported; network only in Commit/Mixed | **PROVEN (headless)** | `test_finish_conversation::CommitDeliveryProofTest::test_strict_delivery_success_and_complete_zero_checks`; `::test_delivery_failure_matrix` (≠1 repo, bad head OID, no merged PR, diverged compare, incomplete checks, PENDING/FAILURE/UNKNOWN all refuse); `test_finish_hardening::DeliveryAndInstallAdversarialTest::test_delivery_pending_failed_and_unstable_empty_refuse` (`merge_commit_enabled=False` → `merge_commit_required_unsupported` = squash/rebase-only unsupported); `CommitDeliveryProofTest::test_network_calls_structurally_commit_only`; `::test_missing_gh_or_network_fails_honestly`; `::test_selected_commit_excludes_unselected_rows_and_requires_fresh_preview` |
| 8 | Dirty confirmed discard | **PROVEN (headless)** | `test_finish_kernel::EngineOffAndLockAbiTest::test_dirty_state_is_discarded_on_close` (dirty tracked + untracked discarded on exact `Close`); `test_finish_operations::GitOperationInventoryTest::test_operation_discard_count_requires_exact_close`; `::test_each_operation_group_retain_restores_and_aborts_in_isolation` |
| 9 | Multi-session blocking (session-lock ABI) | **PROVEN (headless)** | `test_finish_kernel::IdenticalRefusalGateTest::test_cross_session_fresh_blocks` (`finish_session_blocked`, worktree preserved); `SessionGateTest::*` (confirming-pidless waived; other fresh blocks; any live PID blocks; corrupt/branch-mismatch/malformed block); `EngineOffAndLockAbiTest::test_lock_path_is_byte_identical_to_engine_abi` (finish lockfile byte-identical to engine `paths`/`identity` ABI); `test_finish_conversation::HookAndDispatcherTest::test_current_session_cas_uses_shared_common_dir_lock_abi`; `test_retention::TestThrottleAndSharedLock::test_opportunistic_skips_when_lock_is_held_never_races` (maintenance contends on the same lock) |
| 10 | Network-free branch disposition (branch retained/deleted computed with zero network on removal path) | **PROVEN (headless)** | `test_finish_kernel::NoNetworkGateTest::test_removal_and_branch_delete_perform_no_network` (git/gh network-verb sentinel proves zero network); `BranchDispositionTest::test_ephemeral_no_local_only_is_delete_eligible`, `::test_local_only_commits_retained`, `::test_non_ephemeral_branch_retained`, `::test_protected_branch_never_deleted`; `HookIndependentGateTest::test_branch_delete_fallback_still_reports_removed` (compare-and-delete only; branch survives on failure) |
| 11 | Audit-failure honesty (honest confidence; no bare green pill; no invented success) | **PROVEN (headless)** | `test_consumer_translators::TestTranslators::test_outcome_is_honest_about_failure`; `::test_zero_banned_terms_across_all_renderings`; `::test_render_block_never_leaks_real_kernel_guard_text`; `test_finish_publication_projection::DispatcherProjectionTest::test_hostile_removed_refused_uncertain_and_branch_fallback_are_total`; `::test_executor_exception_is_unknown_and_stops_without_exception_text`; `test_finish_phase2_final_blockers::ShellMachineTrustTest::test_malformed_and_contradictory_rc_zero_or_three_never_prove_removal` |
| 12 | Terminal agent-stop after successful `Close` (reports removal, branch result, agent stopping, chat stays open; issues no further task tools) | **PROVEN (headless)** for the structured terminal outcome; the literal "issues no further task tools" is **DEFERRED (live-only)** | Structured outcome: `test_finish_conversation::HookAndDispatcherTest::test_close_routes_only_literal_close_to_kernel_executor` (`workspace_removed`, `agent_stopping=True`, `chat_remains_open=True`, `branch_action`); `test_finish_publication_projection::DispatcherProjectionTest::test_hostile_removed_refused_uncertain_and_branch_fallback_are_total`; `test_finish_conversation::HookAndDispatcherTest::test_next_current_dispatch_repairs_power_loss_after_physical_removal`. **DEFERRED reason:** the agent actually ceasing tool calls is a live-agent runtime behavior directed by `operator-skill.md`/`awa-operator.mdc`, not code — the flags that instruct it are headless-proven, the cessation itself is observable only in a live Desktop session |
| 13 | Phase-3 retention invariants intersecting rollout: only exact `Close` authorizes deletion; destructive uncertainty preserves workspace; zero network on removal; NO retention logic on finish/removal path | **PROVEN (headless)** | `test_retention::TestFinishPathHasNoRetention::test_kernel_finish_has_no_retention`, `::test_consumer_finish_has_no_retention` (structural token scan of `kernel/lib/awa_finish.py` + `consumer/finish_current.py`); `test_finish_final_hardening::HonestRemovalClassificationTest::test_every_partial_content_class_with_same_root_inode_is_uncertain_and_preserved` (destructive uncertainty preserves); `test_finish_kernel::NoNetworkGateTest::test_removal_and_branch_delete_perform_no_network` (zero network); `IdenticalRefusalGateTest::*` + `AuthorizeChallengeTest::test_is_literal_close_exact_only` (only exact `Close` authorizes) |

**Summary: 13/13 scenarios PROVEN headless.** Scenario 12 is fully PROVEN for its structured terminal
outcome; its single sub-aspect "the agent issues no further task tools" is an inherently live-only
agent-runtime behavior (DEFERRED, below). **Zero true source-side coverage gaps were found**, so **no
new tests were added** — the pre-existing suites already prove every scenario with biting tests wired
into `make verify`. (Per the plan discipline: a claimed gap was verified against disk before any test
would be added; none survived scrutiny.)

---

## Biting tests added for genuine gaps

**None.** The audit found no scenario without a genuine, passing, plan-scoped headless proving test.
Adding a redundant test (e.g. re-driving all six phrases through the hook when the deterministic
recognizer gate is already proven for all six and the hook→block composition is proven for a
representative phrase) would be speculative hardening / scope creep and is deliberately avoided.

---

## Honest residuals — what remains live-Desktop-only (cannot be headless-proven)

So the orchestrator does **not** overclaim at ship time, the following are the ONLY aspects that a
headless suite cannot exercise; they require an operator's real prompt/UI/runtime:

- **D1 — Cursor Desktop hard-block rendering.** The hook's exact `user_message` block payload and
  `continue:false` are headless-proven (`test_hook_script_uses_current_block_schema_and_exact_message`),
  but whether the current Cursor build actually renders the modal and enforces "Submission blocked by
  hook" is Cursor-build-dependent. AWA is kernel-first: the load-bearing gate is the kernel's one-use
  exact-`Close` authorization, which holds with the hook/engine/router/MCP all absent. Live-proven for
  `I'm done` only (Phase 2, runtime `e0f3ae4`).
- **D2 — Live operator submission of `Close`/`Commit`/`Retain`/`Mixed`.** Only `I'm done` (display +
  block) and `Cancel` (dispatch → cancelled) were driven on live Desktop (Phase 2). The full CLI/
  dispatch behavior of every choice — including real removal on exact `Close`, real Retain artifact +
  restore, and real Commit delivery — is proven headlessly, but was not (and is not claimed to be)
  exercised by a live operator.
- **D3 — Live agent runtime cessation.** After a terminal `Close` the result carries `agent_stopping`
  / `chat_remains_open` and the skill instructs the agent to issue no further tool calls. The flags are
  headless-proven; the agent actually stopping in a live session is observable only live.
- **D4 — Commit delivery against a real GitHub remote.** `verify_delivery_evidence` (the pure
  evaluator) and its failure matrix are headless-proven, and network is structurally confined to the
  Commit/Mixed action; a real `gh`-backed merged-PR delivery necessarily requires network + a live
  repo and is out of scope for a headless, zero-network gate.

None of D1–D4 is a source-side coverage gap; each is an inherently non-headless surface. The kernel
safety guarantee (exact-`Close`-only, fail-safe preservation, zero-network removal) is fully proven
headlessly and does not depend on any of them.

---

## Gate results

| Gate | Result |
|------|--------|
| Cited finish/retention/consumer suites | all run under `make verify` (unittest discover) — GREEN |
| `make verify` engine suite | **GREEN** — `Ran 763 tests … OK (skipped=15)` |
| `make verify` dashboard emitter suite | **GREEN** — `Ran 6 tests … OK` |
| `awa-contract-freeze.sh` | **OK** (active-root/v1 + 5-state disposition + finish schemas/keysets exact-pinned) |
| `install.sh --check` (static, no HOME writes) | **PASS** (contract JSON, frozen floor, policy, finish operator entrypoint, data-free dashboard seed) |
| `verify-live-verify.sh` | **OK** (this new RESULTS file added no required-file regression) |
| `make verify` overall | **`verify: OK`** (exit 0) |
| Router uninstalled (kernel-first) | confirmed — the 15 skips ARE the router-uninstalled seam tests; `make verify` is green with the router absent |
| `git diff --check` | clean (audit adds only this markdown; no code/test changes) |

**Verdict: Root-Bound Worktree Finish is source-side coverage-complete for Final Rollout — 13/13
scenarios PROVEN headless, no gaps, no new tests required. Remaining live-Desktop-only surfaces
(D1–D4) are honestly enumerated and must not be reported as headless-proven.**
