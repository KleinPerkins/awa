# AWA Verification and Discovery Velocity — measured feedback without weakening proof

- **Version:** v1
- **Status:** DRAFT — 2026-08-29
- **Date:** 2026-08-29
- **Owning repository:** `KleinPerkins/awa` (`~/dev/capabilities/awa`)
- **Plan-type:** agentic-execution
- **Relates to:** draft [ADR 0021](../adr/0021-verification-and-discovery-velocity.md), ADR 0001
  (independent engine/kernel guard parity), ADR 0002 (AWA product vs. host ownership), ADR 0017
  (documentation governance boundary), and ADR 0020 (kernel-first integrity surveillance; ADR 0021
  narrowly supersedes only its guard-byte freeze for conditional M3-B, never its guard behavior).
- **Review provenance:** first draft built from repository and bounded live measurements at
  `0390779930455273b6203676ae01437c43f8845f`; one bounded standard-band swarm review
  (one probe, three reviewers: architecture, test evidence, concurrency; no verifier required)
  followed by one parent correction pass.

**Goal:** reduce AWA's routine verification wall time and uncertainty while preserving every
authoritative test, safety seam, isolation boundary, and release proof.

**Architecture:** one stdlib verification runner emits progress, timings, exact inventory, and a
non-authorizing clean-HEAD receipt. Named docs/focused/pre-PR/install/release lanes compose one
verification graph. After serial equivalence is proven, independent unittest modules may run in
separate processes; later bodies reduce boundary and fixture process amplification and split fast
dashboard inventory from deep display enrichment.

**Tech stack:** Python 3.9 stdlib, Bash 3.2, `unittest`, Git, isolated HOME/XDG fixtures, existing
contract-freeze/install/live-verify surfaces, and existing runnerless PR automation only.

> **For agentic workers:** REQUIRED SUB-SKILL — use `subagent-driven-development` or
> `executing-plans`. This plan is DRAFT. Do not execute Task M1-A.1 or any later task without an
> explicit operator GO. Work in order, one Draft PR body at a time; leave every Draft PR unarmed.
> Never call `gh pr merge --auto`, enable/disable auto-merge, or mark a PR ready without the
> operator's explicit GO.

---

## Global constraints

- **No safety reduction.** Kernel-first, guard behavior, engine/kernel parity, fail-safe uncertainty,
  finish stable-snapshot recapture, physical durability, and cleanup refusal stay unchanged.
- **Narrow guard supersession only.** M3-B may change guard bytes solely for ADR 0021 Decision 6's
  invocation-local probe collection after exact parity/state-drift proof. ADR 0020's no-relaxation,
  no-carve-out, and no-integrity-dependency decisions remain binding.
- **No shared mutable state.** Every test keeps independent HOME, XDG, Git refs/config/hooks/index/
  worktree/object state, locks, and fault boundaries.
- **No automatic skip from receipts.** `awa-test-receipt/v1` is local evidence only.
- **No cross-invocation cache.** Git/guard/finish/lifecycle/cleanup evidence is live per invocation.
  Dashboard enrichment is display-only.
- **No automatic cleanup/lifecycle action.** This project changes verification and read-only display
  discovery, not destructive authority.
- **No host coupling.** AWA does not import or invoke `~/dev`'s doc-warden or local-jobs. Host-owned
  checks remain separately invoked.
- **No new service or runner.** No GitHub-hosted/self-hosted Actions runner, paid CI, daemon, standing
  server, or `chaos-scheduler` change.
- **Compatibility.** Preserve Python 3.9 and Bash 3.2 on existing supported paths; add no runtime
  dependency. Keep `make verify`, `make test`, `make verify-install`, and `make trial` compatible.
- **Hermetic ordinary tests.** No real HOME, Cursor hooks, installed AWA runtime/state, governed
  worktree, credential, or network access.
- **Evidence before claims.** Every performance result records exact HEAD, clean/dirty state, test
  count/inventory digest, Python/Git versions, command/lane, pass/fail, machine/worker count, and
  load caveat. The 2026-08-25 loaded profile is ranking evidence, not a baseline or SLA.
- **Review cadence.** Complete one body → open a Draft PR → run Bugbot; add security review for M3
  production guard changes, M4 physical fixture/durability changes, or any later change that touches
  a safety boundary. Hold at the merge gate for the operator/reviewer App.
- **Accepted-doc immutability.** Never edit accepted ADRs/plans. Once this plan is accepted it is
  byte-identical forever; future changes use `-v2`.

## 1. Purpose and operator value

AWA currently discovers 1,045 tests in under one second but can spend many minutes executing them,
with little indication of what is active. The first milestone must deliver a usable loop—not a
profiling side project: a developer can run a bounded docs lane for prose, an explicit focused lane
while coding, or the complete existing pre-PR proof; each run shows progress and produces honest
evidence. Later milestones attack the dominant process and fixture costs only behind equivalence
gates.

The operator gets shorter feedback, fewer blind reruns, and an exact answer to “what passed against
which source?” AWA keeps one reproducible full proof and fails unknown/mixed change classification
to that broader lane.

## 2. Scope and non-goals

**In scope**

- serial measurement/progress, inventory manifests, and clean-HEAD evidence receipts;
- explicit docs, focused, pre-PR, install, and release lanes;
- removal of only the proven duplicate explicit Makefile freeze in M1, with any later
  single-owner consolidation separately evidenced and gated;
- opt-in process-isolated module sharding with serial/parallel equivalence;
- guard/hook boundary profiling, corpus layering, and per-invocation Git-context reuse if proven;
- independent immutable Git fixture seeds and finish pure-vs-physical boundary separation;
- fast dashboard inventory plus deep display enrichment;
- advisory performance baselines and existing runnerless-check output.

**Non-goals**

- changing a guard verdict, finish authorization, cleanup/lifecycle action, removing/renaming a
  frozen contract field, versioning a product schema, or changing a production durability algorithm
  for speed;
- automatically choosing a focused test set from arbitrary source dependencies in v1;
- automatic receipt reuse or gate suppression;
- sharing repositories/XDG state between cases;
- replacing `unittest`, adding pytest/xdist, or adding a runtime dependency;
- making a loaded-host timing result an SLA;
- wiring external doc-warden into AWA;
- running full transition/PM trials for unrelated changes;
- new CI infrastructure, hosted runners, or `chaos-scheduler`.

## 3. Verified live state and baseline protocol

Verified 2026-08-29 on clean GitHub `main`/local HEAD
`0390779930455273b6203676ae01437c43f8845f`, AWA `1.7.3`:

- discovery: 1,045 tests, 60 tracked test modules, 0.63 seconds;
- `./install.sh --check`: passed in 37.26 seconds;
- `dashboard/emitter.py --root ~/dev`: passed in 8.34 seconds;
- `engine/tests/run-tests.sh` is one serial discovery process plus dashboard;
- contract freeze is reached by `test_contract_schemas`, the explicit Makefile line, and
  `install.sh --check`;
- `helpers.make_repo()` starts each repository with repeated Git subprocesses;
- the full finish transition rehearsal remains separately filtered and typically takes 2–3 minutes.

The old 902-test loaded profile remains useful only to select the first surfaces. M1-A records a
fresh **passing serial baseline** before M2 can claim improvement. Baseline protocol:

1. stop other AWA suites; record `git status`, HEAD, `python3 --version`, `git --version`,
   `sys.platform`, logical CPU count, and a plain load note;
2. run discovery-only once, then the complete serial pre-PR lane once;
3. record result/intentional skips, elapsed/user/system time, max RSS where available, module/test
   durations, and receipt/inventory digests;
4. repeat only if the run failed for an identified environmental reason; preserve both observations;
5. never normalize the 35–42-minute overlapping-host observations into the baseline.

## 4. Target verification graph and promotion rules

| Lane | Entry point | Required contents | Authority |
|---|---|---|---|
| `docs` | `make verify-docs VERIFY_BASE=<ref>` | changed-path allow-list, diff whitespace, relative links, ADR/plan indexes | non-authoritative for runtime |
| `focused` | `make verify-focused TESTS="..."` | explicit unittest selectors plus progress/receipt | non-authoritative |
| `pre-pr` | `make verify` | complete serial/approved-parallel engine inventory, dashboard, contract integration, static install, live-verify check | authoritative local gate |
| `install` | `make verify-install` | direct/external install/repair/doctor/uninstall lifecycle | authoritative when install/projection changes |
| `release` | `make trial TRIAL_ARGS=...` plus affected runbook | filtered/full transitions and PM/router trials | authoritative only for selected release surface |

`docs` accepts only non-empty change records whose every old and new side is a contained,
repository-relative `*.md` regular-file path. A Markdown deletion is eligible when its old Git mode
was regular; a rename/copy is eligible only when **both** source and destination are eligible.
No paths, escape/absolute paths, symlink/special-file modes (including dangling symlinks), a
non-Markdown side, or any mixed set returns `pre-pr`. `focused` requires explicit selectors and
prints `NON-AUTHORITATIVE`; it never auto-selects tests. `make verify` stays the broad default and
does not trust lane receipts.

The proposed timing targets—docs under 30–60 seconds, focused feedback under 1–3 minutes, and pre-PR
around 3.5–5.5 minutes—are hypotheses, not promises and not derived from a controlled 12-minute
baseline. Only fixed-workload docs and pre-PR targets may be accepted: M6 requires at least five
passing controlled observations across two ordinary-load sessions, p90 within the target, and no
correctness/equivalence regression. Because focused selectors are arbitrary, focused timing stays
descriptive per invocation unless a later plan defines a fixed digest-bound benchmark manifest.
Otherwise M6 records `rejected` or a wider measured budget. Timing remains warning-only until a
separate owner GO promotes a stable budget.

## 5. Work items and Draft-PR bodies

### Milestone M1 — measured canonical verification DAG (minimum viable end-to-end)

M1 completes only when both bodies are merged and a developer can run all five named lanes. It
preserves serial execution and all current tests. M1-A establishes exact evidence; M1-B establishes
the usable lane graph and removes only the explicit `Makefile` freeze line proven redundant with the
immediately following `install.sh --check`. M1 is the minimum usable end-to-end graph, but does not
claim final single-owner freeze execution; M6 owns that separately evidenced consolidation.

#### Task M1-A.1: Serial progress runner, inventory, and non-authorizing receipt

**Purpose and operator value:** show active work and slow tests, preserve the exact suite, and bind
each result to source/tool state so agents stop blind polling or rerunning an already observed pass.

**Dependencies:** accepted ADR 0021 and explicit owner GO. No other implementation body.

**Acceptance ledger:** V01, V12–V13, V20–V22.

**Files:**
- Create: `engine/tests/suite_runner.py`
- Create: `engine/tests/verification_contract.py`
- Create: `engine/tests/test_suite_runner.py`
- Modify: `engine/tests/run-tests.sh:22-36`

**Interfaces:**
- Consumes: unittest selectors passed after `--`; repository root from `Path(__file__).parents[2]`;
  optional `AWA_TEST_RECEIPT` path.
- Produces: `discover_test_ids(selectors: Sequence[str]) -> Tuple[str, ...]`;
  `run_serial(selectors: Sequence[str], stream: TextIO) -> Dict[str, object]`;
  `summarize_timings(records, limit=20) -> Dict[str, object]` with per-module totals and bounded
  slowest-test/module lists;
  `source_identity(root: Path) -> Dict[str, object]`; `build_receipt(before_identity,
  after_identity, inventory, records, lane, jobs, run, context)`; machine-readable
  `RECEIPT_KEYS`, `RECORD_KEYS`, `RUN_KEYS`, `CONTEXT_KEYS`, and `RESOURCE_KEYS`, plus
  `validate_receipt(value: Mapping[str, object]) -> None` in `verification_contract.py`; closed JSON
  schema `awa-test-receipt/v1`; CLI flags `--list-ids`, `--json-out PATH`, `--jobs 1`,
  `--selectors-env NAME` (non-empty `shlex.split`), and `--`; existing unittest verbosity, buffering,
  fail-fast, catch, name-pattern, and explicit-selector arguments remain compatible after `--`.

- [ ] **Step 1 — write the failing tests**

