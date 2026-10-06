# AWA — Security verification ledger + threat model

> Authoritative security doc for Agent Worktree Automation (AWA). It records individually
> verifiable rows rather than a self-referential "posture verified sound" bless. No
> security-touching layer may be marked done while its Cluster-D rows are
> **NEEDS RE-VERIFICATION**.
>
> **Path convention.** AWA is a two-layer system. Engine rows are backed by this repo's test
> suite (`engine/tests/`). Kernel rows reference the host-installed kernel shims (the worktree
> adapter/CLI, the `beforeShellExecution` gate `worktree-guard.sh`, and the host's
> `worktree-verify` suite), which live in the host repo, not here.

## Platform limitation — Cursor enforces hook `deny`, not `ask` (L4)

**Finding (L4, proven live).** Cursor's agent honors a `beforeShellExecution` hook that returns
`{"permission":"deny"}` (the command is blocked), but treats `{"permission":"ask"}` as
**non-blocking** on the agent path: the agent proceeds as if allowed, with no human modal. And
`afterFileEdit` ignores the permission field entirely — a returned `deny` there is discarded and the
edit lands on disk (independently observed 2026-07-05; the returned `deny` was ignored). This is a
Cursor platform behavior, documented in the Cursor community forum (threads reporting
`beforeShellExecution: ask` as non-blocking on the agent path) and acknowledged by Cursor staff as a
known limitation with no committed ETA.

**Consequence for AWA (design decision).** AWA does **not** rely on `ask` for prevention. A
**confirmed mutating command on an INCLUDED PRIMARY checkout** (mode ON) returns an enforced `deny`,
not `ask`, unless the exact command and live state affirmatively prove the narrow upstream-maintenance
exception below. `ask` is retained only as an **honest no-op signal** on the genuine-uncertainty path
(an included-looking checkout whose command payload the hook could not parse): AWA emits `ask` there
knowing Cursor will not block, so it never *silently* downgrades an uncertain case to allow, but it
also never pretends `ask` prevents anything.

**Fail-safety posture.** The deny path is fail-*safe*, never fail-*brick*:

- **Only `off` disables.** Any other mode value (a typo, a removed legacy value, an unknown) resolves
  to ON/`include` → protected. One fail-safe rule governs both the classifier read-path and the modes
  writer.
- **Infra failure ⇒ allow.** If the hook crashes, times out, or its interpreter is missing, it
  degrades to `allow` (anti-brick) — the kernel guarantee is *detection*, which never depends on the
  gate succeeding.
- **Cloud ⇒ allow.** A Cursor Cloud / background agent runs in an already-isolated, own-branch
  `/workspace` clone; the guard detects that (background-agent identity broker / `is_background_agent`
  / a `/workspace` root) and degrades to `allow` **before** the deny branch, so a cloud VM is never
  hard-blocked.

## Protected-primary upstream maintenance

The only direct Git maintenance mutation allowed on an included primary is a closed, state-aware
lane for `git fetch [<configured-upstream-remote>]` and
`git merge --ff-only --no-overwrite-ignore [<configured-upstream>]`. The optional merge target must
be exactly `@{u}`, `@{upstream}`, or the configured `<remote>/<branch>` short name. Both families
remain classified as mutating; the allow exists only inside the included-primary decision branch.

The recognizer rejects wrappers, assignments, executable paths, Git global options, redirects,
substitutions, control operators, extra flags, arbitrary URLs/remotes/refs/refspecs, `pull`, `push`,
explicit prune, remote update, and ordinary merge. Before either allow, bounded local Git probes
require a clean, attached, idle checkout; one remote-tracking upstream; fetch destinations contained
beneath that remote's tracking namespace; an exact upstream mapping; and no visible
repository-retargeting or config-injection `GIT_*` environment. The inspector also rejects every
`skip-worktree` or `assume-unchanged` index bit because those bits can hide tracked-file edits from
ordinary status output. Merge additionally requires `HEAD` to equal or precede the live upstream.
Any timeout, malformed output, missing mapping, or other uncertainty retains the deny and emits
bounded, plain-language guidance; merge also denies local-only or divergent history.

This is not a sandbox around configured Git. Fetch may write common-repository objects,
`FETCH_HEAD`, remote-tracking refs, reachable tags, and ordinary bookkeeping, and may invoke
configured transport/credential helpers, hooks, and automatic maintenance. Merge may advance the
current branch and update its index, worktree, reflogs, and `ORIG_HEAD`; configured hooks, filters,
fsmonitor, and submodule behavior remain active. After each allowed command, the caller must check
`git status --short`. If configured automation leaves residue, the caller stops, preserves it, and
diagnoses it from a Safe Workspace; routine maintenance never calls for disabling AWA, using the
session-wide primary override, or resetting the primary.

The engine and kernel implement independent mirrors. Shared stateful corpora drive the engine,
source hook, and installed role-resolved hook, while contract-freeze UAT covers canonical allows and
representative denials. A false or uncertain maintenance predicate falls through to deny; only a
genuine hook-internal failure retains the product-wide fail-open behavior.

**Known platform caveat — the hook runner can fail before AWA starts.** Phase 3 Step 3.2 of the
2026-07-15 Desktop UAT (Cursor 3.11.19) directly captured this path. In one Local conversation,
Cursor requested both registered `beforeShellExecution` commands for the restored-ON commit, but
each exited in 0–1 ms with empty output and the host-generated error
`Shell execution is not available in the worker extension host`; Cursor then logged that no hook
returned a valid response. The same failure affected every `sessionStart`, `beforeSubmitPrompt`,
and `stop` command in that conversation, including unrelated hooks. Cursor's agent-exec log then
recorded `hookForcesPrompt:false`, auto-approved the shell call, and the fixture reflog recorded the
commit. There was therefore no AWA decision to enforce: neither AWA guard process reached its code.
This establishes the immediate cause of the observed allow as Cursor hook-execution unavailability,
not an AWA mode/classification result. It does **not** establish why Cursor selected or lost shell
execution in that worker extension host, and no same-chat caching claim is made.

