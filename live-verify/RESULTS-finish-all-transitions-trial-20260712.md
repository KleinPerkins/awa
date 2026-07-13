# AWA Root-Bound Worktree Finish — comprehensive transition trial (Layer A) — 2026-07-12

**Feature under test:** Root-Bound Worktree Finish (kernel-authorized closeout + hook/consumer
convenience surfaces + Phase-3 recovery retention). The only prior **live** UAT was a single
transition (`I'm done` → warning+block → `Cancel`,
[`RESULTS-finish-phase2-uat-20260712.md`](RESULTS-finish-phase2-uat-20260712.md)). This session builds
and runs a **comprehensive headless transition harness** that drives **every** other transition
end-to-end through the production surfaces, and prepares a **live operator runbook** for the four
inherently live-Desktop-only surfaces.

**Source pin:** branch `cursor/worktree/awa-20260711033524` @ HEAD `763be87` (the released v1.1.0,
fully merged to `main`; tree clean at trial start apart from the additive trial-runner).
**Harness:** `live-verify/trial-runner/` (Layer A) + `LIVE-OPERATOR-RUNBOOK.md` (Layer B).
**Sandbox:** each transition runs in its own `tempfile.mkdtemp(prefix="awa-uat-p123.")` with XDG +
`AWA_HOME` + kernel-lib overrides — it **never** reads/writes the real state root
`~/.local/state/awa`, the released runtime, this worktree's git, or the operator's `~/.cursor/*`.

> Convention: topic-scoped `RESULTS-<topic>-<date>.md` (cf.
> [`RESULTS-finish-final-rollout-20260712.md`](RESULTS-finish-final-rollout-20260712.md)). No
> screenshots. Machine evidence is the emitted `awa-finish-uat-matrix/v1` JSON (regenerate with
> `--json-out`); the human matrix is reproduced below.

---

## Headline

| Metric | Value |
|--------|-------|
| Headless transitions driven end-to-end | **75** (23 Phase-1 + 33 Phase-2 + 19 Phase-3) |
| Result | **75 PASS, 0 FAIL, 0 ERROR** |
| Real-environment guard | **PASS** (finish/recovery/non-volatile state unchanged; worktree git unchanged) |
| Live-deferred (Layer B, D1–D4) | **4 SKIP** (recorded so the matrix has zero silent gaps) |
| Total matrix rows | **80** |
| Wall time | ~153s |
| Genuine product bugs surfaced | **0** |
| Test-infra issues found + fixed this session | **2** (both in the new harness, see §4) |

**Re-run (one line):**

```bash
python3 live-verify/trial-runner/run_trial.py
```

---

## 1. Full transition matrix (0 gaps vs the plan's scenario list)

`H` transitions are headless (driven now); `SKIP (live)` are the Layer-B Desktop-only surfaces
(D1–D4), each pointing at the operator step that proves it.
<!-- BEGIN MATRIX (awa-finish-uat-matrix/v1 @ 763be87) -->

### Phase 1 — kernel core (23)

