# Native Codex capture-tool source bundle v1

CP0 source preparation only. These eight regular, non-executable files are not
installed, connected to hooks, or exercised by the repository test suite.

Authority: `docs/plans/native-codex-bounded-evidence-capture-preview-v1.md`,
SHA-256 `21af39a50ad2d098e12db464ee6dee5e9ac7d255d64ed6b728955bfbd468a710`,
baseline `e68c6be90e132629e0c78d80d31f6bcc95623d51`. The preview merged in PR
#187 at `57fb1355163cc9c6a569330dd0828468d666535e`. CP0 permits source preparation,
independent review, commit/push and normal reviewer-App delivery. It does not
permit execution of these tools, fixture allocation, hook trust, live capture,
or later consent gates. Static parsing/hashing is not a live capture claim.

## Contents

- `capture_hook.py`: fixed, quiet observer; no tool denial, command execution,
  network, environment lookup, transcript access, installation or config discovery.
- `verify_capture.py`: offline verifier of one already-approved disposable run;
  emits one canonical export, never executes scenarios or approves later actions.
- `capture-schema.v1.json`: closed record types and bounded values.
- `scenario-catalog.v1.json`: fixed action identifiers and closed event, source,
  tool, root and session predicates; no raw prompts/tool inputs.
- `forbidden-fields.v1.txt`: additional serialized-export deny corpus.
- `fixture-hooks.v1.json.in`: exactly one token occurrence for the absolute hook
  path in a seed handler. The pure `render_config` function replaces it once and
  expands that seed across the twelve frozen events for the later CP1 preview.
  It is not active configuration.
- `MANIFEST.sha256`: every other file, in byte-sorted relative-path order.

Current source targets the already-present `/usr/bin/python3` (Python 3.9+).
The exact command uses `-I -S -B`: isolated imports, no site startup, no bytecode.
The hook and verifier refuse execution without those flags. No install or
PATH-based interpreter selection is included. The verifier loads only the
manifest-checked sibling core, never an ambient module with the same name.

## Later fixture contract (CP1 is still required)

CP1 must show the proposed absolute operation root, its parent's descriptor and
ancestor preimages, exact rendered bytes and digests before allocating anything.
Require an owned private parent with no group/other-writable ancestor. Each path
component must use only ASCII letters, digits, dot, underscore or hyphen; no
symlink, traversal, whitespace, shell substitution or environment expansion.
Immediately recheck all preimages before any approved write; a mismatch stops.

Only after CP1 approval, an external controller may create the preview's fixed
layout. The hook resides at `fixture/.codex/hooks/capture_hook.py`; the capture
directory is its operation-root sibling. Directories are `0700`; all capture
files, rendered config and hook are `0600`, owned by the current user, with one
link. No path is resolved from cwd, an environment variable, raw hook input or
an argument supplied to the hook. None of these files is created by the hook.

The controller supplies `manifest.json` with exactly these fields:

```text
schema = awa-codex-capture-run/v1
run_label = C1..C999
scenario_ids = approved, unique catalog IDs in catalog order
input_sha256 = map of the seven source paths to MANIFEST.sha256 values
hook_content_sha256 = exact installed hook digest
rendered_config_sha256 = exact private rendered config digest (never exported)
config_template_sha256 = source template digest
expected_event_counts = selected scenario ID -> 1..8 distinct exact count maps
each count map = all twelve event names -> count
control_event_names = selected scenario ID -> nonempty event-route list
```

`salt.bin` contains 32 random bytes. `labels.json` starts as `{"session":{},"turn":{}}`.
`ledger.ndjson` starts empty. `capture.lock` must remain empty on every read.
`export.json` is not
created until verification; an existing export is never overwritten.

This source bundle deliberately provides no fixture installer, configuration
writer, host-action runner or approval parser. Their exact future commands and
bytes belong to the CP1 operation preview. Operator consent is not inferred
from a manifest, cwd, process identity, file ownership or these helpers.

## Witness protocol

An approved external controller, outside the fixture session, serializes its
witness records with the same exclusive `capture.lock` as the hook. It appends
one canonical JSON line, fsyncs the ledger, and releases the lock after each
transition. All witness values are reviewed synthetic enums/counters/digests.

A `pre` record has exactly:

```text
kind = pre; scenario_id; nonce = 32 lowercase random hexadecimal characters
action_sha256 = SHA-256 of canonical catalog row (sorted keys, compact UTF-8)
manifest_sha256 = SHA-256 of exact private CP1-approved manifest bytes
```

It opens `BEFORE`. After the before-controls complete, a `phase` record containing
exactly `kind = phase`, `scenario_id`, `nonce`, `phase = ACTION`, and
`session_label = S1..S2048 | null` opens the action window and seals its session.
A second phase record with `phase = AFTER` and the same session opens the
after-controls.
Both transitions are mandatory, including when controls are unavailable. Only
ACTION callbacks must match exactly one of the approved count maps; before/after
callbacks remain in the event export as positive controls. Timing buckets measure
this observer's processing interval, not host-action latency.
Control-route lists are frozen in CP1's manifest too; C05 alone has an empty list.

Only one scenario may be active. The nonce is generated independently of hook
callbacks and stays private. The controller invokes the approved catalogued host
action, observes its bounded terminal outcome independently, and appends `post`:

```text
kind = post; scenario_id; nonce; action_sha256; manifest_sha256
terminal = COMPLETED | FAILED | TIMEOUT | UNKNOWN
origin = HOST | HARNESS
health = SAME_ROUTE | UNAVAILABLE
config_stability = MATCH | MISMATCH | UNAVAILABLE
children_clean = true | false
process_exit_class = ZERO | TWO | OTHER | SIGNAL | TIMEOUT | NOT_APPLICABLE
action_session_label = same sealed phase label
control_sequences = each declared route -> {before: event sequence, after: event sequence}
```

