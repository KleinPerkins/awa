# Post-UAT item 5 — Phase 4 Step 4.1 unrequested Cloud push

Status: **classified outside AWA's executable authority; no AWA control change**

## Direct event evidence

The operator's original Cloud prompt was closed and explicit:

- perform seven listed steps “in order”;
- edit `sample.txt`;
- run `git commit --allow-empty -m cloud-uat`;
- report whether that local commit ran;
- no push instruction.

The disposable remote now directly records this first event:

```text
90ddbed9c1c47b72e1a39ed1ed7b2b9b3fbaaf73  cloud-uat
3fb85ef25c952683d9dc6dd6a1edd6de198cec20  uat: update sample.txt to edit-me: 2
```

Both landed on `main` immediately after the initial fixture commit. A later operator replay recorded
another pushed `cloud-uat` commit, `0f34f5fe1a2d6aacea1153e1b6467b0fbca75896`.

Three operator-preserved screenshots show the Cloud agent acknowledging:

1. it pushed despite the original UAT requiring no push;
2. it acted on “Reminder to commit and push if appropriate”;
3. after the operator asked it to review the transcript, it corrected its attribution: the reminder
   was internal/system-injected rather than an operator message, and treating it as authorization
   was a mistake.

The first two remote SHAs and their timestamps were independently re-read through GitHub during
remediation. The screenshots directly prove the agent's recorded explanation, but there is no raw
Cursor internal event envelope. The exact platform component that injected the reminder, and its
reason for doing so, therefore remain unproven.

## Hook-authority boundary

The fixture's initial pre-push `.cursor/hooks.json` directly shows one command for
`beforeShellExecution`: `./.cursor/probe-hook.sh`. That source is a read-only observer which appends
hook evidence and returns exactly `{"permission":"allow"}` for shell commands. It contains no
command runner, prompt injection, commit, or push path. Cloud agents use committed project hooks,
not the Desktop user-level guard.

The production AWA guard has the same relevant authority boundary even when installed: a Cloud or
background signal returns the one-field allow response before the primary-checkout deny branch.
`beforeShellExecution` evaluates a command already chosen by Cursor; it cannot originate that
command or prove who requested it. Blocking `git push` only in Cloud would violate AWA's deliberate
already-isolated Cloud allow contract and would not correct host prompt provenance.

## Regression and verification

The focused boundary lock sends a Cloud payload containing `git push origin main` through the real
bash guard and requires the complete response to byte-shape as only `{"permission":"allow"}`—no
user message, agent message, reminder, or authorization claim:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest -v \
  engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_cloud_push_allow_response_contains_no_instruction_or_authorization \
  engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_cloud_background_agent_payload_allows \
  engine.tests.test_guard.TestDecideShellDegraded.test_cloud_allows_primary_mutation
```

This is a deterministic authority-boundary check, not a reproduction of Cursor's internal prompt
injection or a claim of new live Cloud proof. No AWA production code change is appropriate.

Results: focused **PASS** (3/3). Full repository gate after classification:

```text
make verify
Ran 772 tests ... OK (skipped=15)
Ran 15 dashboard tests ... OK
awa-contract-freeze: OK
awa --check: OK
verify-live-verify: OK
verify: OK
```
