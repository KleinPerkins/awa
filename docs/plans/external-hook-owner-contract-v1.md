# External Hook-Owner Contract and AWA v1.5.2 Release

- **Version:** v1
- **Status:** DRAFT — 2026-08-15
- **Date:** 2026-08-15
- **Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
- **Plan-type:** agentic-execution
- **Program milestone:** Context Efficiency Program `E-04`
- **Relates to:** accepted Dev `context-efficiency-program-v1.md`; accepted Dev ADR 0004; accepted AWA ADR 0002
- **Implementation baseline:** AWA `origin/main` `536f9cc0ebfd6bc1d7308603bf6e62c80c624d17`
- **Behavior baseline:** published AWA `v1.5.1` at `f4b3c9b85ea1cce83d00ab9eb9f26bf3be900342`
- **Candidate release:** `v1.5.2` (available when this draft was authored; re-check before implementation)
- **Review provenance:** remote-first authority verification; source-level audit of AWA's installer,
  five-row hook reconciler, doctor, generic hook scripts, lifecycle tests, contract freeze, release
  configuration, and Dev's current thin overlay; Appendix-B and E-04 self-review. No implementation,
  hook-file mutation, installed-state mutation, or release action occurred while authoring this plan.

**Goal:** Add one explicit, persistent AWA hook-owner contract so standalone installs continue to
own the Cursor user hook file by default while an external host can own that file without any AWA
install, repair, doctor, or uninstall path writing it. Publish the result as a tested AWA patch
release without changing any `v1.5.1` hook/product behavior.

**Architecture:** Extend AWA's existing canonical behavior contract additively with
`awa-hook-owner/v1`; persist a machine-local `direct|external` selection; make the existing
installer and hook reconciler honor it; advertise support, selection, and contract digest in the
existing release pointer; and keep every runtime hook script byte-identical to `v1.5.1`. No new
runtime, router, registry, daemon, delivery channel, or host literal is introduced.

**Tech stack:** Bash 3.2-compatible shell, Python stdlib, JSON, existing AWA installer/runtime,
`unittest`, contract-freeze UAT, isolated `HOME` lifecycle fixtures, Cursor hook-probe evidence,
Git/GitHub releases, and runnerless PR automation.

> **Authority boundary:** Acceptance of this DRAFT plan authorizes no implementation and no
> release. Implementation requires this owner plan to be accepted plus a separate explicit
> implementation GO. Publishing `v1.5.2` requires the separate Release-GO gate in §8.2 after the
> exact merged candidate passes every required check. Skills `E-05` and Dev `E-06` remain separate
> downstream owner changes.

---

## Global constraints

- Execute implementation only in an AWA Safe Workspace or an isolated standalone clone; never
  mutate the protected primary checkout.
- Preserve `direct` as the effective mode on a truly fresh install and on a valid legacy install
  with no hook-owner fields.
- In `external` mode, every standard AWA lifecycle path (`install`, `--repair`, `--doctor`, and
  `--uninstall`) must perform **zero writes to the selected hook file**: no create, truncate,
  rename, backup, chmod, or removal of that file or its hook backups. Other existing AWA outputs
  such as MCP/rule files remain in scope. Doctor may report the owner but must not validate or
  claim ownership of the external host's hook rows.
- Do not remove or rewrite a live owner during E-04. This release provides the contract only.
  Dev `E-06` owns the later atomic five-role reconciliation.
- Keep the four runtime hook scripts and finish executor byte-identical to `v1.5.1`:
  `worktree-guard.sh`, `worktree-session.sh`, `awa-recovery-maintenance.sh`,
  `before-submit-prompt.sh`, and `consumer/finish_current.py`.
- Preserve AWA's kernel-first invariant. No installer mode, config file, contract descriptor,
  release-pointer field, host process, daemon, MCP server, or router may become a prerequisite for
  protected-primary denial, finish authorization, recovery correctness, or heartbeat safety.
- Preserve `v1.5.1` Git command classification exactly. The same shared command corpus must return
  the same permission result through the direct AWA guard and a generic external-host delegator.
- Global hooks stay fail-open on hook/infrastructure failure. `afterFileEdit` stays
  observation-only and omits `failClosed`.
- Preserve finish-current exact-literal `Close` authorization, recovery-maintenance behavior,
  session heartbeat/current-session binding, Cloud/background fail-open behavior, and all existing
  MCP, mode, dashboard, retention, and operator-entrypoint behavior.
- Add no organization name, Dev path, Skills path, governed-root literal, or host-specific policy
  to AWA source or fixtures. External-host fixture paths use generic placeholders only.
- Do not change `engine/tests/git_guard_command_corpus.py` to make parity pass. It is consumed as
  the frozen `v1.5.1` corpus.
- Do not mutate Skills or Dev from this plan. `E-05` owns the exact release pin; `E-06` owns the
  live five-row file and host rollback.
- Do not tag, publish, or move a release before the Release-GO gate. Never move or delete a
  published tag; a post-publication defect uses the next patch.
- Merging the planning PR leaves this file DRAFT. Only explicit owner acceptance may update the
  mutable index status; once accepted, this v1 file is byte-immutable and any material revision is
  `external-hook-owner-contract-v2.md`.

## 1. Purpose and boundary

AWA `v1.5.1` directly reconciles five logical Cursor user-hook roles. Dev currently redirects that
reconciler to a throwaway file and independently writes only the three host-policy roles. This
means the two installers are individually idempotent but not jointly convergent: a clean Dev path
can omit AWA's recovery and finish rows, while a later direct AWA repair can recreate three policy
duplicates.

E-04 solves only the AWA-owned prerequisite:

1. define and implement an explicit external-host hook-owner mode while preserving standalone
   direct ownership as the default; and
2. publish a tested AWA release preserving all `v1.5.1` hook/product behavior.

E-04 does **not** select Dev as owner, edit the live hook file, advance the Skills binding, or
reconcile the Dev matrix. Those are serial dependents:

```text
E-04 AWA contract + release
  -> E-05 Skills exact release pin
  -> E-06 Dev atomic five-role reconciliation
```

## 2. Bound authority and verified live state

### 2.1 Immutable dependency record

