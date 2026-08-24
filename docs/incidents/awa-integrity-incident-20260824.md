# Incident: AWA integrity — refuted guard-bug, real entry/lifecycle/surveillance gap (2026-08-24)

**Status:** DRAFT — 2026-08-24 (open; corrective milestones M1–M2 tracked in the ADR/plan below)
**Owning repo:** `awa`
**Owner:** KleinPerkins (Laurence Duggan)
**Date of incident:** 2026-08-24 (discovered), root causes span 2026-07-09 → 2026-08-24
**Severity:** P2 — operationally degraded observability/lifecycle; **no data loss and no protection breach** (the guard held).

> **Governance.** This is a doc-warden incident record (`~/dev/_ops/doc-warden/POLICY.md` §2
> taxonomy + §10 rule 9; AWA uses the `docs/` convention → `docs/incidents/`). Its five sections
> are fixed in shape; content is mutable until the record is `closed`. Everything below was
> re-derived **live** on 2026-08-24 against the installed runtime and on-disk state; nothing here
> depends on the originating chat transcript for its authority. **No repository source, worktree,
> lease, hook, branch, git config, or AWA runtime state was mutated to produce this record.** The
> one prior, authorized, reversible recovery cleanup is recorded in *What We Changed* and was
> re-verified read-only here.

---

## What Happened

**The original headline — "the AWA shell guard has a bug that let an agent commit into a protected
primary" — is REFUTED.** The guard did its job. The evidence-corrected story:

- An agent working on `pr-automation-controller` needed to move into a Safe Workspace (a linked
  worktree) to commit. The **external** Cursor capability that relocates an agent's root —
  `cursor-app-control.move_agent_to_root`, **not part of AWA** — aborted/errored twice, so the
  agent stayed rooted at the **protected primary**.
