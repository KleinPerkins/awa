# Native Codex C-Bounded Evidence-Capture Consequence Preview

- **Version:** v2
- **Status:** DRAFT — CP0 SOURCE DELIVERY COMPLETE; CP1 ALLOCATION AND ALL LATER GATES NO-GO
- **Date:** 2026-10-29
- **Supersedes:** [v1](native-codex-bounded-evidence-capture-preview-v1.md) for the
  current decision frontier only; v1 remains the immutable CP0 authority and the
  inherited capture/data/consent contract.
- **Baseline:** AWA `main` `125d17242b36f8a9b2557222b5c4094bf694112f`
  ([PR #188](https://github.com/KleinPerkins/awa/pull/188)).
- **Relates to:** draft [ADR 0029](../adr/0029-native-codex-interoperability-boundary.md)
  and draft [Native Codex Interoperability v1](native-codex-interoperability-v1.md).
- **Plan type:** post-CP0 consequence refresh and CP1 approval contract; no host
  allocation, hook execution, capture, architecture acceptance or implementation GO.

**Purpose:** Bind the next allocation decision to the delivered source bytes.
Keep machine paths and proposed rendered bytes in a separate private approval
packet; do not put that packet or a capture result in this repository.

## 1. Verified authority and completed work

The operator authorized CP0 against v1 SHA-256
`21af39a50ad2d098e12db464ee6dee5e9ac7d255d64ed6b728955bfbd468a710`
and preparation baseline `e68c6be90e132629e0c78d80d31f6bcc95623d51`.
[PR #187](https://github.com/KleinPerkins/awa/pull/187) delivered v1 at
`57fb1355163cc9c6a569330dd0828468d666535e`.

PR #188 delivered exactly v1's eight regular `100644` source files through
independent static review, local verification, the five exact-head App checks,
reviewer-App approval and native squash merge. Its reviewed head was
`5816af8d77e3cc92b2e44d87d94de1bdcb338eac`; its merge is the baseline above.
The helpers were not executed or imported. No native capture fixture, rendered
hook configuration, hook trust, capture, chat or AWA state operation was created.

The source directory is `live-verify/codex-native-capture-v1/`.
`MANIFEST.sha256` has SHA-256
`af08cc4adf393f773844fb9e8836b6845ad0df74de81f8d4beed1340952abf92`.
Its exact seven entries are:

```text
af1609bf24477c77d539c1ee086262152e73b6be7e7f6383862d3ab77b189ffc  README.md
2bfba76707d89744034613a4b79ba4f6061fa55003785af4ff0894374ab57676  capture-schema.v1.json
03214bba8da8a1fcacddad3ad50ea92728e2525ce9a9fbb905b009ab619787b5  capture_hook.py
46b724df9b9048d692f9e552e512303b2512d0af125a6b1072a316f3db4354cc  fixture-hooks.v1.json.in
9adf67e5de8b1e6ad67351e72bace8c31a5a7b4bb8c1891d1e9ac89f4dce437e  forbidden-fields.v1.txt
7b5c42de2ca2e4fa61ddb6ca124cb39e5c4fa7266c78bad214bce8537d4fe159  scenario-catalog.v1.json
55df048d6e7af72e549eb73951cd4412d6fd398931c964ab6fe37378edf762fd  verify_capture.py
```

V1, ADR 0029 and its plan retain their previously bound bytes. D0 remains
`EVALUATE_C_BOUNDED`. Native attachment is not AWA registration or protection.
No architecture/profile choice, reduced-protection acceptance, ADR 0026
activation, registration, protection or exact `Close` is authorized here.

## 2. The private CP1 approval packet

Before requesting CP1, prepare one complete, machine-specific packet outside
Git and outside the proposed fixture. Source rendering is a calculation over
reviewed repository data; it is not hook/verifier execution. The packet must
include all of the following with no unresolved placeholder:

1. This successor's SHA-256 and merged revision; the CP0 baseline and all eight
   source digests; one non-identifying, high-entropy operation ID.
2. One exact absolute existing private parent and proposed container/root.
   Bind descriptor-derived device/inode, owner/group and mode for every existing
   ancestor. Bind absence of every proposed new path. Use decimal strings for
   device/inode values so a JSON consumer cannot round a 64-bit identity.
3. Exact future directories/files, modes, byte lengths and SHA-256 values.
   Include the hook's unchanged bytes, canonical rendered project `hooks.json`,
   initial run manifest, labels, empty ledger/lock and fixed synthetic file.
   State the fresh 32-byte salt-generation rule; never publish the salt, its
   digest or equality-map ephemera. Git-generated metadata is limited to the
   new fixture's `.git/` and is bound by the exact isolated init command.
4. The precise allocation procedure as reviewable data, interpreter and Git
   executable identities/digests (including resolved implementations behind any
   launcher), literal subprocess arguments/environment,
   execution bounds, failure behavior and success checks. It must not run or
   import either capture helper, discover existing hook configuration, open a
   fixture chat, trust a project/hook, register AWA or use the network.
5. A named controller outside the future fixture chat, a fixed approval expiry,
   a fixed retention deadline, and a plain-language residual/cleanup handoff.
   Do not imply a background monitor exists. Cleanup remains CP1-CLEAN unless
   its distinct exact payload is also explicitly approved.
6. A SHA-256 of the complete canonical packet. Approval binds that packet,
   this successor, source revision and exact root together. A generic
   continuation, boolean or copied approval does not authorize allocation.

The existing parent must be owned and private, with no group/other-writable
ancestor and no symlinked component. `/private/tmp` remains ineligible. No
existing directory is chmodded, relocated, cleaned or reused by inference.
If a newly proposed container is absent, CP1 may explicitly include its creation
at `0700` beneath the already-bound parent; its name is then part of the packet.

The private packet and approval conversation necessarily retain the proposed
path, rendered bytes/digests and preimages outside fixture deletion. They must
contain no credentials, user configuration bytes, transcripts or work data.
Do not deliver this packet as a CP6 capture result or promise its purge.

## 3. Minimum initial fixture and run

The next proposed CP1 is allocation only, preparing one run `C1` with the single
future scenario `A01`. This reserves an exact later action without authorizing
it. A01 is a new synthetic fixture chat/session start and still requires its
own CP2-A approval and ordinary Codex-service-traffic disclosure.
Whether the host can expose startup separately from first-prompt callbacks is
still unqualified. If it cannot, A01 fails evidence validation; do not widen
the catalog or count alternatives after allocation to make that run pass.

The initial manifest is the merged bundle's closed
`awa-codex-capture-run/v1` shape. It freezes all seven source hashes, the exact
hook/rendered-config/template hashes, `scenario_ids = ["A01"]`, and exactly two
allowed count maps: all twelve event counts zero; or `SessionStart = 1` and
the other eleven zero. Its control-route list is `["SessionStart"]`.
No expectation may be changed after a witness. A different scenario set or
count alternative requires a new bound operation preview before its writes.

The catalog marks A01 `OBSERVE`: startup cannot supply the same-session
before/after controls. Its future witness must use health `UNAVAILABLE`; an
absent callback stays `UNPROVEN`. A callback can be retained as an observation,
but this initial run cannot establish AWA coverage or D2/D3 acceptance.
No witness or event is written during CP1.

Only the following initial content is proposed beneath the operation root:

- `fixture/`, `fixture/.codex/`, `fixture/.codex/hooks/`, `fixture/synthetic/`
  and `capture/`: `0700` directories.
- `fixture/.codex/hooks/capture_hook.py`: unchanged merged source, `0600`.
- `fixture/.codex/hooks.json`: the exact private rendered bytes, `0600`.
- `fixture/synthetic/fixture.txt`: one fixed synthetic line, bound in the
  private packet, `0600`.
- `capture/manifest.json`: exact private canonical manifest, `0600`.
- `capture/labels.json`: empty session/turn maps, `0600`.
- `capture/ledger.ndjson` and `capture/capture.lock`: empty files, `0600`.
- `capture/salt.bin`: 32 fresh random bytes generated only after approved
  allocation, `0600`; no value/digest printed or copied elsewhere.
- `fixture/.git/`: only metadata from the exact bounded, isolated Git init.

`export.json`, `export.pending`, controller witness rows, logs, caches, commits
and remotes are not created. No other source file is installed. The fixture is
never this AWA worktree, another work repository or a primary checkout.

Rendering replaces the template's single token once with the proposed absolute
hook path, copies its seed handler over the twelve merged event literals, then
uses sorted-key compact ASCII JSON and one LF. The command remains the exact
`/usr/bin/python3 -I -S -B` invocation with a three-second hook timeout. Do not
execute the renderer or either helper to qualify host behavior during planning;
static source inspection and independent data rendering provide only proposed
bytes, not evidence of hook delivery or safety.

## 4. Approved-allocation execution and failure boundary

Immediately before any future approved write, revalidate the source hashes,
packet hash/expiry, launcher and resolved executable identities, every bound existing ancestor,
parent descriptor, exact path spelling and each absent-entry preimage. Resolve
nothing to a substitute path. A mismatch expires the payload and writes nothing.

Use no-follow descriptor-relative exclusive directory/file creation with
`umask 077`, explicit final modes, regular-file/single-link/owner checks,
bounded writes and fsync. Recheck namespace identities before further writes.
Existing entries, links, special files or unexpected ownership refuse rather
than overwrite. Newly allocated directories remain private.

Git init is local-only and bounded. Use the packet's absolute existing Git
executable with literal arguments, empty templates, disabled hooks/fsmonitor,
no system/global configuration or attributes, and a literal minimal environment.
Do not read/copy user Git configuration, use inherited aliases/includes/hooks,
write identity overrides, commit, push, open the fixture in Codex or contact a
service. Its child must reach a bounded terminal result; a surviving child or
uncertain result is allocation failure, not permission to start capture.

After creation, verify the exact allowed namespace, owner/modes/link counts,
fixed-content hashes, fresh salt length and empty ledger/lock. Do not run the
hook/verifier, commit the fixture or open its configuration through the app as
a test. Report the allocated root and measured identities, with no salt or raw
child stdout/stderr. This proves only untrusted allocation.

On a partial failure, stop further writes, terminate only owned children within
the reviewed bound, keep the exact residual private and report its measured
paths/identities and retention deadline. Do not delete, broaden cleanup or
retry under a new name. CP1-CLEAN needs its own exact, current-state payload.
An expired retention deadline or uncertain cleanup blocks CP6. No unattended
cleanup/monitoring, hook-trust purge or AWA Close is implied.

## 5. Inherited limits and remaining gates

V1 §§4–9 remain the capture/data/negative-evidence/cleanup/consent contract.
The merged source README and manifest add exact source implementation limits;
neither expands authority. Conflicts stop the operation rather than weakening
the inherited contract.

C03/C04/C06 are unsupported by the merged synchronous observer and rejected by
its manifest parser. They require a new exact artifact preview and independent
gate before timeout, malformed-response or async experiments. C05 remains
documentation-only; no MCP fixture, server, handler or configuration exists.

CP2-T still requires supported hook-browser review of the exact active source
set and exact hook trust. Any additional/unresolved source aborts qualification;
never inspect, disable or modify another live source to work around it.
CP2-A, CP2-HOSTED, CP2-CLEAN and CP3–CP7 remain distinct. No chat creation,
prompt/tool execution, ordinary or hosted capture traffic, restart, install,
live-config inspection, credentials, subagent/race experiment, archive/delete/
snapshot/restore, export delivery or D2/D3 adjudication follows from CP1.

The next decision is **CP1 allocation against a complete private packet**, after
this successor is delivered and its actual merged revision/hash are known.
Approval must name that packet's exact SHA-256, exact absolute root, source
baseline, successor SHA-256, expiry and retention deadline. Preparing or merging
this document is not that approval. All host operations remain NO-GO until then.
