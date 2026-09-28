# ADR 0025 Body C execution ledger — 2026-09-28

This ledger is append-only during execution. Earlier entries are not rewritten.
Accepted ADRs, frozen plans, Body A schema/protocol semantics, Body B
admission/status semantics, and protected independent authorities remain
unchanged.

## Entry 001 — inherited authority and exact live baseline

The original ADR 0025 implementation, implementation-delivery, and
throwaway-only R0 GO recorded byte-for-byte in the Body A ledger remains the
sole authority. Body C does not grant R1, C1, R2, release, live installation,
host activation, Skills, or cross-repository mutation.

- Root:
  `/Users/laurence.duggan/.cursor/worktrees/awa/4u64`
- Retained clean Body B branch head:
  `d3979e2105614eaf83b8370edf9ff87a19a042b6`
- Live GitHub `main` and Body C base:
  `71e5a3e2c03d9ed09f9c76d5ec0f52da8e664c8c`
- Live-main parent:
  `d336dfe1170df3fa5aefb8ec85b2d1e7539359f6`
- Body B retained-head tree and live-main squash tree:
  `ba28e3d0c5976a93016a4a4bd16fa7194eb40ba7` (exactly equal)
- Body C branch:
  `feat/adr-0025-body-c`
- PR #177 source head:
  `d3979e2105614eaf83b8370edf9ff87a19a042b6`
- PR #177 reviewer approval: exact source head, reviewer App
  `kleinperkins-review-bot`
- PR #177 checks: contract, engine-tests, source, tests, and verify all
  `SUCCESS`
- PR #177 merge:
  `71e5a3e2c03d9ed09f9c76d5ec0f52da8e664c8c`
- Remote `feat/adr-0025-body-b`: absent (`404`)
- Linked worktree, identity, policy, hook chain, and guard classification:
  healthy; `KleinPerkins <49759187+KleinPerkins@users.noreply.github.com>`;
  Safe Workspace; managed pre-commit chain present.
- Session lock:
  `env:adr0025-body-c-4u64-20260928`, held by this session.
- Protected primary and no-touch roots were clean; the primary was only one
  expected squash merge behind before the Body C fetch. No no-touch root was
  mutated.

Fresh immutable hashes:

```text
ADR 0025                    dabac24ccb8097888a485ef55fd9a5b83eaa1ec87976387f8ba7f834e3a8ea1f
v3 plan                     d5b03f0364a77ccd8877d88dacb0e52683e8407ba014b0e3adc89cbf22276ab8
ADR index                   d79f6a9fe818ea978cde3e33184eeac5a402859e63e1c79cf7a964a5bc774190
plan index                  d2e45c34adcb5591903c9f410620557d33668c16e304ac621b9624cfc1e03632
canonical SQL               221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede
ADR 0020                    f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98
ADR 0023                    71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051
ADR 0024                    cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911
frozen first-prompt v1      e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9
hook-owner v2               0c2753a3ced8be7d47b3a6613db0ba59dd55830cb6efa2fa801a0aeb0c0cd22b
hook-owner v3               0ca6d682552c00205d6abd872ddde7a054a6b29f7c9d2c1123757ab6f18e6ccf
awa-contract v1             408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9
finish consumer             299ffa4fbffab7ae1701a47ba1aaffe4c78aecdfbab2ce570fb0cf1ac4d9c132
before-submit hook          d594519c8962a8cdb8d5adc8262a09a61c00ec074317b3d07be144823220da5a
guard hook                  aeee0c147f08976f20ea600d6fd3c891030346554871bdf7f39b6bf1e42baedf
```

## Entry 002 — source and official-contract revalidation

Current Cursor hook documentation was re-read before implementation. It
documents:

- `preToolUse` as a permission hook called before all tools, including Shell,
  Read, Write, MCP, and Task;
- `preToolUse` matcher values including `Shell`, `Read`, `Write`, `Grep`,
  `Delete`, `Task`, and `MCP:<tool_name>`;
- `subagentStart` as a separate deny-capable Task/subagent launch seam;
- `beforeShellExecution`, `beforeReadFile`, and `beforeMCPExecution` as
  deny-capable specialized compatibility seams; and
- crashes, timeouts, and nonzero statuses other than intentional exit 2 as
  fail-open by default when `failClosed:false`.

Body A exposes typed authenticated CONTROL transitions and selected authority;
Body B exposes the closed parser, launch-first policy oracle,
B1/E@R1/B2/R2 admission, deterministic reason renderer, service coordinator,
and fair tick machinery. Body C writes no relation and adds no schema,
trigger, reason, phase, operation, body, alert, or cleanup authority.

## Entry 003 — tests-first RED and initial GREEN

The first Body C-focused run was intentionally RED: the new projection,
hook-runtime, installer, host, hook-owner v4, startup/tick, R0, and Desktop
UAT surfaces did not exist. External-owner v1–v3 compatibility remained
green.