```python
class SuiteRunnerTest(unittest.TestCase):
    def test_inventory_is_sorted_unique_and_stable(self):
        ids = suite_runner.discover_test_ids(("engine.tests.test_redact",))
        self.assertEqual(ids, tuple(sorted(set(ids))))
        self.assertTrue(ids)

    def test_dirty_or_changed_source_receipt_is_never_reusable(self):
        before = {"head": "a" * 40, "clean": True}
        after = {"head": "b" * 40, "clean": True}
        receipt = suite_runner.build_receipt(
            before, after, ("a.Test.test_x",), (), "focused", 1, passed_run(),
            receipt_context(),
        )
        self.assertFalse(receipt["reusable"])
        self.assertEqual(receipt["source_state"], "unstable")
        self.assertFalse(receipt["authorizes_skip"])

    def test_clean_stable_pass_is_reusable_but_never_authorizes_skip(self):
        identity = {"head": "a" * 40, "clean": True}
        receipt = suite_runner.build_receipt(
            identity, identity, ("a.Test.test_x",), (), "focused", 1,
            passed_run(), receipt_context(),
        )
        verification_contract.validate_receipt(receipt)
        self.assertTrue(receipt["reusable"])
        self.assertFalse(receipt["authorizes_skip"])

    def test_receipt_validator_rejects_unknown_missing_and_wrong_type(self):
        receipt = valid_receipt()
        for mutate in (add_unknown_key, remove_inventory_digest, make_jobs_a_string):
            with self.subTest(mutate=mutate):
                with self.assertRaises(verification_contract.ContractError):
                    verification_contract.validate_receipt(mutate(copy.deepcopy(receipt)))

    def test_progress_names_case_and_elapsed_time(self):
        stream = io.StringIO()
        result = suite_runner.run_serial(
            ("engine.tests.test_redact.RedactTest.test_secret_assignment",), stream
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertIn("engine.tests.test_redact", stream.getvalue())
        self.assertRegex(stream.getvalue(), r"\[[0-9]+\.[0-9]s\]")

    def test_timing_summary_has_module_totals_and_stable_slowest_order(self):
        summary = suite_runner.summarize_timings(TIMING_RECORDS, limit=2)
        self.assertEqual(summary["modules"][0]["module"], "engine.tests.test_slow")
        self.assertEqual(
            [item["test_id"] for item in summary["slowest_tests"]],
            ["engine.tests.test_slow.Case.test_a",
             "engine.tests.test_slow.Case.test_b"],
        )

    def test_worker_count_other_than_one_is_refused_in_m1(self):
        with self.assertRaisesRegex(ValueError, "M2 sharding is not enabled"):
            suite_runner.validate_jobs(2)

    def test_existing_unittest_flags_remain_compatible(self):
        for args in (
            ("-v", "engine.tests.test_redact"),
            ("engine.tests.test_redact", "--failfast"),
            ("-k", "secret_assignment", "engine.tests.test_redact"),
        ):
            with self.subTest(args=args):
                self.assertTrue(suite_runner.inventory_from_unittest_args(args))
```

- [ ] **Step 2 — run the tests and verify they fail**

Run: `python3 -m unittest engine.tests.test_suite_runner -v`

Expected: FAIL with `ImportError` because `engine.tests.suite_runner` does not exist.

- [ ] **Step 3 — implement the serial runner and closed receipt**

```python
# verification_contract.py: normative keys consumed by every writer/reader
RECEIPT_SCHEMA = "awa-test-receipt/v1"
RECEIPT_KEYS = frozenset({
    "schema", "head_before", "head_after", "source_clean_before",
    "source_clean_after", "source_state", "reusable", "authorizes_skip",
    "lane", "jobs", "python", "git", "runner_sha256", "inventory_sha256",
    "test_count", "records", "run", "context",
})
RECORD_KEYS = frozenset({"test_id", "module", "outcome", "skip_reason", "elapsed_ms"})
RUN_KEYS = frozenset({"outcome", "elapsed_ms", "counts"})
CONTEXT_KEYS = frozenset({
    "command", "selectors", "platform", "architecture", "logical_cpu_count",
    "load_note", "generated_at_utc", "resource",
})
RESOURCE_KEYS = frozenset({"user_ms", "system_ms", "max_rss_kb"})

def validate_receipt(value):
    require_exact_keys(value, RECEIPT_KEYS, "receipt")
    require_literal(value["schema"], RECEIPT_SCHEMA, "receipt.schema")
    require_types_and_enums(value)
    require_sha256(value["runner_sha256"], "runner_sha256")
    require_sha256(value["inventory_sha256"], "inventory_sha256")
    for index, record in enumerate(value["records"]):
        require_exact_keys(record, RECORD_KEYS, "records[{0}]".format(index))
        validate_record(record)
    require_exact_keys(value["run"], RUN_KEYS, "run")
    require_exact_keys(value["context"], CONTEXT_KEYS, "context")
    require_exact_keys(value["context"]["resource"], RESOURCE_KEYS, "context.resource")
    validate_run_context_and_cross_fields(value)

class TimingResult(unittest.TextTestResult):
    def startTest(self, test):
        self._started = time.monotonic()
        self.stream.writeln("START {0}".format(test.id()))
        super().startTest(test)

    def stopTest(self, test):
        elapsed = time.monotonic() - self._started
        self.case_timings.append((test.id(), round(elapsed, 6)))
        self.stream.writeln("[{0:.1f}s] END {1}".format(elapsed, test.id()))
        super().stopTest(test)

def discover_test_ids(selectors=()):
    suite = load_suite(selectors)
    return tuple(sorted({case.id() for case in iter_cases(suite)}))

def build_receipt(before, after, inventory, records, lane, jobs, run, context):
    inventory_bytes = "\n".join(inventory).encode("utf-8")
    stable = before == after and before["clean"] and after["clean"]
    receipt = {
        "schema": verification_contract.RECEIPT_SCHEMA,
        "head_before": before["head"],
        "head_after": after["head"],
        "source_clean_before": before["clean"],
        "source_clean_after": after["clean"],
        "source_state": "stable" if stable else "unstable",
        "reusable": bool(stable and run["outcome"] == "passed"),
        "authorizes_skip": False,
        "lane": lane,
        "jobs": jobs,
        "python": platform.python_version(),
        "git": git_version(),
        "runner_sha256": runner_digest(
            ("engine/tests/suite_runner.py",
             "engine/tests/verification_contract.py",
             "engine/tests/run-tests.sh"),
        ),
        "inventory_sha256": sha256(inventory_bytes).hexdigest(),
        "test_count": len(inventory),
        "records": sorted(records, key=lambda item: item["test_id"]),
        "run": run,
        "context": context,
    }
    verification_contract.validate_receipt(receipt)
    return receipt

def validate_jobs(value):
    if value != 1:
        raise ValueError("M2 sharding is not enabled; use --jobs 1")
    return 1
```

Implement `iter_cases()` recursively, `load_suite()` through `unittest.defaultTestLoader`,
`source_identity()` with `git rev-parse HEAD` plus `git status --porcelain=v2 --untracked-files=all`,
and capture identity immediately before and after execution. Parse the bounded unittest-compatible
flags above without treating them as selectors; unknown runner flags fail with usage rather than
silently changing inventory. `verification_contract.validate_receipt`
requires exact keys/types/enums/nested keys and cross-field consistency (`test_count`, inventory
digest, source stability/reusability, run counts) and rejects unknown keys. `load_note` comes from
`AWA_TEST_LOAD_NOTE` or literal `not_provided`; machine context excludes hostname, username, paths,
environment, and source. `runner_digest()` hashes each listed repository-relative path plus a NUL
plus its bytes in sorted order. Write atomic JSON (same-directory temp, `fsync`, `os.replace`), stable
sorted records, result categories
`passed|failure|error|skipped|expected_failure|unexpected_success`, and exit 1 for any non-passing
outcome. Record each case's exact `test.__class__.__module__`, aggregate module duration from that
closed field, sort durations descending then ID, and print bounded top-20 slow tests/modules after
the result. Capture `resource.getrusage` user/system deltas and max RSS with the platform unit
normalized to KiB. Keep dashboard execution after an unfiltered successful engine run exactly as
`run-tests.sh` does today.

- [ ] **Step 4 — run focused and compatibility tests**

Run:

```bash
python3 -m unittest engine.tests.test_suite_runner -v
bash engine/tests/run-tests.sh --list-ids > /tmp/awa-test-ids.txt
bash engine/tests/run-tests.sh --jobs 1 -- engine.tests.test_redact -v
```

Expected: PASS; inventory output is sorted; focused output names live tests; no dashboard runs for a
filtered selection.

- [ ] **Step 5 — record the controlled serial baseline**

Run the §3 protocol once with
`AWA_TEST_RECEIPT=/tmp/awa-serial-baseline.json /usr/bin/time -lp make verify`.
Record the bounded result in
`live-verify/RESULTS-verification-serial-baseline-YYYYMMDD.md`, including exact command, HEAD,
versions, inventory digest/count, load note, pass/fail/skips, and timing. Do not call it an SLA.

- [ ] **Step 6 — review and open the Draft PR**

Run focused tests, `make verify` once, Bugbot, then create one Draft PR containing only this body and
its baseline record. Leave it unarmed.

**Measurable acceptance:** on the same candidate tree the legacy direct loader and new runner
discover identical IDs and produce the same complete serial outcome; baseline-to-candidate inventory
changes contain only the planned runner/contract tests with an explicit ID mapping; progress appears
within one test start; bounded slow-test/module summaries are stable; receipt is machine-validated,
deterministic apart from declared timestamps/timings, `authorizes_skip=false`, stable clean source
is reusable, and dirty/drifting source is unstable/non-reusable; real HOME/XDG/network remain
untouched.

**Evidence:** both inventory files and their SHA-256; receipt; `/usr/bin/time -lp`; git status before/
after; baseline record.

**Rollback:** revert this Draft-PR body; `run-tests.sh` returns to direct `unittest discover`. Delete
only generated `/tmp` evidence.

**Explicit non-goals:** parallelism, automatic test selection, receipt-based skips, hard budgets.

**Draft-PR boundary / GO:** one Draft PR. Owner GO is required before merge and before M1-B starts.

#### Task M1-B.1: Named lane graph, docs fail-closed classifier, and proven freeze deduplication

**Purpose and operator value:** documentation changes get a sub-minute, honest check; code changes
retain the full gate; every lane is discoverable from `make help`.

**Dependencies:** merged M1-A; explicit owner GO.

**Acceptance ledger:** V01, V06, V09–V13, V20–V21.

**Files:**
- Create: `engine/tests/verify_lane.py`
- Create: `engine/tests/test_verify_lane.py`
- Modify: `Makefile:3-45`
- Modify: `engine/tests/test_contract_schemas.py:85-92` only to assert the remaining integration
  path still executes (do not remove it)

**Interfaces:**
- Consumes: target-exported `AWA_VERIFY_BASE` Git ref from `VERIFY_BASE`; target-exported
  `AWA_TEST_SELECTORS` parsed with `shlex.split` from whitespace-separated `TESTS` (never interpolated
  into shell source).
- Produces: immutable
  `ChangeRecord(status, old_path, new_path, old_mode, new_mode, source)` values from committed,
  staged, unstaged, and untracked state; `changed_records(root: Path, base: str) ->
  Tuple[ChangeRecord, ...]`; `classify_changes(records: Sequence[ChangeRecord]) -> str` returning only
  `docs|pre-pr`;
  CLI `python3 -m engine.tests.verify_lane require-docs --base REF|--base-env NAME`;
  Make targets `verify-docs`, `verify-focused`, `verify-pre-pr`, `verify-release`.

- [ ] **Step 1 — write failing classification and Make-graph tests**

