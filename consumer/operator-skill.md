# AWA operator loop (consumer of the intent-router) — thin skill/rule

This is the agent-facing entrypoint for AWA's operator loop (phase A0). It is deliberately thin: the
substance lives in `consumer/operator_loop.py` (the loop), `consumer/translators.py` (plain-language
rendering), and the KERNEL (`kernel/lib/awa_consequence.py`, the consequence source). This document is
a maintainer/agent rule, not a PM-facing surface — so it may name mechanism.

## When to use

When a non-technical operator speaks a request about protecting / checking / resuming / saving /
cleaning up their work, run ONE turn of the loop rather than translating their words into a raw
command yourself.

## The loop (never skip a step, never reorder)

1. **hear** — take the operator's exact words. Do not paraphrase into a verb yourself.
2. **map** — `OperatorLoop.map(utterance)` asks the router to PROPOSE (read-only). The router never
   executes and never authorizes.
   - If the router is not installed, `map` returns `None` and the loop DEGRADES to ask + the
     secondary explicit path (the five plain options). Never guess a destructive action.
3. **confirm-consequence** — the confirmation is sourced from the KERNEL consequence descriptor
   `{destroys_unshared_work, irreversible, affects_shared_ref}`, computed from the LIVE target, never
   from the router and never from a static verb list. A safe-looking verb with a destructive
   consequence MUST confirm; a benign verb MUST NOT nag.
4. **execute AWA's OWN verb** — only after the confirmation gate passes. The loop runs an AWA verb;
   it NEVER runs anything from the router's output.
5. **verify-real-outcome** — check the verb actually did what it claimed.
6. **narrate** — report what ACTUALLY happened in plain language, with honest confidence ("what I
   checked and what I couldn't"), zero banned terms — never a bare green pill.
7. **record-feedback** — emit an `intent-feedback/v1`-shaped record (not persisted in A0).

## Hard rules

- The router PROPOSES; AWA verbs EXECUTE; the KERNEL sources every consequence confirmation.
- Kernel-first / off-switch: everything here degrades safely when the router is uninstalled, and the
  kernel guard/refuse/audit path is never on the router's critical path.
- Every operator-facing string is jargon-free (zero Tier A/B/C banned terms) and honest about
  confidence. The egress gate (`consumer/egress.py`) and its tests enforce this.

## Programmatic entry

```python
from consumer.operator_loop import OperatorLoop
loop = OperatorLoop(catalog)              # router resolved lazily; degrades to ask if uninstalled
result = loop.handle(utterance, target=resolved_target, facts=kernel_facts, confirm=None)
# result["decision"] in {execute, awaiting_confirmation, need_more_info, degraded_to_ask, not_understood}
```
