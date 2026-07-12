# AWA Root-Bound Worktree Finish — Phase 2 live Desktop UAT — 2026-07-12

**Feature under test:** Root-Bound Worktree Finish (hook-owned warning + kernel-authorized
closeout). This session verifies the **live Desktop** display+block and the **`Cancel`** dispatch
path end-to-end against the refreshed disposable UAT runtime.

**Source pin:** branch `cursor/worktree/awa-20260711033524` @ `e0f3ae4` (foreign-lock false-positive
fix; ancestors `1162aab` warning-readability, `4228702` Phase 1/2 + Cancel-fix safety commit).
**UAT runtime (disposable):** `~/.local/share/awa-phase2-uat/awa/current`, refreshed to source HEAD
`e0f3ae4`. Released runtime `~/.local/share/awa/current` left untouched.
**State root:** default `~/.local/state/awa` (finish challenge/dialogue/index/envelope +
metadata-only hook observations).

> Convention: topic-scoped `RESULTS-<topic>-<date>.md` (cf. `RESULTS-R-A-2026-07-05.md`). No
> screenshots committed — operator-observed UI is cited in prose; the machine-side evidence is the
> metadata-only hook observations and the dispatcher JSON, both reproduced below.

---

## Scope of change under test

- `beforeSubmitPrompt` hook renders the fixed **"WARNING: Finish workspace requested"** block for a
  finish-intent prompt on a matched included worktree, with the five options (`Commit`, `Retain`,
  `Mixed`, `Cancel`, `Close`) each on their own line, and returns `continue:false` /
  `decision:block_warning`.
- A subsequent canonical choice (here lowercase `cancel`) is captured into a one-use
  root/session/generation-bound **choice envelope** (`decision:allow_choice_envelope`,
  `reason:canonical_cancel`), `continue:true`.
- `finish_current.py dispatch --current` consumes the envelope. **`Cancel` is unconditional and
  case-insensitive** — it clears the pending dialogue and never mutates the repository.
- Every hook observation is **metadata-only** (payload key *names* + `output_sha256` + boolean/enum
  outcomes; never raw prompt values, paths, or git content).
- **Kernel-first / convenience-not-dependency:** the hook block is an ergonomic backstop. Removal is
  authorized only by an exact standalone attachment-free `Close` consumed by the kernel, never by the
  hook.

---

## Phase 2 — live Desktop UAT

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `I'm done` → hook renders **"WARNING: Finish workspace requested"**, 5 options each on own line, "Submission blocked by hook" | **PASS (operator screenshot)** | operator-observed Desktop modal on runtime `e0f3ae4` |
| 2 | Hook returns `continue:false` / `decision:block_warning`, matched root + identity, metadata-only | **PASS** | obs `hook-1783893370…-27b60287.json`: `decision=block_warning`, `continue=false`, `identity_outcome=matched`, `root_outcome=matched`, `root_candidate_count=1`, `attachments_present=false`, `reason=redacted`, `output_sha256` only |
| 3 | Operator dismisses modal without "Try again"; submits lowercase `cancel` | **PASS (operator action)** | — |
| 4 | `cancel` captured as choice envelope, `continue:true`, no false finish/choice positives on intermediate prompts | **PASS** | obs `hook-1783893568…-68de8363.json`: `decision=allow_choice_envelope`, `continue=true`, `reason=canonical_cancel`, `identity_outcome=matched`, `root_outcome=matched (1)`, `attachments_present=false`; two intervening prompts recorded `allow_unrecognized` (correctly not treated as finish/choice) |
| 5 | Dispatcher (exact sanctioned invocation) cancels with **no casing complaint** | **PASS** | `dispatch --current` → `{"ok": true, "state": "cancelled", "mutated_repo": false}` (rc=0); lowercase `cancel` accepted |
| 6 | Challenge, dialogue, current-index, choice-envelope cleared | **PASS** | `read_challenge → absent`; `read_dialogue live? False`; `finish-dialogue/`, `finish-current-index/`, `finish-choice-envelope/` = 0 files |
| 7 | Only residual is the inert **cancelled** generation tombstone (replay-safety, by design) | **PASS** | `finish/generation-9170f208…-1-…json`: `transition="cancelled"`, `generation_state_status=cancelled`, `conversation_id=deb9956d…`, `generation=1` — not a live challenge |
| 8 | Worktree / repository content unchanged | **PASS** | before/after `git rev-parse` = `e0f3ae4`, `git status --porcelain` = 0 both times; dispatcher `mutated_repo=false` |
| 9 | No raw prompt / path / content leakage in observations | **PASS** | observations carry payload key *names* (`payload_keys`, `prompt_keys_present=["prompt"]`) + `output_sha256` + enum/boolean outcomes only; no raw worktree path, no raw home path, no raw prompt value. (The literal `cancel` substring appears only inside the fixed reason enum `canonical_cancel`, not as an echoed prompt.) |

### Dispatcher output (reproduced)

```json
{
  "mutated_repo": false,
  "ok": true,
  "state": "cancelled"
}
```

---

## Honest caveats

- **Desktop hard-block enforcement is Cursor-build-dependent, and the design does not rely on it.**
  On this refreshed runtime (`e0f3ae4`) the operator's screenshot showed "Submission blocked by
  hook" and the hook returned `continue:false`. AWA treats the hook as a convenience backstop
  (kernel-first): the load-bearing safety gate is the kernel's one-use exact-`Close` authorization,
  which holds with the hook, engine, router, and MCP all absent. No claim is made that the hook
  guarantees the prompt never reaches the model on every Cursor build.
- **Two intervening `allow_unrecognized` prompts** were recorded between the block and the cancel.
  This is correct behavior (ordinary prompts are passed through and are NOT treated as finish-intent
  or as choices) — logged here for timeline completeness, not as a defect.
- Live proof covers **display + block + `Cancel`** only. `Close` / `Commit` / `Retain` / `Mixed`
  live-Desktop coverage is deferred to the Final Rollout gate; their headless/CLI behavior is covered
  by the source test suites.

---

## Verdict

| Layer | Status |
|-------|--------|
| Hook display (warning modal, options each on own line) | **PASS (operator screenshot, `e0f3ae4`)** |
| Hook block + metadata-only observation (`block_warning`, `continue:false`, matched root/identity) | **PASS** |
| `Cancel` capture + unconditional case-insensitive dispatch (`state:cancelled`, `mutated_repo:false`) | **PASS** |
| Pending-state clearing (challenge/dialogue/index/envelope) + inert cancelled tombstone | **PASS** |
| Worktree/repository unchanged; zero leakage | **PASS** |

**Phase 2 live UAT: display + hook-block + `Cancel` PROVEN on runtime `e0f3ae4`.** Remaining live
choices (`Close`/`Commit`/`Retain`/`Mixed`) are carried into the Final Rollout gate.