```python
class VerifyLaneTest(unittest.TestCase):
    def test_markdown_add_modify_delete_rename_and_copy_are_docs(self):
        for record in (
            change("A", None, "docs/new.md", None, 0o100644),
            change("M", "docs/a.md", "docs/a.md", 0o100644, 0o100644),
            change("D", "docs/old.md", None, 0o100644, None),
            change("R100", "docs/old.md", "docs/new.md", 0o100644, 0o100644),
            change("C100", "docs/source.md", "docs/copy.md", 0o100644, 0o100644),
        ):
            with self.subTest(record=record):
                self.assertEqual(verify_lane.classify_changes((record,)), "docs")

    def test_empty_mixed_rename_escape_and_symlink_fail_broad(self):
        cases = (
            (),
            (change("M", "docs/x.md", "docs/x.md", 0o100644, 0o100644),
             change("M", "engine/x.py", "engine/x.py", 0o100644, 0o100644)),
            (change("R100", "engine/x.py", "docs/x.md", 0o100644, 0o100644),),
            (change("A", None, "../outside.md", None, 0o100644),),
            (change("A", None, "docs/dangling.md", None, 0o120000),),
            (change("X", "docs/x.md", "docs/x.md", 0o100644, 0o100644),),
            (change("A", None, None, None, None),),
        )
        for records in cases:
            with self.subTest(records=records):
                self.assertEqual(verify_lane.classify_changes(records), "pre-pr")

    def test_receipts_are_not_inputs_to_lane_choice(self):
        signature = inspect.signature(verify_lane.classify_changes)
        self.assertNotIn("receipt", signature.parameters)

    def test_make_inputs_are_exported_not_interpolated_as_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = pathlib.Path(tmp) / "must-not-exist"
            payload = "$(shell touch {0})".format(marker)
            for assignment, target in (
                ("TESTS=" + payload, "verify-focused"),
                ("VERIFY_BASE=" + payload, "verify-docs"),
            ):
                subprocess.run(("make", target, assignment), cwd=ROOT, check=False)
                self.assertFalse(marker.exists())

    def test_makefile_has_named_lanes_and_no_direct_freeze(self):
        text = (ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ("verify-docs:", "verify-focused:", "verify-pre-pr:", "verify-release:"):
            self.assertIn(target, text)
        self.assertNotIn("@AWA_HOME=$(CURDIR) bash kernel/checks/awa-contract-freeze.sh", text)
        self.assertIn("@./install.sh --check", text)

```

- [ ] **Step 2 — run the tests and verify they fail**

Run: `python3 -m unittest engine.tests.test_verify_lane -v`

Expected: FAIL because `verify_lane` and the named targets do not exist.

- [ ] **Step 3 — implement fail-closed path collection/classification**

```python
@dataclasses.dataclass(frozen=True)
class ChangeRecord:
    status: str
    old_path: Optional[str]
    new_path: Optional[str]
    old_mode: Optional[int]
    new_mode: Optional[int]
    source: str

def eligible_doc_side(path, mode):
    if path is None:
        return mode is None
    pure = pathlib.PurePosixPath(path)
    contained = not pure.is_absolute() and ".." not in pure.parts and ".git" not in pure.parts
    regular = mode in (0o100644, 0o100755)
    return contained and path.endswith(".md") and regular

def classify_changes(records):
    if not records:
        return "pre-pr"
    for record in records:
        kind = record.status[:1]
        shape = (record.old_path is not None, record.new_path is not None)
        if kind not in ("A", "M", "D", "R", "C"):
            return "pre-pr"
        if ((kind == "A" and shape != (False, True)) or
                (kind == "D" and shape != (True, False)) or
                (kind in ("M", "R", "C") and shape != (True, True))):
            return "pre-pr"
        if kind == "M" and record.old_path != record.new_path:
            return "pre-pr"
        if not eligible_doc_side(record.old_path, record.old_mode):
            return "pre-pr"
        if not eligible_doc_side(record.new_path, record.new_mode):
            return "pre-pr"
    return "docs"
```

Parse `git diff --raw -z --no-abbrev --find-renames --find-copies` for base...HEAD, index, and
working-tree state so rename/copy records retain both paths and modes. Add untracked entries with
`lstat()` mode; a read error or duplicate/conflicting record broadens to `pre-pr`. `require-docs`
must JSON-escape and print every status/old/new side and return 2 unless classification is exactly
`docs`. It then runs `git diff --check` for base...HEAD, staged, and working-tree state plus an
equivalent trailing-whitespace/conflict-marker check for each untracked file; validates relative
links across all currently tracked Markdown plus eligible untracked Markdown (skip `http:`, `https:`,
`mailto:`, and pure `#anchor`); and proves every `docs/adr/[0-9]{4}-*.md` and every
`docs/plans/*.md` governed artifact except `docs/plans/README.md` has exactly one index link. Invoke
Git without a shell, validate the base ref, and terminate revision arguments with `--`. It must not
invoke doc-warden or any external host path.

- [ ] **Step 4 — express the Make DAG and remove only the proven explicit duplicate**

```make
.PHONY: verify-docs verify-focused verify-pre-pr verify-release
unexport VERIFY_BASE TESTS

verify-docs: export AWA_VERIFY_BASE := $(value VERIFY_BASE)
verify-docs:
	@PYTHONDONTWRITEBYTECODE=1 python3 -B -m engine.tests.verify_lane require-docs --base-env AWA_VERIFY_BASE
	@echo "verify-docs: OK (NON-AUTHORITATIVE FOR RUNTIME)"

verify-focused: export AWA_TEST_SELECTORS := $(value TESTS)
verify-focused:
	@echo "verify-focused: NON-AUTHORITATIVE"
	@bash engine/tests/run-tests.sh --jobs 1 --selectors-env AWA_TEST_SELECTORS

verify-pre-pr: verify

verify-release:
	@$(MAKE) trial TRIAL_ARGS="$(TRIAL_ARGS)"
```

First run `bash -x -c 'make verify'` against the unchanged graph and record the three source-context
checker invocations. Delete only the explicit `Makefile` checker recipe. Keep
`test_contract_schemas.test_freeze_checker_passes` and `install.sh --check` unchanged. Add comments
that those remaining executions prove separate integration entrypoints and are not authorized for
removal by M1.

- [ ] **Step 5 — prove all lane behaviors**

Run:

```bash
python3 -m unittest engine.tests.test_verify_lane engine.tests.test_contract_schemas -v
make verify-docs VERIFY_BASE=origin/main
make verify-focused TESTS="engine.tests.test_redact"
make verify
```

Expected: tests pass; Markdown add/modify/delete and docs-to-docs rename select docs; any
non-Markdown old/new side, escape, unknown mode, symlink/special file, empty, or mixed set selects
pre-PR; focused output is plainly non-authoritative; full verify still executes the contract checker
via the unit integration and `install.sh --check`; new lane test IDs are mapped, with no unplanned
ID loss.

- [ ] **Step 6 — review and open the Draft PR**

Run Bugbot and create one Draft PR containing only M1-B. Leave it unarmed.

**Measurable acceptance:** docs-only source avoids engine execution; both sides of every
rename/copy are classified; docs and focused labels cannot be mistaken for merge authority;
mixed/unknown/escape/symlink selects broad; `make verify` loses exactly one explicit freeze
execution and remains green; no accepted/frozen doc changes.

**Evidence:** command transcript, path-class matrix, before/after freeze invocation count, full
receipt, and `git diff --check`.

**Rollback:** revert M1-B; named targets disappear and the explicit Makefile freeze returns. M1-A's
serial runner remains independently usable.

**Explicit non-goals:** removing either remaining freeze integration, automatic focused selection,
external doc-warden wiring.

**Draft-PR boundary / GO:** one Draft PR. Owner GO required before merge and before M2.

### Milestone M2 — opt-in process-isolated module sharding

#### Task M2-A.1: Deterministic module workers and serial-equivalence manifests

**Purpose and operator value:** reduce full-gate wall time without sharing mutable test state or
changing the authoritative default.

**Dependencies:** M1 complete; passing serial baseline; explicit owner GO.

**Acceptance ledger:** V01–V06, V12–V13, V20–V22.

**Files:**
- Modify: `engine/tests/suite_runner.py`
- Modify: `engine/tests/verification_contract.py`
- Modify: `engine/tests/test_suite_runner.py`
- Create: `engine/tests/test_parallel_equivalence.py`
- Modify: `engine/tests/run-tests.sh`

**Interfaces:**
- Consumes: M1 `discover_test_ids`, receipt schema, optional prior receipt durations.
- Produces: `group_by_module(test_ids) -> Dict[str, Tuple[str, ...]]`;
  `schedule_modules(modules, prior_ms) -> Tuple[str, ...]`;
  `run_parallel(selectors, jobs, prior_receipt, stream, worker_factory=None,
  worker_timeout_s=None) -> Dict[str, object]`; both serial and parallel results contain exact
  `inventory: Tuple[str, ...]` and `outcomes: Dict[str, Dict[str, object]]`; internal worker CLI
  `--worker-module MODULE --worker-json PATH`; supported jobs `1|2|4`; machine-validated
  `awa-test-worker/v1` keys in `verification_contract.py`.

- [ ] **Step 1 — write failing deterministic/equivalence/failure tests**

```python
class ParallelEquivalenceTest(unittest.TestCase):
    def test_schedule_is_longest_first_then_name(self):
        modules = ("engine.tests.test_a", "engine.tests.test_b", "engine.tests.test_c")
        prior = {"engine.tests.test_a": 10, "engine.tests.test_b": 20,
                 "engine.tests.test_c": 20}
        self.assertEqual(
            suite_runner.schedule_modules(modules, prior),
            ("engine.tests.test_b", "engine.tests.test_c", "engine.tests.test_a"),
        )

    def test_one_and_two_workers_emit_identical_inventory_and_outcomes(self):
        selectors = ("engine.tests.test_redact", "engine.tests.test_identity_paths")
        serial = suite_runner.run_serial(selectors, io.StringIO())
        parallel = suite_runner.run_parallel(selectors, 2, None, io.StringIO())
        self.assertEqual(serial["inventory"], parallel["inventory"])
        self.assertEqual(serial["outcomes"], parallel["outcomes"])

    def test_every_worker_fault_fails_overall(self):
        for mode in ("crash", "timeout", "signal", "partial", "malformed", "extra"):
            with self.subTest(mode=mode):
                result = suite_runner.run_parallel(
                    ("engine.tests.test_redact",), 2, None, io.StringIO(),
                    worker_factory=failing_worker(mode),
                    worker_timeout_s=0.05,
                )
                self.assertEqual(result["outcome"], "error")

    def test_duplicate_test_id_from_two_workers_is_rejected(self):
        docs = {
            "engine.tests.test_a": worker_doc("engine.tests.test_a", ["same.Case.test_x"]),
            "engine.tests.test_b": worker_doc("engine.tests.test_b", ["same.Case.test_x"]),
        }
        with self.assertRaisesRegex(suite_runner.RunnerError, "duplicate test id"):
            suite_runner.aggregate_worker_records(tuple(docs), docs)

    def test_worker_contract_rejects_unknown_key(self):
        doc = worker_doc("engine.tests.test_a", ["a.Case.test_x"])
        doc["surprise"] = True
        with self.assertRaises(verification_contract.ContractError):
            verification_contract.validate_worker(doc)

    def test_workers_use_distinct_private_temp_and_xdg_roots(self):
        reports = run_worker_sandbox_probe(("engine.tests.test_a", "engine.tests.test_b"))
        self.assertEqual(len({report["tmp"] for report in reports}), 2)
        self.assertEqual(len({report["xdg"] for report in reports}), 2)
        self.assertTrue(all(report["cleaned"] for report in reports))
```

- [ ] **Step 2 — run and verify failure**

Run: `python3 -m unittest engine.tests.test_parallel_equivalence -v`

Expected: FAIL because parallel interfaces do not exist.

- [ ] **Step 3 — implement isolated workers and deterministic aggregation**

```python
# verification_contract.py
WORKER_SCHEMA = "awa-test-worker/v1"
WORKER_KEYS = frozenset({
    "schema", "module", "inventory_sha256", "records", "outcome", "elapsed_ms", "resource",
})

def validate_worker(value):
    require_exact_keys(value, WORKER_KEYS, "worker")
    require_literal(value["schema"], WORKER_SCHEMA, "worker.schema")
    require_sha256(value["inventory_sha256"], "worker.inventory_sha256")
    require_exact_keys(value["resource"], RESOURCE_KEYS, "worker.resource")
    validate_module_name_outcome_elapsed_and_records(value)

# suite_runner.py
def schedule_modules(modules, prior_ms):
    return tuple(sorted(modules, key=lambda name: (-int(prior_ms.get(name, 0)), name)))

def worker_command(module, output):
    return (
        sys.executable, "-B", "-m", "engine.tests.suite_runner",
        "--worker-module", module, "--worker-json", str(output),
    )

def aggregate_worker_records(expected_modules, worker_docs):
    if set(worker_docs) != set(expected_modules):
        raise RunnerError("missing or extra worker result")
    records = []
    for module in sorted(expected_modules):
        doc = worker_docs[module]
        verification_contract.validate_worker(doc)
        if doc["module"] != module:
            raise RunnerError("worker module mismatch")
        records.extend(doc["records"])
    test_ids = [record["test_id"] for record in records]
    duplicates = sorted(test_id for test_id in set(test_ids) if test_ids.count(test_id) > 1)
    if duplicates:
        raise RunnerError("duplicate test id: {0}".format(",".join(duplicates)))
    return sorted(records, key=lambda item: item["test_id"])

def worker_timeout_seconds(module, prior_ms, override):
    if override is not None:
        return max(0.01, min(float(override), 1800.0))
    prior_s = int(prior_ms.get(module, 0)) / 1000.0
    return max(300, min(int(prior_s * 4) or 300, 1800))

def stop_worker(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
```