| ID | Precondition | Input | Expected | Result |
|----|--------------|-------|----------|--------|
| `P1-CLOSE-REMOVES` | ephemeral linked worktree, dirty draft, pending challenge from preview | kernel finish-execute --answer Close | outcome=removed; worktree gone; challenge consumed once | **PASS** |
| `P1-CONSUME-REPLAY` | pending challenge from preview | challenge-consume x2 | first consumed=true, second consumed=false | **PASS** |
| `P1-NONCLOSE-REFUSE` | pending challenge | finish-execute with close/CLOSE/cLoSe/' Close '/'Close\n'/'Close please'/yes/true/'' | outcome=refused reason=not_close; worktree preserved for every variant | **PASS** |
| `P1-NO-CHALLENGE` | no preview performed | finish-execute --answer Close (never previewed) | outcome=refused receipt_code=finish_no_challenge; preserved | **PASS** |
| `P1-FINGERPRINT-DRIFT` | pending challenge, then a new untracked file appears | finish-execute --answer Close after drift | outcome=refused receipt_code=finish_fingerprint_mismatch; preserved | **PASS** |
| `P1-CROSS-ROOT` | preview A, execute B with the same conversation id | finish-execute B --answer Close (challenge minted for A) | outcome=refused receipt_code=finish_target_mismatch; A and B preserved | **PASS** |
| `P1-STALE-TTL` | pending challenge aged far past the 15-min backstop | challenge-read x2 | first read status=stale, second read status=absent (backstop discarded it) | **PASS** |
| `P1-CANCEL-NOOP` | pending challenge; a file present in the worktree | challenge-delete then challenge-read | challenge absent; the worktree file is untouched (no mutation) | **PASS** |
| `P1-CROSS-SESSION` | another live session heartbeat recorded BEFORE preview | finish-execute --answer Close from the confirming session | outcome=refused receipt_code=finish_session_blocked; preserved | **PASS** |
| `P1-BRANCH-EPHEMERAL` | cursor/worktree/* branch with no unshared commits | branch-disposition | action=delete_eligible | **PASS** |
| `P1-BRANCH-LOCALONLY` | ephemeral branch carrying an unshared commit | branch-disposition | action=retain_local_only | **PASS** |
| `P1-BRANCH-NONEPHEMERAL` | feature/keep worktree branch | branch-disposition | action=retain | **PASS** |
| `P1-BRANCH-PROTECTED` | branch names main and master | _is_ephemeral_branch | False for main and master (never delete-eligible) | **PASS** |
| `P1-NO-NETWORK` | PATH shim whose git/gh touch a sentinel on any network verb | finish-execute --answer Close under the net-bomb PATH | outcome=removed, branch deleted, sentinel NEVER created | **PASS** |
| `P1-CLI-REQUIRES-CLOSE` | ephemeral worktree | clean --finish-current --preview  THEN  --authorization Close | preview preserves (finish_preview); Close removes (finish_removed) | **PASS** |
| `P1-FLAG-ALONE` | ephemeral worktree | clean --finish-current (no --authorization) | refused finish_no_authorization; worktree preserved | **PASS** |
| `P1-SPOOF-PRIMARY` | a primary (non-linked) checkout | clean --finish-current --authorization Close in the primary | refused finish_not_linked; preserved | **PASS** |
| `P1-SPOOF-SUBDIR` | a nested subdir inside a linked worktree | clean --finish-current --authorization Close in a subdir | refused finish_not_linked; preserved | **PASS** |
| `P1-REJECT-PATH` | ephemeral worktree | clean --finish-current --path <wt> --authorization Close | refused finish_bad_args; preserved | **PASS** |
| `P1-BRANCH-FALLBACK` | git shim that fails update-ref; ephemeral worktree | clean --finish-current --authorization Close | removed; branch_action=delete_failed; branch survives (compare-and-delete, no force) | **PASS** |
| `P1-DIRTY-DISCARD` | ephemeral worktree with a modified tracked file + a new untracked file | clean --finish-current --preview then --authorization Close | removed (dirty work discarded once authorized) | **PASS** |
| `P1-RECEIPT-FIELDS` | ephemeral worktree with two discardable files | clean --finish-current --preview then --authorization Close | receipt: finish_current=true, branch_action=deleted, discard_count>=2, fingerprint+nonce present | **PASS** |
| `P1-LITERAL-CLOSE` | none (pure predicate) | is_literal_close over an adversarial matrix | True only for 'Close'; False for casing/trim/attachment/boolean/None variants | **PASS** |

### Phase 2 — conversational ergonomics (33)

| ID | Precondition | Input | Expected | Result |
|----|--------------|-------|----------|--------|
| `P2-REC-POSITIVES` | none (pure recall matcher) | recognize_finish over the approved-phrase matrix | all direct triggers + paraphrases + uppercase -> True (would preview) | **PASS** |
| `P2-REC-NEGATIVES` | none | recognize_finish over negated/quoted/doc/feature/hypothetical/meta phrases | all -> False (no preview) | **PASS** |
| `P2-REC-CLI` | none | python3 finish_current.py recognize <phrase> | finish_current=true for a direct trigger, false for a negation | **PASS** |
| `P2-HIGH-SIGNAL` | OperatorLoop with a router that explodes if consulted | OperatorLoop.map('I'm done') | verb=finish_current without the router ever being consulted | **PASS** |
| `P2-WARNING-SNAPSHOT` | none | WARNING_STATIC bytes + contract cross-check | byte-identical to the frozen approved copy; contract carries the heading + Close correction | **PASS** |
| `P2-WARNING-ROWS` | none | render_warning(150 rows) and render_warning('') | 150th row present, no truncation; empty rows -> the None default line | **PASS** |
| `P2-WARNING-CLI` | none | python3 finish_current.py warning [--rows ...] | default ends with the None line; explicit rows are appended verbatim | **PASS** |
| `P2-HOOK-BLOCK` | linked worktree with a dirty draft | handle_hook_payload('I'm done') | continue=false; user_message == render_warning(rows); challenge minted; never routes to model | **PASS** |
| `P2-HOOK-SHELL-SCHEMA` | linked worktree with a dirty draft | echo <payload> \| before-submit-prompt.sh | rc=0; keys=={continue,user_message}; continue=false; exact render_warning message | **PASS** |
| `P2-HOOK-FAILOPEN` | none | echo '{bad' \| before-submit-prompt.sh | rc=0; {continue:true} (never blocks a user on a parse fault) | **PASS** |
| `P2-HOOK-UNSUPPORTED` | primary checkout / background(cloud) / multi-root / absent-target payloads | handle_hook_payload for each unsupported shape | {continue:true}; no challenge; no dialogue for each | **PASS** |
| `P2-HOOK-OBSERVABILITY` | linked worktree; a blocking preview | handle_hook_payload then inspect the observation record + bound | decision=block_warning; no prompt/path/file leak; 0700/0600; count<=limit | **PASS** |
| `P2-PREVIEW-EXC-CLEAN` | linked worktree; write_dialogue raised mid-preview | handle_hook_payload with write_dialogue injected to fail | {continue:true}; challenge left with hook_activated=false; no dialogue | **PASS** |
| `P2-CANON-CHOICES` | none (pure canonicalizer) | canonicalize_choice over the full choice matrix | Commit/Retain/Mixed/Cancel case/trim-insensitive; Close exact-only; documented reject reasons | **PASS** |
| `P2-CANCEL-NOOP` | pending dialogue; a draft present | dispatch_choice(Cancel) | {ok, cancelled, mutated_repo:false}; file untouched; dialogue+challenge gone | **PASS** |
| `P2-CLOSE-ROUTING` | pending dialogue; an executor spy | dispatch_choice over Close variants, attachments, then exact Close | variants refused (reason + CLOSE_CORRECTION), executor untouched; exact Close removes once | **PASS** |
| `P2-CRM-SELECTION` | pending dialogue per choice | dispatch_choice(Commit\|Retain\|Mixed) | awaiting_(commit\|retain\|mixed)_selection; challenge preserved; no removal | **PASS** |
| `P2-DISPATCH-CLI-CLOSE` | hook preview + published + captured Close on a THROWAWAY worktree | python3 finish_current.py dispatch --current (cwd=throwaway wt) | workspace_removed=true; agent_stopping=true; chat_remains_open=true; worktree gone | **PASS** |
| `P2-CANCEL-UNDER-DRIFT` | pending dialogue, then a new untracked file appears (drift) | dispatch_choice(Cancel) after drift | cancelled; no repo mutation; dialogue+challenge cleared despite drift | **PASS** |
| `P2-CLOSE-REFUSE-UNDER-DRIFT` | hook preview + published + captured Close, then drift appears | dispatch --current after drift (real kernel executor) | refused (fingerprint mismatch); worktree preserved; dialogue kept live | **PASS** |
| `P2-RETAIN-LIFECYCLE` | linked worktree with staged/renamed/secret/symlink content | create_retain (secret gate), manifest, list, restore, delete-exact-id | protected+restore_proven+explicit_secrets; 0700/0600; restore content+symlink; delete needs exact id | **PASS** |
| `P2-RETAIN-FRESH-PREVIEW` | pending dialogue; a draft | complete_retain then inspect the refreshed dialogue | close_still_required=true; fresh_preview blocks; challenge preserved | **PASS** |
| `P2-RETAIN-CLI` | pending dialogue in awaiting_retain_selection (non-secret row) | retain --rows; retain-list; retain-restore; retain-delete (wrong then exact id) | artifact created + listed + restored; delete refuses a wrong confirmation, succeeds on exact id | **PASS** |
| `P2-IGNORED-RETAIN-ONLY` | worktree with ignored files/dir + an ignored .env secret | inventory eligibility flags + commit_selected_local(ignored rows) | each ignored row commit_eligible=false/retain_eligible=true; commit raises retain_only pre-mutation | **PASS** |
| `P2-COMMIT-EVIDENCE-OK` | none (pure evaluator) | verify_delivery_evidence(good) and complete-zero-checks-stable | ok=true for a single-repo exact-head merge-commit PR with complete passing checks | **PASS** |
| `P2-COMMIT-FAILURE-MATRIX` | none | verify_delivery_evidence over the failure matrix (+ merge_commit_enabled=false) | ok=false for multi-repo, bad head, no PR, diverged, incomplete/pending/failing checks, squash/rebase-only | **PASS** |
| `P2-COMMIT-NETWORK-COMMITONLY` | linked worktree; a gh-call bomb installed | preview + Cancel with UX.subprocess.run trapping any gh call | no gh invocation escapes outside Commit/Mixed delivery | **PASS** |
| `P2-COMMIT-GH-MISSING` | delivery runner raises FileNotFoundError('gh') | verify_delivery_network with a missing-gh runner | ok=false; reason=delivery_evidence_unavailable (never a false success) | **PASS** |
| `P2-COMMIT-SELECTED` | linked worktree with selected + unselected files; deliver_commit stubbed ok | complete_commit([selected]) with a pre-commit hook present | only the selected file is committed; unselected stays untracked; close_still_required; fresh preview blocks | **PASS** |
| `P2-COMMIT-FAIL-HONEST` | linked worktree; deliver_commit stubbed to fail | complete_commit with a failing delivery | ok=false; local_commit_preserved=true; the local commit remains; worktree preserved | **PASS** |
| `P2-MIXED-EXECUTE` | linked worktree with >=3 rows; deliver_commit stubbed ok | complete_mixed(commit_rows, retain_rows) incl. overlap + incomplete refusals | overlap + incomplete refuse pre-mutation; disjoint+complete delivers commit + protected retain; re-previews | **PASS** |
| `P2-REPUBLISH-2ND-CLOSE` | a completed hook-owned Retain (action_complete_refresh_pending) | Close #1 (republishes) -> publish -> Close #2 (acts once) | first Close republishes the warning (no removal); only the second exact Close invokes removal once | **PASS** |
| `P2-HOOK-INSTALL` | a disposable hooks.json path | install-hooks.sh twice + --check | idempotent bytes; matcher=UserPromptSubmit; failClosed=false; timeout=20 | **PASS** |

### Phase 3 — recovery retention lifecycle (19)

| ID | Precondition | Input | Expected | Result |
|----|--------------|-------|----------|--------|
| `P3-MANIFEST-UNIFIED` | a fresh archive | build_manifest + scan of the kernel bundler for the shared schema token | declares MANIFEST_KEYS; schema/id/size/sha over real bytes; dev-worktree.sh emits the same schema | **PASS** |
| `P3-TTL-SOURCE-CLOCK` | artifacts with live vs deleted sources | run_maintenance: live source; source-deleted+TTL; first-absence starts clock; default TTL | live source never prunes; expired prunes; first absence preserves then prunes; TTL=7d | **PASS** |
| `P3-PROTECTED-NEVER` | a protected archive + an ordinary sibling both aged past TTL, tiny watermark | run_maintenance with TTL + pressure both selecting them | protected archive+manifest survive; ordinary pruned; protected_bytes reported honestly | **PASS** |
| `P3-PRESSURE` | three aged ordinary artifacts + a size-lying manifest | run_maintenance under a tiny watermark + default-constant + accounting checks | oldest-first until under watermark; young preserved; reason=pressure; 1GiB/24h defaults; size=on-disk | **PASS** |
| `P3-CONTAINMENT` | a symlink archive escaping the root + a path-traversal artifact_id | _delete_one on a symlink; _safe_target checks; _delete_one with ../.. id | refused_containment (outside survives); _safe_target rejects escape/symlink; journal stays inside trash | **PASS** |
| `P3-CRASH-RESUME` | a prepared deletion journal (simulated crash) + an escaping journal | _resume completes the prepared txn; refuses the escaping journal; _delete_one leaves no journal | resume unlinks+tombstones+removes journal; escaping journal surfaced (outside survives); clean delete leaves no journal | **PASS** |
| `P3-RECONCILE` | a recorded recovery row aged past TTL | run_maintenance then inspect the row/tombstone/clock | row status=pruned; tombstone exists; source-deletion clock cleared | **PASS** |
| `P3-LEGACY` | a pre-unified manifest + a bare .patch | scan (deterministic id) + bare-patch classification + legacy TTL prune | legacy id stable+prefixed; bare patch participates as ordinary; legacy artifact TTL-prunes | **PASS** |
| `P3-PERMISSIONS` | world-readable drift on ordinary + protected archives | repair_permissions over a scan | ordinary->0600; protected->0400; recovery dir->0700 | **PASS** |
| `P3-THROTTLE-LOCK` | an opportunistic run, then a second; then a held state-root lock | run_maintenance(opportunistic) x2 + under a held lock; lockfile perms | second run throttled; under lock skips lock_busy (never races); lockfile is private-perms | **PASS** |
| `P3-PRUNE-ON-CREATION` | a scratch repo with an ignored file | recovery.create_bundle (with state, and state=None) | META_LAST_RUN advances (one pass ran under the lock); creation never fails if maintenance raises | **PASS** |
| `P3-NEEDS-REPAIR` | a manifest whose archive is missing + a bare archive with no manifest | scan + a maintenance pass | both surfaced in needs_repair; the unmanifested archive is never auto-deleted | **PASS** |
| `P3-FINISH-NO-RETENTION` | none (structural scan of the finish sources) | scan kernel/lib/awa_finish.py + consumer/finish_current.py for retention tokens | neither references run_maintenance/engine.retention/prune_* (removal is retention-free) | **PASS** |
| `P3-STATUS-SURFACE` | one protected + one ordinary artifact | retention.status | ttl_days=7; watermark=1GiB; counts + protected/ordinary bytes + tombstone_count | **PASS** |
| `P3-CLI-RECOVER` | isolated sandbox XDG state | python3 -m engine recover status; recover prune --maintenance | status: ttl_days=7, watermark=1GiB; prune: ran=true, trigger=manual (dashboard-stable JSON) | **PASS** |
| `P3-DAEMON-RUNONCE` | isolated sandbox XDG state | python3 -m engine daemon run-once | ok=true; action=run-once (quarantine cleanup + opportunistic maintenance, zero network) | **PASS** |
| `P3-EMITTER-PROBE` | no engine state db | dashboard/emitter.py recovery_status | recovery.available=false; NO state.db created by the probe | **PASS** |
| `P3-SESSION-HOOK` | empty sandbox XDG state (no state.db) | echo '{}' \| awa-recovery-maintenance.sh | rc=0; stdout=={}; creates no engine state from a passive session | **PASS** |
| `P3-UNINSTALL-SURVIVAL` | install.sh into a sandbox HOME; a protected-retain dir + an ordinary state file | install.sh then install.sh --uninstall (HOME + XDG redirected into the sandbox) | protected-retain manifest survives uninstall; the ordinary state file is removed | **PASS** |

### Live-deferred (Layer B, D1–D4) (4)

| ID | Precondition | Input | Expected | Result |
|----|--------------|-------|----------|--------|
| `LIVE-D1-HOOK-RENDER` | disposable UAT runtime + throwaway worktree opened in a Cursor window | operator submits `I'm done` | the fixed WARNING block renders, five options each on their own line, submission blocked | **SKIP (live)** |
| `LIVE-D2-CHOICE-SUBMIT` | pending finish dialogue on the throwaway worktree | operator submits each choice; agent runs `dispatch --current` | real removal on exact Close; real Retain artifact; real Commit delivery; correction on Close-variant | **SKIP (live)** |
| `LIVE-D3-AGENT-STOP` | a successful live Close on the throwaway worktree | observe the agent after the terminal receipt | agent issues no further task tools; chat stays open (flags headless-proven, cessation live-only) | **SKIP (live)** |
| `LIVE-D4-COMMIT-GITHUB` | a throwaway GitHub repo with merge commits enabled | operator submits Commit; agent runs `commit` against a real merged PR | exact-head merge-commit PR into the live default branch with complete passing checks | **SKIP (live)** |

### Real-environment guard (1)

| ID | Precondition | Input | Expected | Result |
|----|--------------|-------|----------|--------|
| `GUARD-REAL-ENV-UNTOUCHED` | fingerprint before/after the whole run | compare ~/.local/state/awa non-volatile file-set + worktree git status/HEAD | no added/removed/resized files in the finish/recovery/non-volatile state; worktree git unchanged | **PASS** |
<!-- END MATRIX -->

**Machine matrix:** `{"counts":{"ERROR":0,"FAIL":0,"PASS":76,"SKIP":4},"source_head":"763be874176298c7fce4539af32f2733c0967617"}`
(76 PASS = 75 headless transitions + the guard row).

### 0-gap check vs the plan's 13 rollout scenarios

Every plan scenario (as enumerated in
[`RESULTS-finish-final-rollout-20260712.md`](RESULTS-finish-final-rollout-20260712.md)) is now driven
end-to-end by ≥1 headless transition; D1–D4 remain live-only by nature:

| Plan scenario | Covering transition(s) |
|---------------|------------------------|
| 1. Representative finish phrases → preview/block | `P2-REC-POSITIVES`, `P2-REC-CLI`, `P2-HIGH-SIGNAL`, `P2-HOOK-BLOCK`, `P2-WARNING-SNAPSHOT/ROWS/CLI` |
| 2. Metalinguistic negatives never trigger | `P2-REC-NEGATIVES` |
| 3. All choices + casing; exact one-use `Close`; variant→correction, dialogue live | `P2-CANON-CHOICES`, `P2-CLOSE-ROUTING`, `P1-LITERAL-CLOSE`, `P1-NONCLOSE-REFUSE`, `P1-CONSUME-REPLAY`, `P2-DISPATCH-CLI-CLOSE` |
| 4. Attachment / booleans / "yes" / approval-click rejected | `P2-CANON-CHOICES`, `P2-CLOSE-ROUTING`, `P1-NONCLOSE-REFUSE` |
| 5. Retain: row selection, protected restore-proven artifact, secret gate, list/restore/delete | `P2-RETAIN-LIFECYCLE`, `P2-RETAIN-CLI`, `P2-RETAIN-FRESH-PREVIEW`, `P2-IGNORED-RETAIN-ONLY` |
| 6. Mixed (row-partitioned commit + retain) | `P2-CRM-SELECTION`, **`P2-MIXED-EXECUTE`** (disjoint/complete partition end-to-end) |
| 7. Commit delivery boundaries + network only in Commit/Mixed | `P2-COMMIT-EVIDENCE-OK`, `P2-COMMIT-FAILURE-MATRIX`, `P2-COMMIT-NETWORK-COMMITONLY`, `P2-COMMIT-GH-MISSING`, `P2-COMMIT-SELECTED`, `P2-COMMIT-FAIL-HONEST` |
| 8. Dirty confirmed discard | `P1-DIRTY-DISCARD`, `P1-RECEIPT-FIELDS` |
| 9. Multi-session blocking (session-lock ABI) | `P1-CROSS-SESSION` |
| 10. Network-free branch disposition | `P1-NO-NETWORK`, `P1-BRANCH-EPHEMERAL/LOCALONLY/NONEPHEMERAL/PROTECTED`, `P1-BRANCH-FALLBACK` |
| 11. Audit-failure honesty (no bare green pill) | `P2-COMMIT-FAIL-HONEST`, `P2-CLOSE-REFUSE-UNDER-DRIFT`, `P1-BRANCH-FALLBACK` |
| 12. Terminal agent-stop after `Close` (structured outcome) | `P2-DISPATCH-CLI-CLOSE`, `P1-CLOSE-REMOVES`; literal cessation = **D3 (live)** |
| 13. Phase-3 retention invariants (only `Close` deletes; uncertainty preserves; zero-net; no retention on finish path) | `P3-FINISH-NO-RETENTION`, `P1-NO-NETWORK`, `P1-NONCLOSE-REFUSE` + all `P3-*` |

**Conclusion: 0 headless coverage gaps.** The one gap found during construction (Mixed was only
driven to its *selection* state) was closed this session with `P2-MIXED-EXECUTE` (see §4). D1–D4 are
inherently live-Desktop-only (see §7) and are carried by the Layer-B runbook.

---

## 2. Harness location + re-run + self-clean proof

- **Location:** `live-verify/trial-runner/` (`run_trial.py` orchestrator; `_trial_lib.py` core;
  `_trial_phase{1,2,3}.py`; `_trial_live.py`; `README.md`).
- **Re-run:** `python3 live-verify/trial-runner/run_trial.py` (add `--json-out matrix.json`,
  `--filter <text>`, `--list`, `--quiet`). Deliberately **not** wired into `make verify` (it is the
  heavier pre-live/pre-release UAT rehearsal; the finish/retention *unit* suites already run in
  `make verify`).
- **Self-clean:** every transition provisions + tears down its own `awa-uat-p123.*` sandbox on exit
  (success or failure). Verified post-run: `ls ${TMPDIR}/awa-uat-p123.*` → **no matches**.
- **Real env untouched (asserted every run):** `GUARD-REAL-ENV-UNTOUCHED` → **PASS**:
  `finish/recovery/non-volatile state unchanged (149 files); worktree git status+HEAD unchanged; 0
  live-runtime volatile heartbeat/receipt/lock file(s) changed concurrently (not harness-caused)`.
  The guard is **robust to the operator's live runtime**: it tolerates concurrent churn in the
  live-runtime-owned volatile subtrees (`roots/` heartbeats, `receipts/`, `locks/`, hook metadata)
  while staying **strict** on the finish-authorization + recovery/retain subtrees a real leak would
  hit. `git status` after the run shows only the additive `live-verify/trial-runner/` directory.

---

## 3. Gate results

| Gate | Result |
|------|--------|
| `python3 live-verify/trial-runner/run_trial.py` | **75/75 headless PASS, 0 FAIL, 0 ERROR**, 4 live-deferred SKIP, guard PASS (80 rows, ~153s) |
| `make verify` | _recorded in the session report_ |
| `git diff --check` | _recorded in the session report_ |

---

## 4. Test-infra issues found + fixed this session (no product bugs)

**Zero genuine product bugs were surfaced.** Every headless transition matches the behavior the
source suites already encode. Two issues were in the **new harness itself** and were fixed +
re-verified here (they are test infrastructure, not product):

1. **Mixed coverage gap (added a transition).** The harness originally drove Mixed only into its
   `awaiting_mixed_selection` state (`P2-CRM-SELECTION`), not through a full disjoint+complete
   row-partitioned execution. Closed with **`P2-MIXED-EXECUTE`**, which mirrors
   `test_finish_hardening::StateMachineAdversarialTest::test_mixed_requires_exact_disjoint_complete_partition`
   + the completion latch: overlap and incomplete partitions refuse **pre-mutation**; a disjoint +
   complete partition delivers the commit rows (stubbed `deliver_commit`) + a protected retain
   artifact, commits only the commit-row, and re-previews (a separate exact `Close` is still
   required; Mixed never removes).

2. **Real-env guard false-positive on live-runtime churn (hardened the guard).** The guard
   fingerprinted the *entire* real state root, so the operator's live runtime rotating a heartbeat
   (`roots/.hb-hot-*`) or another session appending a `receipts/clean-*` **during** a run tripped the
   guard even though the harness (XDG-redirected per sandbox) wrote nothing there. The guard now
   classifies changes: live-runtime-owned volatile subtrees (`roots`/`receipts`/`locks`/`detections`/
   `hook-probe`/`current-session`/finish-hook metadata) are reported as informational churn, while
   the finish-authorization + recovery/retain (and every other non-volatile) subtree stays **strict**
   — a real harness leak there still fails the run. This was a true positive about the guard's
   fragility, confirmed by observing that a known-good transition (`P2-COMMIT-SELECTED`) passed the
   guard while the same window's live heartbeat/receipt churn was the only diff on a longer run.

No product code, product tests, or the frozen contract were modified. The changes are confined to
`live-verify/trial-runner/`.

---

## 5. Layer B — live operator runbook

- **Location:** [`live-verify/trial-runner/LIVE-OPERATOR-RUNBOOK.md`](trial-runner/LIVE-OPERATOR-RUNBOOK.md)
  (steps **L1–L6**), with agent-run helpers `provision-live-uat.sh` + `teardown-live-uat.sh`.
- **Disposable runtime + throwaway target provisioning:** `bash
  live-verify/trial-runner/provision-live-uat.sh` installs this source (v1.1.0) into a **fully
  disposable** runtime `~/.local/share/awa-finish-trial-uat/awa/current` with a **disposable state
  root** `~/.local/state/awa-finish-trial-uat` and a **disposable hooks file** (it never touches the
  real state root or the operator's `~/.cursor/hooks.json`), and builds three throwaway linked
  worktrees (`target-close.wt` / `target-retain.wt` / `target-commit.wt`). `--dry-run` was verified
  to print the exact plan and touch nothing. Teardown: `bash
  live-verify/trial-runner/teardown-live-uat.sh` (removes the disposable runtime/state/worktrees,
  restores any Part-A hooks backup, verifies real-env parity).
- **Default is safe (Mode B):** the operator submits every prompt in the throwaway window; the agent
  seeds each pending dialogue with the production hook script and runs the production dispatcher
  against the operator's exact typed text — `~/.cursor/hooks.json` is never touched. The live modal
  (D1) is an explicit opt-in (Part A) that backs up + swaps + restores the user-global hooks file.
- **EXACT first operator prompt to begin the live portion (after the agent provisions):**

  > Open a **new Cursor Desktop window** on `~/.local/share/awa-finish-trial-uat/target-close.wt`,
  > start an agent chat there, and submit exactly: **`I'm done`**

- **Honest caveat carried in the runbook:** on some Cursor builds `beforeSubmitPrompt` is advisory;
  the D1 pass criterion is the hook returning `continue:false` / `decision:block_warning` + a
  metadata-only observation, not the client's enforcement.

---

## 6. Git state

_Filled in the session report: safety-commit SHA on `cursor/worktree/awa-20260711033524`, PR link,
and whether the `pr-automation-controller` armed auto-merge (the controller arms itself — no manual
`gh pr merge --auto`)._

---

## 7. Honest residuals — the four live-Desktop-only surfaces (unchanged classification)

These are **inherently** non-headless and remain **DEFERRED (live-Desktop-only)**; the Layer-B runbook
drives them. None is a headless coverage gap, and the kernel safety guarantee (exact-`Close`-only,
fail-safe preservation, zero-network removal) is fully headless-proven and depends on **none** of
them.

- **D1 — Cursor Desktop hard-block rendering** (build-dependent; convenience, not the safety gate).
  Live-proven for `I'm done` only (Phase 2, runtime `e0f3ae4`).
- **D2 — Live operator submission of `Close`/`Commit`/`Retain`/`Mixed`.** The full CLI/dispatch
  behavior is headless-proven; a live operator submitting them was not (only `I'm done` + `Cancel`
  were, to date).
- **D3 — Live agent runtime cessation** after a terminal `Close` (the flags are headless-proven; the
  cessation itself is observable only live).
- **D4 — Commit delivery against a real GitHub remote** (the evaluator + failure matrix are
  headless-proven; a real merged-PR delivery needs network + a live repo).