| Authority | Exact ref | Evidence and consequence |
|---|---|---|
| AWA live default | `origin/main` = `536f9cc0ebfd6bc1d7308603bf6e62c80c624d17` | Planning base and pre-implementation rollback ref. GitHub default branch is `main`. |
| AWA behavior baseline | tag/release `v1.5.1` = `f4b3c9b85ea1cce83d00ab9eb9f26bf3be900342` | Published, non-draft, non-prerelease on 2026-08-12. All behavior-preservation assertions compare to this commit. |
| AWA upgrade fixture | version-`1.5.0` commit `331e633027aa489c08f22b96c979fde36079e220` | The in-place upgrade fixture starts from this version-`1.5.0` state; there is no live `v1.5.0` tag, so the commit—not an invented tag—is authoritative. |
| Dev accepted default | `origin/main` = `0818be2f3beb0bfafaa17abd6250e780f87a19a1` | Parent program/ADR acceptance authority. |
| Dev accepted program | blob `f6de269c9c2f88e78e58abd9c247405cb506a123`; raw SHA-256 `327a87b930a9d26a62388005db39c2b097660e0ebfd95aa01d80b17819c17cc4` | Supplies §4.3 invariants, §4.4 transition order, §4.6 client matrix, §5 E-04 DoD, and Appendix B. |
| Dev accepted ADR 0004 | blob `0578f7d7b4ace6c233d5f56c9d20fc43ad979450`; raw SHA-256 `77ddcd3b5e480b77cf283afd8e5593b08022483920ff55451bf5d79fcfc51060` | Keeps product authority in AWA and live host-file ownership in Dev without a second runtime/registry. |

`origin/main` advanced beyond `v1.5.1` only in PR-automation configuration, one policy test, and a
smoke marker. A path-limited diff over `install.sh`, `kernel/`, `contracts/`, `consumer/`, the Git
command corpus, and the relevant hook/finish tests is empty. The parent program's E-04 assumptions
therefore remain valid at the bound AWA tip.

Before implementation, refresh all refs and stop if:

- AWA `origin/main` changes hook ownership, hook script behavior, release versioning, or plan
  governance;
- `v1.5.2` already exists as a tag or GitHub release;
- Dev supersedes the bound program plan or ADR;
- Skills or Dev changes the declared serial owner boundary; or
- current Cursor documentation removes an eligibility assumption used in §6.

An unrelated AWA main advance may be rebased into a fresh Safe Workspace only after recording the
new OID and proving the protected-surface diff remains empty.

### 2.2 Current AWA source facts

| Surface | Current fact at `536f9cc0` | Planned responsibility |
|---|---|---|
| `install.sh` | Every install/repair invokes `kernel/hooks/install-hooks.sh`; doctor always requires its direct five-row check; uninstall removes installed AWA rows. | Resolve/persist mode, pass it to the reconciler, advertise it, and make doctor/uninstall owner-aware. |
| `kernel/hooks/install-hooks.sh` | Installs and checks five rows; recognizes prior installed AWA paths; preserves unrelated rows; backs up before changed writes. | Keep direct behavior, add external zero-write behavior, consume the canonical mode, and retain non-live staging via `AWA_HOOKS_JSON`. |
| `kernel/lib/install-lib.sh` | Owns XDG helpers and installer primitives shared by installed source. | Add one strict, reusable hook-owner resolver; no host literals or network. |
| `contracts/awa-contract.v1.json` | Canonical behavior contract; additive backward-compatible top-level fields are allowed within v1. | Add the sole `awa-hook-owner/v1` block; do not create a parallel registry or second contract authority. |
| `kernel/checks/awa-contract-freeze.sh` | Proves role-resolved kernel behavior, protected-primary denial, Git family classifications, fail-open behavior, and `afterFileEdit`. | Validate the new owner block and exact five-role installer parity while preserving every existing assertion. |
| Generic hook scripts | Implement session heartbeat/context, guard/edit behavior, recovery maintenance, and finish recall. | Remain byte-identical to `v1.5.1`; ownership changes only their hook-file projection. |
| Existing tests | `test_finish_conversation` proves direct install idempotence; `test_finish_hardening` proves malformed/drift behavior; `test_guard_hook_wrappers` consumes the shared Git corpus. | Retain those tests and add isolated owner-mode lifecycle/parity fixtures. |
| `Makefile` | `verify-install` exercises a direct double-install/doctor/uninstall in a throwaway `HOME`. | Extend the lifecycle gate with an external-mode zero-write lane; never touch real `HOME`. |

The exact `v1.5.1` SHA-256 baselines retained for release comparison are:

| Path | SHA-256 |
|---|---|
| `kernel/hooks/worktree-guard.sh` | `6ebbe9ee6c3ec3799f9f0e1be1ae762a44eb2ec5b81ee0fd875a144691d8f474` |
| `kernel/hooks/worktree-session.sh` | `1ea89ba2ad486510be7976d55771e09f7e9201119c4eed38a354ade6eed77938` |
| `kernel/hooks/awa-recovery-maintenance.sh` | `a49911ad61da905a384e5251cc4af1ad6beacc8243aa30b15c63b19f6998ef6c` |
| `kernel/hooks/before-submit-prompt.sh` | `d594519c8962a8cdb8d5adc8262a09a61c00ec074317b3d07be144823220da5a` |
| `consumer/finish_current.py` | `0e8b097a7f118ad71b8889de3cad4d04009fc3db2413bd122f4f4803cea4e26f` |
| `engine/tests/git_guard_command_corpus.py` | `bc648f5ab3885c891b6bc168db478315b1e538a2afb9c0207aa564f9f211c4bf` |

## 3. Hook-owner contract

### 3.1 Selection and persistence

The operator/host input is one environment variable:

```text
AWA_HOOK_OWNER=direct|external
```

The persisted selection is:

```text
$XDG_CONFIG_HOME/awa/hook-owner.json
```

with exact shape:

```json
{
  "schema": "awa-hook-owner-selection/v1",
  "contract": "awa-hook-owner/v1",
  "mode": "direct"
}
```

Resolution is deterministic:

1. an explicitly present `AWA_HOOK_OWNER` wins and must be exactly `direct` or `external`;
2. otherwise, a valid persisted selection wins;
3. otherwise, a valid legacy/current release pointer carrying `hook_owner_mode` wins;
4. otherwise, only when both records are absent or valid legacy records omit owner fields, use
   `direct`.

An unknown explicit value, malformed selection, conflicting schema/contract, or malformed
selection-bearing release pointer is an error before any hook-file or selection mutation. A valid
explicit value is the only repair authority for malformed persisted selection. This prevents
corrupt state from silently converting an external host back into a direct writer.

The selected record is deterministic (no timestamp), private (`0600`), and written atomically
before hook reconciliation. `install.sh` also projects the selected default into
`$XDG_CONFIG_HOME/awa/env` without overriding an already explicit process value. Repeated install,
repair, or GCB invocation without the environment variable therefore preserves `external` instead
of reintroducing direct rows.

This file is local SSP configuration, not a cross-repository registry. It selects only who writes
the one Cursor hook file; it enrolls no capability, repository, route, event, or policy.