Use a bounded `subprocess.Popen` pool (never in-process test threads), each worker in its own Python
interpreter. Give each worker a unique temp output path and monotonic deadline from
`worker_timeout_seconds`; poll active workers, call `stop_worker` at deadline, and classify timeout
as overall error. Give each child private `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, and
`XDG_CACHE_HOME` beneath the runner temp root; preserve HOME unless existing test helpers explicitly
sandbox it, and prove the real HOME/XDG state fingerprint is unchanged. Never wait serially on one
worker while completed peers remain unreaped. Validate
each worker document with `verification_contract` before aggregation. Reject unsupported jobs,
timeout, signal, non-zero exit, missing/extra/late module, malformed/oversized JSON, duplicate test
ID, inventory mismatch, or leftover worker. On interrupt, terminate then bounded-kill and reap all
children before removing temp state. Each worker records `getrusage` CPU deltas and max RSS; the
parent receipt sums child user/system time and records the maximum worker RSS, rather than reporting
parent-only resource use. Dashboard still runs once after all engine modules pass.

- [ ] **Step 4 — run the equivalence campaign**

For jobs 1, 2, and 4, run the complete inventory once under the §3 controlled protocol. Then run the
best non-1 candidate three additional times. Compare sorted test IDs, per-ID outcome, intentional
skip reason, dashboard outcome, real-state fingerprint, and cleanup. Any mismatch blocks promotion.

- [ ] **Step 5 — record evidence and open the Draft PR**

Write `live-verify/RESULTS-verification-parallel-equivalence-YYYYMMDD.md` with all observations,
including failures and load context. Run Bugbot. Open one Draft PR with `--jobs 2|4` opt-in only;
leave `make verify` on jobs=1.

**Measurable acceptance:** exact serial/parallel ID and outcome manifests; duplicate IDs refuse; no
worker survives; crash/timeout/signal/partial/malformed worker fault always fails overall; 1/2/4
data recorded; best parallel p50 improves serial by at least 25% without higher flake rate, or the
default remains serial with an honest no-promotion result.

**Evidence:** receipts/manifests for every run, process list after faults, before/after real-state
fingerprint, `/usr/bin/time -lp`, equivalence record.

**Rollback:** revert M2-A; `--jobs` returns to M1's jobs=1 refusal.

**Explicit non-goals:** default promotion, threaded tests, shared fixtures, retries that hide flakes.

**Draft-PR boundary / GO:** one Draft PR. Owner GO required before merge.

#### Task M2-B.1: Promote the measured worker count, or record serial retention

**Purpose and operator value:** make the proven faster path ordinary, but only when the evidence
supports it.

**Dependencies:** merged M2-A and accepted equivalence record.

**Acceptance ledger:** V01–V06, V12–V13, V20–V22.

**Files:**
- Modify: `Makefile`
- Modify: `engine/tests/run-tests.sh`
- Modify: `live-verify/RESULTS-verification-parallel-equivalence-YYYYMMDD.md` only while still a
  draft record in the same body; otherwise create a new dated promotion record

**Interfaces:**
- Consumes: exact M2-A receipts and operator-selected `AWA_TEST_JOBS`.
- Produces: default `AWA_TEST_JOBS=<1|2|4>` for `make test`/`make verify`; serial override
  `AWA_TEST_JOBS=1`.

- [ ] **Step 1 — write the failing default/fallback test**

```python
def test_make_default_matches_approved_record_and_serial_override_works(self):
    approved = load_approved_parallel_record()
    self.assertIn(approved["selected_jobs"], (1, 2, 4))
    self.assertEqual(make_default_jobs(), approved["selected_jobs"])
    result = run_make_test(env={"AWA_TEST_JOBS": "1"}, selectors=("engine.tests.test_redact",))
    self.assertEqual(result.returncode, 0)
    self.assertIn('"jobs":1', result.receipt_text)
```

- [ ] **Step 2 — run and verify failure**

Run: `python3 -m unittest engine.tests.test_parallel_equivalence -v`

Expected: FAIL until the approved default and serial override are wired.

- [ ] **Step 3 — implement only the owner-approved outcome**

```bash
# run-tests.sh
jobs="${AWA_TEST_JOBS:-APPROVED_JOBS}"
exec python3 -B -m engine.tests.suite_runner --jobs "$jobs" "$@"
```

Replace `APPROVED_JOBS` with the literal owner-approved 1, 2, or 4. If evidence rejects sharding,
set `1` and record that M2 delivered an opt-in diagnostic only. Do not silently choose.

- [ ] **Step 4 — verify default plus serial fallback**

Run the selected default full `make verify` once and
`AWA_TEST_JOBS=1 bash engine/tests/run-tests.sh -- engine.tests.test_redact -v` as the focused serial
compatibility run. Both must pass with their exact expected inventory.

- [ ] **Step 5 — review and open the Draft PR**

Run Bugbot; open one Draft PR; leave unarmed.

**Measurable acceptance:** default exactly matches approved evidence; `AWA_TEST_JOBS=1` remains
usable; no result/evidence change.

**Evidence:** owner decision, selected/default and serial receipts, exact inventory diff.

**Rollback:** set default to literal `1` in a normal revert PR; opt-in code may remain dormant.

**Explicit non-goals:** dynamic CPU-count default, adaptive unbounded workers, automatic retries.

**Draft-PR boundary / GO:** separate Draft PR and explicit owner GO are mandatory.

### Milestone M3 — guard/hook process-amplification reduction

#### Task M3-A.1: Boundary-specific process profile and canary equivalence decision

**Purpose and operator value:** identify which engine/source-kernel/installed/owner-mode boundary
creates process amplification before changing production guard code.

**Dependencies:** M2 complete or explicitly retained serial default; explicit owner GO.

**Acceptance ledger:** V01, V06–V08, V12–V13, V20–V22, V24.

**Files:**
- Create: `engine/tests/guard_boundary_profile.py`
- Create: `engine/tests/test_guard_boundary_profile.py`
- Modify: `engine/tests/verification_contract.py`
- Modify: `engine/tests/test_guard.py`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `engine/tests/test_hook_owner_modes.py`
- Create: `live-verify/RESULTS-verification-m3-guard-boundaries-YYYYMMDD.md`

**Interfaces:**
- Consumes: one shared closed case manifest
  `GuardCase(label: str, command: str, expected_permission: str, state_fixture: str)`.
- Produces: `run_engine_cases`, `run_source_hook_cases`, `run_installed_hook_cases`,
  `run_owner_mode_cases`; per-boundary outcome/inventory/duration/Git-process counts; explicit
  `installed_matrix_decision=retain_full|byte_identity_plus_canaries`; CLI
  `python3 -m engine.tests.guard_boundary_profile --boundary
  engine|source|installed|owner --count-git --json-out PATH`; closed
  machine-validated `awa-guard-boundary-profile/v1` output with producer SHA-256, case-manifest
  SHA-256, and `counter_scope`.

- [ ] **Step 1 — write failing parity and counter tests**

```python
class GuardBoundaryProfileTest(unittest.TestCase):
    def test_all_boundaries_consume_same_case_ids(self):
        reports = profile_all_boundaries(CASES)
        expected = tuple(case.label for case in CASES)
        for report in reports.values():
            self.assertEqual(report["case_ids"], expected)

    def test_git_counter_reports_scope_and_never_changes_verdicts(self):
        plain = run_source_hook_cases(CASES)
        counted = run_source_hook_cases(CASES, count_git=True)
        self.assertEqual(plain["outcomes"], counted["outcomes"])
        self.assertEqual(counted["counter_scope"], "PATH-resolved git children only")
        self.assertGreater(counted["git_processes"], 0)