- From that primary root the agent tried `cd <worktree> && git …`. AWA **correctly denied** it:
  the guard classifies against the Cursor **session root** (the hook payload's `cwd`); an
  in-command `cd` is just text in the command string and never changes that root. This is exactly
  the bypass the deny copy is written to reject.
- So the block the operator saw was **correct protection, not a defect.** The real gaps are (a) a
  **Safe-Workspace *entry* / recovery-UX** failure (an external mover broke and AWA had no loud,
  enforced in-product fallback the agent followed) and (b) a set of **lifecycle and surveillance
  invariants that nothing watches** — orphaned worktrees, unreconciled leases, dangling session
  records, and a legacy recovery-scan error that accumulated silently.

**Do not "fix" this by weakening the guard** — no lease-aware relaxation, no path-pattern
allowance, no `cd`-into-worktree carve-out. The correct fixes (owned by the ADR/plan, not this
record) are robust, loud Safe-Workspace *entry* and honest, runnerless *surveillance* of the
lifecycle invariants.

### Scope and method

Read-only live inspection: `git -C … status/rev-parse/branch` per worktree (**no `fetch`, no
mutation**), `ls`/`stat`/`shasum`/`gzip -t`/`tar tzf` on state files, the read-only AWA MCP
diagnostics (`awa_status`, `awa_guard_shell`), direct reads of installed pointers and repo source,
and a `python3` re-count of session records. Installed runtime:
`~/.local/share/awa/release-pointer.json` → `awa-release-pointer/v1`, `version 1.5.2`,
`commit a2b13f7e7feb47f53ebb63ee59b4c61eb1e38fc3`, `hook_owner_mode external`. Repo
`engine/__init__.py __version__ = "1.5.2"` and `pyproject.toml version = "1.5.2"` agree — this is
**release-identity agreement, not a zero-behavior-drift proof** (behavioral evidence is the live
guard probes C1–C3). Current host boot id `darwin-boot-1787357417` (`kern.boottime`).

### Per-claim verification table

Verdict key: **CONFIRMED** = independently reproduced live · **REFUTED** = disproven ·
**UNCLEAR** = not adjudicable read-only.

| # | Claim under test | How verified (command / key output / path) | Verdict |
|---|---|---|---|
| C1 | "The guard has a bug: it let / would let a commit reach a protected primary." | `awa_guard_shell{cwd=<AWA primary>, command="git commit -m x"}` → `permission=deny, classification=include`. Same for the AWA repo primary. | **REFUTED** |
| C2 | Guard **allows** commit/checkout/worktree/diff inside a linked Safe Workspace. | `awa_guard_shell{cwd=/…/worktrees/pr-automation-controller/pr-automation-controller-20260824062903, command="git commit -m x"}` → `permission=allow, reason="linked worktree (Safe Workspace)", classification=worktree`. Source `engine/guard.py:934-935`. | **CONFIRMED** |
| C3 | From the primary, `cd <worktree> && git commit` is **denied** (`cd` does not move the classification root). | `awa_guard_shell{cwd=/Users/laurence.duggan/dev/personal/pr-automation-controller, command="cd /…/pr-automation-controller-20260824062903 && git commit -m x"}` → `permission=deny, classification=include`. Deny copy explicitly rejects the `cd <worktree> && <cmd>` form. Payload `cwd` parsed at `kernel/hooks/worktree-guard.sh:80-91`; deny at `:1182-1187`. | **CONFIRMED** |
| C4 | The agent stayed on the primary because the **external** `move_agent_to_root` failed — that capability is outside AWA. | `kernel/bin/dev-worktree.sh:5,307-312` only *emits* a `cursor-app-control move_agent_to_root` instruction; execution is Cursor's. R-A live results (`live-verify/RESULTS-R-A-2026-07-05.md`) already show move does not relocate for the AWA `ensure` layout. | **CONFIRMED** |
| C5 | AWA already tells users to relaunch via the **Agents-Window Worktree dropdown**. | Deny/ask copy at `kernel/hooks/worktree-guard.sh:1165,1186,1195`; operator runbook `live-verify/OPERATOR-UAT-SESSION.md:48-49`. | **CONFIRMED** |
| C6 | Cursor hooks are present; `beforeShellExecution` guard has `failClosed:false`. | `~/.cursor/hooks.json` → `beforeShellExecution[0]={command:".../worktree-guard.sh", timeout:20, failClosed:false}`. Deliberate fail-open rationale `kernel/hooks/worktree-guard.sh:11-14`. | **CONFIRMED** |
| C7 | The MCP guard view and the engine classifier agree (**adapter parity**, not two independent implementations). | `awa_guard_shell` (MCP) is a thin adapter over `engine/guard.py::decide_shell`; the kernel `check_probe` shares the same classification corpus. Agreement is adapter/parity evidence; the *behavioral* evidence is the live cwd probes C1–C3. | **CONFIRMED** (parity) |
| C8 | Installed runtime **release identity** is v1.5.2 `a2b13f7e…` and matches source version fields. | `release-pointer.json` `version/commit` vs repo `engine/__init__.py:20` / `pyproject.toml:7`. **This proves release identity, not zero behavior drift** — drift is excluded only for the *probed* guard behavior (C1–C3). | **CONFIRMED** (release identity) |
| C9 | 64 worktree dirs under `~/.local/share/awa/worktrees`, all leaseless; 11 empty repo-group dirs. | Read-only walk (Notes → Appendix A): exactly 64 leaves, 11 empty groups. Engine holds only 2 leases and neither points at any of the 64 (`awa_status`). | **CONFIRMED** |
| C10 | Class tally 18 clean-with-cached-redundancy / 39 local-only / 2 dirty / 3 husk / 2 standalone. | Live fetch-free rule (`git branch -r --contains HEAD`): **16 / 41 / 2 / 3 / 2**. Dirty/husk/standalone match **exactly**; the redundant↔local-only boundary differs by 2 rows (fetch-free wobble, note below). **No row is removal-eligible from this walk alone.** | **CONFIRMED** (structure) |
| C11 | 2 `active` leases, both with dead pids and pre-current-boot boot ids. | `awa_status` → 2 leases; boot ids `1785929758`, `1786920702` ≠ current `1787357417`; `ps -p 1270`/`87050` both **DEAD**; both roots **ABSENT** on disk (live `ls`). **Per `engine/lease.py:10,49` PID is informational and durable leases survive process/boot — dead-pid + old-boot is NOT itself staleness or removal authorization.** | **CONFIRMED** (facts) |
| C12 | Session records: 5 point at existing worktrees, 12 dangling point at absent ones. | Scoped to the AWA-managed namespace `~/.local/share/awa/worktrees/*` (live `python3` recount): **5 existing / 12 absent**. Separately, **1 existing / 14 absent** point *outside* that namespace (see Appendix B). No "12+" ambiguity. | **CONFIRMED** |
| C13 | Cited pr-automation-controller worktree edits are **byte-identical** to merged PRs #339/#340. | Prior forensic pass computed cryptographic diff hashes — `journal.rs`: `bc1d9f9a…f8d967`; `github.rs`+`runtime.rs`: `4f142081…89778` — against merged **PRs #339/#340**; the parent independently confirmed both PRs merged with **no local-only commits**. Not re-computed in the later fetch-free re-walk (state re-verified: row #50 leaseless, HEAD `fed9a6e`, RC=6, dirty=3). | **CONFIRMED** (forensic cryptographic proof) |
| C14 | Recovery pre-state had one `needs_repair` legacy bare archive; archive intact; no `recover repair` verb. | `engine/cli.py` recover verbs = `bundle/patch/archive/restore-*/list/prune/status` (**no `repair`**, unknown verb → exit 2); `recovery.py:338-370` synthesizes a bare legacy entry only when the `*.manifest.json` sidecar is absent; a naive manifest would enrol it into TTL maintenance. Archive intact: size `18758`, sha256 `52231ca1…`, valid gzip/tar. | **CONFIRMED** |
| C15 | Recovery cleanup completed & reverified: legacy archive moved to `recovery/.trash/`, `recover prune --maintenance` → ok, post-state clean. | On-disk: `~/.local/state/awa/recovery/.trash/pr-automation-controller-20260714040423-untracked-20260714075000.tar.gz`, inode `339046901`, size `18758`, sha256 `52231ca10dc62d8e2efcd4a5b59ebc9c9eeb4ecf62791480601ac1d2f8714993`, `gzip -t` OK, `tar tzf` → `docs/plans/architecture-remediation-roadmap-v2.26.md`. **Caveat: `.trash` is the deletion-journal namespace, not a durable quarantine — see *What We Changed*.** | **CONFIRMED** |

> **Fetch-free reachability wobble (C10).** The redundant↔local-only boundary is time-sensitive:
> it depends on how fresh each repo's cached remote-tracking refs are. The forensic pass credited
> "HEAD reachable from a remote ref **or merged into `origin/main`**" (18/39); this record uses
> the stricter, fetch-free `git branch -r --contains HEAD` (16/41) because two rows whose commits
> are (or were) on `origin` are no longer contained in a *locally-cached* remote ref and I did
> **not** `fetch`. Both passes agree the clean total is 57 and that dirty=2 / husk=3 /
> standalone=2. The wobble is the point: **class `R` (below) is cached-redundancy evidence only —
> never removal authorization** — and every local-only row is ambiguous without an online check,
> which is exactly why lifecycle GC must preserve-on-ambiguity (plan M2).

## Impact

No user data was lost and no protection boundary was breached: the guard denied the mutating
command on the protected primary, exactly as designed. The impact is **degraded operational
integrity that nothing was watching**. Guard *safety* and Safe-Workspace *entry UX* are different
invariants and are scored separately.

| Invariant | State | Evidence |
|---|---|---|
| **Guard safety** — mutating command on an included primary denies; linked/leased/cloud allow | **HOLDS** | C1–C3, C7; `guard.py:918-967`, `worktree-guard.sh:1142-1204` |
| **Kernel/engine parity & kernel-first** (engine off the critical path) | **HOLDS** | kernel imports no engine; shared corpus; `worktree-guard.sh:7-9` |
| **Hooks present + fail-open** | **HOLDS** | C6; `hooks.json`, `worktree-guard.sh:11-14` |
| **MCP/engine classifier parity** | **HOLDS** | C7 (adapter parity) |
| **Installed-release identity matches source** (not a drift proof) | **HOLDS** | C8 |
| **Recovery health** (no legacy scan error; fresh) | **HOLDS (now)** | *What We Changed*; C14–C15 — clean only after the reversible cleanup, and `.trash` homing is a residual risk |
| **Safe-Workspace entry / root handshake** | **VIOLATED** | C4–C5; external mover failed, no enforced in-product fallback, agent looped on a denied `cd` bypass |
| **Bounded orphan/lease/session lifecycle** (preserve-on-ambiguity; hard-no-touch respected; leases reconciled; sessions bounded) | **VIOLATED** | Appendix A/B: 64 leaseless worktrees (41 local-only/ambiguous), 2 unreconciled active leases (roots absent on disk), 12 in-namespace dangling sessions (+14 absent outside), 3 husks |
| **Surveillance freshness** (a fresh, trustworthy integrity status exists) | **VIOLATED** | no status artifact exists; every finding required a manual pass |
| **Alert-delivery health** (a flip to non-green is delivered loudly) | **VIOLATED** | no alerting exists |

**Net: guard/parity/hook/identity HOLD; recovery is clean-but-improperly-homed; entry, lifecycle,
surveillance, and alerting are VIOLATED → overall AWA integrity is DEGRADED, not green.**

## Root Cause

A composition of one **correct** behavior and several **missing** ones. No single layer is
"buggy"; the failure is the seam between a broken external mover and the absence of a loud
in-product fallback and any surveillance.

- **Cursor hook layer — correct, fail-open by design.** `~/.cursor/hooks.json` registers
  `beforeShellExecution → …/worktree-guard.sh` with `failClosed:false`. The hook derives its
  classification root from the payload
  (`workspace = data.get("cwd") or … or _first_root(data.get("workspace_roots")) or os.getcwd()`,
  `kernel/hooks/worktree-guard.sh:80-91`) and parses the command string separately (`:61`). An
  in-command `cd` never changes `workspace`. Fail-open is deliberate (`:11-14`). **Not a defect.**
- **Kernel guard — correct deny; where prevention happens.** `check_probe`
  (`worktree-guard.sh:1142-1199`, invoked at `:1204`) returns an enforced `deny` (`:1182-1187`)
  for a confirmed mutating command on an `include` non-linked primary; the deny copy anticipates
  and rejects both `cd <worktree> && <cmd>` and the inline `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1`
  prefix, and names the Agents-Window recovery. **Not a defect.**
- **Engine mirror — correct, off the critical path.** `engine/guard.py::decide_shell` (`:918-967`)
  allows a linked worktree (`:934-935`) and a present adopted lease (`:936-938`), denies a mutating
  command on an `INCLUDE` primary (`:953-966`), with ADR-0001 target narrowing (`:869-915`). The
  kernel imports no engine code (kernel-first). **Not a defect.**
- **`~/dev` host shim — correct, but only *emits* an external instruction.**
  `kernel/bin/dev-worktree.sh` (`ensure`) prints a `cursor-app-control move_agent_to_root`
  instruction (`:5,307-312`) and documents the native Agents-Window path (`:42`); it cannot
  *execute* the move. When the external mover aborted, the shim had done its part but nothing in
  AWA re-drove entry or hard-blocked progress until entry succeeded. **Gap: entry/handshake is
  advisory, not enforced or self-healing.**
- **The external mover — the actual trigger, outside AWA.**
  `cursor-app-control.move_agent_to_root` aborted/errored twice. AWA cannot fix a Cursor tool
  (`live-verify/RESULTS-R-A-2026-07-05.md:99-111`).
- **Recovery subsystem — a real, latent defect (now cleaned, see caveat).** A legacy bare
  `*.tar.gz` with **no sidecar manifest** made `recover status` report `errors`/`needs_repair`
  (`recovery.py::list_artifacts:338-370`); there is **no `recover repair` verb**, and a naive
  manifest would enrol the archive into TTL maintenance and eventually delete it.
- **Surveillance — the systemic gap.** Every fact here was discoverable only by a hand-driven
  forensic pass. **Nothing watches these invariants**, so a DEGRADED state persists silently. This
  is the motivating gap for the follow-on ADR/plan.

## What We Changed

**No fix was implemented in this pass; this record is documentation-only.** The corrective design
lives in [ADR 0020](../adr/0020-awa-integrity-surveillance-and-lifecycle.md) and
[the v1 plan](../plans/awa-integrity-surveillance-and-lifecycle-v1.md). The only state change is a
prior, authorized, reversible recovery cleanup, re-verified read-only here.

### Completed recovery cleanup (prior authorized pass) + exact reversal

- **Pre-state:** `recover status` → `last_status="errors"`, exactly one `needs_repair` legacy bare
  archive, `artifact_count=0`, `tombstone_count=95`. The archive was **intact, not corrupt** (size
  `18758`, sha256 `52231ca10dc62d8e2efcd4a5b59ebc9c9eeb4ecf62791480601ac1d2f8714993`, valid
  gzip/tar, content `docs/plans/architecture-remediation-roadmap-v2.26.md`); the **missing sidecar
  manifest** — not corruption — caused the scan error.
- **Action (reversible):** atomic same-filesystem `mv` to
  `~/.local/state/awa/recovery/.trash/pr-automation-controller-20260714040423-untracked-20260714075000.tar.gz`,
  preserving **inode `339046901`** and hash/size; then `awa-engine recover prune --maintenance` →
  status `ok`, `deleted=[]`, `errors=[]`, `needs_repair=[]`.
- **Post-state (re-verified live):** recovery root holds only `.trash/`; the moved file's
  inode/size/sha256 and gzip/tar validity are unchanged; `recover status` → `last_status="ok"`,
  `needs_repair=[]`, `tombstone_count=95` (unchanged).
- **Exact reversal:** `mv ~/.local/state/awa/recovery/.trash/pr-automation-controller-20260714040423-untracked-20260714075000.tar.gz ~/.local/state/awa/recovery/`
  (then re-run maintenance only if you deliberately want the prior `errors` status back).
- **Blast radius:** only the recovery subsystem's own artifact tree; no worktree, lease, hook,
  branch, git config, repository, source, or docs changed.

> **Residual-risk caveat (source-checked).** `recovery/.trash` is **not a durable quarantine** — it
> is the recovery subsystem's **transient deletion-journal namespace**: `retention.py:87`
> (`_TRASH_DIRNAME=".trash"`) and the frozen contract (`contracts/awa-contract.v1.json:367,390`)
> describe `.trash` as holding crash-resumable `*.deletion.json` journals written *before* an
> unlink and removed after the durable tombstone is recorded. Reconcile only globs
> `*.deletion.json` (`retention.py:455`), so the moved `.tar.gz` is **currently inert/ignored** by
> both `list_artifacts` (which skips `.trash`, `recovery.py:353`) and reconcile — but it is
> **improperly homed** and depends on that glob never widening. It also currently sits at mode
> `0644` inside a `0700` tree. **M2 must migrate unknown legacy bytes into a dedicated private
> quarantine namespace structurally excluded from retention/deletion journals** (preserving
> bytes/name/mtime/hash + reversal metadata). `.trash` is a reversible holding spot, not the final
> architecture.

### Corrective actions (owned, time-bounded; tracked in the ADR/plan)

- [ ] **M1** — stand up the integrity evaluator + atomic status store + fast hooks +
  `com.kleinperkins.awa-integrity` sweep + native/opt-in-Slack alerts + static console (ADR 0020;
  plan M1-A…M1-D). *Owner: AWA implementer per PR.*
- [ ] **M2** — lifecycle reconciliation (lease/worktree/session), Safe-Workspace entry handshake,
  and the dedicated recovery quarantine namespace that migrates the `.trash` legacy artifact.
  *Owner: AWA implementer per PR.*
- [ ] **`~/dev` host wiring** — external hook rows/config + `local-jobs` registration/activation of
  the sweep, via a separate governed `~/dev` Draft PR (ADR 0020 §8). *Owner: host.*

### Active-root-preserved worktree (pr-automation-controller) — lifecycle plan

- **Path:** `~/.local/share/awa/worktrees/pr-automation-controller/pr-automation-controller-20260824062903`
  (Appendix A row #50). **No lease.** Branch `cursor/worktree/pr-automation-controller-20260824062903`,
  HEAD `fed9a6e` (cached remote redundancy RC=6). Tracked edits to `src/github.rs`, `src/journal.rs`,
  `src/runtime.rs` (+251/-27) are **byte-identical to merged PRs #339/#340** (C13, forensic
  cryptographic proof).
- **Removal eligibility NOW: INELIGIBLE.** The kernel active-root gate reports **`active heartbeat
  fresh (<43200s TTL)`** for this root (corroborated by a current-session record dated
  `2026-08-23T…`), so the session may still be live; **the operator chose PRESERVE.** Cached
  redundancy (RC/#339/#340) is *not* sufficient on its own — removal requires **all** canonical
  gates (see Notes). Never suggest a bypass/force over a fresh heartbeat.
- **Later capture/cleanup (only after the heartbeat expires / session is definitively closed):**
  capture a **restore-proven source patch + Git bundle**, **omit** the regenerable ~1.6 GB Rust
  `target/`, then remove through the **kernel-authorized** path (existing consequence / active-root
  / content gates). This is a plan-M2 lifecycle action, not part of this record.

## Notes

- **Residual risk / no false GREEN.** Recovery is clean but the `.trash` homing is a tracked
  residual risk (above). **Overall AWA integrity is DEGRADED** — entry, lifecycle, surveillance,
  and alerting remain violated and unmonitored; a regression here would be silent. Nothing in this
  record should be read as "AWA is healthy."
- **Removal-eligibility rule (canonical).** No worktree is "reap-eligible" from cached remote
  reachability alone. Class `R` below is **cached redundancy evidence only.** Removal eligibility
  requires **all** of: active-root disposition **non-active**; content/redundancy proof;
  topology/registration; no-touch policy clearance; explicit operator authorization; and
  restore-proven capture where required. **No autonomous deletion.**
- **Permanent hard no-touch.** Everything under `~/.local/share/awa/worktrees/chaos-scheduler/**`
  (Appendix A rows #13–#16) is documented only and must **never** be mutated or auto-reaped.
- **Originating evidence (recorded, not relied on for authority).** Primary incident chat session
  `e1559421-e3c6-4673-bb4e-a79b0a8aef92`, machine-local transcript
  `~/.cursor/projects/Users-laurence-duggan-dev-personal-pr-automation-controller/agent-transcripts/e1559421-e3c6-4673-bb4e-a79b0a8aef92/e1559421-e3c6-4673-bb4e-a79b0a8aef92.jsonl`
  (grep: `worktree guard|standalone repo|recover status|orphaned|/tmp/prac-ship|move_agent_to_root`).
  Operator-facing citation: [AWA guard blocked commits](e1559421-e3c6-4673-bb4e-a79b0a8aef92). The
  independent forensic worktree walk re-verified here lives at subagent
  `8ecc11a5-f381-453b-bb7a-a0e695a01cb8` under chat `c620cdbe-0d34-4ac9-928b-f92a1daa734e`.

### Appendix A — exhaustive worktree inventory (live, read-only)

Base directory `~/.local/share/awa/worktrees/`. Walked read-only on 2026-08-24 with
`git -C <path> rev-parse/branch/status` (no `fetch`). **Class:** `R` = clean & HEAD contained in
≥1 **cached** remote-tracking branch (**redundancy evidence only — not removal authorization**);
`A` = clean but local-only / no cached redundancy (ambiguous); `D` = dirty (uncommitted/untracked);
`H` = git-dangling husk (gitdir gone); `C` = standalone full clone (`.git` is a directory).
**Dirty** = `git status --porcelain --untracked-files=all` line count. **RC** = cached
remote-branch containment count. All 64 are **leaseless**.

| # | Full path (under base) | Branch | HEAD | Dirty | RC | Class |
|---|---|---|---|---:|---:|:---:|
| 1 | `ai-analytics-context/ai-analytics-context-20260722011338` | `ab-testing/card-context-2026-07` | `5d84a09` | 0 | 0 | A |
| 2 | `ai-analytics-context/ai-analytics-context-20260730121902` | `cursor/worktree/ai-baseline-202607301221` | `e4c905c` | 0 | 0 | A |
| 3 | `ai-analytics-context/ai-analytics-context-20260818075006` | `feat/w1-local-job-freshness-bridge` | `f256894` | 0 | 0 | A |
| 4 | `archive-repos/archive-repos-20260725212207` | `(detached) HEAD` | `222542f` | 0 | 2 | R |
| 5 | `awa-e04-hook-owner-plan-20260815/awa-e04-hook-owner-plan-20260815-20260815235913` | `cursor/worktree/awa-e04-hook-owner-plan-20260815-20260815235913` | `536f9cc` | 0 | 2 | R |
| 6 | `awa/awa-20260810090331` | `cursor/worktree/awa-20260810090331` | `9bffa83` | 0 | 1 | R |
| 7 | `awa/awa-20260810090645` | `cursor/worktree/awa-20260810090645` | `3f3c1b3` | 0 | 0 | A |
| 8 | `awa/awa-20260817070937` | `cursor/context-efficiency-e04-20260817` | `385e6a7` | 0 | 0 | A |
| 9 | `awa/awa-20260821153826` | `cursor/worktree/awa-20260821153826` | `fdbaeb2` | 0 | 1 | R |
| 10 | `awa/s1b-v070-bind` | `test/m5-s1-awa-pilot` | `9ee80b9` | 0 | 0 | A |
| 11 | `chaos-scheduler-mcp-resource-foundation/chaos-scheduler-mcp-resource-foundation-20260714022758` | `security/issue-292-diff-suppression-foundation` | `bf67328` | 0 | 2 | R |
| 12 | `chaos-scheduler-mcp-resource-foundation/chaos-scheduler-mcp-resource-foundation-20260729014232` | `chore/m5-strip-machine-memory-20260728` | `4af36d7` | 0 | 0 | A |
| 13 | `chaos-scheduler/chaos-scheduler-20260710112429` **(no-touch)** | `feat/d05-pr2e-cloud-nondraft` | `af45342` | 0 | 0 | A |
| 14 | `chaos-scheduler/chaos-scheduler-20260823170432` **(no-touch)** | `security/redact-mcp-tool-reads` | `3ea7cce` | 4 | 4 | D |
| 15 | `chaos-scheduler/chaos-scheduler-20260824055648` **(no-touch)** | `recovered/mcp-resource-foundation-workflow-authoring-20260713` | `af485c2` | 0 | 1 | R |
| 16 | `chaos-scheduler/track-tokens` **(no-touch)** | `feat/popup-mini-dashboard` | `9bea7b9` | 0 | 0 | A |
| 17 | `duggan-bach-source/bach-m3-v05-policy-pin` | `chore/m3-v05-policy-pin` | `72d2ac7` | 0 | 0 | A |
| 18 | `duggan-bach-source/m3-local-evidence` | `chore/m3-v05-local-evidence` | `d235c06` | 0 | 0 | A |
| 19 | `duggan-bach-source/m3-lock` | `chore/m3-v05-lock` | `df7ae40` | 0 | 0 | A |
| 20 | `duggan-bach-source/m3-recipe` | `chore/m3-v05-recipe` | `0f7449b` | 0 | 0 | A |
| 21 | `duggan-bach-source/m3-shadow-evidence` | `chore/m3-v05-shadow-evidence` | `a24dc4f` | 0 | 0 | A |
| 22 | `duggan-bach-source/s1b-v070-bind` | `chore/relock-pr-automation-v0.7.1` | `8924014` | 0 | 0 | A |
| 23 | `ecosystem-orchestrator/ecosystem-orchestrator-20260807063358` | `cursor/worktree/ecosystem-orchestrator-20260807063358` | `ac9ef6b` | 0 | 0 | A |
| 24 | `ecosystem-orchestrator/ecosystem-orchestrator-20260808023454` | `cursor/worktree/ecosystem-orchestrator-20260808023454` | `05adde1` | 0 | 0 | A |
| 25 | `ecosystem-orchestrator/ecosystem-orchestrator-20260808031413` | `cursor/worktree/ecosystem-orchestrator-20260808031413` | `dbb2aba` | 0 | 0 | A |
| 26 | `ecosystem-orchestrator/ecosystem-orchestrator-20260808034640` | `chore/approve-operator-voice-v017-digest` | `80554ea` | 0 | 0 | A |
| 27 | `ecosystem-orchestrator/ecosystem-orchestrator-20260815102058` | `cursor/worktree/ecosystem-orchestrator-20260815102058` | `44767cf` | 0 | 9 | R |
| 28 | `ecosystem-orchestrator/ecosystem-orchestrator-20260815105538` | `pr-automation/g4-r2-ecosystem-requiredness-proof` | `698fe47` | 0 | 1 | R |
| 29 | `ecosystem-orchestrator/ecosystem-orchestrator-20260823031428` | `cursor/worktree/ecosystem-orchestrator-20260823031428` | `7283a74` | 0 | 1 | R |
| 30 | `ecosystem-orchestrator/ecosystem-orchestrator-20260824023031` | `cursor/worktree/ecosystem-orchestrator-20260824023031` | `c830c4c` | 0 | 1 | R |
| 31 | `ecosystem-orchestrator/m3-local-evidence` | `test/m3-v05-local-evidence` | `786cd29` | 0 | 0 | A |
| 32 | `ecosystem-orchestrator/m3-recipe` | `chore/m3-v05-recipe` | `446eb50` | 0 | 0 | A |
| 33 | `ecosystem-orchestrator/orchestrator-m3-v05-policy-pin` | `chore/m3-v05-policy-pin` | `ede92cf` | 0 | 0 | A |
| 34 | `intent-router/m3-local-evidence` | `test/m3-v05-local-evidence` | `02b6be4` | 0 | 0 | A |
| 35 | `intent-router/m3-shadow-evidence` | `test/m3-v05-shadow-evidence` | `144fe57` | 0 | 1 | R |
| 36 | `ir/ir-20260709065108` | — | **DANGLING** | — | — | H |
| 37 | `kp-mcp/m3-local-evidence` | `chore/m3-v05-local-evidence` | `64ec927` | 0 | 0 | A |
| 38 | `kp-mcp/m3-lock` | `chore/m3-v05-lock` | `99c38df` | 0 | 0 | A |
| 39 | `kp-mcp/m3-recipe` | `chore/m3-v05-recipe` | `a280d9c` | 0 | 0 | A |
| 40 | `kp-mcp/m3-shadow-evidence` | `chore/m3-v05-shadow-evidence` | `e845eb0` | 0 | 0 | A |
| 41 | `kp-pr-bot-canary/kp-pr-bot-canary-20260815210234` | `pr-automation/g4-canary-requiredness-proof` | `cdd769d` | 0 | 1 | R |
| 42 | `local-jobs/local-jobs-20260727093013` | `cursor/worktree/local-jobs-20260727093013` | `f65bffc` | 0 | 0 | A |
| 43 | `local-jobs/local-jobs-20260815162203` | `pr-automation/g4-local-jobs-requiredness-proof` | `a5fae4e` | 0 | 1 | R |
| 44 | `local-jobs/local-jobs-main-reconcile` | `main` | `f2b0fbf` | 0 | 4 | R |
| 45 | `mcp/mcp-20260729014232` | `chore/m5-strip-machine-memory-20260728` | `b68ab09` | 0 | 0 | A |
| 46 | `mcp/mcp-20260815140052` | `pr-automation/g4-kp-mcp-requiredness-proof` | `8d6e844` | 0 | 1 | R |
| 47 | `mcp/mcp-m3-v05-policy-pin` | `chore/m3-v05-policy-pin` | `9f8462d` | 0 | 0 | A |
| 48 | `operator-voice/operator-voice-20260819074418` | `cursor/worktree/operator-voice-20260819074418` | `2c6bafd` | 0 | 1 | R |
| 49 | `pr-automation-controller-scratch/pr-automation-controller-scratch-20260726234439` | — | **DANGLING** | — | — | H |
| 50 | `pr-automation-controller/pr-automation-controller-20260824062903` **(cited; PRESERVE — fresh heartbeat, INELIGIBLE)** | `cursor/worktree/pr-automation-controller-20260824062903` | `fed9a6e` | 3 | 6 | D |
| 51 | `server-guard/server-guard-20260730122218` | — | **DANGLING** | — | — | H |
| 52 | `skills/skills-20260813005700` | `chore/awa-v1.5.1-bind` | `6b4eedb` | 0 | 0 | A |
| 53 | `skills/skills-20260814091450` | `fix/local-jobs-stable-head-comparison` | `d50c215` | 0 | 0 | A |
| 54 | `skills/skills-20260815120036` | `pr-automation/g4-skills-requiredness-proof` | `a59c801` | 0 | 0 | A |
| 55 | `skills/skills-20260817070934` | `feat/context-efficiency-e01-durable-skills-source` | `f9d37a0` | 0 | 0 | A |
| 56 | `skills/skills-20260817215912` | `feat/context-efficiency-e03-description-eligibility` | `4b0177f` | 0 | 0 | A |
| 57 | `skills/skills-20260817224610` | `feat/context-efficiency-e05-awa-v1-5-2-pin` | `ca5867d` | 0 | 0 | A |
| 58 | `skills/skills-20260818072309` | `cursor/worktree/skills-20260818072309` | `74f7a7d` | 0 | 0 | A |
| 59 | `skills/skills-20260819161315` | `fix/continual-learning-consolidate-e08` | `a0318bd` | 0 | 0 | A |
| 60 | `skills/skills-20260819225508` | `docs/agent-route-client-parity-plan` | `25e47f8` | 0 | 0 | A |
| 61 | `skills/skills-20260819234600` | `feat/agent-route-exposure-primary-ranking` | `8cdcde5` | 0 | 0 | A |
| 62 | `skills/skills-20260820215801-refresh-bridge` | `fix/local-jobs-canvas-refresh-bridge` | `ceeb566` | 0 | 0 | A |
| 63 | `skills/skills-s02-impl-20260820-clone` | `main` | `b39a705` | 0 | 2 | C |
| 64 | `skills/skills-s02-plan-20260820-clone` | `main` | `5b62418` | 0 | 1 | C |

**Live class tally:** R=16 · A=41 · D=2 · H=3 · C=2 = **64** (leaseless). Forensic pass counted
R=18 · A=39 (same 64) — the 2-row difference is the fetch-free wobble (C10 note). **No row is
removal-eligible from this walk alone; #50 is explicitly INELIGIBLE (fresh heartbeat).**

**11 empty repo-group directories** (present, hold no worktree; `.DS_Store`-only or empty):
`app-ux`, `awa-uat-20260714t215314`, `chaos-labs`, `chaos-session-system`, `cpp`, `dev`,
`kp-pr-bot-canary-phase-b`, `operator-voice-profile`, `orchestrator`, `pac-docs-djx73i`,
`sterling`.

Husk rows #36/#49/#51 are ambiguous and **preserved** (gitdir gone, no redundancy proof). Rows
#63/#64 are standalone full `.git` clones, not linked worktrees.

### Appendix B — leases and session-record inconsistencies (live)

**B.1 Active leases (`awa_status`) — 2 rows, both unreconciled.** Current host boot id
`darwin-boot-1787357417`.

| Lease id | Worktree path | Branch | Boot id | pid | Created / attested | Root on disk |
|---|---|---|---|---:|---|---|
| `awa1-c78f61eafab78d97ba0b14f1466ff7b25a2cb384d5f18081377e3d9c76d19c83` | `/private/tmp/awa-attest-verify/wt` | `branch-b` | `darwin-boot-1785929758` | `1270` (**DEAD**) | 2026-08-06 | **ABSENT** (live `ls`) |
| `awa1-b4ae1bb2d9075f5eef2af0b807051188d0607cb90f0b1e52b49cb8bbed84d6ac` | `/Users/laurence.duggan/.local/state/ai-analytics-context-curation/worktrees/4702054266d4e3d47e4b24d43421ee2335f76ecb-to-79c1503dbe52557023d8869d005f21e9813c4b9d` | `auto-curation/47020542-to-79c1503d` | `darwin-boot-1786920702` | `87050` (**DEAD**) | 2026-08-18 / 2026-08-19 | **ABSENT** (live `ls`) |

Both boot ids predate the current boot and both pids are dead, and **both roots are absent on disk
(live `ls` → "No such file or directory").** But per `engine/lease.py:10,49` **PID is
informational only and durable leases survive the creator process/boot** (they are mirrored into
SQLite precisely so orphans can be discovered without a live process). **Dead-pid + old-boot +
absent-root is therefore NOT itself staleness or removal authorization.** These are **unreconciled
active bookkeeping rows** whose lifecycle evidence needs canonical reconciliation — a durable row
should be retired only when root absent **and** unregistered **and** no live root/session **and**
no pending journal/recovery ambiguity (plan M2). Neither points at any of the 64 worktrees.
`detections: []`.

**B.2 Session records (`~/.local/state/awa/current-session/*.json`) — 32 total** (live `python3`
recount; each record keys on `root`):

- **AWA-managed namespace `~/.local/share/awa/worktrees/*`: 5 existing / 12 absent (dangling).**
  Existing (leaseless): `awa/awa-20260810090331`, `chaos-scheduler/chaos-scheduler-20260710112429`,
  `pr-automation-controller/pr-automation-controller-20260824062903`, `skills/skills-20260814091450`,
  `skills/skills-20260820215801-refresh-bridge`. Dangling: `awa/awa-20260820202056`,
  `chaos-scheduler/chaos-scheduler-20260713011821`, `cpp/cpp-20260805032559`,
  `ecosystem-orchestrator/ecosystem-orchestrator-20260812183303`,
  `operator-voice/operator-voice-20260807061655`,
  `pr-automation-controller/pr-automation-controller-20260714040423`, `skills/skills-20260715215741`,
  `skills/skills-20260801090530`, `skills/skills-20260802225921`, `skills/skills-20260809080435`,
  `skills/skills-20260814091655`, `sterling/sterling-20260716214116`.
- **Outside that namespace: 1 existing / 14 absent** (1 existing Cursor worktree
  `~/.cursor/worktrees/awa/p3g8`; 12 absent `~/.cursor/worktrees/*`; 1 absent
  `~/dev/affirm/src/card-platform-product-d03-impl`; 1 absent `/private/tmp/awa-livecheck.*/wt`).

The in-namespace 5/12 split matches the forensic figure exactly. The unbounded, unmonitored growth
of session records (32 and rising) is itself motivation for the lifecycle reconciliation in plan M2.