### 3.2 Canonical `awa-hook-owner/v1` block

Add one backward-compatible top-level `hook_ownership` block to
`contracts/awa-contract.v1.json`. It is the sole product contract consumed by the installer,
contract-freeze checker, release pointer, and downstream host. Required fields:

- `schema: awa-hook-owner/v1`
- `modes: [direct, external]`
- `default_mode: direct`
- `selection_env: AWA_HOOK_OWNER`
- `selection_schema: awa-hook-owner-selection/v1`
- `external_real_hook_file_writes: false`
- the following ordered, uniquely identified five roles.

| Stable role ID | Event | Direct command role | External command-path class | Required entry fields |
|---|---|---|---|---|
| `worktree.session-context` | `sessionStart` | installed `kernel/hooks/worktree-session.sh` | `host-policy-delegator` | `type: command`; `timeout: 5`; `failClosed: false` |
| `worktree.shell-guard` | `beforeShellExecution` | installed `kernel/hooks/worktree-guard.sh` | `host-policy-delegator` | `type: command`; `timeout: 20`; `failClosed: false` |
| `worktree.file-observer` | `afterFileEdit` | installed `kernel/hooks/worktree-guard.sh` | `host-policy-delegator` | `type: command`; `timeout: 20`; `failClosed` absent |
| `recovery.maintenance` | `sessionStart` | installed `kernel/hooks/awa-recovery-maintenance.sh` | `installed-awa` | `type: command`; `timeout: 5`; `failClosed: false` |
| `finish.prompt-recall` | `beforeSubmitPrompt` | installed `kernel/hooks/before-submit-prompt.sh` | `installed-awa` | `type: command`; `matcher: UserPromptSubmit`; `timeout: 20`; `failClosed: false` |

Contract rules:

- `direct` means AWA owns reconciliation of exactly these five roles in the selected hook file.
- `external` means the host owns the entire real hook file and must project exactly one of each
  logical role while preserving unrelated hooks. AWA owns the product scripts and semantics, not
  the host's path literals or atomic file transaction.
- `host-policy-delegator` may only inject host policy/root data and then execute the matching
  installed AWA role. Its failure fallback remains fail-open. It may not fork guard/session
  semantics.
- `installed-awa` points to the installed AWA runtime even when the external host owns the file.
- Role identity is the stable ID plus event, not command-path spelling. Direct and delegated path
  variants are two projections of the same role and must never coexist in the converged matrix.
- Unrelated third-party rows are outside AWA ownership and are always preserved.
- The contract adds no hook event and changes no output or authorization schema.

`kernel/checks/awa-contract-freeze.sh` must prove that the direct installer's five intended rows
and this ordered contract agree exactly. The existing `contracts/awa-contract.v1.json` required
floor remains unchanged; this is an additive optional-within-v1 block, not `awa-contract.v2`.

### 3.3 Lifecycle behavior

| Lifecycle path | `direct` | `external` |
|---|---|---|
| `./install.sh` | Reconcile five AWA rows exactly as `v1.5.1`. | Install all non-hook SSP surfaces; persist/advertise external owner; do not open or write the selected hook file. |
| `./install.sh --repair` | Re-copy runtime and reconcile five rows exactly as `v1.5.1`. | Re-copy runtime and repair non-hook surfaces; preserve external selection; perform zero selected-hook-file writes. |
| `./install.sh --doctor` | Report `hook owner: direct`; require one exact direct entry for each role. | Report `hook owner: external`; validate selection, installed contract, release-pointer agreement, and script presence; explicitly report that the host hook file is not inspected by AWA. |
| `./install.sh --uninstall` | Remove only proven direct AWA entries, preserving unrelated hooks. | Do not read, back up, rewrite, or remove the external host's hook file; warn that the host must reconcile its rows before/with runtime removal. |
| `./install.sh --check` | Validate source contract/reconciler parity without writing `HOME`. | Same static result; selection is irrelevant to source readiness. |
| `install-hooks.sh` / `--check` | Existing direct reconciliation/exact check. | No-op/report-owner path that does not touch `AWA_HOOKS_JSON`; contract validation remains available through the top-level doctor/check. |

The release pointer remains `awa-release-pointer/v1` and gains additive identity fields:

```text
hook_owner_contract = awa-hook-owner/v1
hook_owner_mode = direct|external
hook_owner_contract_sha256 = SHA-256(installed contracts/awa-contract.v1.json)
```

Mode transitions change release-pointer identity and therefore refresh `installed_at`; an
idempotent same-release/same-mode repair preserves it. Doctor fails if selection, pointer mode,
contract schema, contract digest, runtime version/commit, or installed contract bytes disagree.
This is the machine-readable advertisement Dev must verify before E-06.

### 3.4 Non-live staging and rollback interface

Preserve the existing `AWA_HOOKS_JSON` destination override. An explicit one-shot direct invocation
against a **non-live staging file** must remain possible even when persisted mode is external:

```bash
AWA_HOOK_OWNER=direct \
AWA_HOOKS_JSON="$staging_hooks_json" \
"$AWA_HOME/kernel/hooks/install-hooks.sh"
```

This low-level invocation does not persist owner selection. It lets an external host construct and
validate the complete direct AWA five-role projection without touching the live file. Downstream
rollback may atomically replace the host-owned live matrix only after that staged projection passes
`--check`. AWA does not implement the host transaction in E-04.

Rollback ordering is immutable:

1. stage and verify a complete direct AWA five-role owner;
2. make that complete owner live atomically; and only then
3. retire external host ownership.

Never remove the active owner first. A direct top-level repair against the live host-owned file is
not the rollback transaction because it could create a duplicate interval; E-06 must use its
accepted host plan and the staging interface above.

## 4. Work items

### Task 1: Freeze the owner contract and drive it from failing tests

**Files:**

- Modify: `contracts/awa-contract.v1.json`
- Modify: `kernel/checks/awa-contract-freeze.sh`
- Create: `engine/tests/test_hook_owner_modes.py`
- Create: `engine/tests/fixtures/hook-owner/empty.json`
- Create: `engine/tests/fixtures/hook-owner/v1.5.0-direct.json`
- Create: `engine/tests/fixtures/hook-owner/external-3-plus-3-plus-2.json`
- Create: `engine/tests/fixtures/hook-owner/foreign-sentinel.json`
- Create: `engine/tests/fixtures/hook-owner/malformed.json`
- Consume unchanged: `engine/tests/git_guard_command_corpus.py`

**Interfaces:**

- Consumes: §3 contract, `v1.5.1` hook fields and SHA-256 baselines, version-`1.5.0` commit
  `331e6330`, existing `AWA_HOOKS_JSON`, and AWA's XDG path helpers.