```

- [ ] **Step 2 — run and verify failure**

Run:
`python3 -m unittest engine.tests.test_guard_boundary_profile engine.tests.test_guard_hook_wrappers engine.tests.test_hook_owner_modes -v`

Expected: FAIL because the shared profile does not exist.

- [ ] **Step 3 — implement a bounded Git wrapper profile**

```python
def git_counting_env(real_git, log_path, base_env):
    wrapper = log_path.parent / "bin" / "git"
    wrapper.parent.mkdir()
    wrapper.write_text(
        "#!/bin/sh\nprintf '%s\\n' git >>\"$AWA_GIT_PROCESS_LOG\"\n"
        "exec \"$AWA_REAL_GIT\" \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    env = dict(base_env)
    env.update({
        "AWA_REAL_GIT": real_git,
        "AWA_GIT_PROCESS_LOG": str(log_path),
        "PATH": str(wrapper.parent) + os.pathsep + env["PATH"],
    })
    return env
```

Report interception scope honestly; do not claim absolute-path Git children were counted. Run every
case against the independent engine and source kernel. Profile installed copy separately after
proving source/installed bytes and interpreter. Run direct/external owner canaries with external
zero-access assertions.

- [ ] **Step 4 — make and record the installed-boundary decision**

`byte_identity_plus_canaries` is eligible only if (a) source and installed guard/checker bytes are
exact, (b) the same Python/Bash versions are used, (c) representative allow/deny/uncertainty,
maintenance, malformed input, owner-mode, and kernel-off canaries fail when deliberately broken,
and (d) full engine/kernel case parity remains elsewhere. Otherwise record `retain_full`.

- [ ] **Step 5 — verify, review, and open the Draft PR**

Run full guard/owner/kernel-off modules, Bugbot, and security review because the result determines
future boundary coverage. Open one Draft PR containing tests/profile/evidence only.

**Measurable acceptance:** one case ID manifest across boundaries; exact engine/kernel verdict
parity; process counts and timing per boundary; deliberate-break canaries bite; decision is evidence
backed and may honestly retain the full installed matrix.

**Evidence:** boundary report, wrapper scope, byte hashes, versions, deliberate-break results.

**Rollback:** revert profile/layering only; production guard remains untouched.

**Explicit non-goals:** production Git snapshot, guard verdict change, reducing full engine/kernel
corpus, cross-invocation cache.

**Draft-PR boundary / GO:** one Draft PR. Owner GO before merge and a second explicit GO before
M3-A.2.

#### Task M3-A.2: Apply measured installed-boundary layering, or retain the full matrix

**Purpose and operator value:** stop replaying an equivalent installed-copy corpus in every pre-PR
run only when byte/interpreter identity and biting installed canaries prove that the source corpus
plus canaries preserves the boundary.

**Dependencies:** merged M3-A.1, `installed_matrix_decision` in its accepted record, and explicit
owner GO. If the decision is `retain_full`, record the no-change outcome and do not open an empty PR.

**Acceptance ledger:** V01, V06–V08, V12–V13, V20–V22.

**Files (only for `byte_identity_plus_canaries`):**
- Create: `engine/tests/installed_guard_canaries.py`
- Create: `engine/tests/test_installed_guard_layering.py`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `engine/tests/test_hook_owner_modes.py`
- Modify: `engine/tests/run-tests.sh`
- Modify: `Makefile`

**Interfaces:**
- Consumes: M3-A case-manifest digest and selected canary IDs.
- Produces: closed `INSTALLED_GUARD_CANARIES` registry; ordinary source/engine full corpus plus
  installed direct/external/owner/allow/deny/uncertainty canaries; explicit
  `make verify-guard-installed-full`; serial full-matrix fallback
  `AWA_FULL_INSTALLED_GUARD_MATRIX=1`.

- [ ] **Step 1 — write failing selection, identity, and canary tests**

```python
class InstalledGuardLayeringTest(unittest.TestCase):
    def test_canary_registry_covers_every_accepted_boundary(self):
        required = {
            "direct_allow", "direct_deny", "external_allow", "external_deny",
            "uncertainty", "maintenance", "malformed", "owner_mode", "kernel_off",
        }
        self.assertEqual(required, set(INSTALLED_GUARD_CANARIES))
        inventory = set(suite_runner.discover_test_ids())
        for test_id in INSTALLED_GUARD_CANARIES.values():
            self.assertIn(test_id, inventory)

    def test_byte_or_interpreter_mismatch_refuses_layered_mode(self):
        for mutation in (mutate_installed_guard_byte, change_installed_interpreter):
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(LayeringError, "full installed matrix required"):
                    verify_installed_identity(mutation(installed_fixture()))

    def test_full_fallback_manifest_matches_pre_layering_manifest(self):
        before = load_m3_boundary_manifest("installed")
        after = run_installed_matrix(env={"AWA_FULL_INSTALLED_GUARD_MATRIX": "1"})
        self.assertEqual(before["case_ids"], after["case_ids"])
        self.assertEqual(before["outcomes"], after["outcomes"])
```

- [ ] **Step 2 — run and verify failure**

Run:
`python3 -m unittest engine.tests.test_installed_guard_layering -v`

Expected: FAIL because the registry, identity check, and fallback do not exist.

- [ ] **Step 3 — implement only the accepted M3-A decision**

Move no oracle and remove no full case. Preserve the full installed matrix behind the explicit
fallback. Before layered mode, verify exact installed/source guard and checker SHA-256 values and
the Python/Bash interpreter identities recorded by M3-A; mismatch fails closed with the fallback
command and never silently selects canaries. Generate ordinary canary tests from the closed registry
and keep the independent full engine/source-kernel case manifest in ordinary `make verify`.
`make verify-guard-installed-full` executes the complete pre-layering installed case-ID manifest;
`make verify-install` includes that target whenever install/projection files change.

- [ ] **Step 4 — prove canaries and fallback bite**

Run the ordinary gate and explicit full fallback. In isolated temporary patches, break each canary
boundary and prove its registered test fails; alter one installed byte and interpreter marker and
prove ordinary layering refuses. Compare the explicit fallback's exact case IDs/outcomes/skips with
the M3-A record. Record ordinary and fallback process counts.

- [ ] **Step 5 — review and open the conditional Draft PR**

Run Bugbot and security review. Open one Draft PR only for an accepted
`byte_identity_plus_canaries` result; leave it unarmed.

**Measurable acceptance:** full engine/source-kernel parity remains ordinary; every installed
boundary category has a loadable, suite-executed, deliberate-break-proven canary; byte/interpreter
drift fails closed; explicit full fallback preserves exact pre-layering IDs/outcomes/skips; ordinary
guard process count improves at least 15%, or retain the full matrix.

**Evidence:** accepted M3-A record, case-ID lane map, ordinary/full receipts, hashes/interpreters,
deliberate-break log, process counts.

**Rollback:** restore the full installed matrix to ordinary discovery; retain the profile record.

**Explicit non-goals:** weakening engine/source parity, deleting installed cases, trusting a stale
receipt, or using canaries when bytes/interpreters differ.

**Draft-PR boundary / GO:** conditional separate Draft PR. Owner GO before merge and a new explicit
GO before M3-B.

#### Task M3-B.1: One validated Git context per eligible maintenance decision

**Purpose and operator value:** remove repeated identical Git probes inside one decision while
proving a later invocation always observes changed state.

**Dependencies:** M3-A.2 has applied or honestly retained the selected boundary mode, M3-A identifies
repeated live maintenance probes as material, and the owner explicitly approves a production
safety-boundary change.

**Acceptance ledger:** V01, V06–V08, V12–V13, V16, V20–V22.

**Files:**
- Modify: `engine/guard.py`
- Modify: `kernel/hooks/worktree-guard.sh`
- Modify: `engine/tests/test_guard.py`
- Modify: `engine/tests/test_guard_hook_wrappers.py`
- Modify: `engine/tests/test_kernel_off_matrix.py`

**Interfaces:**
- Consumes: an exact valid ADR 0019 `_PrimaryMaintenanceShape`, fixed Cursor session cwd, sanitized
  environment, policy, and existing Git timeout.
- Produces: private engine `PrimaryMaintenanceGitContext` and byte-equivalent kernel dict containing
  only values already read for that eligible maintenance decision;
  `_collect_primary_maintenance_context(...)`; no persistence. Invalid, multi-segment, in-command
  `cd`, wrapped, redirected, `git -C`, `--git-dir`, and `--work-tree` forms never receive a context
  and retain their current path/verdict.

- [ ] **Step 1 — write pre-fix failing process and state-change tests**

```python
def test_one_invocation_has_two_state_captures_and_no_downstream_git_rereads(self):
    response, trace = decide_with_git_spy(self.safe_primary, "git fetch")
    self.assertEqual(response.permission, "allow")
    self.assertEqual(trace.phase_names.count("state_capture"), 2)
    self.assertEqual(trace.downstream_git_calls, ())

def test_second_invocation_observes_dirty_state(self):
    self.assertEqual(run_engine_and_hook(self.repo, "git fetch"), ("allow", "allow"))
    Path(self.repo, "dirty").write_text("x", encoding="utf-8")
    self.assertEqual(run_engine_and_hook(self.repo, "git fetch"), ("deny", "deny"))

def test_second_invocation_observes_advanced_upstream(self):
    before = run_engine_and_hook(self.repo, FAST_FORWARD)
    advance_upstream_fixture(self.repo)
    after = run_engine_and_hook(self.repo, FAST_FORWARD)
    self.assertNotEqual(before, after)

def test_ineligible_forms_never_receive_reusable_context(self):
    cases = (
        "git -C {0} fetch".format(self.other_repo),
        "git --git-dir {0} fetch".format(self.other_git_dir),
        "cd {0} && git commit -m nope".format(self.linked_worktree),
        "git status && git fetch",
    )
    for command in cases:
        with self.subTest(command=command):
            result = run_engine_and_hook(self.protected_primary, command)
            self.assertEqual(result.verdicts, existing_expected_verdicts(command))
            self.assertEqual(result.maintenance_context_count, 0)

def test_state_change_during_collection_uses_uncertainty_path(self):
    for mutation in (
        change_head_after_first_state_capture,
        dirty_worktree_after_first_state_capture,
        advance_upstream_after_first_state_capture,
        change_fetch_config_after_first_state_capture,
        create_operation_marker_after_first_state_capture,
    ):
        with self.subTest(mutation=mutation):
            result = decide_with_probe_hook(self.repo, mutation)
            self.assertEqual(result.permission, "deny")
            self.assertEqual(result.reason, CURRENT_UNCERTAINTY_REASON)

def test_incomplete_collector_falls_back_to_existing_live_probes(self):
    legacy = run_engine_and_hook(self.repo, "git fetch", force_legacy_probes=True)
    fallback = run_engine_and_hook(
        self.repo, "git fetch", collector_fault=INCOMPLETE_CONTEXT,
    )
    self.assertEqual(fallback, legacy)
```

- [ ] **Step 2 — run and verify the process assertion fails**

Run:
`python3 -m unittest engine.tests.test_guard engine.tests.test_guard_hook_wrappers engine.tests.test_kernel_off_matrix -v`

Expected: the two-capture/no-downstream-reread test fails before context reuse; all existing verdict
tests remain green.

- [ ] **Step 3 — implement an invocation-local immutable snapshot in both mirrors**

```python
@dataclasses.dataclass(frozen=True)
class RepositoryStateToken:
    worktree_root: str
    common_git_dir: str
    head_oid: str
    upstream_name: str
    upstream_oid: str
    maintenance_config_sha256: str
    status_sha256: str
    operation_markers_sha256: str
    hidden_index_sha256: str

@dataclasses.dataclass(frozen=True)
class PrimaryMaintenanceGitContext:
    repository_identity: Tuple[str, str]
    session_cwd: str
    branch: str
    upstream: str
    upstream_remote: str
    status_porcelain_v2: bytes
    operation_in_progress: bool
    hidden_index_bits: bool
    head_is_ancestor_of_upstream: Optional[bool]
    state_before: RepositoryStateToken
    state_after: RepositoryStateToken
    errors: Tuple[str, ...]
```

Canonical repository identity binds physical worktree root plus common Git directory. Only after
`_primary_maintenance_shape` accepts the exact bare-Git form, capture the closed
`RepositoryStateToken` before and after collecting required maintenance facts; compare every field
and take the current uncertainty/deny path on any mismatch. Use the validated captured values for
that decision and allow no downstream Git rereads. Every ineligible form bypasses this collector
entirely and retains current ADR 0001/0019 behavior. An unsupported or incomplete collection uses
the existing uncached live-probe path; detectable state drift takes the existing fail-safe
uncertainty/deny result and never authorizes from mixed evidence. Pass the immutable context down
only the maintenance call graph. Mirror the same keys, collection order, and fallback in the
embedded kernel Python. Create no module/global cache, file, environment export, memoization
decorator, or process-lifetime singleton.

- [ ] **Step 4 — run full parity, stale-state, kernel-off, and installed canaries**

Run M3-A's complete engine/kernel corpus and selected installed/owner canaries, plus every
state-change test twice. Deliberately corrupt one context field in a fixture and prove uncertainty
fails safe.

- [ ] **Step 5 — review and open the Draft PR**

Run Bugbot and security review. Open one Draft PR for snapshot changes only; leave unarmed.

**Measurable acceptance:** verdicts/case IDs unchanged; each eligible maintenance decision uses
exactly two closed state captures and no downstream Git rereads; ineligible/multi-target/redirected
forms receive no context; intra-collection HEAD/dirty/upstream/config/operation drift uses existing
uncertainty; incomplete collection preserves the uncached fallback verdict; second invocation sees
dirty/upstream/operation changes; no persistent cache symbol/artifact; measured guard corpus
Git-process count decreases by at least 20%, otherwise revert and record no-benefit.

**Evidence:** before/after boundary profile, parity manifests, state-change results, source/kernel/
installed hashes.

**Rollback:** revert the snapshot PR; independent old probes return without data migration.

**Explicit non-goals:** command-crossing cache, policy change, guard relaxation, production
parallelism.

**Draft-PR boundary / GO:** separate security-sensitive Draft PR; explicit owner GO required.

### Milestone M4 — finish-suite fixture and boundary optimization

#### Task M4-A.1: Independent immutable Git seeds for eligible finish tests

**Purpose and operator value:** avoid repeated `git init/add/commit/branch/remote` setup while every
test still owns physically independent mutable Git state.

**Dependencies:** fresh M1 timing identifies eligible finish modules; explicit owner GO.

**Acceptance ledger:** V01, V06, V12–V14, V20–V22.

**Files:**
- Modify: `engine/tests/helpers.py`
- Create: `engine/tests/test_helpers_seed.py`
- Modify: only current top measured eligible modules among
  `engine/tests/test_finish_hardening.py`,
  `engine/tests/test_finish_phase2_final_blockers.py`,
  `engine/tests/test_finish_final_hardening.py`,
  `engine/tests/test_finish_kernel.py`,
  `engine/tests/test_finish_operations.py`,
  `engine/tests/test_finish_conversation.py`,
  `engine/tests/test_finish_publication_projection.py`, and
  `engine/tests/test_finish_semantic_drift.py`

**Interfaces:**
- Consumes: `EngineTestCase._tmp`; existing `git()` and `commit_all()`.
- Produces: `RepoSeed.materialize(destination: Path, origin: bool = True) -> str`;
  `EngineTestCase.make_seeded_repo(...)`; explicit `fresh=True` escape for repo-construction tests.

- [ ] **Step 1 — write isolation and eligibility tests**

```python
class RepoSeedTest(EngineTestCase):
    def test_materializations_have_independent_refs_config_objects_and_hooks(self):
        left = Path(self.make_seeded_repo("left"))
        right = Path(self.make_seeded_repo("right"))
        git(str(left), "checkout", "-qb", "left-only")
        git(str(left), "config", "awa.test", "left")
        (left / ".git/hooks/pre-commit").write_text("exit 1\n", encoding="utf-8")
        commit_all(str(left), "left")
        self.assertNotIn("left-only", git(str(right), "branch").stdout)
        self.assertNotEqual(git(str(right), "config", "--get", "awa.test", check=False).returncode, 0)
        self.assertFalse((right / ".git/hooks/pre-commit").exists())
        self.assertNotEqual(os.stat(left / ".git/HEAD").st_ino, os.stat(right / ".git/HEAD").st_ino)

    def test_worktrees_and_xdg_state_are_not_shared(self):
        left = self.make_seeded_repo("left")
        right = self.make_seeded_repo("right")
        left_common = Path(left, git(left, "rev-parse", "--git-common-dir").stdout.strip()).resolve()
        right_common = Path(right, git(right, "rev-parse", "--git-common-dir").stdout.strip()).resolve()
        self.assertNotEqual(left_common, right_common)
        self.assertFalse(any(path.is_symlink() for path in left_common.rglob("*")))
```

- [ ] **Step 2 — run and verify failure**

Run: `python3 -m unittest engine.tests.test_helpers_seed -v`

Expected: FAIL because `make_seeded_repo` does not exist.

- [ ] **Step 3 — implement copy-only independent seeds**

```python
class RepoSeed:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-git-seed.")
        self.root = Path(self._tmp.name) / "repo"
        build_seed_from_scratch(self.root)

    def materialize(self, destination, origin=True):
        shutil.copytree(
            self.root, destination, symlinks=False,
            copy_function=shutil.copy2,
        )
        if not origin:
            git(str(destination), "remote", "remove", "origin")
        return str(destination)
```

Hold one immutable seed per test process, verify it contains no symlink or special file before first
use, never modify it after publication, use ordinary copies (no hard links or alternates), validate
destination beneath the test temp root, and restore private permissions. Keep `make_repo()` for
tests whose subject is repository creation/configuration or physical copy behavior.

- [ ] **Step 4 — migrate one module at a time behind before/after manifests**

For each eligible module: capture IDs/outcomes/process count, replace only semantically identical
setup calls, rerun, compare, then proceed. Stop on any ref/config/hook/object/worktree/fault-boundary
difference.

- [ ] **Step 5 — run finish physical seams and review**

Run all changed finish modules plus retention/publication/durability modules, Bugbot, and security
review. Open one Draft PR containing seed helper and eligible migrations only.

**Measurable acceptance:** exact IDs/outcomes; independent inode/ref/config/hook/common-dir proof;
no alternates/hardlinks; at least 10% fewer Git setup processes in migrated modules or revert the
migration; production files unchanged.

**Evidence:** per-module before/after receipts/process counts, isolation tests, seed hash and
read-only audit.

**Rollback:** revert helper and migrations; no state migration.

**Explicit non-goals:** shared object store, APFS-only clone requirement, production finish change,
moving physical durability tests to fakes.

**Draft-PR boundary / GO:** one Draft PR; explicit owner GO.

#### Task M4-B.1: Separate pure finish matrices from physical/durability canaries

**Purpose and operator value:** run combinatorial state transitions without rebuilding physical
repositories while retaining every real crash/durability/stable-snapshot seam.

**Dependencies:** M4-A and a current module profile that identifies cases already expressible through
an existing production pure-decision seam; explicit owner GO. If no such seam exists, record
no-promotion and retain the physical cases rather than refactor production finish code for speed.

**Acceptance ledger:** V01, V06, V12–V13, V15, V20–V22.

**Files:**
- Create: `engine/tests/finish_case_manifest.py`
- Create: `engine/tests/test_finish_case_manifest.py`
- Modify: eligible matrix sections in the M4-A finish modules
- Do not modify: `kernel/lib/awa_finish.py`, `kernel/lib/awa_durability.py`,
  `consumer/finish_current.py`

**Interfaces:**
- Consumes: closed immutable `FinishCase` inputs and current production decision functions.
- Produces: one case-ID manifest; pure matrix runner; explicit physical-canary registry mapping every
  crash/fsync/publication/retention/stable-snapshot requirement to at least one real test ID.

- [ ] **Step 1 — write failing coverage-partition tests**

```python
def test_every_finish_case_has_exactly_one_layer_and_oracle(self):
    ids = set()
    for case in ALL_FINISH_CASES:
        self.assertIn(case.layer, ("pure", "physical"))
        self.assertTrue(case.oracle)
        self.assertNotIn(case.case_id, ids)
        ids.add(case.case_id)

def test_required_physical_seams_remain_real(self):
    required = {
        "crash_cut", "fsync", "f_fullfsync", "retention", "publication",
        "stable_snapshot_recapture", "no_follow", "shared_lock", "removal_journal",
    }
    self.assertEqual(required - set(PHYSICAL_CANARIES), set())
    loader = unittest.defaultTestLoader
    inventory = set(suite_runner.discover_test_ids())
    for seam, pair in PHYSICAL_CANARIES.items():
        with self.subTest(seam=seam):
            self.assertEqual(loader.loadTestsFromName(pair["positive"]).countTestCases(), 1)
            self.assertEqual(loader.loadTestsFromName(pair["negative"]).countTestCases(), 1)
            self.assertIn(pair["positive"], inventory)
            self.assertIn(pair["negative"], inventory)

def test_pure_cases_refuse_physical_access(self):
    case = pure_case("probe")
    with self.assertRaisesRegex(AssertionError, "physical access from pure case"):
        run_pure_case(case, adapter=adapter_that_calls_git)
```

- [ ] **Step 2 — run and verify failure**

Run: `python3 -m unittest engine.tests.test_finish_case_manifest -v`

Expected: FAIL because no explicit partition exists.

- [ ] **Step 3 — author the closed manifest and move only pure cases**

```python
@dataclasses.dataclass(frozen=True)
class FinishCase:
    case_id: str
    layer: str
    input: Mapping[str, object]
    expected: Mapping[str, object]
    oracle: str

@contextlib.contextmanager
def deny_physical_access():
    forbidden = (
        "builtins.open", "os.open", "os.stat", "os.lstat", "os.replace",
        "os.rename", "os.unlink", "os.mkdir", "os.makedirs", "os.chmod",
        "os.fchmod", "os.fsync", "subprocess.run", "subprocess.Popen",
        "fcntl.flock", "time.time", "time.monotonic", "socket.socket",
    )
    with contextlib.ExitStack() as stack:
        for target in forbidden:
            stack.enter_context(mock.patch(
                target, side_effect=AssertionError("physical access from pure case")
            ))
        yield

def run_pure_case(case, adapter=production_decision_adapter):
    if case.layer != "pure":
        raise AssertionError("physical case cannot use pure runner")
    with deny_physical_access():
        actual = adapter(case.input)
    if actual != case.expected:
        raise AssertionError("{0}: {1!r} != {2!r}".format(
            case.case_id, actual, case.expected))
```

A case is pure only when its assertion depends solely on supplied values and invokes no Git,
filesystem identity, descriptor/no-follow, lock, clock, fsync, subprocess, or crash boundary.
Run pure cases in the existing serial test process under scoped mocks for every physical call site
imported by the selected production module (Git, open/lstat, sockets, locks, clocks, fsync and
subprocess); a physical call fails the case and every mock is restored before the case returns.
Never run this scoped section concurrently. Do not use a process-global `sys.addaudithook` because it
cannot be removed. Everything else stays physical. Do not create a second semantic implementation:
the adapter calls the production decision function.

`PHYSICAL_CANARIES` maps every required seam to one loadable positive behavior test ID and one
loadable negative/fault-injection test ID. The ordinary suite executes both IDs; the registry test
proves none is renamed or omitted. Step 4's deliberate-break campaign remains review evidence, not
the sole ongoing oracle.

- [ ] **Step 4 — run deliberate-break and complete finish tests**

For each seam, temporarily bypass its production/fault-injection behavior in an isolated patch and
prove the registered negative test fails; restore immediately. Separately remove one registry entry
and rename one registered test in temporary patches and prove the registry test fails. Run all
finish/retention/publication/durability tests and compare manifests.

- [ ] **Step 5 — review and open the Draft PR**

Run Bugbot and security review. Open one Draft PR; leave unarmed.

**Measurable acceptance:** same case IDs/outcomes; required physical seams map to loadable,
suite-executed positive and negative tests; pure cases fail on any physical call; no production
finish files changed; migrated matrix sections reduce child-process count without changing oracle.

**Evidence:** case/layer manifest, physical-canary registry, deliberate-break log, before/after
receipt.

**Rollback:** revert test partition; physical implementation unaffected.

**Explicit non-goals:** production semantic refactor, fake fsync, removal of stable recapture, fewer
crash cut points.

**Draft-PR boundary / GO:** one Draft PR; explicit owner GO.

### Milestone M5 — fast operational discovery

#### Task M5-A.1: Fast inventory and deep display enrichment profiles

**Purpose and operator value:** common status refresh returns quickly without recursive size/history
work; operators can still request the complete display.

**Dependencies:** explicit owner GO; M1 measurement infrastructure available.

**Acceptance ledger:** V01, V13, V17–V18, V20–V22.

**Files:**
- Modify: `dashboard/emitter.py`
- Modify: `dashboard/test_emitter.py`
- Modify: `dashboard/render.py`
- Modify: `dashboard/test_render.py`

**Interfaces:**
- Consumes: existing root and Git timeout.
- Produces: `build(root: Path, timeout: float, detail: str = "deep") -> dict`;
  `render.publish(..., detail: str = "fast")`;
  detail values `fast|deep`; additive top-level `detail` and per-value
  worktree/orphan-branch `enrichment_state=checked|not_checked|unknown`; internal
  `AWA_DASHBOARD_DETAIL=fast|deep` selection for direct emitter profiling. The frozen
  `dev-worktree.sh dashboard-data` flags remain unchanged and default to deep.

- [ ] **Step 1 — write failing fast/deep/honesty tests**

```python
def test_fast_never_calls_du_or_history(self):
    with mock.patch.object(emitter, "disk_usage_bytes") as du, \
         mock.patch.object(emitter, "last_commit_detail") as history:
        doc = emitter.build(FIXTURE_ROOT, 1.0, detail="fast")
    du.assert_not_called()
    history.assert_not_called()
    self.assertEqual(doc["detail"], "fast")
    self.assertEqual(doc["repos"][0]["worktrees"][0]["enrichment_state"], "not_checked")

def test_deep_preserves_current_fields(self):
    legacy = load_normalized_legacy_deep_fixture()
    doc = emitter.build(FIXTURE_ROOT, 30.0, detail="deep")
    self.assertEqual(doc["detail"], "deep")
    self.assertEqual(doc["repos"][0]["worktrees"][0]["enrichment_state"], "checked")
    self.assertEqual(strip_additive_detail_fields(doc), legacy)

def test_deep_timeout_is_unknown_not_checked(self):
    doc = emitter.build(HANGING_FIXTURE_ROOT, 0.01, detail="deep")
    item = doc["repos"][0]["worktrees"][0]
    self.assertEqual(item["enrichment_state"], "unknown")
    self.assertIsNone(item["size_bytes"])

def test_render_requests_fast_by_default_and_allows_explicit_deep(self):
    with mock.patch.object(render.emitter, "build", return_value=VALID_DOC) as build:
        render.publish(FIXTURE_ROOT, canvas_dir=CANVAS_DIR)
        self.assertEqual(build.call_args.kwargs["detail"], "fast")
        render.publish(FIXTURE_ROOT, detail="deep", canvas_dir=CANVAS_DIR)
        self.assertEqual(build.call_args.kwargs["detail"], "deep")
```

Before changing production code, capture `load_normalized_legacy_deep_fixture()` from the existing
hermetic fixture with generated timestamps/absolute temp paths normalized; review and commit only
the minimal expected field/value structure.

- [ ] **Step 2 — run and verify failure**

Run: `python3 dashboard/test_emitter.py`

Expected: FAIL because `detail` is not accepted and `du` is eager.

- [ ] **Step 3 — implement the additive profile**

```python
DETAILS = ("fast", "deep")

def worktree_detail(wt_path, block, base, timeout, detail="deep"):
    if detail not in DETAILS:
        raise ValueError("detail must be fast or deep")
    item = required_inventory(wt_path, block, base, timeout)
    if detail == "fast":
        item.update({
            "size_bytes": None,
            "plain_size": "not checked",
            "last_commit_ts": None,
            "last_commit_subject": None,
            "enrichment_state": "not_checked",
        })
        return item
    return enrich_display(item, timeout)
```

Preserve the emitter and frozen `dashboard-data` default `deep` and every required key. Make
`dashboard.render.publish()` call `build(..., detail="fast")` explicitly only after render/consumer
tests prove the “not checked” copy is honest; expose an internal render `--detail deep` override for
the complete display. No cache in M5-A and no new frozen kernel CLI flag.

- [ ] **Step 4 — benchmark representative fixtures**

Create hermetic small, many-worktree, dirty, stale/unresponsive, and build-artifact-heavy fixtures.
Measure fast/deep at the same HEAD and timeout. A timed-out probe must be `unknown`, never cached or
green. Fingerprint real AWA/home state before/after.

- [ ] **Step 5 — review and open the Draft PR**

Run dashboard emitter/render tests, contract freeze, and Bugbot. Open one Draft PR; leave unarmed.

**Measurable acceptance:** fast performs zero `du`/history probes; deterministic sorted output;
frozen schema floor preserved; unknown remains honest; representative common path improves by at
least 30% or interactive default stays deep.

**Evidence:** fixture definitions, commands, HEAD/tool/load context, fast/deep timings and JSON
diff limited to additive/detail fields.

**Rollback:** revert profile/consumer selection; default deep behavior remains compatible.

**Explicit non-goals:** display cache, concurrent probes, safety-evidence use, schema v2.

**Draft-PR boundary / GO:** one Draft PR; explicit owner GO.

#### Task M5-B.1: Batched/bounded deep enrichment, only if M5-A data justifies it

**Purpose and operator value:** keep explicitly requested deep display bounded on large fleets.

**Dependencies:** M5-A evidence shows deep enrichment remains material; snapshot-consistency review;
explicit owner GO.

**Acceptance ledger:** V01, V13, V17–V22.

**Files:**
- Modify: `dashboard/emitter.py`
- Modify: `dashboard/test_emitter.py`

**Interfaces:**
- Consumes: M5-A deep profile.
- Produces: `enrich_many(items, timeout, workers) -> list`; fixed worker choices `1|2|4`; output
  sorted independently of completion order.

- [ ] **Step 1 — write failing order/timeout/snapshot tests**

```python
def test_completion_order_cannot_change_output_order(self):
    serial = emitter.enrich_many(ITEMS, 1.0, 1)
    with mock.patch.object(emitter, "enrich_display",
                           side_effect=reverse_completion_enricher):
        parallel = emitter.enrich_many(ITEMS, 1.0, 2)
    self.assertEqual(normalize_time(serial), normalize_time(parallel))

def test_timeout_is_per_item_unknown_and_never_reuses_old_value(self):
    result = emitter.enrich_many((HANGING_ITEM,), 0.01, 2)[0]
    self.assertEqual(result["enrichment_state"], "unknown")
    self.assertIsNone(result["size_bytes"])

def test_exception_or_identity_drift_is_per_item_unknown(self):
    for failure in (OSError("gone"), IDENTITY_CHANGED):
        with self.subTest(failure=failure):
            result = run_enrichment_with_failure(failure)
            self.assertEqual(result["enrichment_state"], "unknown")
            self.assertIsNone(result["last_commit_ts"])
            self.assertIsNone(result["size_bytes"])
```

- [ ] **Step 2 — run and verify failure**

Run: `python3 dashboard/test_emitter.py`

Expected: FAIL because `enrich_many` does not exist.

- [ ] **Step 3 — implement bounded enrichment**

```python
def enrich_many(items, timeout, workers):
    if workers not in (1, 2, 4):
        raise ValueError("workers must be 1, 2, or 4")
    indexed = [(index, item, read_display_identity(item))
               for index, item in enumerate(items)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(enrich_display, item, timeout): (index, item, identity)
            for index, item, identity in indexed
        }
        completed = []
        for future, (index, item, before) in futures.items():
            try:
                value = future.result(timeout=display_future_budget(timeout))
                after = read_display_identity(item)
                if before != after:
                    value = unknown_enrichment(item)
            except (Exception, concurrent.futures.TimeoutError):
                value = unknown_enrichment(item)
            completed.append((index, value))
    return [value for _, value in sorted(completed)]
```

Threads may coordinate independent read-only display subprocesses here; they do not run tests or
share safety state. `read_display_identity()` binds canonical worktree path, Git common directory,
HEAD, and the inventory status digest; `unknown_enrichment()` preserves only inventory identity and
nulls every enrichment field.
Every `enrich_display` subprocess call has its own timeout, and `display_future_budget()` is a fixed
sum of those bounded probes plus one second. Catch per-item failures without copying raw exception
text; never convert them to checked values. If a worker does not respect its bounded subprocess
timeouts, reject M5-B rather than leave a background thread. Prefer one `for-each-ref` format over
per-branch log calls where fields are equivalent. Do not persist a cache in this version.

- [ ] **Step 4 — benchmark 1/2/4 and run deterministic repeats**

Use M5-A fixtures; run each worker count three times. Reject concurrency if output, timeout truth,
cleanup, or p90 worsens.

- [ ] **Step 5 — review and open the Draft PR**

Run dashboard/contract tests and Bugbot. Open one Draft PR only if evidence selects a worker count.

**Measurable acceptance:** stable order/values; per-item exception/identity drift/timeout is unknown
with enrichment fields nulled; no raw exception text or worker survives; bounded workers; selected
count improves deep p50 by at least 20% without p90 regression.

**Evidence:** 1/2/4 receipts, output digest comparisons, timeout/drift matrix.

**Rollback:** revert to serial deep enrichment; fast profile remains.

**Explicit non-goals:** persistent cache, safety consumer, unbounded fleet fan-out.

**Draft-PR boundary / GO:** optional separate Draft PR; explicit owner GO.

### Milestone M6 — regression governance and runnerless integration

#### Task M6-A.1: Advisory budgets, process-growth probe, and lane runbook

**Purpose and operator value:** keep improvements from silently eroding and document exactly when
full install/release rehearsals are required.

**Dependencies:** M1–M5 accepted outcomes (including honest no-promotion decisions); explicit owner
GO.

**Acceptance ledger:** V01, V05–V06, V09–V13, V20–V25.

**Files:**
- Create: `engine/tests/performance_policy.py`
- Create: `engine/tests/test_performance_policy.py`
- Create: `engine/tests/performance-baseline.v1.json`
- Create: `docs/runbooks/verification-lanes.md`
- Modify: `engine/tests/verification_contract.py`
- Modify: `engine/tests/suite_runner.py`
- Modify: `engine/tests/test_contract_schemas.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: M1 receipts; selected fixed-workload controlled observations; current M3 source-hook
  process observation from `python3 -m engine.tests.guard_boundary_profile --boundary source
  --count-git --json-out PATH`, with exact `counter_scope`.
- Produces: machine-validated schema `awa-test-performance-baseline/v1`; advisory
  `evaluate(current, baseline, require_process=False) -> Tuple[Warning, ...]`; explicit
  `make verify-performance` process probe; CLI
  `python3 -m engine.tests.performance_policy evaluate-lane --lane docs|pre-pr --elapsed-ms N
  [--receipt PATH] [--process-profile PATH]`; timing/inventory warning lines in existing
  `make verify` output; final single source-freeze owner in `make verify`; no new remote
  service/check.

- [ ] **Step 1 — write failing policy tests**

```python
def test_time_is_warning_only_and_context_is_required(self):
    current = observation(elapsed_ms=999999, load_note="")
    warnings = performance_policy.evaluate(current, BASELINE)
    self.assertIn("missing load context", messages(warnings))
    self.assertTrue(all(item["severity"] == "warning" for item in warnings))

def test_inventory_and_process_growth_are_reported_not_hidden(self):
    current = observation(
        test_count=BASELINE["test_count"] + 50,
        process_measurement={
            "status": "measured",
            "counter_scope": BASELINE["process_measurement"]["counter_scope"],
            "producer_sha256": BASELINE["process_measurement"]["producer_sha256"],
            "case_manifest_sha256":
                BASELINE["process_measurement"]["case_manifest_sha256"],
            "git_processes": BASELINE["process_measurement"]["git_processes"] + 500,
        },
    )
    messages_ = messages(performance_policy.evaluate(
        current, BASELINE, require_process=True
    ))
    self.assertIn("test inventory grew", messages_)
    self.assertIn("scoped Git process count grew", messages_)

def test_missing_process_measurement_is_not_zero(self):
    current = observation(process_measurement=None)
    self.assertIn("scoped Git process count not measured",
                  messages(performance_policy.evaluate(
                      current, BASELINE, require_process=True
                  )))

def test_arbitrary_focused_run_has_no_lane_wide_time_budget(self):
    current = observation(lane="focused", elapsed_ms=999999)
    self.assertNotIn("wall time exceeded advisory budget",
                     messages(performance_policy.evaluate(current, BASELINE)))

def test_receipt_can_never_suppress_verification(self):
    for path in (ROOT / "Makefile", ROOT / "engine/tests/verify_lane.py",
                 ROOT / "install.sh", ROOT / "live-verify/verify-live-verify.sh"):
        source = path.read_text(encoding="utf-8")
        self.assertNotIn("authorizes_skip", source)
        self.assertNotIn('["reusable"]', source)
    source = inspect.getsource(performance_policy)
    self.assertNotIn("return_cached_pass", source)

def test_baseline_contract_rejects_unknown_or_incomplete_shape(self):
    for value in (dict(BASELINE, surprise=True),
                  dict(BASELINE, process_measurement=None)):
        with self.subTest(value=value):
            with self.assertRaises(verification_contract.ContractError):
                verification_contract.validate_performance_baseline(value)
```

- [ ] **Step 2 — run and verify failure**

Run: `python3 -m unittest engine.tests.test_performance_policy -v`

Expected: FAIL because policy/baseline do not exist.

- [ ] **Step 3 — implement closed advisory evaluation**

```python
# verification_contract.py
PERFORMANCE_SCHEMA = "awa-test-performance-baseline/v1"
PERFORMANCE_KEYS = frozenset({
    "schema", "status", "head", "test_count", "inventory_sha256", "python", "git",
    "lanes", "process_measurement", "observation_count", "session_count",
    "module_durations_ms", "machine_contexts", "evidence",
})
PERFORMANCE_LANE_KEYS = frozenset({
    "status", "workload_sha256", "observation_count", "session_count", "p90_ms",
    "warning_elapsed_ms",
})
PROCESS_MEASUREMENT_KEYS = frozenset({
    "status", "counter_scope", "producer_sha256", "case_manifest_sha256", "git_processes",
})
BASELINE_CONTEXT_KEYS = frozenset({
    "platform", "architecture", "logical_cpu_count", "load_note",
})

def validate_performance_baseline(value):
    require_exact_keys(value, PERFORMANCE_KEYS, "performance baseline")
    require_literal(value["schema"], PERFORMANCE_SCHEMA, "performance schema")
    require_exact_lane_keys(value["lanes"], ("docs", "pre-pr"), PERFORMANCE_LANE_KEYS)
    require_exact_keys(
        value["process_measurement"], PROCESS_MEASUREMENT_KEYS, "process measurement"
    )
    for context in value["machine_contexts"]:
        require_exact_keys(context, BASELINE_CONTEXT_KEYS, "machine context")
    validate_performance_types_enums_digests_and_counts(value)

# performance_policy.py
def evaluate(current, baseline, require_process=False):
    verification_contract.validate_performance_baseline(baseline)
    warnings = []
    required = ("head", "inventory_sha256", "python", "git", "lane", "jobs",
                "test_count", "outcome")
    missing = [key for key in required
               if key not in current or current[key] is None]
    if missing:
        warnings.append(warning("missing context: " + ",".join(sorted(missing))))
    if not current.get("load_note"):
        warnings.append(warning("missing load context"))
    if current.get("test_count", 0) > baseline["test_count"]:
        warnings.append(warning("test inventory grew"))
    process = current.get("process_measurement")
    expected_process = baseline["process_measurement"]
    if require_process:
        if (not process or process.get("status") != "measured" or
                expected_process.get("status") != "measured" or
                process.get("counter_scope") != expected_process["counter_scope"] or
                process.get("producer_sha256") != expected_process["producer_sha256"] or
                process.get("case_manifest_sha256") !=
                    expected_process["case_manifest_sha256"]):
            warnings.append(warning("scoped Git process count not measured"))
        elif process["git_processes"] > expected_process["git_processes"] * 1.20:
            warnings.append(warning("scoped Git process count grew"))
    lane = current.get("lane")
    lane_baseline = baseline["lanes"].get(lane)
    if lane_baseline and lane_baseline["status"] == "accepted" and (
            current.get("elapsed_ms", 0) >
            lane_baseline["warning_elapsed_ms"]):
        warnings.append(warning("wall time exceeded advisory budget"))
    return tuple(warnings)
```

`verification_contract.validate_performance_baseline()` enforces exact keys/types/enums, including a
required process object: `status=measured` requires non-empty `counter_scope`, producer digest,
case-manifest digest, and integer count; `status=not_measured` requires all four value fields to be
null. `producer_sha256` hashes the profile source and validator contract, never the generated result
or its timing/count fields.
Baseline JSON stores only controlled aggregate evidence: schema, accepted/rejected fixed-workload
targets, observation count, environment/tool fields, inventory/process scope, module durations,
warning thresholds, and source evidence links. No raw paths, logs, source, prompts, or secrets.
Require five passing observations across two ordinary-load sessions before accepting docs or
pre-PR targets. Focused observations remain descriptive. A failed target is recorded `rejected`,
not adjusted silently.

- [ ] **Step 4 — collect fixed-workload timing and current scoped-process observations**

Run controlled docs and pre-PR workloads under §3. For the current process observation, run exactly:

```bash
python3 -B -m engine.tests.guard_boundary_profile \
  --boundary source --count-git --json-out /tmp/awa-guard-process-current.json
```

Require the same producer digest, case-manifest digest, and `counter_scope` as the accepted M3
baseline. If M3 did not ship, scope/digest differs, or the profile is not run, record
`not_measured`; never substitute zero.
Only `make verify-performance` runs this potentially expensive profile and calls
`evaluate(..., require_process=True)`; ordinary `make verify` does not add a second guard corpus.
The target creates private temp receipt/profile paths, traps cleanup, runs one authoritative
`make verify` at the current HEAD with warning recursion disabled, runs the fixed profile above, then
evaluates both artifacts. Any authoritative command failure remains the target's exit failure;
performance findings remain warnings and cannot mask or replace it.

- [ ] **Step 5 — document lane/rehearsal selection**

The runbook must state:

- docs/focused are non-authoritative; mixed/unknown → pre-PR;
- pre-PR is required for every runtime/test/Make/contract change;
- install is additionally required for `install.sh`, package/runtime projection, hook-owner,
  installer, and uninstall changes;
- filtered release rehearsal is required for changed PM/router/finish/retention surfaces;
- the complete finish transition rehearsal is required before a finish/retention release, not for
  unrelated work;
- live Desktop UAT remains required where headless tests cannot prove UI/hook behavior;
- receipts never skip; serial fallback command; no paid runner.

- [ ] **Step 6 — prove and establish final pre-PR freeze ownership**

M1 intentionally removed only the low-risk explicit Makefile duplicate. Recapture an invocation
trace at the current HEAD, compare the unit and `install.sh::do_check` checker command, AWA_HOME,
inputs, and failure propagation, and stop if they are not the same source-context proof. Once
equivalence is demonstrated, replace only `test_contract_schemas.test_freeze_checker_passes` with a
static wiring assertion while preserving every schema-content test:

```python
def test_install_check_is_single_pre_pr_freeze_owner(self):
    install = (_REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    invocation = 'AWA_HOME="$SRC_ROOT" "$SRC_ROOT/kernel/checks/awa-contract-freeze.sh"'
    self.assertEqual(install.count(invocation), 1)
    self.assertIn("@./install.sh --check", makefile)
    self.assertNotIn("bash kernel/checks/awa-contract-freeze.sh", makefile)
```

Run this test before the replacement and record its expected failure. Update the module docstring and
remove only imports/constants made unused by the replacement. Then run `bash -x -c 'make verify'` and
record exactly one source checker invocation. `make check` still executes its checker once; install
lifecycle tests retain distinct installed-runtime checks. If equivalence or failure propagation
cannot be proven, make this body NO-GO and report the unresolved conflict with ADR 0021 rather than
removing the unit integration.

- [ ] **Step 7 — use only the existing runnerless path**

Have `make verify` print timing/inventory advisory warnings after the authoritative result; it must
not invoke `make verify-performance` or the process profile. The existing
`pr-automation / verify` check is runnerless; verify its live controller recipe before claiming it
reaches this repository's `make verify` or changing any binding. If it already reaches `make verify`,
change no `.github/pr-automation.json` field. If it does not, stop this body and open a separate
controller-owned plan; do not invent an AWA-side runner or workflow.

Wire the existing docs and pre-PR recipes as single `set -e` shell blocks with private temp paths and
cleanup traps: capture monotonic start, run every authoritative command unchanged, then invoke the
advisory CLI. Pre-PR supplies the current runner receipt; docs supplies its change-manifest digest and
zero test count. The advisory CLI prints warnings and exits zero; malformed committed baseline data
still fails its unit/contract test in the authoritative engine suite. Preserve the first failing
authoritative exit and M1's one-freeze invocation trace.

- [ ] **Step 8 — verify, review, and open the Draft PR**

Run unit tests, docs checks, one controlled `make verify`, Bugbot, and the existing runnerless PR
check. Open one Draft PR; leave unarmed.

**Measurable acceptance:** five fixed-workload observations/two sessions or targets remain
hypotheses; arbitrary focused timing stays descriptive; timing violations warn only; missing process
count says `not measured`; test-ID/scoped process growth is visible; `make verify` executes source
freeze once after explicit equivalence proof and gains no second guard corpus; no receipt skip;
runbook covers every release lane; no Actions workflow/runner or controller mutation.

**Evidence:** baseline JSON, source receipts, before/after freeze invocation trace, existing
runnerless check URL/result, runbook link check, no-workflow diff.

**Rollback:** revert M6 policy/runbook wiring and restore the executable contract-freeze unit
integration; prior authoritative gates remain.

**Explicit non-goals:** focused lane-wide budget, timing hard-fail, automatic baseline rewrite, new
CI service, automatic release selection.

**Draft-PR boundary / GO:** one Draft PR. Explicit owner GO required before merge. A later separate
owner decision is required to promote any hard timing budget.

## 6. Acceptance-test ledger

Every row is required unless its milestone records an explicit evidence-backed no-promotion outcome;
no row may be waived merely for speed.

| ID | Acceptance proof | Required by | Evidence |
|---|---|---|---|
| V01 | On each candidate tree, legacy/new discovery returns the same complete sorted test IDs; across commits every planned added/renamed ID is mapped and no unplanned ID disappears | M1, every body | inventory manifests + digest + ID map |
| V02 | Serial and parallel manifests have identical IDs | M2 | 1/2/4 receipts |
| V03 | Per-ID outcomes and intentional skip reasons match | M2 | equivalence report |
| V04 | Worker crash, timeout, signal, malformed/partial output, extra module, or duplicate test ID fails the overall run and every child is reaped | M2 | fault-injection tests |
| V05 | Serial fallback remains usable and authoritative | M2+ | `AWA_TEST_JOBS=1` receipt |
| V06 | `test_kernel_off_matrix` remains green | M1–M6 affected bodies | test output |
| V07 | Full independent engine/kernel guard corpus parity remains | M3 | shared case manifest |
| V08 | Installed/direct/external owner-mode canaries remain loadable, suite-executed, and biting; exact pre-layering installed IDs/outcomes/skips remain behind the full fallback | M3 | registry test + deliberate-break record + fallback manifest |
| V09 | Contract freeze still runs through every authoritative entrypoint that requires it; M1 removes only the explicit Makefile duplicate and M6 proves `install.sh --check` is the final single executable source-context owner in `make verify` | M1, M6 | wiring test + invocation traces |
| V10 | Docs/focused output says non-authoritative | M1 | CLI snapshot tests |
| V11 | Both sides/modes of add/modify/delete/rename/copy are classified; empty/unknown/mixed/non-Markdown/escape/symlink/special set selects pre-PR | M1 | raw-diff record matrix |
| V12 | Shared machine validators close receipt/worker/baseline schemas; receipts bind clean unchanged before/after source, always have `authorizes_skip=false`, and no gate consumes them to skip | M1–M6 | validator/schema/source tests |
| V13 | Tests leave real HOME, hooks, AWA runtime/state, governed worktrees, and network unchanged | every body | before/after fingerprint + socket denial |
| V14 | Git seed materializations have independent refs/config/hooks/index/common-dir/object files and no alternates/hardlinks | M4 | seed isolation tests |
| V15 | Finish crash, fsync/`F_FULLFSYNC`, retention, publication, no-follow, lock, removal-journal, and stable-recapture seams each retain suite-executed positive and negative physical tests; pure cases fail on physical access | M4 | physical canary registry + purity fault tests |
| V16 | Context exists only for an exact eligible bare-Git maintenance decision; multi-segment/redirected/`git -C`/in-command-`cd` forms retain current behavior with no context; intra-collection drift denies, later invocations observe live state, and no persistent cache exists | M3 | eligibility/state-change/source tests |
| V17 | Dashboard timeout/exception/identity drift remains honest per-item `unknown` with enrichment nulled; fast omission says `not_checked` | M5 | fixture matrix |
| V18 | Display enrichment/cache is not imported by guard, finish, cleanup, lifecycle, reconciliation, recovery, or deletion code | M5 | structural import/search test |
| V19 | Dashboard output order and values are deterministic across worker completion order | M5 | digest comparison |
| V20 | No automatic lifecycle/cleanup/destructive action is added | every body | diff/security review |
| V21 | No paid runner, Actions workflow, hosted service, or `chaos-scheduler` change | every body | changed-path assertion |
| V22 | Performance claims include HEAD, exact command, count/digest, tool versions, worker count, load context, and pass/fail | M1–M6 | receipt/baseline validation |
| V23 | Docs and fixed pre-PR targets are accepted only after five controlled passes across two sessions; otherwise explicitly rejected/hypothesis | M6 | baseline status |
| V24 | Focused timing remains descriptive; docs/pre-PR timing starts warning-only; explicit `verify-performance` gets current scoped-process count from the fixed M3 producer or says `not measured`; ordinary pre-PR adds no second guard corpus | M6 | policy tests + profile receipt |
| V25 | Full finish transition and PM/router rehearsals are selected only for affected release surfaces | M6 | runbook tests |

## 7. Milestone promotion and owner GO/NO-GO gates

At each Draft PR boundary, the implementer reports:

1. exact source/HEAD and changed paths;
2. acceptance rows exercised and their receipts;
3. before/after wall/process measurements with load caveats;
4. Bugbot findings and, where required, security-review findings;
5. rollback command/commit plan;
6. whether the body met its measured threshold or should be retained as no-promotion evidence.

**GO** requires all correctness/safety rows, clean hermetic state, complete evidence, and the
operator's explicit instruction. Performance improvement alone cannot override a failed equivalence
row.

**NO-GO** if any test ID/outcome/skip disappears unexpectedly; kernel/engine/installed parity differs;
a worker/fixture leaks state; an unknown becomes green/checked; receipt affects authorization; a
production finish safety seam changes for speed; host/runner dependency appears; or evidence is
environment-unbound. Revert the body, preserve the evidence, and do not start the next body.

M1 is the minimum viable end-to-end release and may stand alone. M2–M6 are serial production
increments, not prerequisites for using M1. M3-A.2, M3-B, M4-B, and M5-B are conditional: an honest
evidence-backed no-change outcome completes their evaluation without forcing complexity.

## 8. Rollback

- **M1-A:** revert runner delegation; direct serial discovery returns.
- **M1-B:** revert named targets/classifier and restore the one explicit Makefile freeze line.
- **M2:** reset default to literal one worker or revert opt-in sharding; receipts are disposable
  evidence and require no migration.
- **M3:** restore the full installed matrix to the ordinary lane and/or revert the maintenance
  context; each invocation resumes independent live probes.
- **M4:** revert seed/pure-matrix test changes; no production state or fixture migration exists.
- **M5:** select/revert deep serial default; additive fields remain removable before release or
  retained harmlessly after.
- **M6:** remove advisory policy/runbook hook and restore the executable contract-freeze unit
  integration; authoritative correctness gates remain.

After merge, rollback uses a normal revert PR—never reset, force-push, amend a pushed commit, move a
tag, or bypass checks. Stop worker processes before reverting M2. Remove only generated temp/
machine-local evidence after confirming it is not the sole audit record.

## 9. Full end state

- Docs-only work gets a fail-closed, repository-local, sub-minute path with no full code suite.
- Developers get named, timely focused feedback and one reproducible full pre-PR gate.
- The full gate shows live progress and exact evidence, runs the selected proven 1/2/4 module worker
  count with serial fallback, and fails every worker ambiguity.
- Full engine/kernel parity and representative installed/owner canaries bite; the exact full
  installed matrix remains an explicit serial fallback; no safety seam is removed for speed.
- Eligible finish tests use independent immutable seeds and pure matrices while every physical
  durability/stable-snapshot boundary remains real.
- Dashboard fast status avoids recursive `du`/history; deep enrichment stays deterministic, bounded,
  honest, and display-only.
- Controlled docs/pre-PR warning budgets detect inventory/module growth through the existing
  runnerless verification path; explicit local `verify-performance` measures scoped process growth
  without burdening every pre-PR run; focused timing stays descriptive, with no paid runner or new
  service.

This plan is complete only when every implemented milestone's acceptance rows are evidenced and any
conditional no-promotion decision is explicit. It authorizes nothing until accepted plus an
operator GO.