The boundary matches Cursor's documented hook contract: hook errors other than exit code 2 proceed
fail-open by default, and `failClosed:true` is the opt-in alternative
([Cursor Hooks](https://cursor.com/docs/hooks)). AWA deliberately keeps this global hook
`failClosed:false`: a prior live incident showed that fail-closed global shell infrastructure can
brick every workspace under timeout/load, while AWA's guaranteed floor is detection and cleanup
refusal, not universal shell sandboxing. A fresh Local conversation on the same 3.11.19 install
subsequently recorded the guard returning valid `deny` and Cursor blocking the primary-checkout
command. The deterministic lock
`test_same_conversation_mode_transition_is_rechecked` reuses one conversation/session payload,
changes OFF→ON, and proves the AWA process re-reads current mode on every invocation; it cannot
substitute for a live Desktop host-runner test.

**Known platform caveat — Cloud prompt provenance and unrequested remote writes are outside AWA's
hook authority.** In Phase 4 Step 4.1 of the 2026-07-15 Cloud UAT, the operator's closed seven-step
prompt requested one local empty commit and no push. The Cloud agent nevertheless committed the
edited file and pushed both commits to `origin/main`; the disposable remote directly recorded
`90ddbed` and `3fb85ef`. A repeat later pushed `0f34f5f`. In the preserved chat, the agent said it
treated “Reminder to commit and push if appropriate” as permission, then corrected itself after
reviewing the transcript: that text came from an internal system reminder, not the operator, and
the push was out of scope. This proves the remote writes and the agent's recorded attribution; no
raw Cursor internal event envelope was preserved, so the exact injector implementation and motive
remain unproven.

AWA was not an executable source of that instruction. At the fixture's initial pre-push commit,
its only committed `beforeShellExecution` command was the read-only hook probe, which logs and
returns `{"permission":"allow"}`; Cloud does not load the Desktop user-level guard. Even where the
production guard is present, its Cloud branch returns that same one-field allow response before
primary-checkout classification. Hooks authorize or refuse a command already selected by the host;
they neither originate a `git push` nor attest that the operator requested it. A Cloud push-specific
AWA block would contradict the explicit Cloud allow boundary and still could not repair prompt
provenance, so no product control was added. The regression
`test_cloud_push_allow_response_contains_no_instruction_or_authorization` locks this boundary.

**Recovery / override (operator path).** A routine maintenance denial is resolved from its specific
reason: preserve local state, repair tracking or fetch configuration in a Safe Workspace, and retry
only after the primary is clean. Development work belongs in a Safe Workspace opened through the
Cursor Agents-Window Worktree dropdown. `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` remains an explicit
operator escape hatch for a separately authorized exceptional action; it is not maintenance
guidance. An inline `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>` prefix does **not** work — the hook
reads its own process environment, not the command's inline assignment — and
`cd <worktree> && <cmd>` is still denied.

**Residual to close.** Desktop `deny` blocking is now independently re-proven by the 2026-07-15
fresh-conversation event above. A complete same-build ask-then-deny matrix on Desktop and Cloud
remains tracked in `live-verify/RESULTS-e2e-uat-20260707.md` (Phase 1). The
`ask`-is-non-blocking and `afterFileEdit`-ignores-permission halves were already proven by the
2026-07-05 live observation, on-disk mutation, and L2 doc snapshot.

## MCP guidance and resource boundary

MCP guidance is advisory and never grants safety authority. Tool descriptions and
`initialize.instructions` are the primary routing surface; the host may optionally list/read the
single fixed `awa://assistant/operator-guide/v1` document. Neither the server nor the guide assumes
Cursor automatically consumes resources. A guard-tool result is diagnostic rather than permission
to execute. Lease reads check only required fields and the identity hash; absent, unreadable, and
malformed records all report `found:false`, and cleanup instead uses the active-root heartbeat plus
git/content checks. `dev-worktree.sh` owns current-repo state, Safe Workspace selection, health, and
cleanup; other lifecycle/recovery intents remain on `awa-engine`. Engine status is not a full health
check, and all kernel guarantees continue with the engine off.

The resource renderer is pure: it consumes only in-memory advertised tool descriptions and cannot
read the environment, host policy, filesystem, database, contracts, or live AWA state. The guide excludes
live status/modes/leases, machine paths, audit or SQLite history, recovery artifacts, raw contracts,
templates, subscriptions, notifications, and lifecycle actions. Protocol handling accepts only an
exact resource URI, returns sanitized standard errors (`-32600` invalid request, `-32602` invalid
params, `-32002` resource not found), classifies every syntactically valid non-matching URI
(including `urn:` forms) as not found, validates 2024-11-05 initialize fields and request-ID types,
accepts only integer/string request IDs, rejects explicitly null params, non-finite/over-nested JSON,
and oversized newline-delimited messages, ignores request-method notifications without executing
them, and recovers after malformed input without terminating or contaminating the next request. The
undeclared caller-supplied `policy` override is not accepted by `awa_guard_shell`; policy remains
server-resolved.

Mode tools read/write only the referenced host modes file; effective runtime mode also merges
inline host-policy settings, then resolves exact before first matching glob, with `default_mode`
only at final eligibility. Higher-priority safety exclusions outrank `on`. A present but
unreadable/non-regular referenced file forces modes/default to fail-safe `on`, including over
inline `off` values, and FIFO inputs are rejected without blocking.

**Live evidence status: RETAIN, narrowly.** A real Cursor Desktop explicit on-demand resource read
alone proved the plan's alternative utility criterion; catalog discovery is not treated as model
routing. The resource added no routing coverage beyond inline metadata; authentication blocked the
model-output matrix, no substitute was fabricated, and no model-routing benefit is claimed. See
[`RESULTS-MCP-GUIDANCE-BASELINE-20260709.md`](live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md).
`consent_prompt()` is only contract-tested candidate copy for a future host integration: the stdio
server does not render or enforce it, so it is not a production consent control.

## Integrity surveillance security boundary (M1-B)

Integrity surveillance is advisory and engine-side; the kernel guard and cleanup refusal do not
import it. Its private store uses `0700` directories and `0600` files, generation-tagged artifacts,
per-child-directory fsync, and a status-last atomic replace. The alert receipt is a typed
generation/transition compare-and-swap: retry is idempotent, crash-before-status preserves the prior
authority, and a stale receipt is audited without overwriting newer status.

A separate `0600` dispatch lock makes the authoritative status/outbox re-read, native invocation,
and receipt CAS single-file across competing evaluators. Undelivered and failed current transitions
stay pending; superseded transitions are privately audited and not invoked. The receipt/current-
generation advance is exactly once. Native OS delivery cannot be made transactional: a crash after
notification acceptance but before receipt commit intentionally retries at least once.

Neither notification nor console receives raw invariant evidence. The public projection is a closed
allowlist of fixed invariant ids/severities, bounded counts/history, and timestamps; absolute paths,
release identity, arbitrary fields, and credentials are dropped. Native notification text is
derived only from severity names and is bounded by timeout. The static console revalidates the
closed projection, embeds script-safe JSON (`<`, `>`, `&`, U+2028, U+2029 escaped), has no remote
assets, and permits one SHA-256-pinned clock-only script under a strict CSP. That script can only
recompute age and force `STALE / RED`; there is no form/action surface, and ordinary browser refresh
is the only reload path.

AWA installs the sweep executable, schedule contract, and renderer but no plist. It never activates
`com.kleinperkins.awa-integrity`; host `local-jobs` owns activation and expected-severity exit-code
normalization. External hook-owner mode remains zero-access. Slack credentials/transport are absent
until M1-D; lifecycle repair/quarantine remain absent until M2.

## Native Worktree post-entry registration boundary

Native Cursor Worktree entry is fail-open and engine-side. The `sessionStart` shell hook only
dispatches the bounded payload to two independent authorities: the existing exact ensure-handoff
consumer and the native registrar. It does not rely on hook ordering, call a network, weaken the
guard, or block entry when parsing, Git, policy, locks, SQLite, or the engine fail.

Registration requires one explicit session id and one canonical non-symlink root. It strips ambient
`GIT_*` selectors and permits only closed local Git reads with optional locks and lazy fetch
disabled. Policy eligibility, exact linked registration, attached branch, HEAD, Git/common
directories, visible index, clean/unrelated-ignored state, and private lease/receipt state are
rechecked under the existing common-directory collision lock before mutation. Adoption rechecks an
expected complete identity inside that lock. Existing exact state attests; disk/SQLite asymmetry
repairs only one-to-one exact identity. Malformed, duplicate, mismatched, symlinked, dirty, detached,
primary, excluded, or live-drifting state is preserved. A clean same-branch HEAD advanced between
sessions may update only the exact same lease's persisted HEAD before attestation; HEAD movement
between the pre-lock and under-lock observations still refuses before adoption.

`awa-native-entry/v1` receipts are private `0700`/`0600`, bounded, no-follow, and atomically
published per root/session. They contain metadata only—no prompt, transcript, file content,
credential, arbitrary environment, or operator text. A receipt is successful only after final
adoption/attestation validation. Explicit failed/in-progress evidence is published before lifecycle
mutation, so a crash cannot leave silently managed state without entry evidence. Receipt replay is
rechecked against current root/session/branch/HEAD/Git/common-dir, lease, SQLite, and heartbeat
identity before it can be green.

Receipts, leases, events, attestation, heartbeat, and discovery remain non-authorizing observations.
The kernel cleanup path still independently requires active-root/session, Git registration,
content/ignored-state, recovery, operation, branch-safety, and explicit operator gates. Engine
failure therefore reduces registration recall and integrity health but never weakens kernel-first
refusal or changes linked-worktree shell allowance.

## Hard-no-touch pre-access boundary

`hard_no_touch_paths` is a host-owned lexical refusal primitive, not a repository detector.
Consumers must classify a candidate before opening a child directory, resolving a symlink, or
asking Git for identity. Exact-root and managed-namespace entries match their root and descendants
only on component boundaries; basename, substring, and glob matching are forbidden.

The trusted policy file and trusted `HOME` are the only readable inputs. Candidate normalization
uses strings only and performs no realpath/resolve/stat/lstat/open/read/list/scan/Git/subprocess
operation. This intentionally does not infer physical symlink aliases; a host lists each lexical
alias it needs protected. Relative or malformed candidates and unreadable/malformed configured
policy fail closed.

The canonical engine-off matcher lives in `kernel/lib/awa_policy.py`; the independent engine mirror
is parity-tested. Neither imports router/consumer code or reads router output. This boundary does
not alter include/exclude, read-only/reference, artifact, lifecycle, guard-command, or cleanup
semantics. Product bytes carry no concrete host values.

## Cluster D — Security ledger

Status legend: **Verified** (closed with evidence) / **Partially closed** (kernel part done, engine
part gated) / **NEEDS RE-VERIFICATION** (requires the unbuilt engine, a live probe, or a design
decision).

| ID | Assertion | Status | Evidence / close method |
|---|---|---|---|
| S1 | Recovery bundles won't leak secrets/PII into a source-tracked location or the archive. | **Verified (kernel)** | Bundles live under `${XDG_STATE_HOME:-~/.local/state}/awa` (outside any repo; `.gitignore:40-75` also can't track them). `awa_bundle_ignored` (`dev-worktree.sh`) applies an S1 secret denylist (`.env`/`.pem`/`.key`/`id_rsa`/`credential`/`secret`/`token`/`.netrc`/`.npmrc`…) and **excludes** matches from the archive, recording them in the manifest `skipped_secrets` (override only with `AWA_BUNDLE_ALLOW_SECRETS=1`). UAT: seeded `.env`/`*.key` are refused-from-archive and manifested as skipped. |
| S2 | Symlink traversal on worktree/recovery paths cannot escape the intended root. | **Verified (kernel)** | `clean_worktree` rejects a symlinked `--path` outright and canonicalizes via `pwd -P` before any git op; `awa_bundle_ignored` computes each entry's `realpath` and drops any that escape the worktree root (`skipped_symlink_escape`). UATs: (a) symlinked worktree path is refused; (b) a symlinked ignored file pointing outside the worktree is not archived. |
| S3 | GitHub token scope split (read vs write) for push/PR. | **Verified (code + unit test + LIVE end-to-end apply-back)** | The Phase-9 remote adapter (`engine/remote.py`) implements the least-privilege split: `select_token` returns a READ-scoped token for `status`/`poll` and a WRITE-scoped token for `push`/`pr`, and **refuses** a write op that has no write token (never falls back to the read token). `apply_back_execute` is SHA-bound (refuses on HEAD/base drift since the reviewed preview), recovery-BEFORE-mutation (asserts the recovery patch exists before any push), and preview→confirm gated. **Unit:** `test_remote` (token split incl. missing-write refusal; preview-no-mutation; recovery-before-push ordering; SHA-drift refusal; honest no-pusher operator-step refusal). **LIVE (2026-07-04 — disposable private remote `KleinPerkins/awa-applyback-uat`, deleted after via `gh repo delete`):** driven end-to-end against a real GitHub remote with a scratch worktree (base `main`, one commit ahead on `feat`): **(A)** preview (`confirm=False`) → `mutated=False pushed=False`, recovery patch written, remote had NO `feat`; **(B)** a missing recovery patch → `RemoteError: recovery-before-mutation invariant violated`, no push; **(C)** a confirmed write with no write token → `RemoteError: S3 least-privilege: write op 'push' requires a WRITE-scoped token…` (identical refusal from the CLI `awa-engine apply-back --execute --confirm` with no `AWA_GITHUB_WRITE_TOKEN`: `ok=False`); **(D)** HEAD moved after preview → `RemoteError: SHA drift … re-preview required before push`, no push; **(E)** a confirmed write with a real write token performed a genuine `git push` + `gh pr create` (opened PR #1 `feat→main`; SHA-bound: pushed ref == reviewed HEAD `c3c0e37`), while the status/poll op received the READ token — a **sentinel** read token was used, so the private-repo push could only have authenticated with the WRITE token, proving the split is real and not a fallback. Interacts with the §H2 quarantine-ref push (write path stays minimal). |
| S4 | Socket + file perms: state/config/recovery dirs `700`, files `600`, daemon lock/socket `600`. | **Verified (engine)** | The engine sets `umask 0o077` before opening SQLite and `chmod`s on create: `paths.ensure_dir`→`700` (state/recovery/detections/locks/run dirs), `paths.write_private`→`600` (lease.json, manifests, patches), `state.State`→`600` on `state.db`/`-wal`/`-shm`, and the `lock`/`daemon` pidfiles→`600`. `awa-engine doctor` asserts the modes (`s4-perms`) and refuses a synced/network state root (WAL placement, §H6). UATs: `test_state_lock.test_s4_perms`, `test_identity_paths` perms, `awa-engine doctor`. Single-instance uses an flock'd pidfile (the §H6-sanctioned alternative to a Unix socket). |
| S5 | Audit-log PII: no prompt/transcript/file-content in audit/command logs; secret/PII redaction. | **Verified (engine audit writer)** | The engine audit writer (`state.record_event`) pipes every `detail` through `redact.redact` before persisting; detection records are metadata-only (path+repo+timestamp, never file content). `engine/redact.py` redacts GitHub/AWS/Slack/Google tokens, bearer, private-key blocks, URL credentials, `--password=`/`TOKEN=` assignments. UAT: `test_state_lock.test_event_redaction` (seeded token redacted in the persisted event) + `test_redact` (the redaction pass directly). |
| S6 | Repo-controlled config is not executed during policy resolution / worktree setup. | **Verified (fixed in §H3)** | `run_worktree_setup` is **default-off**: repo-committed `.cursor/worktrees.json` is not executed unless the operator opts the repo in out-of-repo (`${XDG_CONFIG_HOME}/awa/setup-allow/<repokey>.<confighash>`), re-armed on config change, and never in advisory/exclude/foreign repos. UATs: default-off (setup not run, notice emitted) and opt-in (runs on stderr, JSON stdout pure). |
| S7 | Integrity status/alert bookkeeping is private, crash-safe, CAS-idempotent, and never overwrites a newer evaluation. | **Verified (engine)** | `test_integrity_store` and `test_integrity_alert` cover `0600`/`0700`, status-last crash cuts, child-dir fsync, immutable outbox/receipt artifacts, dispatch-lock concurrency, same-severity pending replay, failed-delivery retry, stale-transition audit/refusal, the explicit at-least-once external-notification crash boundary, exactly-once receipt advancement, no recursion, and bounded native failure. |
| S8 | The integrity console/installer leaks no raw evidence/path/credential, executes no remote content, and cannot activate the host job. | **Verified (engine + install sandbox)** | `test_integrity_console` covers closed projection revalidation, injection/path/credential dropping, deterministic bytes, CSP hash, one clock-only script, no form/action surface, self-staling RED, private mode, shipped assets, no plist, no host activation, and unchanged external hook-file bytes. |
| S9 | Native post-entry registration cannot seize ambiguous state, follow hostile links, forge ensure evidence, block Cursor entry, or weaken cleanup gates. | **Verified (engine + kernel compatibility)** | `test_native_entry` covers strict payload/root/session parsing, exact policy/Git/index/clean-state checks, under-lock identity drift, one-adoption concurrency, exact asymmetry repair, private distinct receipts, malformed/mismatched/duplicate/symlink preservation, fail-open lock/engine/exception paths, stale replay, and independent cleanup refusal. `test_entry_handshake`, `test_lifecycle_reconcile`, `test_kernel_off_matrix`, hook-owner/install tests, and the full guard suites preserve ensure, discovery, kernel-off, direct/external ownership, and guard behavior. |
| S10 | Hard-no-touch classification occurs before target access, matches only component roots, fails closed, and retains kernel/engine parity. | **Verified (kernel + engine)** | `test_hard_no_touch_policy` covers immutable typed schema, exact/managed root and descendant decisions, sibling nonmatch, trusted lexical normalization, malformed policy/candidate refusal, old-policy compatibility, semantic round trip, access spies over filesystem/Git/subprocess surfaces, policy-check rejection, kernel-off structure, parity, semantic isolation, and global contamination absence. |

**Gating.** Phase 2 (git/worktree lifecycle) gated on **S2, S6** — both **Verified**. Phase 3
(recovery manager) gated on **S1, S5** — both **Verified** (S1 kernel bundle denylist; S5 engine
audit-writer redaction). Phase 4 (watcher/daemon) touches **S4** — **Verified** (engine perms +
doctor). Phase 9 (apply-back / any remote touch) is gated on **S3** — the read/write token split,
SHA-binding, and recovery-before-mutation ordering are **Verified (code + unit test)** in the
Phase-9 remote adapter, and were additionally exercised **live end-to-end** (real `git push` +
`gh pr create`, PR opened) against a disposable private remote on 2026-07-04, deleted after — so
the adapter's live network path (token split, SHA-binding, recovery-before-mutation, preview→confirm)
is now proven, not just unit-tested. A production apply-back against a real target repo remains a
per-repo operator decision, but is no longer an unverified surface. Phase 6 (hook
adapters) is gated on the §H1 copy-honesty gate + the live hook-probe. **Desktop half — Verified
(probe, 2026-07-05)**: a live Cursor Desktop run of the committed hook-probe harness observed
`beforeShellExecution` firing as a project hook with a `command`+`cwd`+`sandbox` payload (the
load-bearing kernel-gate fact), `beforeSubmitPrompt` carrying raw `prompt`+`attachments` (L3), and
`beforeMCPExecution`/`sessionStart`/`stop` with their payload shapes; `afterFileEdit` was
operator-observed to be **observation-only** (a returned `{"permission":"deny"}` was ignored — the
edit landed on disk), corroborating the X2 detect-only design (see `hook-probe/RESULTS-2026-07-05.md`
for the per-event evidence and honest residuals — `afterFileEdit`/`beforeReadFile` hook records were
not retained in the captured `events.jsonl`, so L4 rests on the live observation + on-disk mutation +
the L2 doc-snapshot; optional re-drive: `live-verify/desktop-hook-redrive-runbook.md`). **Engine
build (reconciled 2026-07-05):** recovery manager, daemon/watcher, MCP server, and degraded-mode
guard are **built** in this repo (`engine/recovery.py`, `daemon.py`, `mcp_server.py`, `guard.py`)
with the full engine test suite (`engine/tests/`) passing under `make verify`. Copy-honesty `recovery-manager` capability is green when
`engine.tests.test_recovery` passes (see host `operator-copy.json`). **Live verification ledger
(operator-driven, 2026-07-05):**

| Row | Status | Evidence |
|-----|--------|----------|
| L9/L10 cloud project hooks | **Verified** | `hook-probe/RESULTS-CLOUD-2026-07-05.md` |
| Live AWA-MCP (`awa_*` + `beforeMCPExecution`) | **Verified** | `hook-probe/RESULTS-MCP-2026-07-05.md` |
| R-A `move_agent_to_root` | **Verified (A+B+C)** | `live-verify/RESULTS-R-A-2026-07-05.md` |
| E2E UAT mode + MCP write + apply-back (2026-07-06) | **Partially closed (headless GREEN; live UX pending operator)** — **superseded by 2026-07-07** | `live-verify/RESULTS-e2e-uat-20260706.md` — headless: mode guard ask/off, MCP mode tools + broad-off reject, apply-back PR on disposable remote; **operator pending:** live ask prompt, `beforeMCPExecution` on `awa_mode_set`, cloud re-probe post-hardening, dashboard canvas. **Superseded by 2026-07-07: ASK_ON removed (two-state on/off, enforced `deny`; dashboard no longer emits `ask_on`) — see `live-verify/RESULTS-e2e-uat-20260707.md`** |

**E2E UAT (2026-07-06, superseded):** after per-repo mode + round-2 hardening (`a965adf`), headless
verification confirmed `awa_mode_*` MCP tools resolved against host `modes_file`, broad-off `.` was
rejected with MCP `isError: true`, and apply-back opened PR #1 on disposable
`KleinPerkins/awa-uat-eligible-20260706T110803`. That session exercised the **pre-refactor** three-state
model (ASK_ON/OFF) where guard `ask` and dashboard `ask_on` were live surfaces. Live Desktop/cloud UX
rows required operator sign-off via `live-verify/OPERATOR-UAT-SESSION.md`. **Superseded 2026-07-07:**
ASK_ON was removed — the runtime is now two-state on/off with an enforced hook `deny` on included-primary
mutations, and the dashboard no longer emits `ask_on`. See `live-verify/RESULTS-e2e-uat-20260707.md`.

**L9/L10 (Verified, cloud probe 2026-07-05):** live Cursor **Cloud** agent on committed project
hooks in `KleinPerkins/awa-cloud-hook-uat` recorded 6 hook events: 3× `beforeShellExecution`
(`command`+`sandbox`), 1× `afterFileEdit` (edit to `sample.txt` landed), 2× `beforeReadFile`.
Desktop-only events (`sessionStart`, `beforeSubmitPrompt`, `beforeMCPExecution`, `stop`) were
**absent**. Shell was **not** blocked (cloud VM not bricked). Evidence:
`hook-probe/RESULTS-CLOUD-2026-07-05.md`. Pairs with Desktop probe
`hook-probe/RESULTS-2026-07-05.md` — together they close the §H5 hook-probe gate for L3/L4/L9/L10
and the cloud kernel-gate row.

**Live AWA-MCP (Verified, Desktop 2026-07-05):** in `~/awa-mcp-uat`, live agent called `awa_status`
and `awa_guard_shell` via the `awa` MCP server; hook log recorded 2× `beforeMCPExecution` with
`mcp_server_name: awa` and `tool_name` ∈ `{awa_status, awa_guard_shell}`. Evidence:
`hook-probe/RESULTS-MCP-2026-07-05.md`.

**R-A (Verified, Desktop 2026-07-05 — Obs. A + B + C):** `move_agent_to_root` with
`rootPath=~/dev/personal/awa-move-uat.wt` **never relocated** the agent across all three
conditions; `pwd` stayed on the primary checkout. **(A)** `origin` unreachable → fetch failed
(repository not found). **(B)** repo exists, worktree branch on `origin`, `main` absent on
`origin` → `couldn't find remote ref refs/heads/main`. **(C)** both refs on `origin` @ `d5ea248` →
`git checkout main` failed: `'main' is already used by worktree` at primary (git one-branch-per-
worktree rule; move tries to checkout `main` in `.wt`, not the worktree branch). **Conclusion:**
Cursor move migration fetches/checks out **`main`**, not `cursor/worktree/…`; incompatible with AWA
`ensure` layout. Native-window adopt remains the sole default (v2.1 §H2). Evidence:
`live-verify/RESULTS-R-A-2026-07-05.md`.

The §H1 copy-honesty gate: **all three capabilities are green** on the host (`operator-copy.json`):
`shell-gate-and-native-detection` (Desktop + cloud hook-probe), `recovery-manager`
(`engine.tests.test_recovery`), and `kernel-guarantee` (`engine.tests.test_guard` +
`kernel-guarantee-verify.sh` env matrix). Operator surfaces use the upgraded `strings[]` table;
copy-honesty-check enforces gated verbs at build time.

## Recovery retention lifecycle security (Phase 3)

The retention lifecycle deletes ordinary recovery artifacts on a schedule, so it is treated as a
destructive surface and inherits AWA's destructive-path discipline — while staying **off** the
kernel finish/removal path.

- **Strictly separate from finish authorization.** No retention logic runs on the exact-`Close`
  authorization or worktree-removal path. Retention runs only in the engine; worktree cleanup and
  kernel safety hold with the engine, hook, router, and MCP all absent (kernel-first).
- **Protected artifacts never auto-removed, and survive uninstall.** A manifest `protected:true`
  (whole-worktree archives + kernel Retain artifacts) is excluded from TTL and pressure pruning.
  `install.sh --uninstall` preserves `protected-retain/` AND every protected artifact inside
  `recovery/` (an unreadable manifest is preserved fail-safe), removing only ordinary state.
- **Containment + fail-safe deletion.** Every deletion target must be a non-symlink file resolving
  beneath the physical recovery root; symlink/path-escape targets are refused, including via a
  tampered resume journal. Deletion is crash-resumable (transient `recovery/.trash` journal written
  before any unlink; durable `awa_recovery_tombstone/v1` recorded; journal removed last) and
  idempotent on resume. A failed archive unlink is an honest ERROR that PRESERVES the artifact and
  writes no tombstone — destructive uncertainty never reports success. Bounded retry/backoff caps a
  transient failure at 3 attempts.
- **Zero network, local disk, owner-only perms.** No retention path performs any network call.
  recovery dir + `.trash` are `0700`; ordinary archives/manifests/journals `0600`; a protected
  artifact's archive + manifest `0400`. Legacy pairs are permission-repaired before evaluation (S4).
- **One lock ABI.** Maintenance serializes on the single global state-root lock using the same
  advisory-flock ABI + private-lockfile perms as the finish/clean/Retain per-common-dir lock; an
  opportunistic trigger acquires non-blocking and skips rather than racing a concurrent pass.
- **Never fails silently.** Failed maintenance, protected-storage growth, and watermark overage
  surface in the dashboard (`environment.recovery`) and a bounded sessionStart context warning.

## Shell-gate interception scope (adversarial UATs)

The `beforeShellExecution` gate (`worktree-guard.sh`) is AWA's pre-mutation gate — the only hook whose
decision Cursor can enforce *before* a command runs (`afterFileEdit` is observation-only, §H1/L4), and
Cursor enforces only `deny`, not `ask` (see the L4 platform limitation above). Its mutating-command
classifier is adversary-aware and intercepts the review-flagged bypasses — each has a UAT asserting the
gate returns an enforced `deny` on an included primary checkout:

- `git -C <path> commit` / `git -c k=v commit` — global options are skipped to find the real
  subcommand (not just a literal `git commit`).
- `sed -i` / `perl -i` in-place edits.
- `>` / `>>` file redirection (to a real path, not `/dev/null` or an fd-dup like `2>&1`).
- in-place mutators (`rm`/`mv`/`cp`/`tee`/`truncate`/`dd`/`chmod`/…) and package installs.
- interpreter one-liners (`bash -c "git commit"`, `python3 -c`, `perl -e`) and privilege wrappers
  (`builtin`, `exec`, `doas`, `run0`, `setsid`, `script -c`) — the script body is recursively
  classified.

**Honest residual (documented, not hidden).** A shell gate is a **backstop, not a sandbox**. A
determined command can always encode a write the classifier does not model (e.g.
`python -c 'open("f","w").write(...)'`, a base64-decoded script, an interpreter one-liner). AWA does
**not** claim to intercept every possible write path. Cross-cwd `git -C <primary> commit` from a
linked worktree is another documented blind spot (the gate classifies the payload cwd, not a `-C`
target). Two compensations make this acceptable: (1) the
gate only needs to fire on the **included primary** checkout, where the operator should be in a Safe
Workspace anyway (the classifier is intentionally conservative / over-asks there); (2) native file
edits to a primary are independently **detected** via the `afterFileEdit` metadata receipt
(observation-only, cannot pre-block — see §H1). Prevention is best-effort on shell; detection is the
guaranteed floor.

**Fixed regression (found live, 2026-07-06 — `workspace_roots` payload-shape gap).** Live operator
UAT on a fresh Cursor Desktop chat rooted directly at an eligible fixture repo found the gate
returning `allow` (not `ask`) for a plain `git commit`, with **no ask prompt shown**. Root cause:
Cursor's real `beforeShellExecution` payload sends the target directory as `workspace_roots`
(plural, snake_case, a JSON array) whenever the caller relies on the chat's default root instead of
an explicit `cwd` override — the common case for exactly this scenario (a chat opened directly in
the target checkout, no `cd`/override on the command). The parser's fallback chain only checked
`cwd`, `workspaceRoot` (singular camelCase), `workspace_path`, `root`, `projectRoot` — never
`workspace_roots` — so on an empty `cwd` it fell through every key to `os.getcwd()`: the **hook
script's own** execution directory (e.g. `~/.cursor`), never the target repo. That silently
misclassified the target as outside any governed root, defeating the ask on precisely the case AWA
exists to catch. Confirmed via Cursor's own hook debug log (`cursor.hooks.*.log`): both the host
delegator and kernel copy of `worktree-guard.sh` independently returned `{"permission":"allow"}` for
the identical real payload. **Fix:** `workspace-guard.sh` and `worktree-session.sh` now also check
`workspace_roots[0]` (and `tool_input.workspace_roots[0]`) before falling back to `os.getcwd()`,
strictly after all existing explicit keys (no precedence regression). **Evidence:**
`engine/tests/test_guard_hook_wrappers.py::test_empty_cwd_falls_back_to_workspace_roots` (+ 2 more)
drive the real bash hook end-to-end with the exact real-world payload shape; confirmed red (`allow`)
against the pre-fix script, green (`ask`) against the fix. **Why prior UATs missed it:** every
existing hook-payload fixture in this repo (`test_guard_hook_wrappers.py`'s pre-fix `_guard()`
helper, `test_mcp.py`, `kernel/checks/awa-contract-freeze.sh`, and the host's
`_ops/checks/worktree-verify.sh`) always synthesized an explicit `cwd`, never the real empty-cwd +
`workspace_roots` shape — a systemic fixture-realism gap, not just a code bug. Those fixtures still
correctly prove the classifier itself; they just never exercised workspace *resolution* against a
real payload.

## Finish-session gate residual — pid-less session collapse (`DEV_SESSION_ID` unset)

The root-bound finish path (`awa_finish.finish_session_gate`) is a **finish-only** gate, distinct
from `disposition()`: it may **waive only the confirming session's own** pid-less, TTL-fresh
heartbeat (when that session's recorded branch + `git_common_dir` match the finish target) and
otherwise **blocks** (fail-safe). Session identity keys off
`session_key = 's-'+sha256(session_id)[:20]` when a `session_id` is present, else a single stable
**`unattributed`** bucket (so many pid-less hookless callers do not each inflate membership).

**Residual (documented, not hidden).** When **no per-session id is set** — `DEV_SESSION_ID` unset
*and* the caller is a pid-less, hookless invoker so no `session_id` is derived — every such caller
collapses into the one shared `unattributed` bucket. Two **concurrent pid-less** sessions in the
**same** worktree are therefore indistinguishable to the gate: the confirming session's waiver of
"its own" pid-less, TTL-fresh heartbeat can waive what is in fact a *second* pid-less session's
heartbeat, so the gate may **waive rather than block**. This sits **inside the explicitly
unsupported one-writer-per-worktree boundary** (two writers sharing a single working tree is
already unsupported — see the concurrency model in the operating docs); it is not a new exposure
outside that boundary. The content-addressed challenge target-binding + fingerprint gates still
independently protect against an unrelated or drifted worktree.

**Scope bound — specifically two PID-LESS sessions.** A **live-pid** session on the same boot
**still blocks** the finish regardless of session identity: `finish_session_gate` blocks on ANY
live pid (including the confirming session's own). A real running agent process in the worktree is
never waived. The residual is narrowly the case of *two or more concurrent pid-less* sessions
colliding in the `unattributed` bucket.

**Mitigation.** Propagate a real per-session id so each session lands in its own `s-<hash>` bucket
instead of the shared `unattributed` one. The Phase 2 conversational surface does this
automatically; an operator/harness can set **`DEV_SESSION_ID` per agent** to get the same
separation today. With distinct session ids the gate correctly blocks a second session's fresh
heartbeat. (Contract cross-ref: `active_root.finish_session_waiver` + `finish_session_residual`.)

## Conversational finish boundary

The Phase-2 recognizer, operator loop, installed skill, prompt hook, and dialogue dispatcher are
recall/UX components, not removal authority. A false-positive recognizer can only show the fixed
warning. Removal still requires the Phase-1 kernel, under the shared lock, to consume a live
challenge after exact bytes `Close` and either a byte-identical full final fingerprint or a
byte-identical path-granularity structural fingerprint. The structural alternative preserves the
ordered displayed deletion scopes, each row-root type/mode/link target, every directory/symlink
descendant, structure outside displayed directory scopes, Git path/mode/stage structure, operation
state, target/incarnation, and session membership. It treats regular files below an already
displayed directory as opaque contents of that authorized scope and omits their
presence/name/mode/bytes plus ordinary index blob ids. Commit, Retain, Mixed, and Cancel are
case-insensitive non-destructive dialogue choices; this relaxation never applies to Close. Trusted
booleans, “yes”, approval UI, router/model assertions, attachments, Close case/trim variants, and
extra words cannot substitute.

The `beforeSubmitPrompt` hook is globally fail-open (`failClosed:false`) to avoid bricking all
workspaces. Hook challenges are explicitly inactive until `dispatch --current` consumes one valid,
attachment-free, root/session/conversation/generation/nonce-bound choice envelope. Invalid Close
casing is consumed only as a non-activating correction and leaves the dialogue/challenge live. The hook has an
internal deadline below Cursor's platform timeout; interruption after any partial write leaves
unconfirmable forensic state. Every cleanup/delete is nonce+generation CAS, so stale cleanup cannot
delete newer state. If the hook is absent, crashes, times out, or blocking is ignored, the unchanged
direct Phase-1 preview→literal Close flow remains available and kernel-authoritative.
The consumer mirrors guard context parsing across top-level and nested `tool_input` sources:
empty and explicit false/0/no/off Cloud/background values remain Desktop-negative, while every
other non-empty broker/background handle is unsupported and mints no challenge. The shell guard,
engine mirror, and consumer apply that same rule to both fields and their environment forms,
including opaque strings/objects rather than only boolean truth.

An activated hook Close also carries its expected nonce/generation into the kernel. Exact binding is
checked before an exclusive-created `close_claimed` terminal record makes that generation inert;
the claim occurs before shared-lock acquisition, so contention and every later refusal/fault consume
the attempt without weakening the one-lock removal ABI. Cancel similarly writes `cancelled` before
bounded projection cleanup. Terminal records—not unlink success—are authority: stale dialogue,
index, envelope, or challenge files cannot be resolved, and cleanup failures surface explicitly.
Finish-only session validation exact-checks every member's keyset, identity, pid, target, boot, and
timestamps; malformed evidence blocks finish while ordinary disposition/clean semantics remain
unchanged. Heartbeat's existing-record reads/merges/writes and finish membership snapshots use the
same common-dir lock. Malformed existing bytes are never normalized away: heartbeat refuses
without rewriting, preview creates no challenge/dialogue, and the linked-root/common-dir/branch
identity is rechecked inside the lock before a valid merge. Structurally valid prior-boot
current-session/heartbeat projections are replaceable or prunable only after that live recheck;
malformed mixed-boot evidence remains untouched. Dual timestamp writers sample once, and migration
accepts only the known one-second legacy skew under the lock.

The private full finish fingerprint covers every filesystem object, not only Git-visible rows: encoded
raw relative path, object type, permission bits, size, regular-file SHA-256, symlink target, exact
Git status/index evidence, and every sorted descendant hidden behind one grouped ignored-directory
row. Regular files use no-follow open plus lstat/fstat/re-lstat identity checks; directories are
likewise opened and scanned by no-follow descriptors. The companion structural fingerprint is
derived from the same twice-stable capture. It exact-binds displayed scope order/path/root
type/mode/link target, every directory/symlink descendant, structure outside displayed directory
scopes, Git path/mode/stage structure, operation state, target identity, and membership. Regular
files below a displayed directory are deliberately omitted because the warning names the whole
directory as one deletion scope. Any capture drift, displayed-row insertion/removal/reorder,
non-content structural drift, read error, mount boundary, escape, special file, or nested repository
at any depth refuses. Private paths, link targets, content, and hashes never enter hook/operator
diagnostics.
The challenge also binds a non-empty install id and exact root/Git-admin physical incarnation.
Execution rechecks all three under the shared lock; a reused path/branch/HEAD cannot alias the
previewed physical worktree.

This row-content tolerance is phase-specific. Retain may proceed only when the structural proof is
unchanged and every explicitly selected row's full descendant/content proof still matches;
selected-row changes refuse. Commit and Mixed retain their exact live-inventory rules. Retain
completion cannot authorize removal: it latches a mandatory fresh full preview, and a later
independently exact `Close` is still required. At Close, regular-file
creation/removal/rename/mode changes/rewrites below an already displayed directory do not expand the
path-granularity deletion authority; any new/reordered displayed row,
scope/root-type/root-mode/root-link change, directory/symlink descendant change, structure outside
a displayed directory, or Git
structure change does and therefore refuses. A legacy challenge without a structural proof remains
strict full-fingerprint-only. The removal journal separately records the final execution
fingerprint so a failed remove can clear `prepared` only against the bytes actually checked
immediately before the attempt. This does not weaken active-root/session protection, one-use
generation binding, or literal-`Close`.

Git index visibility is checked before every finish status/tree inventory and before any challenge
is minted. The finish-only preflight refuses unchanged as well as modified assume-unchanged entries,
skip-worktree entries, materialized or sparse-index checkouts, fsmonitor-valid state/extensions, and
effective fsmonitor configuration. It also refuses malformed, ambiguous, unsupported split, or
unreadable evidence. All such outcomes collapse to `index_visibility_flags`; paths, object ids,
hashes, config values, hook stderr, and contents are never surfaced. The probe parses SHA-1 and
SHA-256 index checksums/extensions directly, reads flags with NUL delimiters and
`core.fsmonitor=false`, and sets `GIT_OPTIONAL_LOCKS=0` plus `GIT_NO_LAZY_FETCH=1`. It therefore
cannot refresh/write the index, lazy-fetch, or invoke fsmonitor/clean/smudge hooks. A refusal mints
no challenge/dialogue and leaves the physical root in place. This gate is deliberately absent from
ordinary `clean --path`, which retains its separate active-root, commit-safety, dirty, and
bundle-or-refuse gates.

Ordinary clean treats adoption's `.awa/lease.json` as removable AWA bookkeeping only after a narrow
fail-closed proof: `.awa` is an owned private real directory containing exactly one owned private
regular file; the bounded JSON lease has a valid schema and identity hash; its path, branch, and Git
common directory match the live target; and Git tracks no `.awa` path. Validation and unlink use
no-follow descriptors, run again under the shared lifecycle lock, and unlink only `lease.json`.
Any malformed, linked, permission-drifted, identity-mismatched, additional, tracked, or concurrently
changed state preserves the worktree. Unrelated untracked content remains dirty; unrelated ignored
content remains bundle-or-refuse.

Dispatcher output is a separate fail-safe boundary. One typed builder handles every success,
refusal, error, uncertain result, cancellation, and correction after the one-use authorization
steps. It accepts only closed outcome/reason/branch values and fixed messages; child stdout/stderr,
exception and kernel text, local paths, object ids, hashes, prompt bytes, unvalidated branch reasons,
and extra child JSON are never copied. The clean shell's internal machine mode emits exactly one
closed JSON projection; malformed, oversized, extra-field, or exit-status-contradictory output is
uncertain, never heuristically trusted. A proven removal reports `workspace_removed:true`,
agent-stopping/chat-open truth, and a validated conservative branch result. A proven pre-removal
refusal reports false. Any exception or post-invocation ambiguity reports null and stops, so
sanitization cannot turn uncertain removal into a false preservation claim or alter authorization.
All finish-local Git processes discard every inherited `GIT_*` selector, config injection, object
store, namespace, and alternate-index variable before applying the fixed locale,
`GIT_OPTIONAL_LOCKS=0`, `GIT_NO_LAZY_FETCH=1`, and `GIT_TERMINAL_PROMPT=0` profile. Non-Git
`HOME`/XDG/PATH survive so repository/global configuration and ordinary filters retain their
documented semantics. Discovery is immediately checked against no-follow Git pointer/back-pointer,
common-dir, and real-index validation, then every mutable identity is repeated through explicit
Git-dir/worktree/index binding. Commit alone may add its contained validated temporary index.

An active Git operation is never inferred from a label alone. The kernel privately binds a
content-addressed, twice-identical no-follow scan of the complete supported operation admin tree,
logical/pseudo/original refs resolved through Git, exact raw index and stages, worktree
dependencies, and the locally reachable object closure. Public output receives only one fixed row
per logical operation group—never an oid, message, todo, patch, or admin path. Unknown/ambiguous
markers, links, special files, mounts, lockfiles, escapes, or read drift refuse preview. Detached
HEAD is accepted only for recognized operation state with one validated original local branch, and
that branch cannot be deleted.

Physical removal is a local durable transaction. A file-and-parent-fsynced 0600
`awa_finish_removal/v1` journal is `prepared` before Git removal, then reconciled through `removed`
and `finalized` under the same lock. Recovery requires both exact root existence and local Git
worktree registration; disagreement remains uncertain. Confirmed removal idempotently completes
conditional branch handling, durably stores that result before one operation-bound receipt, and
performs exact challenge/heartbeat/current-session cleanup. A superseding current-session record
is never deleted. The shell immediately reconciles a child that exits after real removal, and a
later invocation repairs power-loss state; a pre-removal interruption never reports removal. Git's
return code is never the removal oracle: every result is physically classified under the lock.
Absent plus unregistered finalizes removal even after a nonzero return; present plus registered can
clear `prepared` only after the original incarnations and complete operation fingerprint still
byte-match. Partial content deletion, unreadable proof, incarnation drift, or signal disagreement
keeps the journal/challenge/branch state and emits only bounded uncertainty with no removed receipt.
Prepared/current journals carry the same physical identities in their operation id. A same-path
replacement is therefore uncertain and retained, never cleared as a pre-removal interruption.
Legacy journals may finalize only when root-absent plus unregistered; legacy present state remains
uncertain.
Critical kernel state uses one stdlib durability primitive: complete writes, private atomic
replacement/exclusive creation, durable unlink/adoption, and one-component-at-a-time private
directory publication. Every fd is retried on `EINTR` and `fsync`ed; Darwin must additionally
complete `F_FULLFSYNC` for both files and directories or the operation fails. A visible name after a
failed parent sync is not trusted in-process—reconciliation explicitly re-adopts it. After Git
logically removes the worktree, the root-parent and Git-admin-parent namespaces must sync before any
branch action. Ref deletion uses explicit Git ref-fsync configuration and then syncs the concrete
loose-ref/reflog/packed-refs or reftable backend. Failure leaves branch action empty and the journal
retryable; no receipt/finalization or retained/deleted claim is fabricated.

The removal, authorization, preview, Cancel, Retain, and branch-disposition paths contain no `gh`,
fetch, push, or remote proof. Network is structurally limited to Commit/Mixed delivery before a
fresh preview. Delivery requires merge commits (squash/rebase-only repositories are unsupported)
and fails closed on ambiguous remotes, non-exact/missing merged PR head, default-branch
non-incorporation, unstable/transient empty checks, incomplete/failed/unknown checks, missing `gh`/auth/network,
timeouts, and malformed evidence. A failed delivery may leave a truthful local commit on the
retained branch; it never authorizes Close.

Protected Retain artifacts use collision-resistant ids, path containment, `0700` directories,
`0600` regular files/manifests, explicit row selection, explicit secret inclusion, typed
file/deletion/rename/conflict/staged/symlink metadata, and a disposable restore proof before success.
They carry `protected:true`, are outside the worktree, survive normal uninstall, and require the
exact artifact id for manual deletion. Artifact writes/deletes share the per-common-dir lock with
finish. Retained-row suppression recomputes the same canonical selected snapshot and requires exact
equality of status/index bytes, modes, hashes, links, absence, and all recursive directory
descendants; malformed/error/drift evidence keeps the source row visible.
Publication is crash-durable: complete write loops plus file/full sync, bottom-up directory sync,
an unpublished `restore_proven:false` restore proof, then a `restore_proven:true` manifest written
and synced while still hidden. A private pending marker binds artifact id to the exact final-manifest
digest; staging is renamed to final and the Retain root is synced while readers still reject it;
only atomic pending→committed marker rename latches trust. Any later root-sync/cleanup failure
returns success with bounded warning because readers can already validate the latch. Every
pre-latch fault remains pending or hidden/tombstoned; rollback attempts final→hidden plus root sync,
and failure remains untrusted. Readers, restore, list, and kernel suppression independently require
the committed marker and matching true-manifest digest for new artifacts. Markerless legacy v1
artifacts remain bounded-status listable/restorable/deletable without data loss but never suppress
source rows; owned pending/staging/publication-tombstone cleanup resumes only under its recorded
common-dir lock. SHA-1/SHA-256 source format is recorded (legacy v1 is inferred), and raw proof
blobs use `hash-object --no-filters`. Deletion renames final/staging to a parent-synced tombstone,
keeps its identifying manifest until payload removal finishes, moves that manifest to a synced
owner marker for the empty-directory boundary, and safely resumes after interruption.
Operation Retain is atomic with the exact raw index/conflict state, all required worktree
dependencies, recursive admin bytes/topology, logical refs, and a local pack sufficient after
source ref deletion or GC. Secret/ignored dependencies require explicit acknowledgement. Proof
imports into an isolated standalone repository of the same object format, verifies exact
bytes/modes/refs/stages/reachability and the operation digest, and runs only operation-specific
abort/reset on a separate copy—never continue, hooks, merge drivers, or rebase exec. Suppression
requires the committed publication latch and exact current operation digest; legacy file-only
artifacts remain readable without gaining operation authority.
Ordinary destructive clean uses that same lock ABI and refuses—`--force` included—when its helper,
lock path, open, or acquisition is unavailable; it never degrades to an unlocked remove.

**Residuals.** This is normal-path accidental-loss protection, not authentication against a same-user
process that can rewrite local state. Raw Terminal `git worktree remove`/`rm`, aliases/scripts that
evade shell classification, Cursor-managed external cleanup, and Cloud workspaces remain outside a
universal hook guarantee. Live Desktop verification of the current build's
`beforeSubmitPrompt` blocking and exact `user_message` remains release UAT; unit/install tests prove
the documented schema and hook-independent kernel refusal, not the UI behavior.

## §H3 threat model — repo-controlled setup execution (RCE/worm)

- **Assets.** The operator's machine, credentials, and every other repo they can reach.
- **Adversary.** Anyone who can land a commit in any repo AWA touches — a compromised dependency, a
  malicious PR branch a PM checks out, a poisoned template.
- **Vector.** `.cursor/worktrees.json` in the repo → `run_worktree_setup` → arbitrary commands
  (historically incl. `shell=True`), amplified across every PM once AWA is a shared capability
  (a **worm**: it executes on every teammate who runs `ensure`).
- **Mitigation (shipped).** Execution is **off by default**; opt-in is **out-of-repo**, per-repo, and
  **re-armed on config change** (the stored approval is keyed by a hash of the committed config, so a
  malicious edit cannot ride an old approval); refused outright in `advisory`/`exclude`/foreign-hook
  repos; argv-only unless the operator opted into a specific `allowShell` entry; bounded timeout.
- **Residual risk.** An operator who opts a repo in and later pulls a malicious setup edit is
  re-prompted (the hash changes) — mitigated, not eliminated. Documented here as required before
  Phase 6.