- Produces: additive `awa-hook-owner/v1`, fixture token expansion for `{{RUNTIME}}` and
  `{{HOST_ROOT}}`, and a focused owner-mode test module.

- [ ] **Step 1 — Add the contract block and fixture snapshots**

  Keep fixtures generic and data-free. `external-3-plus-3-plus-2.json` models three direct policy
  rows, three external-delegator variants, and two AWA product rows plus one unrelated sentinel; it
  contains no Dev path or organization literal. E-04 uses it to prove external zero-write behavior,
  not to repair the host matrix.

- [ ] **Step 2 — Add exact failing tests**

  `engine/tests/test_hook_owner_modes.py` must define at least:

  - `TestHookOwnerContract.test_contract_declares_exact_five_roles_and_direct_default`
  - `TestHookOwnerContract.test_direct_installer_rows_equal_contract`
  - `TestHookOwnerInstall.test_clean_direct_install_creates_exact_five_roles`
  - `TestHookOwnerInstall.test_clean_external_install_creates_no_hook_file`
  - `TestHookOwnerInstall.test_external_switch_and_repair_leave_existing_hook_inode_bytes_and_backups_unchanged`
  - `TestHookOwnerInstall.test_unset_repair_preserves_persisted_external_mode`
  - `TestHookOwnerInstall.test_version_150_upgrade_defaults_to_direct`
  - `TestHookOwnerInstall.test_invalid_or_malformed_selection_refuses_before_hook_mutation`
  - `TestHookOwnerInstall.test_direct_malformed_hook_file_refuses_and_external_does_not_read_it`
  - `TestHookOwnerInstall.test_doctor_reports_and_validates_selected_owner`
  - `TestHookOwnerInstall.test_external_uninstall_never_writes_host_hook_file`
  - `TestHookOwnerInstall.test_direct_staging_override_builds_complete_rollback_candidate`
  - `TestHookOwnerParity.test_shared_git_corpus_matches_direct_and_generic_delegated_paths`
  - `TestHookOwnerParity.test_hook_fail_open_and_after_file_edit_policy_match_both_paths`
  - `TestHookOwnerParity.test_v151_behavior_files_are_byte_identical`

- [ ] **Step 3 — Run the focused tests before implementation and retain RED evidence**

  Run:

  ```bash
  python3 -m unittest engine.tests.test_hook_owner_modes
  AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
  ```

  Expected before implementation: the new tests fail because mode resolution, persistence,
  release-pointer advertisement, external zero-write behavior, owner-aware doctor/uninstall, and
  contract parity do not exist. Existing `v1.5.1` behavior tests must remain green; a failure in an
  existing test is a baseline defect and stops implementation.

- [ ] **Step 4 — Commit the RED test/contract slice only after review**

  Suggested message: `test(hooks): define external owner contract`

**Definition of done:** The contract and every required lifecycle edge are executable
specifications; the new assertions fail for the expected missing behavior, not for fixture,
platform, path, or test-harness errors.

### Task 2: Implement strict selection and zero-write external mode

**Files:**

- Modify: `kernel/lib/install-lib.sh`
- Modify: `kernel/hooks/install-hooks.sh`
- Modify: `install.sh`
- Modify: `engine/tests/test_hook_owner_modes.py`
- Test: `engine/tests/test_finish_conversation.py`
- Test: `engine/tests/test_finish_hardening.py`
- Test: `engine/tests/test_install_lib.py`

**Interfaces:**

- Consumes: `AWA_HOOK_OWNER`, `$XDG_CONFIG_HOME/awa/hook-owner.json`, legacy/current
  `release-pointer.json`, `AWA_HOOKS_JSON`, `awa_write_backup`, and the canonical contract block.
- Produces: strict `direct|external` resolution, private deterministic selection persistence,
  owner-aware lifecycle behavior, additive release-pointer fields, and plain doctor output.

- [ ] **Step 1 — Add one shared resolver**

  Add `awa_hook_owner_resolve` to `kernel/lib/install-lib.sh`. It accepts the selection path and
  release-pointer path, implements §3.1 precedence, emits only `direct` or `external` on success,
  and returns exit `2` with a fixed value-free diagnostic on invalid state. It performs no writes,
  does not source arbitrary files, uses only stdlib tools already required by AWA, and remains
  Bash 3.2 compatible.

- [ ] **Step 2 — Validate and persist before hook reconciliation**

  In `install.sh`, introduce:

  ```text
  HOOK_OWNER_FILE=$XDG_CONFIG_HOME/awa/hook-owner.json
  selected_hook_owner=awa_hook_owner_resolve(...)
  ```

  Resolve before runtime/config/hook mutation; atomically write the exact selection object before
  invoking the hook reconciler; project the selected default into the generated env; and pass the
  explicit selected value to every hook lifecycle call. A valid explicit value repairs malformed
  selection. No other path silently repairs or defaults ambiguous state.

- [ ] **Step 3 — Make the hook reconciler mode-aware**

  `kernel/hooks/install-hooks.sh` keeps direct logic byte-for-behavior compatible. In external
  install/check mode it validates the selected mode, emits a fixed owner report, and exits before
  `mkdir`, `chmod`, `mktemp`, hook-file existence/JSON reads, backup creation, or writes. Preserve
  explicit `AWA_HOOK_OWNER=direct` plus `AWA_HOOKS_JSON=<staging>` for §3.4.

- [ ] **Step 4 — Make doctor and uninstall owner-aware**

  Direct doctor retains the exact five-row assertion. External doctor validates selection,
  contract schema/digest, pointer/runtime/commit agreement, and script presence, then reports:

  ```text
  PASS  hook owner selected: external (host-managed; hook file not inspected by AWA)
  ```

  External uninstall skips `_remove_hooks` before removing AWA-owned non-hook state and prints a
  fixed warning that host reconciliation is required. It must not stat or open the selected hook
  path. Direct uninstall behavior remains unchanged.

- [ ] **Step 5 — Advertise contract support in the release pointer**

  Compute the installed contract SHA-256 without network, add the three §3.3 fields to release
  identity, and require doctor equality. A mode change refreshes pointer identity; same-mode
  repairs preserve `installed_at`.

- [ ] **Step 6 — Run focused tests and retain GREEN evidence**

  ```bash
  python3 -m unittest \
    engine.tests.test_hook_owner_modes \
    engine.tests.test_finish_conversation.HookAndDispatcherTest.test_hook_install_check_and_idempotency \
    engine.tests.test_finish_hardening.DeliveryAndInstallAdversarialTest \
    engine.tests.test_install_lib
  ```

  Expected: all pass; no real `HOME` path is touched.

