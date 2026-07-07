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

**Consequence for AWA (design decision).** AWA does **not** rely on `ask` for prevention. On the one
case where prevention must actually happen — a **confirmed mutating command on an INCLUDED PRIMARY
checkout** (mode ON) — the guard returns an **enforced `deny`**, not `ask`. `ask` is retained only as
an **honest no-op signal** on the genuine-uncertainty path (an included-looking checkout whose command
payload the hook could not parse): AWA emits `ask` there knowing Cursor will not block, so it never
*silently* downgrades an uncertain case to allow, but it also never pretends `ask` prevents anything.

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

**Recovery / override (operator path).** A `deny` on a primary checkout is recovered by the operator,
not by the agent retrying: relaunch the agent in a Safe Workspace via the Cursor Agents-Window
Worktree dropdown (AWA adopts the linked worktree and then allows mutation), or set
`DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1` in Cursor's environment/settings. Note an inline
`DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>` prefix does **not** work — the hook reads its own process
env, not the command's inline assignment — and `cd <worktree> && <cmd>` is still denied. As a last
resort an operator who deliberately wants a repo unprotected can set it `off`.

**Residual to close.** A live ask-then-deny probe on `beforeShellExecution` — recording, on both
Desktop and Cloud, that a returned `ask` lets the command run and a returned `deny` blocks it — is
tracked in `live-verify/RESULTS-e2e-uat-20260707.md` (Phase 1). The `ask`-is-non-blocking and
`afterFileEdit`-ignores-permission halves are already proven (2026-07-05 live observation + on-disk
mutation + the L2 doc snapshot); the deny-blocks-on-Desktop half is the open live confirmation.

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
with **187** passing tests (`make verify`). Copy-honesty `recovery-manager` capability is green when
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
