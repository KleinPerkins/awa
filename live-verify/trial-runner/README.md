# AWA Root-Bound Worktree Finish — comprehensive UAT trial runner

Two-layer trial runner that exercises **every** state transition built across Phases 1–3 of the
Root-Bound Worktree Finish feature. The only live UAT to date was a **single** transition
(`I'm done` → warning+block → `Cancel`, [`RESULTS-finish-phase2-uat-20260712.md`](../RESULTS-finish-phase2-uat-20260712.md)).
This runner closes the gap for every other transition.

- **Layer A — headless comprehensive transition harness** (this directory): agent-invoked,
  deterministic, self-cleaning. Provisions a fully disposable sandbox per transition, drives the
  transition end-to-end through the **production** kernel / consumer / engine surfaces, and asserts
  the outcome against the **same oracle the source test suites use**. Emits a machine- and
  human-readable results matrix.
- **Layer B — live operator runbook** ([`LIVE-OPERATOR-RUNBOOK.md`](LIVE-OPERATOR-RUNBOOK.md)):
  plain-English, agent-driven runbook for the surfaces that can **only** be proven live in Cursor
  Desktop (D1–D4). The runner records these as `live-deferred` (SKIP) rows so the matrix has **zero
  silent gaps** — each SKIP points at the exact operator step that proves it.

> Per `AGENTS.md`: **do not claim live Desktop proof from a headless test.** Layer A proves the
> deterministic behavior; the Cursor-UI rendering / live-operator-submission / live-agent-cessation
> surfaces are honestly deferred to Layer B and marked SKIP here.

---

## Run it (one line)

```bash
python3 live-verify/trial-runner/run_trial.py
```

Useful flags:

```bash
python3 live-verify/trial-runner/run_trial.py --list                 # list transitions, create nothing
python3 live-verify/trial-runner/run_trial.py --filter P3            # only Phase-3 retention rows
python3 live-verify/trial-runner/run_trial.py --json-out matrix.json # also emit the machine matrix
python3 live-verify/trial-runner/run_trial.py --quiet                # summary + failures only
```

Exit code is non-zero iff any headless transition FAILs/ERRORs **or** the real environment was
touched. Typical wall time is ~2–3 minutes (each transition provisions its own sandbox).

It is **not** wired into `make verify` on purpose: `make verify` is the fast per-commit gate (the
finish/retention *unit* suites already run there); this runner is the heavier end-to-end UAT
rehearsal you run before a live operator session or a release.

---

## What "disposable sandbox" means (isolation contract)

Every transition runs inside its own `tempfile.mkdtemp(prefix="awa-uat-p123.")` sandbox that:

- overrides `XDG_STATE_HOME`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `AWA_HOME`, and the kernel library
  paths (`AWA_ROOTS_LIB` / `AWA_FINISH_LIB` / `AWA_DURABILITY_LIB`) into the temp dir, so the harness
  **never reads or writes** the real state root `~/.local/state/awa`, the real runtime
  `~/.local/share/awa/current`, this worktree's git, or the operator's `~/.cursor/*`;
- builds throwaway git repos + linked worktrees (and a throwaway "default branch") inside the temp
  dir for the destructive transitions;
- stubs the GitHub side of Commit delivery **deterministically** — it never hits real GitHub and
  never mutates a real repo;
- is torn down on exit (success **or** failure).

A dedicated `GUARD-REAL-ENV-UNTOUCHED` row fingerprints the real state root's file-set + this
worktree's `git status`/HEAD **before and after** the whole run and asserts they are unchanged. If
anything leaked, that row FAILs and the run exits non-zero.

---

## Layout

| File | Role |
|------|------|
| `run_trial.py` | Orchestrator: discovers registered transitions, runs each in its own sandbox, appends the real-env guard, prints + emits the matrix. |
| `_trial_lib.py` | Harness core: the `Sandbox` context manager, the `Row` dataclass + `@transition` registry, the production-surface drivers (kernel / consumer / engine CLIs), and the real-env fingerprint/diff guard. |
| `_trial_phase1.py` | Phase 1 — kernel core: content-addressed one-use `Close` authorization, refusal matrix, TTL/drift/cross-root/cross-session backstops, branch disposition, zero-network removal, dirty discard, target-spoof refusals. |
| `_trial_phase2.py` | Phase 2 — conversational ergonomics: recognizer positives/negatives, immutable warning, hook block/fail-open/observability, choice canonicalization + rejects, dispatch (incl. `dispatch --current`), Cancel-vs-drift, Retain lifecycle, Commit delivery boundaries, post-action republish. |
| `_trial_phase3.py` | Phase 3 — recovery retention lifecycle: unified `awa_recovery_artifact/v1`, source-clock TTL, pressure ordering, protected-never-removed, containment, crash-resumable deletion, reconciliation, legacy normalization, permissions, throttle/lock, prune-on-creation, CLI/daemon/hook surfaces, uninstall survival, and the structural proof that **no retention logic sits on the finish path**. |
| `_trial_live.py` | The four inherently live-Desktop-only surfaces (D1–D4), registered as `live-deferred` SKIP rows that point at `LIVE-OPERATOR-RUNBOOK.md`. |
| `LIVE-OPERATOR-RUNBOOK.md` | Layer B — the plain-English live runbook (steps L1–L6) + how to provision/tear down a disposable UAT runtime and a throwaway target. |
| `provision-live-uat.sh` | Agent-run provisioner for the Layer-B disposable runtime + throwaway target(s). Never touches the real state root or the operator's `~/.cursor/hooks.json` (writes a disposable hooks file). |
| `teardown-live-uat.sh` | Agent-run teardown for everything `provision-live-uat.sh` created; verifies the real env is back to parity. |

---

## Expected-outcome oracle (not re-derived)

The harness reuses the **exact assertions already encoded in the source suites** as the
expected-outcome oracle — it does not re-invent finish/retention semantics. Each transition names
the suite/test it mirrors in its `oracle` field, so a matrix row is traceable to
`engine/tests/test_finish_*.py` / `engine/tests/test_retention.py`. Where a transition drives a
CLI, it drives the **production** entrypoint (`consumer/finish_current.py`,
`kernel/bin/dev-worktree.sh`, `kernel/lib/awa_finish.py`, `bin/awa-engine.sh`) so the matrix
reflects the shipped surface, not a reimplementation.