- [ ] **Step 7 — Commit the implementation slice**

  Suggested message: `feat(hooks): add external owner mode`

**Definition of done:** Fresh/legacy direct installs behave as before; persisted external mode
survives ordinary repair and makes every standard lifecycle path zero-write with respect to the
hook file; doctor and pointer report one unambiguous owner.

### Task 3: Prove lifecycle, parity, failure, and rollback

**Files:**

- Modify: `Makefile`
- Modify: `live-verify/trial-runner/_trial_phase2.py`
- Modify: `engine/tests/test_hook_owner_modes.py`
- Test unchanged: `engine/tests/test_guard_hook_wrappers.py`
- Test unchanged: `engine/tests/git_guard_command_corpus.py`
- Test unchanged: `engine/tests/test_active_root.py`
- Test unchanged: `engine/tests/test_recovery.py`
- Test unchanged: all finish/consumer/kernel-off suites

**Interfaces:**

- Consumes: throwaway `HOME`/XDG roots, generic delegator fixtures, direct/external selections,
  version-`1.5.0` state, `v1.5.1` shared corpus and script digests.
- Produces: isolated lifecycle receipts for clean install, upgrade, repair, idempotence, failure,
  no-write external state, staged rollback, and behavior parity.

- [ ] **Step 1 — Extend `make verify-install` with two isolated lanes**

  Keep the current direct double-install/doctor/MCP smoke/uninstall lane. Add a second independent
  throwaway `HOME` that:

  1. seeds a foreign sentinel hook file;
  2. installs with `AWA_HOOK_OWNER=external`;
  3. repeats install and `--repair` without the environment variable;
  4. runs doctor;
  5. runs uninstall; and
  6. proves the sentinel path's inode, mode, bytes, mtime, and hook-backup set never changed.

  Both lanes must clean their temp roots on success and failure.

- [ ] **Step 2 — Extend the deterministic trial row**

  Update `P2-HOOK-INSTALL` in `live-verify/trial-runner/_trial_phase2.py` so its oracle covers
  direct idempotence plus external zero-write/doctor output. Keep the live trial headless and
  disposable; it must never swap the operator's `~/.cursor/hooks.json`.

- [ ] **Step 3 — Prove the complete fixture matrix**

  | Case | Starting state | Required result |
  |---|---|---|
  | Clean direct | No selection, pointer, or hook file | Defaults direct; creates exactly five roles; second install byte-identical. |
  | Clean external | Explicit external; no hook file | Persists external; hook file and parent are not created by the hook step. |
  | In-place `1.5.0` upgrade | Fixture based on `331e6330`; no owner fields | Defaults direct; preserves all five-row behavior and unrelated hooks. |
  | External handoff | Generic `3+3+2` plus unrelated sentinel | Selection/pointer change; hook file is byte/stat/backup identical. No E-04 repair claim. |
  | Repeated direct/GCB repair | Persisted external; invocation omits owner env | Remains external; no direct rows reappear. |
  | Direct idempotence | Exact direct five rows | No changed bytes or backup. |
  | External idempotence | Arbitrary/malformed host file | Does not read or write host file; repeated lifecycle output is stable. |
  | Failure | Invalid env, malformed selection, pointer mismatch, unwritable config | Refuses before hook mutation; prior owner remains live. |
  | Rollback staging | Persisted external + non-live staging copy | Explicit direct override generates/checks complete five roles in staging; live host file unchanged. |
  | Uninstall | Direct then external selections | Direct removes only owned rows; external writes no host file and leaves a fixed host-reconcile warning. |

- [ ] **Step 4 — Prove direct/delegated `v1.5.1` behavior parity**

  For every command in `GIT_READONLY_FAMILY_COMMANDS` and `GIT_MUTATING_FAMILY_COMMANDS`, execute
  the installed `v1.5.2` guard directly and through a generic fail-open policy-injecting delegator
  with the same payload/policy. Require byte-equivalent normalized permission outcomes:

  - every `v1.5.1` read-only case allows;
  - every protected-primary mutation denies with the frozen deny shape;
  - guard infrastructure failure allows through both external fallback and Cursor `failClosed:
    false`;
  - Cloud/background signals allow;
  - `afterFileEdit` allows and has no `failClosed`; and
  - no command is added, removed, or reclassified.

- [ ] **Step 5 — Prove protected product behavior**

  Run focused suites:

  ```bash
  python3 -m unittest \
    engine.tests.test_hook_owner_modes \
    engine.tests.test_guard_hook_wrappers \
    engine.tests.test_active_root \
    engine.tests.test_recovery \
    engine.tests.test_finish_conversation \
    engine.tests.test_finish_hardening \
    engine.tests.test_kernel_off_matrix
  ```

  Expected: `OK`. Finish exact-literal, recovery maintenance, heartbeat, kernel-off, and
  fail-open assertions remain unchanged.

- [ ] **Step 6 — Commit the verification slice**

  Suggested message: `test(hooks): prove owner lifecycle parity`

**Definition of done:** Every E-04-owned fixture passes with deterministic evidence; the generic
external contract is proven without claiming the downstream Dev file has already converged.

### Task 4: Document the owner boundary and prepare AWA 1.5.2

**Files:**

- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `engine/__init__.py`
- Modify: `pyproject.toml`
- Do not modify: accepted `docs/adr/0002-awa-dev-overlay.md`
- Do not modify: this accepted plan after owner acceptance

**Interfaces:**

- Consumes: completed Tasks 1–3 and still-available `v1.5.2`.
- Produces: synchronized product version `1.5.2`, operator documentation for direct/external
  ownership, and no duplicate host-specific process.

- [ ] **Step 1 — Re-check release preconditions**

  ```bash
  git fetch origin --tags
  test "$(git rev-parse origin/main)" = "<fresh-reviewed-main-oid>"
  test "$(python3 -c 'import engine; print(engine.__version__)')" = "1.5.1"
  test -z "$(git tag -l v1.5.2)"
  test -z "$(git ls-remote origin refs/tags/v1.5.2)"
  ! gh release view v1.5.2 -R KleinPerkins/awa >/dev/null 2>&1
  ```

  Any failure stops and requires a plan/ref/version review; never overwrite a newer release.

- [ ] **Step 2 — Update only documentation made stale**

  `README.md` documents `AWA_HOOK_OWNER`, direct default, persisted selection, external zero-write
  behavior, doctor output, and host-owned uninstall responsibility. `ARCHITECTURE.md` changes its
  unconditional “merges Cursor hooks” statement to the direct/external owner pattern while
  retaining AWA as product/script authority and hosts as policy/path-literal authority. Add no Dev
  implementation instructions or duplicate program prose.

