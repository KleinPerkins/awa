# AWA hook-probe harness

A self-contained, committed, **read-only** Cursor project-hook logging harness.
Its job is to turn the AWA (Agent Worktree Automation) system's load-bearing —
but currently **doc-derived** — facts about Cursor's hook API into
**reproducible, empirical evidence**.

The files in this directory ARE the artifact. Running the harness produces the
evidence; the harness does not fabricate or assume any result.

## What it proves (ledger rows)

Running this harness on a disposable Desktop agent **and** a disposable cloud
agent promotes these ledger rows from `NEEDS RE-VERIFICATION` to
`Verified (probe)`:

- **L3** — the project-hook event set that actually fires on Desktop, and the
  `beforeSubmitPrompt` payload shape (raw prompt text + attachments).
- **L4** — `afterFileEdit` is observation-only: a `permission` returned from
  this POST-action hook is **ignored** by Cursor; `stop` cannot block.
- **L9** — `beforeSubmitPrompt` is **Desktop-only** (absent in cloud).
- **L10** — which events fire in **cloud** (user-level `~/.cursor/hooks.json`
  hooks do not run in cloud; only committed project hooks run; the Desktop-only
  events are absent).

## Files

| File | Purpose |
|------|---------|
| `hooks.json` | Project-hook registration template. Wires one logging command (`probe-hook.sh`) to **every** project-level event, for both Desktop and cloud. Copy into a throwaway repo's `.cursor/hooks.json`. **Not installed anywhere by this repo.** |
| `probe-hook.sh` | The logging command hook. Logs each invocation as JSONL; returns a deliberate `permission` on gating events. Read-only except appending to its own log. |
| `analyze.py` | Read-only, stdlib-only analyzer of the JSONL log. Prints a per-event table + surface inference + the `afterFileEdit` verdict scaffold. |
| `verify-hook-probe.sh` | Static self-check that the three files above are well-formed. Read-only; no git, no temp repos, no live-state probing. |

## Safety

- **Read-only / logs-only.** The only side effect at runtime is appending to
  `${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl`.
- **Self-cleaning:** delete that log file to reset; the harness never mutates
  the repo it runs in.
- **Never blocks real work.** The only `deny` it ever returns is the deliberate
  `afterFileEdit` probe-deny — which the L4 claim says Cursor ignores. That is
  precisely the fact under test.
- **DISPOSABLE ONLY.** Run this in a throwaway repo with a throwaway agent.
  **Never** copy `hooks.json`/`probe-hook.sh` into a governed repo's `.cursor/`.

## How to run it

The log path is shared across runs, so **reset between Desktop and cloud runs**
to keep the surface inference clean:

```bash
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
```

### 1. Disposable Desktop agent

```bash
# In a throwaway local repo (NOT a governed repo):
mkdir -p .cursor
cp /path/to/_ops/awa/hook-probe/hooks.json      .cursor/hooks.json
cp /path/to/_ops/awa/hook-probe/probe-hook.sh   .cursor/probe-hook.sh
chmod +x .cursor/probe-hook.sh
```

Open the throwaway repo as a Cursor agent and **drive each tool once** so every
event fires:

1. Start a fresh agent session          → `sessionStart`, `workspaceOpen`
2. Submit a prompt (with an attachment)  → `beforeSubmitPrompt`
3. Run a shell command                    → `beforeShellExecution`
4. Read a file                            → `beforeReadFile`
5. Call an MCP tool                        → `beforeMCPExecution`
6. **Edit a file, then check whether the edit landed on disk** → `afterFileEdit`
7. Let the loop end                        → `stop`
8. End the session                         → `sessionEnd`

> For step 6, note whether the file actually changed. `analyze.py` needs that
> human observation to render the L4 verdict (the log alone cannot tell you if
> the edit landed).

Then analyze:

```bash
python3 /path/to/_ops/awa/hook-probe/analyze.py
```

### 2. Disposable cloud agent

Cloud agents only run **committed project hooks**, so commit `.cursor/hooks.json`
+ `.cursor/probe-hook.sh` (with the exec bit) into the throwaway repo and launch
a cloud agent against it. Drive the same tools. Because the log lives on the
cloud machine, run `analyze.py` there (or copy the JSONL back) and compare.

Expected cloud delta: the Desktop-only events
(`sessionStart`, `beforeSubmitPrompt`, `beforeMCPExecution`, `stop`,
`sessionEnd`, `workspaceOpen`) do **not** appear.

## Reading the output

`analyze.py` prints:

- **surface** — `Desktop` if any Desktop-only event fired, else
  `cloud (probable)`. This is how L9/L10 are read.
- **per-event table** — `fired` yes/no, invocation `count`, and the union of
  observed stdin field names (this is the empirical L3 payload shape, including
  `beforeSubmitPrompt`).
- **afterFileEdit deny verdict** — combined with your step-6 observation:
  - edit **landed** → deny **ignored** → **L4 confirmed** (obs-only).
  - edit **blocked** → deny **honored** → **L4 refuted** (investigate).

## Mapping back to the ledger

| Row | Evidence from this harness |
|-----|----------------------------|
| L3  | Desktop-run per-event table (which events fired + their stdin fields, incl. `beforeSubmitPrompt`). |
| L4  | `afterFileEdit` fired + returned `deny`, and the operator observed the edit still landed → deny ignored; `stop` fired but did not block. |
| L9  | `beforeSubmitPrompt` present on Desktop, absent on cloud. |
| L10 | Cloud-run table shows only the cloud-available events; Desktop-only events absent. |

Record the two `analyze.py` outputs (Desktop + cloud) plus the step-6 landed/
blocked observation as the evidence when promoting the rows.
