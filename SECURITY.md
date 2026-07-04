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

## Cluster D — Security ledger

Status legend: **Verified** (closed with evidence) / **Partially closed** (kernel part done, engine
part gated) / **NEEDS RE-VERIFICATION** (requires the unbuilt engine, a live probe, or a design
decision).

| ID | Assertion | Status | Evidence / close method |
|---|---|---|---|
| S1 | Recovery bundles won't leak secrets/PII into a source-tracked location or the archive. | **Verified (kernel)** | Bundles live under `${XDG_STATE_HOME:-~/.local/state}/awa` (outside any repo; `.gitignore:40-75` also can't track them). `awa_bundle_ignored` (`dev-worktree.sh`) applies an S1 secret denylist (`.env`/`.pem`/`.key`/`id_rsa`/`credential`/`secret`/`token`/`.netrc`/`.npmrc`…) and **excludes** matches from the archive, recording them in the manifest `skipped_secrets` (override only with `AWA_BUNDLE_ALLOW_SECRETS=1`). UAT: seeded `.env`/`*.key` are refused-from-archive and manifested as skipped. |
| S2 | Symlink traversal on worktree/recovery paths cannot escape the intended root. | **Verified (kernel)** | `clean_worktree` rejects a symlinked `--path` outright and canonicalizes via `pwd -P` before any git op; `awa_bundle_ignored` computes each entry's `realpath` and drops any that escape the worktree root (`skipped_symlink_escape`). UATs: (a) symlinked worktree path is refused; (b) a symlinked ignored file pointing outside the worktree is not archived. |
| S3 | GitHub token scope split (read vs write) for push/PR. | **Verified (code + unit test); live push is an operator step** | The Phase-9 remote adapter (`engine/remote.py`) implements the least-privilege split: `select_token` returns a READ-scoped token for `status`/`poll` and a WRITE-scoped token for `push`/`pr`, and **refuses** a write op that has no write token (never falls back to the read token). `apply_back_execute` is SHA-bound (refuses on HEAD/base drift since the reviewed preview), recovery-BEFORE-mutation (asserts the recovery patch exists before any push), and preview→confirm gated. UAT: `test_remote` (token split incl. missing-write refusal; preview-no-mutation; recovery-before-push ordering; SHA-drift refusal; honest no-pusher operator-step refusal). **Live residual (honest):** the actual network push/PR (`default_pusher`/`default_pr_opener`) needs a real credential + remote and is an **operator/live step** — it is not exercised headless (the CLI `awa-engine apply-back --execute --confirm` refuses honestly without an `AWA_GITHUB_WRITE_TOKEN`). Interacts with the §H2 quarantine-ref push (write path stays minimal). |
| S4 | Socket + file perms: state/config/recovery dirs `700`, files `600`, daemon lock/socket `600`. | **Verified (engine)** | The engine sets `umask 0o077` before opening SQLite and `chmod`s on create: `paths.ensure_dir`→`700` (state/recovery/detections/locks/run dirs), `paths.write_private`→`600` (lease.json, manifests, patches), `state.State`→`600` on `state.db`/`-wal`/`-shm`, and the `lock`/`daemon` pidfiles→`600`. `awa-engine doctor` asserts the modes (`s4-perms`) and refuses a synced/network state root (WAL placement, §H6). UATs: `test_state_lock.test_s4_perms`, `test_identity_paths` perms, `awa-engine doctor`. Single-instance uses an flock'd pidfile (the §H6-sanctioned alternative to a Unix socket). |
| S5 | Audit-log PII: no prompt/transcript/file-content in audit/command logs; secret/PII redaction. | **Verified (engine audit writer)** | The engine audit writer (`state.record_event`) pipes every `detail` through `redact.redact` before persisting; detection records are metadata-only (path+repo+timestamp, never file content). `engine/redact.py` redacts GitHub/AWS/Slack/Google tokens, bearer, private-key blocks, URL credentials, `--password=`/`TOKEN=` assignments. UAT: `test_state_lock.test_event_redaction` (seeded token redacted in the persisted event) + `test_redact` (the redaction pass directly). |
| S6 | Repo-controlled config is not executed during policy resolution / worktree setup. | **Verified (fixed in §H3)** | `run_worktree_setup` is **default-off**: repo-committed `.cursor/worktrees.json` is not executed unless the operator opts the repo in out-of-repo (`${XDG_CONFIG_HOME}/awa/setup-allow/<repokey>.<confighash>`), re-armed on config change, and never in advisory/exclude/foreign repos. UATs: default-off (setup not run, notice emitted) and opt-in (runs on stderr, JSON stdout pure). |

**Gating.** Phase 2 (git/worktree lifecycle) gated on **S2, S6** — both **Verified**. Phase 3
(recovery manager) gated on **S1, S5** — both **Verified** (S1 kernel bundle denylist; S5 engine
audit-writer redaction). Phase 4 (watcher/daemon) touches **S4** — **Verified** (engine perms +
doctor). Phase 9 (apply-back / any remote touch) is gated on **S3** — the read/write token split,
SHA-binding, and recovery-before-mutation ordering are now **Verified (code + unit test)** in the
Phase-9 remote adapter; the only remaining piece is the **live** network push/PR, which is an
**operator/live step** (real credential + remote) and is refused honestly headless. Phase 6 (hook
adapters) stays gated on the §H1 copy-honesty gate + the live hook-probe (L3/L4/L9/L10), which
needs a real Desktop+cloud agent.

## Shell-gate interception scope (adversarial UATs)

The `beforeShellExecution` gate (`worktree-guard.sh`) is the **one** honored pre-mutation gate. Its
mutating-command classifier is adversary-aware and intercepts the review-flagged bypasses — each has
a UAT asserting the gate returns `ask` on an included primary checkout:

- `git -C <path> commit` / `git -c k=v commit` — global options are skipped to find the real
  subcommand (not just a literal `git commit`).
- `sed -i` / `perl -i` in-place edits.
- `>` / `>>` file redirection (to a real path, not `/dev/null` or an fd-dup like `2>&1`).
- in-place mutators (`rm`/`mv`/`cp`/`tee`/`truncate`/`dd`/`chmod`/…) and package installs.

**Honest residual (documented, not hidden).** A shell gate is a **backstop, not a sandbox**. A
determined command can always encode a write the classifier does not model (e.g.
`python -c 'open("f","w").write(...)'`, a base64-decoded script, an interpreter one-liner). AWA does
**not** claim to intercept every possible write path. Two compensations make this acceptable: (1) the
gate only needs to fire on the **included primary** checkout, where the operator should be in a Safe
Workspace anyway (the classifier is intentionally conservative / over-asks there); (2) native file
edits to a primary are independently **detected** via the `afterFileEdit` metadata receipt
(observation-only, cannot pre-block — see §H1). Prevention is best-effort on shell; detection is the
guaranteed floor.

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