`SAME_ROUTE` means matching positive controls immediately before and after the
action, on the same session and event/matcher route. The controller must actually
observe both. The verifier requires exactly one before/after callback per route,
the exact sealed sequence pair and action session, and verified fixture cwd.
Control routes must belong to the catalog scenario (the disabled-hook C02 uses
the three tool events), and every observed action route must have both controls
before harness health can be HEALTHY.
Every action callback must match its catalog event/source/tool/root predicate.
`SAME` rows also require the sealed session; `OBSERVE` rows always keep coverage
and harness health unproven because lifecycle transitions can change sessions.
Only lexical fixture paths whose no-follow descriptor matches the command cwd
descriptor yield R1/SUBDIR; all unresolved or outside relations are AMBIGUOUS.
One-sided lifecycle routes and hosted tools that cannot satisfy
this condition always use `UNAVAILABLE`; absence is `UNPROVEN`. Controller replay,
direct hook invocation, duplicate registration and ledger injection use `HARNESS`
and cannot support D2/D3. The nonce and descriptor/config preimages are never
copied into the export. Witness JSON is not a cryptographic attestation of host
behavior; D2/D3 require separately consented review of controller evidence.
The private manifest digest is also omitted from the export. It is compared
against every pre/post witness on every read, so changing counts, routes or the
selected scenario set after a witness invalidates the entire run. The external
controller must first compare those bytes with the exact CP1-approved preimage.
CP1 must bind every alternative in each closed outcome set before the action,
including any allowed unexpected positive callback. The export's existing
`expected_event_counts` field is the matching preapproved map, selected by exact
equality with observations. It is not an expectation inferred after the run;
the private sealed manifest is required to audit its membership. Any count map
outside that set fails. The all-zero branch stays UNPROVEN, and C05 permits
only one all-zero map. No ranges or post-run alternatives are accepted.

Hook rows are generated only while a `pre` has no matching `post`. `sequence`
and `ordering_counter` are serialization/observation order, never host total
order. All state updates occur under the same lock and are fsynced. Any partial
write, malformed state, duplicate key, unexpected key or sequence gap makes the
run invalid; the hook remains quiet, and missing positive controls/counts cannot
be converted into a coverage claim.

Witness appends follow `pre -> phase ACTION -> phase AFTER -> post` without
interleaving another scenario. `C05` may be selected for a documentation-only
export row, but never receives a live witness. A scenario's allowed exact counts are
part of CP1's exact manifest bytes and cannot be inferred or adjusted after a run.

## Verification and limits

After separately approved hook disablement, process cleanup and deletion of
`salt.bin`/`labels.json`, the offline verifier can read the run and write
`capture/export.json` exclusively. It checks its source manifest, source/data
containment, exact selected scenario set, action witnesses, config stability,
counts, closed record constraints and deny corpus. The Python validators are
authoritative for cross-row and count equality; the JSON Schema mirrors the
closed export shape and representable within-row relationships. Neither a
schema-only pass nor a structurally valid ledger establishes host execution.
It refuses a run with unexpected
files, incomplete witnesses, surviving ephemera, non-host witnesses or failed
cleanup. It exports only source digests, event rows and scenario rows; no rendered
config digest, path, nonce, raw ID, HMAC, salt, prompt or tool input/output.

The verifier writes and fsyncs only `export.pending`, then atomically links it
to `export.json` without replacement, unlinks the pending name and fsyncs the
directory. Any failure can leave a pending file or an unconfirmed export; both
block retry/copy and require quarantine plus separately approved cleanup. No
partial final file is published. C05 has zero barriers/counts and reports config
stability UNAVAILABLE; it makes no observation claim.

The verifier cannot observe host process liveness or establish that the controller
told the truth. Its acceptance proves the supplied closed evidence is consistent,
not AWA protection, complete hook coverage, architecture acceptance, or capture
success. No automatic `NO_AWA_COVERAGE` or D2/D3 adjudication is emitted.

CP6 must name the resolved destination and SHA-256 of this canonical export.
Quarantine at `0700` and block CP6 if any cleanup, verification, identity or path
check is uncertain. The external controller and retention deadline must be named
before CP1+, terminal scenarios run last, and each cleanup action needs its own
approved payload. Hook trust metadata and the CP1 approval conversation can
outlive fixture deletion; no trust-record or transcript purge is promised.

## Remaining gates

CP1: exact proposed path/bytes/digests and allocation only. CP1-CLEAN: exact
untrusted fixture cleanup. CP2-T: exact hook trust and source-set review.
CP2-A: selected A01–A08 with ordinary Codex service traffic. CP2-HOSTED: exact
A09 tool/input/service/auth/network consequences. CP2-CLEAN: exact hook disablement
and bounded cleanup. CP3/CP4/CP5: individually selected lifecycle, failure/race
and disposable-host destruction scenarios. CP6: exact sanitized export delivery.
CP7: exact-result D2/D3 adjudication. No row authorizes another. C05 is
documentation-only and never executed. C03/C04/C06 are unavailable in this
synchronous observer: the manifest rejects them. Timeout, malformed-response
and async variants need a new exact artifact preview and independent gate;
this bundle does not claim to support the full CP4 batch. Catalog tool choices
(including UPDATE_PLAN for A08) must be available and separately bound in CP1;
an unavailable host route remains unproven, never silently substituted.
Restart, installation, config inspection,
credential changes, new tools and any AWA state operation remain separate gates.

Hook shape and event semantics: [official Codex hooks documentation](https://learn.chatgpt.com/docs/hooks),
checked 2026-10-29. CP0 validation is static source review only; hook delivery,
failure behavior, process cleanup and all live acceptance remain unproven.