Implemented tests then established:

- exact A22 candidate and DIRECT receipt vectors;
- bytewise-sorted exact inventory/projection hashing and mutation sensitivity;
- CATCH_ALL official-contract/live-discriminator proof versus exact
  ENUMERATED proof;
- ordinary, unknown, renamed, MCP, Task, and `subagentStart` ingress;
- closed deterministic serializers and honest fail-open unavailable paths;
- v4 direct composition with v1–v3 fallback and external zero access;
- installer identity/capability/verified protocol-lock binding;
- journal-free C0–C7 restart, no-last-receiver disablement, cancel versus
  containment, concrete atomic receiver files, and real Body A CONTROL calls;
- A25/A27/A28/A32 provider catalogs; and
- ADR 0020 alert plus guard/finish/cleanup/active-root/kernel-off structural
  independence.

Current provisional focused evidence:

```text
34 core Body C tests: PASS
20 exact projection/concrete cutover tests: PASS
22 hook-owner v1–v4 compatibility tests: PASS
5 packaging/static installer tests: PASS
contract freeze: PASS
```

These are implementation-time results, not post-merge R0, R1, C1, or R2
evidence. `native-entry-durable-registration-r0.py --check` reports
`predeployment_evidence=absent`, `rollout_stage=NONE`, and
`live_state_changed=false`.

## Entry 004 — complete-branch review closure

Bugbot was rerun over the complete staged branch until clean. Eight valid
findings were fixed with focused regressions:

1. Body B basis-policy failures were incorrectly converted to wrapper
   unavailability instead of bounded denials.
2. host-tick freshness compared two different monotonic clock domains.
3. startup/tick could reach durable work before R1/R0 deployment-scope
   preflight.
4. an R0 receipt could load a runtime service and emit a false denial.
5. installed receiver and wrapper/runtime bytes were not remeasured against
   the DIRECT receipt.
6. aggregate status asserted storage readiness instead of using a fresh typed
   Body A profile/free-space read.
7. nested `tool_input` root/identity fields were omitted from Body B's
   multi-source agreement check.
8. a synthetic parser self-test depended on `/fixture/root`; parser readiness
   is now invocation-bound to the real payload that already passed the closed
   parser.

One Bugbot candidate was rejected against accepted authority: v3 §4.11
explicitly assigns malformed, preidentity, and root-cardinality failures to
one fixed stateless denial, so preserving `ROOT_COUNT_UNSUPPORTED` copy at
that preidentity seam would have contradicted the plan.

Subtractive review also connected the C0–C7 file authority to the installed
hook path through a stable receiver router. That router verifies the active
projection, DIRECT receipt, receiver containment/mode/hash, and route before
`execve`. `StoreControlAdapter` now requires the same sealed authorization
and rejects any staged protocol candidate not exactly bound to that receipt.

Final Bugbot: no bugs.

Final Security Review over the same complete topology found no medium, high,
or critical issue. It confirmed external zero access, R0 exclusion, R1
root/member scoping, Task denial before basis/persistence, strict duplicate
rejection, private atomic receipts, receiver/protocol hash binding, and honest
fail-open behavior. No security finding remains.

## Entry 005 — final focused, full, and disposable evidence

Final focused/affected command:

```text
133 tests in 82.647s — PASS
```

It covered Body C modules plus all Body B registration admission, basis,
helpers, independence, runtime/fairness, typed store reads, and rendering
suites. Separate v1–v4 compatibility, C0–C7, R0-check, and Desktop-UAT-check
fixtures also passed.

Final gates:

```text
Python compile + shell syntax                              PASS
canonical SQL SHA-256                                     221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede
contract freeze                                           PASS
install.sh --check                                        PASS
bash engine/tests/run-tests.sh                            PASS
  106 module runs / 1,608 tests / 2,338.679s
make verify                                               PASS / 1,958.471s
  full engine + dashboard + installer + live-verify
make verify-install                                       PASS / 264.539s
  5 installed-guard tests / direct double-install,
  doctor, MCP smoke, uninstall / external
  install-repair-doctor-uninstall zero hook-file access
git diff --check                                          PASS
```

The first full-suite attempt exposed the checker producer hash intentionally
bound by the noexec evidence record; its current-producer field was updated
without changing the historical measured subject. The second attempt exposed
a pre-existing parallel-test race: one guard fault test chmodded the shared
source `awa_policy.py` while installer tests copied it. The fault test now
uses an exact private source copy; the affected tests and the complete
two-worker suite pass. Neither correction changes product guard bytes or
behavior.

The R0 harness and Desktop UAT script were only checked. Final post-merge R0
was not run; `predeployment_evidence` remains `absent` and
`rollout_stage` remains `NONE`. No R1 canary, C1, R2, release, tag, live
install, hook/state/job activation, Skills binding, `~/dev` host wiring, or
cross-repository mutation occurred.
