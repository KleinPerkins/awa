# Native Codex C-Bounded Evidence-Capture Consequence Preview

- **Version:** v1
- **Status:** DRAFT — D0 SELECTED; BUNDLE PREPARATION, LIVE CAPTURE, HOST CHANGES, AND IMPLEMENTATION NO-GO
- **Date:** 2026-10-29
- **Relates to:** draft
  [ADR 0029](../adr/0029-native-codex-interoperability-boundary.md) and draft
  [Native Codex Interoperability v1](native-codex-interoperability-v1.md)
- **D0 direction:** `EVALUATE_C_BOUNDED`, selected against ADR SHA-256
  `39b468d12e3808b5679fa658f396403541794f24d223e49641df4824f871d5f1`
  and plan SHA-256
  `96a40f76b483afa56aafdc78061cab42408d918af8c9636f8e082c81cdeb4c88`
- **Preparation baseline:** AWA `main`
  `e68c6be90e132629e0c78d80d31f6bcc95623d51` (PR #186)
- **Plan type:** consequence preview for separately consented evidence capture;
  no architecture, capture, product/runtime implementation, or capture-tool
  source-preparation authority

**Purpose:** Make the minimum C-Bounded native-host evidence operation concrete
enough for consequence review without touching live Codex configuration, hook
trust, credentials, transcripts, work data, AWA state, or product behavior.

> **Current stop:** D0 authorizes this preview only. It does not authorize the
> inert harness bundle, a temporary fixture, hook/config bytes, trust review,
> restart, chat/session creation, capture, network use, subagents, races,
> archive/delete/restore, results publication, AWA registration, protection,
> exact `Close`, ADR 0026 activation, or product implementation.

Here, `subagents` means the future native capture scenario in Batch B. It does
not describe the separately authorized, read-only document-review workers used
to test this preview.

---

## 1. Authority and verified basis

### 1.1 What D0 selected

The owner selected **Evaluate bounded registration evidence**. That maps only
to `EVALUATE_C_BOUNDED` in the merged plan. It authorizes preparation of this
consequence preview. It does not select C-Bounded at D1, accept ADR 0029 or its
plan, accept reduced protection, or authorize any operation listed below.

The unrelated INT008 protected-config-backup exception is explicitly rejected
for this work. Nothing in this preview reads, copies, hashes, backs up, restores,
or mutates a live user configuration, credential, transcript, or general host
state.

### 1.2 Read-only preparation record

| Surface | Observed state |
|---|---|
| Canonical owner | `git@github.com:KleinPerkins/awa.git` |
| Live base | `origin/main` = `e68c6be90e132629e0c78d80d31f6bcc95623d51` |
| Workspace | Attached native linked worktree on a dedicated docs branch; clean before this document; unique writer lease |
| Host/AWA state | Standalone advisory classification; native attachment is not AWA registration or protection |
| Frozen authority | ADRs 0020, 0024, and 0026 remain unchanged; ADR 0029 and its plan remain draft |
| Codex hook contract | Official documentation rechecked 2026-10-29; no live hook/config source inspected |
| Capture | Not run; no payload, transcript, raw identifier, tool input, settings, hook trust, or AWA state observed or written |

Official Codex documentation currently says project-local hooks may live at
`<repo>/.codex/hooks.json` or `<repo>/.codex/config.toml`, require trust of the
exact non-managed hook definition, run with the session `cwd`, and load only in
a trusted project layer. It also says multiple sources compose, hook errors may
fail open, `write_stdin` receives no new `PreToolUse`, hosted/specialized paths
can be uncovered, and `SessionEnd` is advisory. Those facts constrain this
preview; they do not prove delivery or safety.

## 2. Minimal capture topology

The future capture, if separately approved, uses one purpose-built disposable
Git repository containing synthetic files only. It does not use the AWA repo,
another work repo, a primary checkout, or user-level Codex configuration.

The preferred topology is:

```text
proposed private temporary parent (exact absolute path bound at CP1)
└── awa-codex-capture/<operation-id>/              0700
    ├── fixture/                                   0700; disposable Git repo
    │   ├── .codex/hooks.json                      0600; rendered exact bytes
    │   ├── .codex/hooks/capture_hook.py           0600; invoked by python
    │   └── synthetic/                             0700; fixed non-sensitive files
    └── capture/                                   0700
        ├── manifest.json                          0600
        ├── ledger.ndjson                          0600
        ├── export.json                            0600; canonical sanitized result
        ├── labels.json                            0600; ephemeral equality map
        ├── salt.bin                               0600; ephemeral run key
        └── capture.lock                           0600
```

CP1 must name a proposed absolute parent and operation root, render the exact
hook/config bytes against that proposed path, and present their SHA-256 digests
before any allocation or write. Existence is not required to compute those
proposed bytes. Immediately before a later approved write, the operation must
recheck the parent's identity, ownership, mode, ancestor chain, and exact path
preimage. Any mismatch invalidates the approval and requires a refreshed CP1
preview. The accepted parent must have no group/other-writable ancestor;
`/private/tmp` is not acceptable because it is `01777`. The absolute root is
never written into the sanitized export.

The CP1 approval conversation necessarily retains the proposed absolute root,
rendered hook/config bytes, and their digests outside capture-root cleanup. The
path must be non-identifying and high-entropy where practical; neither it nor
the rendered bytes may contain a credential or work-data value. No transcript
purge is claimed.

Project-local `hooks.json` is preferred over user-level config because it
limits discovery to the disposable fixture. Inline `config.toml`, plugin
hooks, managed hooks, and `--dangerously-bypass-hook-trust` are prohibited.
No config representation is merged with an existing one. Because documented
hook sources compose, CP2-T must use the supported hook browser to confirm the
exact active source set without reading or copying live config bytes. Any
additional active source or unresolved source identity aborts qualification as
`FAILED_EVIDENCE`; the operation never disables or edits that other source.

## 3. Proposed AWA-owned inert bundle

The following repository paths are the complete proposed bundle. They do not
exist in this preparation body and may not be created without **CP0**:

```text
live-verify/codex-native-capture-v1/README.md
live-verify/codex-native-capture-v1/capture_hook.py
live-verify/codex-native-capture-v1/verify_capture.py
live-verify/codex-native-capture-v1/capture-schema.v1.json
live-verify/codex-native-capture-v1/scenario-catalog.v1.json
live-verify/codex-native-capture-v1/forbidden-fields.v1.txt
live-verify/codex-native-capture-v1/fixture-hooks.v1.json.in
live-verify/codex-native-capture-v1/MANIFEST.sha256
```

All files are regular mode `100644`. The hook is invoked through an exact
interpreter command and is not executable. `MANIFEST.sha256` covers every other
file in byte-sorted path order. `fixture-hooks.v1.json.in` contains exactly one
render token for the later absolute capture-hook path. No environment expansion,
shell lookup, home-relative path, plugin, MCP hook handler, or user config path
is allowed.

CP0 would authorize only capture-tool source preparation: authoring, reviewing,
committing, pushing, and delivering these inert repository bytes through a
non-draft PR and the normal verifier/reviewer-App merge process. That is not
product/runtime implementation and does not authorize copying the bytes to a
host fixture, trusting them, or running them. After CP0, a later **CP1** preview
must name a proposed absolute root, render the one token without allocating
that root, show the exact resulting
bytes and SHA-256 digests, and request permission before any allocation or host
write. Execution must then revalidate the proposed path and every bound
preimage as required by §2; it may not substitute a newly resolved path.

This two-step boundary preserves the D0 docs-only/source-implementation stop:
CP0 produces the reviewed source bytes; CP1 binds their exact proposed host
representation and consequences before any host state exists.

## 4. Closed sanitized record

### 4.1 Event row

The exported `awa-codex-capture-event/v1` object has only these keys:

```text
schema                       literal awa-codex-capture-event/v1
run_label                    closed non-identifying label, e.g. C1
scenario_id                  value from the frozen catalog
sequence                     positive run-local integer
event_name                   frozen Codex event enum
source                       frozen documented enum or null
session_label                S1..Sn; never the raw session id or its digest
turn_label                   T1..Tn or null; never the raw turn id or its digest
root_label                   R1 | SUBDIR | CHANGED | MISSING | AMBIGUOUS
identity_presence            closed presence/type/length-bucket object
tool_class                   frozen catalog enum or null
tool_discriminator           frozen catalog literal or null
hook_outcome                 OBSERVED | DENIED | ERROR | TIMEOUT | MALFORMED | ABSENT
ordering_counter             positive run-local integer
timing_bucket                LT_10MS | LT_100MS | LT_1S | LT_5S | GTE_5S
process_exit_class           ZERO | TWO | OTHER | SIGNAL | TIMEOUT | NOT_APPLICABLE
```

No free-text value is accepted. Length buckets are `EMPTY | 1_64 | 65_256 |
257_4096 | OVER_4096`, never exact lengths. Tool discriminators are exact
catalog literals; unknown names become `UNKNOWN`, not copied strings.

### 4.2 Equality labels

Each command-hook process receives raw JSON on stdin but must never copy stdin,
stdout, stderr, or a decoded raw field to disk. `session_id` and `turn_id` are
converted in memory to keyed HMACs using the run-only `salt.bin`; `labels.json`
maps only those HMACs to sequential labels. Neither HMAC nor salt is exported.
The root relationship is calculated against the hook's own fixture location and
stored only as the closed `root_label`; no absolute path or path digest is stored.

Before reading stdin, the hook disables core dumps. Stdout contains only the
fixed documented hook response; stderr is empty or a closed value-free code.
Raw payloads and decoded values never enter tracebacks, exception text, argv,
environment, filenames, diagnostics, or logs.

`salt.bin`, `labels.json`, and all unsanitized process memory are capture-root
ephemera. Cleanup deletes them before any result is copied to the AWA repo.

### 4.3 Scenario-ledger row

Every planned action has one `awa-codex-capture-scenario/v1` row containing:

```text
schema, run_label, scenario_id, scenario_action_sha256,
pre_barrier_id, post_barrier_id,
expected_event_counts, observed_event_counts,
harness_health, hook_content_sha256, config_template_sha256,
rendered_config_stability, action_witness, positive_control_route_match,
process_exit_class, completion_status
```

All values are closed enums, counters, or hashes of reviewed synthetic bytes.
The action digest never covers a raw prompt, transcript, path, identifier, tool
input, credential, environment, URL, or host response. Exact rendered-config
digests remain capture-root ephemera because the rendered bytes contain the
private absolute hook path. The export records only `MATCH | MISMATCH |
UNAVAILABLE` for `rendered_config_stability`; `config_template_sha256` covers
only reviewed repository bytes.

Ledger and equality-map updates serialize under `capture.lock`.
`ordering_counter` records callback observation order only; it never claims
host execution order. After validation, the verifier emits exactly one
canonical `export.json` that hash-binds every accepted row plus all reviewed
input digests. Only that file, at an exact path and SHA-256 named by CP6, can be
copied out of the capture root.

### 4.4 Forbidden persistence

The harness and verifier must reject output containing any of:

- prompt text, model text, transcript content or transcript path;
- tool input, tool output, command text, patch text, attachments, or arbitrary
  URLs;
- raw or hashed session/turn/tool-use/agent identifiers in the export;
- absolute paths, user identity, environment, process arguments, credentials,
  tokens, cookies, keys, auth state, or host config bytes;
- work repository names/content, memory records, or raw hook logs; or
- unknown keys, free-text reason strings, non-finite numbers, duplicate keys,
  oversized records, symlinks, special files, or non-owned output.

The verifier scans the parsed closed schema and raw serialized export with the
frozen forbidden corpus. Any hit makes the entire run unusable and blocks copy.

## 5. Negative-evidence controls

An absent callback is evidence only when all of these are true for the exact
scenario:

1. a controller outside the callback under test committed and fsynced a
   run-local nonce plus the frozen catalog-row digest before the action;
2. that controller invoked the action or confirmed its bounded host terminal
   result, then committed the same nonce and a closed terminal outcome;
3. the exact hook/template hashes match the manifest and the ephemeral rendered
   config reports `MATCH` before and after the action;
4. a known-positive control on the same session and hook event/matcher route
   succeeded immediately before and after;
5. every expected callback count reconciles with the observed count;
6. a durable post-barrier was committed only after action cleanup;
7. no capture process, child, lock holder, or partial file survived; and
8. the scenario set equals the accepted catalog exactly.

Missing barriers, hook/config drift, unhealthy probes, count mismatches,
timeouts, host uncertainty, or incomplete cleanup yield `FAILED_EVIDENCE`.
Missing or mismatched controller witness yields `UNPROVEN`. Neither state can
establish `NO_AWA_COVERAGE` from absence alone.

Where the required same-session, same-route positive control is impossible,
absence is always `UNPROVEN`; only an unexpected observed callback is usable.
For `C07` and `C08`, only host-originated callbacks from catalogued actions are
evidence. Direct hook invocation, duplicate hook registration, controller
replay, or ledger injection tests the harness only and cannot populate D2/D3.
Observation order never proves host total order.

## 6. Separately consented scenario batches

### Batch A — local non-destructive delivery

Proposed scenarios use fixed synthetic data only:

- `A01` new fixture chat/session start (`startup`);
- `A02` first `UserPromptSubmit` with the literal synthetic prompt
  `AWA-CODEX-CAPTURE-A02`;
- `A03` later prompt with `AWA-CODEX-CAPTURE-A03`;
- `A04` one-shot Bash command that writes only a fixed fixture file;
- `A05` unified exec that completes without an input-capable handle;
- `A06` unified exec returning a handle, followed by empty polling only;
- `A07` `apply_patch` against one fixed synthetic file;
- `A08` one exact harmless local function tool from the frozen catalog; and
- `A09` one hosted tool expected to have no local hook coverage.

Creating a fixture chat and submitting prompts necessarily uses ordinary Codex
service traffic. CP2-A permits only that baseline traffic. Hosted-tool use adds
tool-specific service/auth consequences and therefore requires separate
CP2-HOSTED consent even if other Batch A scenarios are accepted.

### Batch B — lifecycle and placement

- `B01` manual or automatic compact, separately identified;
- `B02` resume the exact fixture chat;
- `B03` fork the fixture chat;
- `B04` fixture cwd at root and `B05` cwd in a synthetic subdirectory;
- `B06` local-to-native-worktree handoff and `B07` return;
- `B08` create a local fixture branch only;
- `B09` one subagent start/stop with fixed synthetic task text;
- `B10` interrupt, `B11` stop, and `B12` observed `SessionEnd`.

Each host/session action is separately visible in the approval payload. No work
repo, primary checkout, or unrelated chat participates.

### Batch C — uncovered input, failure, and race

- `C01` non-empty `write_stdin` to an input-capable fixture process; expected
  classification from the documented contract is `NO_AWA_COVERAGE`, but any
  live claim remains subject to §5;
- `C02` disabled project hook, `C03` timeout, `C04` malformed response, and
  `C06` async hook;
- `C07` duplicate delivery, `C08` reordered lifecycle events, and `C09`
  bounded concurrent synthetic actions.

`C05` remains a documentation-only `NO_AWA_COVERAGE` classification for a
missing MCP server/tool. This bundle contains no MCP server, handler, or config;
CP4 cannot execute `C05` or turn it into a live-capture claim. Any future MCP
scenario requires a new exact artifact preview and independent gate.

Batch C requires its own failure/race GO. It may not reuse Batch A or B consent.
No timeout or malformed case may touch user config, a real MCP server, or work
data.

### Batch D — archive, host deletion, snapshot, and restore

- `D01` archive the disposable fixture chat;
- `D02` permit host deletion of only the disposable native worktree;
- `D03` observe the host snapshot offer; and
- `D04` restore only that disposable snapshot.

Batch D is destructive to the disposable host surface and requires exact
separate consent. It never calls AWA `Close`, never reports AWA removal, and
never includes this owner worktree or another live repository.

## 7. Host/session consequences

Even a sanitized harness has host-side consequences that the harness cannot
erase:

- Codex will show a trust review for the exact non-managed project hook hash;
- the fixture chat transcript contains the fixed synthetic prompts and actions;
- Codex may retain chat metadata, hook-trust metadata, tool history, and native
  worktree/snapshot metadata outside the capture root;
- project-local hook discovery may require a new session; restart is not assumed
  and is a separate gate if discovery fails;
- the hosted scenario uses the exact separately approved networked service;
- subagent/fork/handoff/interrupt actions change fixture-session topology; and
- archive/delete/restore may trigger `SessionEnd` and host snapshot retention.

The official hook contract documents `/hooks` review/trust/disable, but it does
not document a byte-level purge operation for persisted trust metadata. This
preview therefore cannot promise full trust-record rollback. A later GO must
either accept the residual inactive hash record or first authorize a documented,
read-only cleanup investigation. Reading/copying live config or credentials is
not an acceptable workaround.

## 8. Cleanup and rollback

Every CP1-or-later payload names a controller outside the fixture session, its
exact cleanup verifier, a retention deadline, and the disposition for every
possible residual. Terminal lifecycle scenarios run last. For an approved
batch, cleanup order is fixed:

1. stop new scenarios and wait for bounded capture children;
2. write the scenario post-barrier only if counts and process cleanup reconcile;
3. disable the exact project hook through the supported hook browser before
   deleting its bytes;
4. run the offline verifier over the closed sanitized export;
5. if CP6 separately approves a resolved destination filename and exact
   `export.json` SHA-256, copy only that canonical verified file;
6. delete the disposable fixture repository, capture directory, salt, label map,
   locks, rendered config, and hook bytes by their exact resolved paths;
7. verify the private temporary parent has no remaining run entry or process;
8. leave the owner worktree clean and release its writer lease; and
9. handle fixture chat archive/delete/restore only under Batch D consent.

If hook disablement, verifier completion, path identity, ownership, process
cleanup, or deletion is uncertain, quarantine the exact root at `0700`, block
CP6, and report the exact residual before the named retention deadline. A new
operation-bound cleanup preview and consent is required; no success or deletion
is inferred. Never broaden deletion or use AWA `Close`.

## 9. Consent map

No row implies another:

| Gate | Exact later authority | Excluded consequences |
|---|---|---|
| **CP0** | Author/review the inert eight-file capture-tool source bundle; commit, push, open a non-draft PR, and proceed through normal verifier/reviewer-App merge | No host temp root, hook/config write, trust, execution, capture, or product/runtime implementation |
| **CP1** | Bind one proposed absolute private temp root and the exact rendered project-local bytes/digests; after approval, revalidate the bound path/preimages, allocate that root, and initialize the synthetic fixture repo without trusting/running the hook | No substituted path, hook execution, chat, restart, capture, or network |
| **CP1-CLEAN** | Delete only the exact untrusted CP1 fixture/root after identity, ownership, and process checks | No hook-browser/trust change, chat deletion, broader temp cleanup, or AWA Close |
| **CP2-T** | Review the active source set in the supported hook browser and trust only the exact rendered hook definition | No chat, execution, capture, or change to another hook source |
| **CP2-A** | Create one fixture chat and run only the explicitly selected A01–A08 IDs, with ordinary Codex service traffic | No hosted/MCP tool traffic, restart, subagent, races, or Batch D action |
| **CP2-HOSTED** | Run only A09 using the exact hosted tool ID, fixed input, service/auth posture, and network consequence named in that approval | No MCP tool, unrelated service, credential change, or other scenario |
| **CP2-CLEAN** | Disable the exact project hook and perform only the named bounded cleanup | No trust-record purge, fixture-chat deletion, broader host deletion, or AWA Close |
| **CP3** | Run the individually selected Batch B scenarios | No failure/race or Batch D action |
| **CP4** | Run the individually selected executable Batch C scenarios; C05 remains documentation-only | No MCP fixture, work data, user config, or destructive host lifecycle |
| **CP5** | Run the individually selected Batch D scenarios on the named fixture only | No AWA Close or other repo/chat/worktree |
| **CP6** | Copy one verifier-approved canonical export whose exact SHA-256 and resolved AWA destination filename are in the approval; deliver its PR | No templated path, architecture/profile/plan acceptance, or implementation GO |
| **CP7** | Accept D2/D3 adjudication against exact result hashes | No D1 selection or source implementation |

Any restart, user-level setting/config edit, install, plugin change, live config
inspection, trust-record cleanup research, app update, auth prompt, or new tool
outside the catalog gets a new operation-bound preview and consent.

## 10. Current decision frontier

This document does not request capture GO. The next separately approvable
decision is only:

```text
CP0 — authorize capture-tool source preparation at the exact eight repository
paths in §3, including independent review, commit, push, non-draft PR, and the
normal verifier/reviewer-App merge process.
```

The approval payload must bind this preview's exact SHA-256, baseline OID, and
all eight paths. Any change voids that CP0 payload and requires a refreshed
request. The paths and constraints are exact now; the file bytes are the CP0
deliverable and are not being pre-approved before they exist.

If CP0 is declined, no additional file or host state changes. If CP0 is granted,
the bundle must be delivered through its own ready PR and verifier/reviewer-App
process. CP1 cannot be requested until CP0 bytes and manifest hashes are merged
and this preview is refreshed against that exact revision.

Architecture acceptance, D1 C-Bounded selection, reduced-protection acceptance,
live capture, hook/config trust, restart, installation, AWA state, registration,
protection, exact `Close`, ADR 0026 activation, and product implementation remain
**NO-GO**.

