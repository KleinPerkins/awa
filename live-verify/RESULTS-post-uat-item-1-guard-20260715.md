# Post-UAT item 1 — Phase 3 Step 3.2 guard anomaly

Status: **classified outside AWA's executable path; no AWA control change**

## Direct event evidence

Preserved bundle:
`${XDG_STATE_HOME:-$HOME/.local/state}/awa/uat-evidence/phase-3-step-3.2-20260715/`

For the restored-ON command at `2026-07-15T05:13:00.496Z`, Cursor's hook log records:

1. `beforeShellExecution` was requested with the exact rewritten commit command, empty `cwd`, and
   the correct fixture `workspace_roots`.
2. Cursor selected both registered guard commands.
3. Both commands exited in 0–1 ms, emitted no JSON, and reported
   `Shell execution is not available in the worker extension host`.
4. Cursor logged `All hooks ... completed but none returned a valid response`.
5. The agent-exec log recorded `hookForcesPrompt:false` and auto-approved the tool call.
6. The fixture reflog and Git observation log record the resulting commit.

The same worker-host error affected every command hook in that conversation before the shell call:
all six `sessionStart` commands, the `beforeSubmitPrompt` command, and later unrelated `stop`
commands. This cross-hook failure is direct evidence that the AWA scripts were not entered. No AWA
permission response exists for the event.

Cursor's current hook documentation states that hook failures proceed fail-open unless
`failClosed:true` is configured: <https://cursor.com/docs/hooks>. AWA intentionally configures this
global shell hook fail-open because a failed global fail-closed hook previously blocked all shell
workspaces. The product's guaranteed floor remains detection and cleanup refusal.

## Controlled checks

- The exact empty-`cwd` + `workspace_roots` fixture still returns `deny` from the real bash guard.
- A new regression invokes the real guard twice with identical conversation/session fields while
  changing only the modes file from OFF to ON. It returns `allow`, then `deny`, proving AWA has no
  conversation-local mode cache and resolves current policy on every process invocation.
- In a fresh Local conversation on the same Cursor 3.11.19 installation, the Cursor hook log
  recorded the installed guard returning valid `deny`; Cursor blocked the primary-checkout command.

Focused command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest \
  engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_empty_cwd_falls_back_to_workspace_roots \
  engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_same_conversation_mode_transition_is_rechecked
```

Result: **PASS**

## Bounded conclusion

The directly supported immediate cause is Cursor's inability to execute any command hook in that
conversation, followed by Cursor's documented fail-open behavior. The evidence does not explain why
shell execution became unavailable in the worker extension host. Live same-chat Desktop
reproduction is unavailable to this remediation run, so that platform-internal trigger remains
unproven. No AWA guard change can run before a host that never starts the guard; changing the global
registration to fail-closed would reintroduce the known machine-wide brick risk and is rejected.