- [ ] **Step 3 — Bump both version declarations**

  Set `engine/__init__.py` and `pyproject.toml` to `1.5.2`, then require:

  ```bash
  test "$(make -s version)" = "1.5.2"
  ```

- [ ] **Step 4 — Prove protected files remain byte-identical**

  ```bash
  git diff --exit-code v1.5.1 -- \
    kernel/hooks/worktree-guard.sh \
    kernel/hooks/worktree-session.sh \
    kernel/hooks/awa-recovery-maintenance.sh \
    kernel/hooks/before-submit-prompt.sh \
    consumer/finish_current.py \
    engine/tests/git_guard_command_corpus.py
  ```

  Expected: no diff. Any required semantic change to those files is outside E-04 and requires plan
  revision before implementation continues.

- [ ] **Step 5 — Run focused and full verification**

  ```bash
  python3 -m unittest engine.tests.test_hook_owner_modes
  python3 -m unittest engine.tests.test_guard_hook_wrappers
  python3 -m unittest engine.tests.test_finish_conversation engine.tests.test_finish_hardening
  bash engine/tests/run-tests.sh
  AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
  ./install.sh --check
  make verify
  make verify-install
  git diff --check
  git diff --check origin/main...HEAD
  ```

  From the Dev governance root, run the read-only plan/docs check against this AWA checkout (or the
  repository's then-current documented equivalent):

  ```bash
  ~/dev/_ops/bin/doc-warden.sh check "$(pwd)"
  ```

  Record any environment-only limitation separately; do not call the implementation green if a
  repository-owned failure remains.

- [ ] **Step 6 — Review the complete E-04 implementation**

  Review the whole branch, not only the last commit, for functional defects, security/authority
  drift, unsafe hook-file access, fixture false positives, and release-go completeness. Fix every
  P0/P1, rerun focused/full verification, and repeat until no valid P0/P1 remains.

- [ ] **Step 7 — Commit the release-preparation slice**

  Suggested message: `release: prepare AWA v1.5.2`

**Definition of done:** Version sources agree; docs describe one product authority and two explicit
file-owner modes; all source/install gates pass; protected `v1.5.1` behavior files are byte-identical.

### Task 5: Merge, obtain Release GO, publish, and hand off

**Files:**

- No additional AWA source files unless review finds a defect.
- No Skills or Dev file is changed by this task.

**Interfaces:**

- Consumes: exact reviewed implementation head, governed AWA PR, verified merge commit, and §8.2
  Release GO.
- Produces: immutable `v1.5.2` tag/release at the verified merge commit plus an evidence bundle for
  E-05; no pin and no live host change.

- [ ] **Step 1 — Open the ordinary implementation PR**

  Push the exact branch head, open a non-draft PR, and include refs, RED/GREEN results, full
  verification, fixture matrix, client evidence, rollback staging proof, and the statement that
  auto-merge was not manually armed.

- [ ] **Step 2 — Let governed automation merge**

  Wait for exact-head `pr-automation / verify` and reviewer-App governance. Never call
  `gh pr merge --auto`, enable/disable native auto-merge, bypass the reviewer App, or force-push.
  Re-run the full local gate if the reviewed head changes.

- [ ] **Step 3 — Verify the exact merged candidate**

  Fetch `main`, read the PR's `mergeCommit.oid`, prove it is an ancestor of live `origin/main`,
  prove both version declarations are `1.5.2`, and rerun release-critical focused tests against
  that exact tree. Record the merge OID and contract SHA-256.

- [ ] **Step 4 — Stop at the explicit Release-GO gate**

  Present the evidence in §8.2. Without exact owner GO, leave source merged but untagged and report
  E-04 release pending. Do not advance E-05.

- [ ] **Step 5 — On GO, tag and publish the exact merge**

  ```bash
  git tag v1.5.2 "$merge_sha"
  git push origin v1.5.2
  gh release create v1.5.2 \
    --verify-tag \
    --title "AWA v1.5.2" \
    --generate-notes
  ```

  Verify the remote tag resolves to the merge OID and the release is non-draft/non-prerelease.
  Release notes must say direct remains default, external writes no hook file, and no hook/product
  semantic behavior changed from `v1.5.1`.

- [ ] **Step 6 — Produce the E-05 handoff only**

  Handoff fields:

  - tag and exact commit;
  - GitHub release URL;
  - source/installed contract SHA-256;
  - `awa-hook-owner/v1` schema;
  - `hook_owner_mode` default `direct`;
  - focused/full verification receipts;
  - direct fresh-Desktop canary;
  - external synthetic zero-write/parity receipts;
  - rollback ref `f4b3c9b8...` and current implementation merge ref.

  E-05 independently plans and changes the Skills GCB. E-06 independently plans and changes Dev.

**Definition of done:** The tested `v1.5.2` release exists at one verified merge commit and the
downstream handoff is complete; no Skills pin, Dev hook row, live hook file, or installed machine
state was changed by AWA E-04.

## 5. Acceptance-test ledger

| Requirement | Deterministic proof | Expected result |
|---|---|---|
| Direct remains default | Clean fixture with no env/selection/pointer; legacy `1.5.0` fixture | Exact five direct rows; doctor direct; second install no-op |
| External writes no real hook file | Sentinel inode/bytes/mode/mtime/hook-backups before and after install, repair, doctor, uninstall | Every value unchanged |
| Owner persists | Explicit external once, then install/repair without env | Selection and pointer remain external; no direct rows appear |
| Doctor covers both | Direct exact rows; external arbitrary/malformed host file | Direct validates five; external validates contract/selection and does not inspect host file |
| Failure preserves active owner | Invalid env, malformed selection, pointer/digest mismatch, unwritable config | Non-zero before hook mutation; prior hook bytes unchanged |
| Rollback is stageable | External selection plus direct explicit non-live destination | Staging file has five valid roles; live file unchanged |
| `v1.5.1` behavior preserved | Script SHA table, existing full tests, contract freeze | Protected files byte-identical and all suites pass |
| Git classifier parity | Shared corpus direct vs generic delegated execution | Same allow/deny shapes for every case |
| Fail-open preserved | Missing delegate target, hook internal failure, Cloud/background, Cursor policy fields | Valid allow/fail-open; no global brick |
| `afterFileEdit` preserved | Contract row + direct/delegated runtime payload | Observation-only allow; `failClosed` absent |
| Finish preserved | Existing finish suites and fresh direct Desktop recall canary | Exact-literal safety and one-use generation unchanged |
| Recovery preserved | Existing recovery/retention suites and session-start synthetic run | Maintenance remains fail-open, detached, and engine-owned |
| Heartbeat preserved | Existing active-root/current-session tests via direct/delegated session role | Same binding and safety decisions |
| Release identity | Pointer, tag, release, version declarations, contract digest | All resolve to exact merged `v1.5.2` commit |

No test may pass by weakening the shared corpus, skipping a lifecycle path, redirecting a supposed
“real-file” assertion to a different file, or checking only final bytes while allowing an
intermediate write/backup.

## 6. Fresh-client evidence matrix

E-04 records only affected hook projections. “Fresh” means the candidate release is installed in a
new throwaway/eligible environment and Cursor starts a new process/window that cannot reuse prior
hook loading.

| Cohort / projection | E-04 eligibility | Required E-04 evidence | Owner of later evidence |
|---|---|---|---|
| Cursor Desktop, fresh standalone root, user-home AWA hooks | Eligible | Clean direct `v1.5.2` install; new window; one session-context result, read-only allow, synthetic protected-primary deny without executing mutation, `afterFileEdit` observation, recovery hook smoke, and finish-recall preview/cancel. | AWA E-04 |
| Cursor Desktop, fresh Dev root, user-home external-host hooks | Contract-only before E-06 | Generic delegated parity plus zero-write lifecycle in isolated `HOME`; explicitly no claim that live Dev matrix converged. | Dev E-06 after Skills E-05 |
| Cursor Desktop, rollback canary | Synthetic only in E-04 | Complete direct five-role staging file passes check while host file remains untouched. | Dev E-06 performs actual atomic rollback drill |
| Cursor Cloud, **user-home** AWA hooks | Ineligible | Record that Cloud lacks the operator's `~/.cursor/hooks.json`; make no user-home hook claim. | None unless product eligibility changes |
| Cursor Cloud, **repository-scoped** hooks | Event eligible, delivery out of scope | Record current product fact: repository hooks can support `beforeSubmitPrompt`; do not call the event Desktop-only. AWA E-04 installs no repository hook and makes no Cloud user-home claim. Existing repository hook-probe evidence may be cited only as unchanged baseline. | Any future repository-hook owner |
| Cursor Cloud `sessionStart` | Ineligible | Record current unsupported event; no canary. | None unless product eligibility changes |
| Cursor background / multi-root | Synthetic contract regression | Existing unsupported-context paths remain fail-open and mint no finish challenge; no blanket hook/context-size claim. | AWA E-04; Dev E-06 for actual host matrix |
| Claude fresh process | No Cursor-hook projection | Not affected; verify no AWA capability/MCP regression only through existing full install checks. | E-05 if its capability pin affects discovery |
| Codex fresh process | No Cursor-hook projection | Not affected; same boundary as Claude. | E-05 if its capability pin affects discovery |

If current official Cursor documentation changes repository/user-home or event eligibility before
release, stop and revise this matrix rather than carrying stale evidence.

## 7. Acceptance criteria

E-04 is complete only when all are true:

1. This owner plan is accepted before implementation and remains byte-immutable afterward.
2. AWA source and release bind the exact refs in §2 or an explicitly reviewed non-invalidating
   refresh.
3. `awa-hook-owner/v1` is canonical in `contracts/awa-contract.v1.json`, validated by contract
   freeze, and advertised by the release pointer with exact digest.
4. A truly fresh/legacy install defaults to direct and direct lifecycle behavior is compatible
   with `v1.5.1`.
5. External selection persists and every standard lifecycle path performs zero selected-hook-file
   writes.
6. Doctor reports one selected owner; direct validates five rows; external validates only
   AWA-owned selection/contract/runtime evidence and does not claim the host file.
7. Clean install, version-`1.5.0` upgrade, generic `3+3+2` no-write, repeated repair, idempotence,
   malformed/failure, uninstall, and staged rollback fixtures pass.
8. The complete shared Git corpus produces identical direct/delegated classifications and
   fail-open behavior.
9. Protected-primary denial, `afterFileEdit`, finish exact-literal safety, recovery maintenance,
   session heartbeat, kernel-off behavior, and all `v1.5.1` hook scripts remain unchanged.
10. Focused tests, full engine tests, contract freeze, static check, `make verify`,
    `make verify-install`, diff checks, and repository docs/governance checks pass.
11. Direct fresh-Desktop evidence is current; external/Cloud/background evidence is classified
    honestly as eligible, ineligible, or contract-only.
12. No new runtime, router, registry, daemon dependency, delivery channel, host literal, or
    downstream mutation exists.
13. The implementation PR merges through AWA governance; manual auto-merge is not armed.
14. Explicit Release GO is recorded before tag/release creation.
15. `v1.5.2` tag and release resolve to the verified merge commit, and the E-05 handoff records the
    exact release/contract digests.
16. Final source workspace is clean and no P0/P1, stale ref, unresolved fixture, or unproved
    rollback interface remains.

## 8. Owner GO / NO-GO gates

### 8.1 Plan and implementation gates

- **Plan acceptance GO:** owner explicitly accepts this DRAFT through AWA's plan governance. A
  planning-PR merge alone does not silently authorize code.
- **Implementation GO:** after acceptance, owner explicitly instructs execution of E-04 Tasks 1–4.
- **NO-GO:** leave AWA `v1.5.1`, Skills, Dev, installed hooks, and machine state unchanged. The
  accepted plan remains a frozen record.

### 8.2 RELEASE-GO — explicit, mandatory, and separate

`v1.5.2` may be tagged/published only when the owner is shown:

- accepted plan identity;
- exact implementation PR head and merge OID;
- fresh live `origin/main` ancestry;
- `1.5.2` version equality;
- contract schema and SHA-256;
- RED then GREEN focused evidence;
- full verification and clean-state receipts;
- direct fresh-Desktop result;
- external zero-write/parity/rollback-staging results;
- no P0/P1 review finding;
- release notes;
- rollback ref `v1.5.1` / `f4b3c9b8...`; and
- explicit statement that E-05/E-06 have not run.

Only an explicit owner “GO to publish AWA v1.5.2 at `<merge_sha>`” satisfies this gate. Plan
acceptance, implementation instruction, PR approval, CI success, tag availability, or an approval
button does not.

## 9. Rollback and failure handling

### Before implementation merge

- Correct with ordinary commits in the Safe Workspace; do not amend pushed commits.
- If a ref or authority assumption changes materially, stop and supersede/revise the DRAFT rather
  than adding compatibility behavior.

### After implementation merge but before release

- Use a normal revert PR to restore `origin/main` to pre-implementation behavior.
- No downstream pin exists, so Skills/Dev remain on `v1.5.1`.

### After `v1.5.2` publication but before E-05

- Never move/delete `v1.5.2`.
- Publish a corrective `v1.5.3` only through a reviewed plan-compatible fix and new Release GO.
- E-05 must pin the corrective release, not the known-bad tag.

### After E-05 but before/during E-06

- Skills owns pin rollback through its governed plan/PR.
- Dev owns hook-file rollback. It must make a verified complete direct AWA five-role matrix live
  before retiring its external owner, using §3.4 staging and one atomic host transaction.
- AWA external lifecycle operations remain zero-write throughout; they do not “help” by deleting
  or rewriting host rows.

Any capability, hook, finish, recovery, heartbeat, classification, or fail-open regression stops
rollout and returns to the last complete owner. There is never an ownerless interval.

## 10. Non-goals

- Implementing E-05's Skills pin or E-06's Dev five-row reconciler.
- Editing `~/.cursor/hooks.json`, installed AWA, machine-local selections, rules, MCP config, or
  client state while this plan is authored/reviewed.
- Changing hook script semantics, Git classifications, finish-current UX/authorization, recovery
  policy, heartbeat semantics, host modes, governed-root policy, MCP schemas, or dashboards.
- Adding a runtime service, context registry, hook registry, router, feature flag service, or
  second release channel.
- Making AWA inspect/approve the external host's final path literals.
- Claiming user-home AWA hooks run in Cursor Cloud.
- Claiming `beforeSubmitPrompt` is Desktop-only; repository-scoped Cloud hooks support it under the
  current product contract.
- Repairing the current live `3+3+2` matrix in AWA.
- Cutting any release from the planning PR.

## 11. Appendix-B and protected-invariant mapping

### 11.1 Parent Appendix B

| Parent requirement | This plan |
|---|---|
| Owner classification | Header uses AWA `docs/plans/` and `Plan-type: agentic-execution`; index row remains DRAFT. |
| Bind current owner/dependency refs | §2 records AWA main, `v1.5.1`, version-`1.5.0` commit, Dev main, plan blob/digest, and ADR blob/digest. |
| Exact files/interfaces/tests/commands | §§3–5 enumerate all production/test/docs/version files, schemas, environment/config/pointer fields, methods, and commands. |
| Expected FAIL/PASS | Task 1 records RED expectations; Tasks 2–4 record GREEN focused/full gates. |
| Clean install/upgrade/repair/idempotence/failure/client evidence | Task 3, §5, and §6 provide named fixtures and evidence ownership. |
| One writer/governed PR | Global constraints and Tasks 4–5 require isolation and AWA's ordinary reviewer-App path. |
| Authorization/exact-digest gates | §§8.1–8.2 separate plan, implementation, and exact-merge release GO. |
| Stop on invalidating ref | §2.1 lists explicit stop conditions. |
| Update only stale docs | Task 4 limits docs to `README.md` and `ARCHITECTURE.md`; accepted ADR/plan stay immutable. |

### 11.2 E-04 DoD and transition steps

| Requirement | Planned proof |
|---|---|
| Explicit external hook-owner contract | Canonical `awa-hook-owner/v1`, persisted selection, pointer advertisement, doctor output |
| Direct remains default | Clean and legacy `1.5.0` fixtures |
| External writes no real hook file | Whole-lifecycle inode/bytes/mode/mtime/hook-backup receipts |
| Doctor/fixtures cover both | Owner-aware doctor plus Task 3 matrix |
| Preserve `v1.5.1` behavior | Exact script digests, unchanged corpus, focused/full suites, direct/delegated parity |
| Transition step 1 | Tasks 1–4 |
| Transition step 2 | Task 5 after Release GO |
| E-05 dependent | Exact tag/commit/contract handoff only |
| E-06 dependent | External contract plus staged direct rollback interface only |

### 11.3 Protected invariants

| Invariant | Guardrail |
|---|---|
| Confirmed protected-primary mutations deny | Existing guard/contract suites plus direct/delegated shared corpus; guard bytes frozen |
| `v1.5.1` read-only Git classifications preserved | Corpus file and runtime guard bytes frozen; every case compared |
| Global hook failures fail open | Contract fields, missing-delegator fixture, existing wrapper/kernel-off tests |
| `afterFileEdit` observation-only | Stable role requires omitted `failClosed`; runtime must allow |
| Finish exact-literal safety | Finish script/executor bytes frozen; full finish suites |
| Recovery maintenance preserved | Maintenance script bytes frozen; recovery suites and role retained |
| Session heartbeat preserved | Session script bytes frozen; active-root/current-session tests |
| No skill/MCP/sub-agent/route loss | Installer external lane still runs existing MCP/operator install checks; no capability surface changes |
| No new router/runtime/registry | Selection is one local SSP config; canonical contract and existing installer only |
| Owner boundaries preserved | AWA owns product contract/scripts/release; Skills pins; Dev owns live external file |

## 12. Evidence and clean-state receipts

Implementation and release records must retain:

- refreshed exact refs and tag/release availability;
- source and installed contract SHA-256;
- selection/pointer/runtime agreement for direct and external isolated homes;
- RED then GREEN focused outputs;
- full verification outputs and durations;
- fixture before/after hook-file stat/digest/backup receipts;
- direct/delegated command-corpus result counts;
- protected `v1.5.1` file-digest comparison;
- fresh-client eligibility/evidence rows;
- implementation PR URL/head/merge/check status;
- Release-GO text, tag target, and release URL;
- E-05 handoff;
- `git status --short --branch`, `git diff --check`, and worktree/clone cleanup receipts.

Evidence must contain no operator hook contents beyond generic fixtures, no local private paths
other than bounded test roots, no prompt text, no machine secrets, and no claim that E-05/E-06 or a
live host transition occurred.

## 13. Review provenance and residuals

Source review covered:

- AWA plan/ADR conventions and the current agentic exemplar;
- AWA `install.sh`, `kernel/lib/install-lib.sh`, five-row `install-hooks.sh`, all four generic hook
  scripts, doctor/uninstall paths, contract freeze, relevant unit/lifecycle tests, `Makefile`,
  runnerless PR recipe, release/version state, README, and architecture;
- Dev's accepted program/ADR and current thin overlay/delegators/read-only three-row installer; and
- current official client facts inherited from the accepted program's §4.6 evidence.

Residuals intentionally assigned downstream:

1. E-05 proves the Skills GCB forwards/preserves the released external-owner contract and pins the
   exact release.
2. E-06 designs and proves the actual Dev atomic five-role transaction, current `3+3+2` repair,
   live doctor, and complete-owner-first rollback.
3. AWA E-04 cannot produce a fresh live Dev external-host canary before those serial dependents;
   it produces honest contract-only evidence instead.

No known P0/P1 remains in this DRAFT. Owner review may revise it in place while DRAFT; acceptance
freezes it and requires a v2 successor for material change.
