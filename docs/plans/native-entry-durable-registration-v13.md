# Native Entry Durable Registration

- **Version:** v13
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-06
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v12.md`](native-entry-durable-registration-v12.md),
  preserved byte-identically at SHA-256
  `ddb659b8a700ddc7fd265bb380497918550821184ebfc2e4c427222ac4e5285b`.
- **Inherited authority:** V12 index
  `0ce6153d69ccd3b72542f500c2ea366819fb56474e02a0d44387a3f3d77c0978`;
  V12 normalized digest
  `ce4b9f6445edaaff7209444af9f0e968d24aea1b712e10e1f781e4d90c116bf1`;
  V12 acceptance envelope
  `1dce3f6aaca10ab171a4d10a1be4e57dbc535ea0fb68b086358b04bc8c85b430`;
  immutable [ADR 0026](../adr/0026-durable-registration-authority-hardening.md)
  SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Repository / delivery:** `KleinPerkins/awa`; branch
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`; Draft PR
  [#183](https://github.com/KleinPerkins/awa/pull/183); delivered head
  `ccfab428fff50703299b98fc2f7b308eb1e85385`, tree
  `6d8de830842e6f1359e0f7a5bacd662471f71ef9`, parent
  `611e56d353f5311299ba2a50be8b7a065533fc6f`; immutable
  implementation-lineage / PR comparison-base OID
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`. Live `origin/main` is a
  moving observation rather than a frozen equality-bound authority input; it
  was `07f5f5820e27ad7557f3b7898fabcc6b41b799be` at V13 refinement.
- **Source lock:**
  `a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72`.

> **Governance stop:** this draft authorizes only this new plan file and its one
> DRAFT README row. It authorizes no review or acceptance; implementation,
> test or retained-evidence edit; staging, commit, push, fetch or PR mutation;
> Gate 5 replay; build, packet, key, signature, native prompt or privilege;
> qualification, readiness or merge; actual R0; release, install, activation
> or rollout.

---

## 1. Purpose and controlling adjudication

V12 corrective delivery completed at the exact head above. Its isolated
exact-head Gate 5 ran all ten commanded verification lanes successfully, then
stopped `NONPASS` when fresh Bugbot review
`9cc660f1-7726-4fd4-9857-13d9afa5724f` reported two production defects.
Security Review correctly did not run under the Gate 5 fail-fast rule.

Both findings are confirmed:

1. `build/private-runtime/build.sh` requires
   `stat -f '%Lp:%l'` to equal `700:1` for a newly created empty private
   directory. A real empty Darwin directory has link count two. Qualification
   input and build roots therefore refuse after otherwise-correct creation.
2. `engine/registration_host.py::retained_main` calls
   `registration_hook_runtime.parse_observable_invocation`, but
   `engine/registration_hook_runtime.py` exports no such function. The
   resulting `AttributeError` is caught by the retained entrypoint's global
   fail-quiet boundary and returns failure.

V12 cannot authorize the first correction: its accepted §3.3 classifies both
`build/private-runtime/build.sh` and
`engine/tests/test_private_runtime_build.py` as byte-exact `PRESERVE`, and its
§8 stops for any path outside the 22-path correction or any drift in the 41
preserved paths. V13 is therefore the minimum successor. It reopens exactly
those two preserved paths and exactly the already-V12-reopened runtime/test
owners needed for the parser export and retained-host regression.

This is not a redesign. V13 adds no schema, digest domain, receipt version,
authority object, key, privilege mechanism, rollout stage, dependency,
service, contract or implementation path. V12 and all predecessor plans,
ADRs, contracts, delivery evidence and Gate 5 evidence remain immutable.
Drafting V13 does not supersede V12.

---

## 2. Exact drafting baseline and failed-Gate evidence

Authoring preflight reproduced:

```text
branch                    impl/native-entry-durable-registration-v7-runtime-bootstrap
lineage / PR base         03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d
live origin/main observed 07f5f5820e27ad7557f3b7898fabcc6b41b799be (moving; not equality-bound)
local / remote / PR head  ccfab428fff50703299b98fc2f7b308eb1e85385
HEAD tree                 6d8de830842e6f1359e0f7a5bacd662471f71ef9
HEAD parent               611e56d353f5311299ba2a50be8b7a065533fc6f
PR #183                   OPEN, Draft, base main, auto-merge unarmed
PR checks                 no checks reported; absence is not success
source status             empty
staging                   empty
```

The lineage / PR base is the immutable comparison anchor. Future V13 gates
require both PR `baseRefOid` and the merge base of the bound feature head with
live `refs/heads/main` to equal that OID, and require local, remote and PR
feature heads to remain equal. They record live `refs/heads/main` as read-only
output but do not require it to equal this refinement-time observation or any
frozen value; unrelated default-branch advancement alone is not drift.

V12 corrective delivery remains:

```text
delivery delta
  19 / 3861 / 986e1dced0f6877f7a96d5ece105f1edf653418317f8b8482d120014bb87b400
runtime manifest
  63 / 4358beae4dc48f42dbc58399c47fc9f886254ec35efffbfd0baf097052143ccd
materialization map
  58 / 0acf21c10bf3078e81e43c16e328b4ca9b60cafe206f04674e3d1f4a5ade0402
preserved V11 working map
  41 / c9a026e32fb5a51174beb7524dec6651e4cdcc211d1df205f77c44ea940e3777
current PR union
  67 / 4e9a7429d6023f561b2b2232ebc1326407ac486fa3ebbd4d9e7b82307b7f5787
```

The delivery-delta digest uses:

```text
SHA256(
  ASCII("awa-registration-v12-c-runtime-corrective-delivery-delta/v1") ||
  0x00 ||
  for each sorted path:
    path || 0x00 || old_mode || 0x00 || new_mode || 0x00 ||
    old_blob_oid || 0x00 || new_blob_oid || 0x00 ||
    new_content_sha256 || LF
)
```

The delivered materialization-map digest uses the existing framing:

```text
SHA256(
  ASCII("awa-registration-v10-c-runtime-materialization-map/v1") || 0x00 ||
  JCS(materialization_object) || LF
)
```

`materialization_object` is one JSON object whose keys are exactly the inherited
V12 materialization set defined in §6: the accepted V12 C-RUNTIME set minus
§6's five base-equal exclusions. JCS serializes those 58 path keys in
lexicographic order. Each value has exactly the JCS-key-sorted shape
`{"kind":"REGULAR","mode":"<three-digit-lower-octal>","sha256":"<lowercase-64-hex>"}`.
JCS emits no extra whitespace; exactly one LF follows the canonical object.

The preserved-V11-working-map digest uses the existing framing:

```text
SHA256(
  ASCII("awa-registration-v12-v11-preserved-working-map/v1") || 0x00 ||
  for each of the 41 paths sorted by UTF-8 bytes:
    UTF8(path) || 0x00 || ASCII(lowercase file SHA256) || LF
)
```

The 41 paths are exactly V12 §3.3's preserved-path list, and every hash covers
the delivered byte-exact file at the bound head.

The consumed V12 Gate 5 authority and retained evidence are:

```text
authority receipt   70 / 11680 / 10149224cfd384773557d6afc8057ba7c83f0a11d24ec1d7dad3042809d9a10f
retained root       /var/folders/_q/4vp8ssd11zbg_jclqgkgyqr00000gq/T//awa-v12-gate5.tTAZyP
root.txt receipt    1 / 71 / 48613fd93f47d0218ba7699074c67520365b8e90303351a7891f2300b778ed47
command receipts    10 / 2741 / 9caa3adb668a5b9433744bedd441dc6d2fc6ad751a15eebb5f6c9b5ccd63e14f
retained clone      clean, head ccfab428fff50703299b98fc2f7b308eb1e85385,
                    tree 6d8de830842e6f1359e0f7a5bacd662471f71ef9
commands 01–10      all exit zero
Bugbot              9cc660f1-7726-4fd4-9857-13d9afa5724f, two confirmed findings
Security Review     not launched
Gate 5 verdict      NONPASS
```

The retained root is evidence only. V13 authoring, acceptance, implementation
and delivery may not edit, clean, replace or reuse it. V13 requires an
entirely fresh full exact-head Gate 5 after corrective delivery.

---

## 3. Closed corrective scope

Every path-only digest uses:

```text
SHA256(
  ASCII(the named scope domain) || 0x00 ||
  each sorted UTF8(path) || LF
)
```

### 3.1 Exact four-path ceiling

```text
domain  awa-registration-v13-c-runtime-corrective-scope/v1
count   4
digest  43db9ee98cecd0479b3e4cf41bcf650b1c3596415dabb932a0144d96d4e45cbc
```

```text
build/private-runtime/build.sh
engine/registration_hook_runtime.py
engine/tests/test_private_runtime_build.py
engine/tests/test_registration_host_c.py
```

Production:

```text
domain  awa-registration-v13-production-correction-scope/v1
count   2
digest  aa965b54dabb1d04d6fbb2e5dd8ce6637730da87ad80a8a10068d89a9cee5bec
```

Tests-first:

```text
domain  awa-registration-v13-tests-first-scope/v1
count   2
digest  d1cf894ba1d87140f925278dbd8976a0ff488238f684f3aae6a6665a46f1df20
```

### 3.2 Exact starting bytes and disposition

| Path | Mode | SHA-256 | Disposition |
|---|---:|---|---|
| `build/private-runtime/build.sh` | `100644` | `01398c80fe32a81656c21805e84b7880594619bd047c633639e4a29871a78f3f` | `SUPERSEDE` only the erroneous empty-directory link-count literal |
| `engine/registration_hook_runtime.py` | `100644` | `10f6048738a031a48ccf75f76965ad7993792140253b9997d6cf55c56d5b6c9a` | `COMPLETE` the missing public parser seam and share it with dispatch |
| `engine/tests/test_private_runtime_build.py` | `100644` | `9f8e7ba71f6bcc85eb43e7de46823a15b5f066ae23e13adfa124c562f3cb2548` | `COMPLETE` exact Darwin directory-metadata regression |
| `engine/tests/test_registration_host_c.py` | `100644` | `36224c3f2079c97c8642e3e4930d9b956bf6d1bffa086e44b73f6ab3265eb882` | `COMPLETE` retained-main/public-parser regression |

The controlling read-only parser context remains:

| Path | Mode | SHA-256 |
|---|---:|---|
| `engine/registration_host.py` | `100644` | `099ffbc636dfb718fd541956d4fe5c9542b07bb2b4b572532238021741b07407` |
| `engine/tests/test_registration_hook_runtime_c.py` | `100644` | `43f21434318d25d61fcf2bcb1f0fe11d1e65f4e58731d0e863536a38fe15eb49` |

`engine/registration_host.py` is already the correct caller and is not
reopened. `engine/tests/test_registration_hook_runtime_c.py` already bites
dispatch four-field behavior and remains immutable corroborating coverage.
A fifth corrective path is a successor stop.

### 3.3 Exact preservation

The other 59 C-RUNTIME paths are byte-exact:

```text
domain  awa-registration-v13-c-runtime-preservation-scope/v1
count   59
digest  d4d14c7669c281ba49f056331fc8c255770d3b56da63839b0660e0cbdc721758
```

This is the exact accepted 63-path V12 C-RUNTIME set minus the four paths in
§3.1. All other source, test, harness, build, install, Makefile and shell
paths; all plans except the new V13 and README status row; all ADRs,
contracts and source-lock bytes; and all retained Gate 5 evidence are
immutable.

---

## 4. Exact bounded corrections

### 4.1 Darwin empty-directory metadata

In `require_empty_private_directory`, change only the expected result of
`/usr/bin/stat -f '%Lp:%l' "$path"` from `700:1` to `700:2`.

Preserve all existing requirements:

- the argument is an absolute path;
- the path must be a real directory and not a symlink;
- the directory is newly created when absent;
- its contents are empty;
- when absent, `/bin/mkdir -m 700` creates the directory under the invoking user; existing-directory ownership is not separately verified;
- its mode is exactly `0700`; and
- every existing failure remains fail-closed.

The test creates a real empty mode-`0700` temporary directory, proves its
link count is exactly two, proves the build script requires `700:2`, and
proves the obsolete `700:1` success expectation is absent. It must not invoke
qualification, download, compilation, signing, packet construction or any
network operation.

### 4.2 Public retained invocation parser

`engine/registration_hook_runtime.py` exports one public
`parse_observable_invocation(payload)` function. It:

1. requires a dictionary payload;
2. obtains event and discriminator through the existing
   `_event_and_discriminator` rules;
3. obtains the immutable invocation through the existing
   `_observable_invocation` rules; and
4. returns exactly `ObservableInvocation(event, server_or_empty,
   discriminator, serializer_schema)`.

`dispatch_bytes` calls that same public helper and derives its local event and
discriminator from the returned invocation. There is no second parser,
fallback, wildcard, role inference or permissive retained-only path.

The existing four-field rules remain exact:

- MCP events require and propagate the nonempty exact `mcp_server_name`;
- non-MCP events propagate empty server;
- `subagentStart` uses `cursor-subagent/v1`;
- other permission events use `cursor-permission/v1`; and
- unknown fields, malformed identity and mismatches refuse.

The host regression invokes the retained `admission` route with sealed
authority and a controlled service, proving `retained_main` reaches the
public parser and succeeds rather than returning the swallowed
`AttributeError`. It also bites malformed and four-field mismatch refusal.
It may mock only retained stdin/stdout and service construction; it may not
select authority from environment or filesystem, mock `_bundle_launcher`, or
weaken existing retained-host assertions.

---

## 5. Tests-first execution contract

The implementation sequence is strict:

1. revalidate accepted V13 authority, current Git/PR/status/staging state,
   all four starting hashes, both immutable context hashes, all scopes and
   retained Gate 5 receipts;
2. edit only the two tests-first paths;
3. run this exact focused command once against unchanged production:

   ```text
   PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest -v engine.tests.test_private_runtime_build engine.tests.test_registration_hook_runtime_c engine.tests.test_registration_host_c
   ```

4. require nonzero only because the two new V13 assertions expose the
   `700:1` expectation and missing public parser; syntax, import, fixture,
   unrelated or existing-test failures are not valid red evidence;
5. bind exact red stdout/stderr, exit, duration, byte/line/SHA-256 counts,
   total tests, failures/errors and failing IDs;
6. freeze both test files at their resulting exact hashes;
7. edit only the two production paths; and
8. rerun only the exact same focused command until it exits zero with every
   test passing and no failure/error.

No assertion may be deleted, weakened, skipped, renamed or converted to an
existence-only check. A test defect or need for a fifth path stops for fresh
successor authority. This gate does not run full verification, Gate 5,
qualification or actual R0.

Tests-first, implementation, corrective delivery and fresh Gate 5 remain
separate, one-use owner gates. No gate implies the next.

---

## 6. Inherited and resulting sets

V13 does not change the inherited ceilings:

```text
full implementation  64 / 2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334
C-RUNTIME             63 / 4bc9ddb451db26c3187d828ee1a69b9739a402943797386e3f5261b2c6ff518c
C-FINAL               24 / 1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8
materialization       58 / 8f096b940fb1855f68fb9e0f8cef49887930176ec0a807e04c590e7c48e77dcd
```

The five base-equal exclusions remain:

```text
contracts/awa-contract.v1.json
engine/tests/test_install_lib.py
engine/tests/test_registration_profile.py
engine/tests/test_registration_store.py
engine/tests/test_verify_lane.py
```

The governance-delivery preservation set becomes:

```text
domain  awa-registration-v13-governance-delivery-scope/v1
count   10
digest  294ae75475297a1261d1dc56c14c397e447a2aab93748f736b606bc4b431ca08
```

```text
docs/plans/README.md
docs/plans/native-entry-durable-registration-v10.md
docs/plans/native-entry-durable-registration-v11.md
docs/plans/native-entry-durable-registration-v12.md
docs/plans/native-entry-durable-registration-v13.md
docs/plans/native-entry-durable-registration-v5.md
docs/plans/native-entry-durable-registration-v6.md
docs/plans/native-entry-durable-registration-v7.md
docs/plans/native-entry-durable-registration-v8.md
docs/plans/native-entry-durable-registration-v9.md
```

Only README and V13 change at V13 governance delivery. V5–V12 remain
byte-identical preservation records. The eventual PR union becomes the
disjoint union of 58 runtime-materialization paths and ten governance paths:

```text
domain  awa-registration-v13-final-pr-scope/v1
count   68
digest  84e3f35d9b5484c0f7dd465edfd37513c54caf746eb6d0ad24613d40366d074b
```

Future test, production, runtime-manifest, materialization-map, delivery
commit, tree, delta and verification receipts are outputs. They are never
predicted or substituted into an earlier gate.

---

## 7. Acceptance ledger

| ID | Required evidence | Refusal |
|---|---|---|
| V13-A01 | A real empty private mode-`0700` directory has link count two and the build guard requires exact `700:2` while retaining path/type/empty/mode checks and absent-directory creation semantics | `700:1`, weakened metadata or network/build-based test |
| V13-A02 | One public invocation parser owns the existing exact event/server/discriminator/serializer semantics and `dispatch_bytes` uses it | Duplicate parser, retained-only fallback or inferred identity |
| V13-A03 | `retained_main(route="admission", authority=sealed_authority)` reaches the public parser and controlled service; malformed and every four-field mismatch remain closed | Swallowed `AttributeError`, environment/path authority or existence-only assertion |
| V13-A04 | Tests fail first for exactly the two unimplemented behaviors, then the identical focused command passes after production-only correction | Green-before-production, unrelated red, test mutation after red or command substitution |
| V13-A05 | Exact four-path correction, two-path production and two-path tests-first sets reproduce; every other C-RUNTIME byte matches the 59-path preservation set | Fifth path or preserved drift |
| V13-A06 | V12 plan, ADRs, contracts, source lock, prior delivery evidence and retained failed-Gate root remain immutable | History rewrite or evidence cleanup/reuse |
| V13-A07 | Corrective delivery reproduces the 63-record runtime tree, 58-record materialization map and 68-path PR union with only reviewed future hashes substituted | Missing record, scope expansion or guessed output |
| V13-A08 | Complete fresh exact-head Gate 5 repeats after every assertion/head change, including all ten lanes, fresh Bugbot and fresh Security Review | Reused V12 receipts/reviews, overlay or partial rerun |

No existing assertion may be weakened, deleted, skipped or renamed to pass.

---

## 8. Serial non-transitive gates

1. **`V13-GOVERNANCE-PLAN-AUTHOR`:** create this DRAFT plan and add only its
   DRAFT README row. No review, acceptance, staging, commit, push or PR
   mutation.
2. **Independent read-only plan review:** verify both findings, four-path
   completeness, exact hashes/scopes, tests-first behavior, preservation,
   anti-replay envelope and gate separation. Review does not mutate or accept.
3. **`V13-PLAN-ACCEPT`:** an exact separately submitted owner envelope may
   perform only the three status/index substitutions in §10. No staging,
   delivery or implementation.
4. **`V13-GOVERNANCE-DELIVER`:** after acceptance, a separate exact owner GO
   may stage only README and V13, create one normal commit with message
   `docs: accept V13 registration correction plan`, and push once non-force
   to the existing branch/Draft PR. It must preserve Draft/unarmed state.
5. **`V13-C-RUNTIME-TESTS-FIRST`:** edit only the two test paths and capture
   exact expected-red evidence with the one exact focused command.
6. **`V13-C-RUNTIME-CORRECTIVE-IMPLEMENT`:** bind frozen final test hashes and
   red receipts; edit only the two production paths and rerun only the exact
   focused command until green.
7. **`V13-C-RUNTIME-CORRECTIVE-DELIVER`:** bind all final four-path hashes,
   green receipt, exact 63/58 manifests/maps, 59 preserved records and
   68-path union; stage exactly changed corrective paths, make one normal
   commit and push once to existing Draft PR #183.
8. **`V13-C-RUNTIME-GATE-5`:** an entirely fresh isolated exact-head full
   Gate 5 repeats all V12 Gate 5 commands and preservation checks, then one
   fresh synchronous Bugbot and one fresh synchronous Security Review.
   Prior V12 Gate 5 receipts and review are stale evidence only.
9. **Qualification:** may be derived only after V13 Gate 5 PASS under its own
   future exact owner authority. No V12 qualification gate may bypass V13.
10. **Readiness, C-FINAL, actual R0, release, install, activation and rollout:**
    remain separately authorized exactly as inherited; none is authorized by
    V13 governance or correction.

No gate implies, combines with or replays another. An authority is consumed
at its declared first mutation/review boundary. Any post-consumption failure
stops with exact partial state and requires newly derived owner authority.

---

## 9. Stops and non-goals

Stop for:

- a fifth corrective path or an edit to `engine/registration_host.py`;
- any V12/predecessor plan, ADR, contract or source-lock byte change;
- any retained Gate 5 artifact edit, cleanup, replacement or reuse;
- any new schema, digest domain, receipt, authority, key, privilege mechanism,
  rollout stage, dependency, service or contract;
- weakened, skipped, deleted or renamed assertion;
- status, staging, feature-branch local/remote/PR head, PR comparison-base,
  merge-base, scope, hash or mode drift; live default-branch advancement alone
  is observational and is not drift;
- any use of the failed Gate 5 as PASS or any partial Gate 5 replay; or
- any unauthorized build, packet, signing, native prompt, privilege,
  qualification, actual R0, readiness, merge, release, install, activation or
  rollout action.

V13 does not alter packet-v2, import-manifest v2, bundle-manifest v3,
descriptor topology, retained authority, installer publication, inert R0 or
any other accepted V12 architecture. It does not authorize implementation or
claim review, acceptance, Gate 5 or qualification clearance.

---

## 10. Exact status-only acceptance

### 10.1 Authorized substitutions

Only a future exact `V13-PLAN-ACCEPT` owner envelope may:

1. change this plan status to
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. change the V13 README row status to
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-06`;
3. change only the V12 README row status to
   `SUPERSEDED BY V13 — 2026-10-06`.

V12 plan bytes never change. Acceptance authorizes no staging, commit, push,
PR mutation, implementation, test, review, Gate 5 or downstream action.

### 10.2 Anti-replay normalization

```text
SHA256(
  ASCII("awa-registration-v13-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

Replace exactly one complete V13 status line with:

```text
- **Status:** __AWA_V13_STATUS__
```

The only eligible input match is the complete current document status line:
either exact draft `- **Status:** DRAFT — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`
or exact promoted `- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`.
The fenced placeholder line above is replacement output, not an input match,
and is excluded. Zero or more than one eligible current-document match refuses.

Replace exactly one complete V13 index row with:

```text
| `native-entry-durable-registration-v13.md` | __AWA_V13_INDEX_STATUS__ | Minimal post-Gate-5 corrective successor to accepted v12; fixes private-runtime directory metadata validation and retained-host invocation parsing before fresh exact-head Gate 5. |
```

Replace exactly one complete V12 index row with:

```text
| `native-entry-durable-registration-v12.md` | __AWA_V13_PREDECESSOR_INDEX_STATUS__ | Corrective authority successor to accepted v11; closes receiver-rooted import-manifest v2, bundle-manifest v3, retained launch, four-field hook ABI and inert R0 before exact-head qualification. |
```

Each replacement includes one LF. Zero, duplicate, mixed, non-UTF-8, CRLF,
NUL, nonexact context or any normalized-byte difference refuses.

Simulation is in memory:

1. hash exact draft plan/index;
2. apply only the three substitutions to copies;
3. hash simulated promoted plan/index;
4. normalize draft and promoted pairs independently;
5. require byte-identical normalized preimages and digest; and
6. prove every non-status byte unchanged.

### 10.3 Closed future owner envelope

The external acceptance object is canonical JCS with exactly the key set in
this template. Placeholders are replaced only in the future external owner
submission:

```json
{"accepted_v12_envelope_sha256":"1dce3f6aaca10ab171a4d10a1be4e57dbc535ea0fb68b086358b04bc8c85b430","accepted_v12_index_sha256":"0ce6153d69ccd3b72542f500c2ea366819fb56474e02a0d44387a3f3d77c0978","accepted_v12_normalized_sha256":"ce4b9f6445edaaff7209444af9f0e968d24aea1b712e10e1f781e4d90c116bf1","accepted_v12_plan_sha256":"ddb659b8a700ddc7fd265bb380497918550821184ebfc2e4c427222ac4e5285b","action":"ACCEPT_PLAN_V13","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","authorized":true,"authorized_actions":["MARK_V12_INDEX_SUPERSEDED","PROMOTE_V13_INDEX_STATUS","PROMOTE_V13_PLAN_STATUS"],"authorized_by":"KleinPerkins","auto_merge_armed":false,"base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","branch":"impl/native-entry-durable-registration-v7-runtime-bootstrap","c_final_scope_count":24,"c_final_scope_hash":"1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8","c_runtime_scope_count":63,"c_runtime_scope_hash":"4bc9ddb451db26c3187d828ee1a69b9739a402943797386e3f5261b2c6ff518c","corrective_scope_count":4,"corrective_scope_hash":"43db9ee98cecd0479b3e4cf41bcf650b1c3596415dabb932a0144d96d4e45cbc","delivered_commit":"ccfab428fff50703299b98fc2f7b308eb1e85385","delivered_materialization_map_count":58,"delivered_materialization_map_digest":"0acf21c10bf3078e81e43c16e328b4ca9b60cafe206f04674e3d1f4a5ade0402","delivered_runtime_manifest_count":63,"delivered_runtime_manifest_digest":"4358beae4dc48f42dbc58399c47fc9f886254ec35efffbfd0baf097052143ccd","delivered_tree":"6d8de830842e6f1359e0f7a5bacd662471f71ef9","denied_implications":["ALTER_PRESERVED_WORK","COMMIT_PUSH_OR_MUTATE_PR","GOVERNANCE_DELIVER","IMPLEMENT_OR_DELIVER","INVOKE_REVIEWS_OR_GATE_5","PACKET_KEY_SIGN_PROMPT_OR_PRIVILEGE","QUALIFY_BUILD_OR_PUBLISH","READY_OR_MERGE","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_ACTUAL_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","entry_status_count":2,"entry_status_sha256":"<reviewed lowercase 64-hex>","eventual_final_pr_scope_count":68,"eventual_final_pr_scope_hash":"84e3f35d9b5484c0f7dd465edfd37513c54caf746eb6d0ad24613d40366d074b","full_scope_count":64,"full_scope_hash":"2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334","gate5_authority_sha256":"10149224cfd384773557d6afc8057ba7c83f0a11d24ec1d7dad3042809d9a10f","gate5_bugbot_id":"9cc660f1-7726-4fd4-9857-13d9afa5724f","gate5_command_receipts_sha256":"9caa3adb668a5b9433744bedd441dc6d2fc6ad751a15eebb5f6c9b5ccd63e14f","gate5_result":"NONPASS","governance_delivery_scope_count":10,"governance_delivery_scope_hash":"294ae75475297a1261d1dc56c14c397e447a2aab93748f736b606bc4b431ca08","materialization_scope_count":58,"materialization_scope_hash":"8f096b940fb1855f68fb9e0f8cef49887930176ec0a807e04c590e7c48e77dcd","normalized_digest":"<reviewed lowercase 64-hex>","pr_number":183,"pr_state":"DRAFT","preservation_scope_count":59,"preservation_scope_hash":"d4d14c7669c281ba49f056331fc8c255770d3b56da63839b0660e0cbdc721758","production_scope_count":2,"production_scope_hash":"aa965b54dabb1d04d6fbb2e5dd8ce6637730da87ad80a8a10068d89a9cee5bec","promoted_index_sha256":"<reviewed lowercase 64-hex>","promoted_plan_sha256":"<reviewed lowercase 64-hex>","repository":"KleinPerkins/awa","schema":"awa-registration-v13-plan-acceptance-go/v1","source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","staging_empty":true,"starting_path_hashes":{"build/private-runtime/build.sh":"01398c80fe32a81656c21805e84b7880594619bd047c633639e4a29871a78f3f","engine/registration_hook_runtime.py":"10f6048738a031a48ccf75f76965ad7993792140253b9997d6cf55c56d5b6c9a","engine/tests/test_private_runtime_build.py":"9f8e7ba71f6bcc85eb43e7de46823a15b5f066ae23e13adfa124c562f3cb2548","engine/tests/test_registration_host_c.py":"36224c3f2079c97c8642e3e4930d9b956bf6d1bffa086e44b73f6ab3265eb882"},"tests_first_scope_count":2,"tests_first_scope_hash":"d1cf894ba1d87140f925278dbd8976a0ff488238f684f3aae6a6665a46f1df20"}
```

Its domain-framed digest is:

```text
SHA256(
  ASCII("awa-registration-v13-plan-acceptance-envelope/v1") || 0x00 ||
  JCS(concrete_external_envelope) || LF
)
```

In that envelope, `base_commit` means the immutable implementation-lineage /
PR comparison-base OID, not the moving live `refs/heads/main` value.

`entry_status_count` and `entry_status_sha256` bind the exact unmodified
stdout bytes from:

```text
LC_ALL=C git -c core.quotePath=true status --porcelain=v1 --untracked-files=all
```

`staging_empty:true` requires empty stdout from:

```text
git diff --cached --name-only --
```

Before any acceptance substitution, revalidate the closed key set/schema,
owner identity, all inherited authority, feature-branch local/remote/PR head,
immutable PR comparison-base and merge-base OIDs, Draft/unarmed state, exact
two-record authoring status, staging, all scopes, starting and immutable
hashes, delivered manifests/maps, failed-Gate receipts/findings, retained-root
identity, draft/promoted hashes, normalization equivalence and denied
implications. Record live `refs/heads/main` read-only without equality-binding
it. Any mismatch refuses before mutation.

---

## 11. Separate governance delivery

Acceptance still does not authorize delivery. Only a later exact
`V13-GOVERNANCE-DELIVER` owner message may, after fresh complete
revalidation:

1. stage exactly `docs/plans/README.md` and
   `docs/plans/native-entry-durable-registration-v13.md`;
2. prove the cached delta contains only the accepted bytes for those paths;
3. create exactly one normal commit with message
   `docs: accept V13 registration correction plan`;
4. push exactly once, non-force, to
   `impl/native-entry-durable-registration-v7-runtime-bootstrap`;
5. update only existing Draft PR #183 through that push; and
6. perform read-only delivery verification.

V5–V12 are preservation records in the ten-path governance scope. PR #183
must remain OPEN, Draft and auto-merge unarmed. Resulting commit, tree, delta,
local/remote/PR head and post-delivery status are outputs bound by the next
gate. Governance delivery authorizes no source/test edit, implementation,
verification lane, review, Gate 5, qualification or downstream action.

---

## 12. Review provenance

This draft records the two independently reported and subsequently confirmed
Gate 5 defects and the exact owner-authorized four-path successor boundary.
It claims no plan-review, acceptance, implementation or verification
clearance.

Independent read-only review must confirm:

- both findings remain true at the bound head;
- no path beyond the exact four is necessary;
- `700:2` preserves every existing directory guard;
- the public parser shares, rather than forks, four-field dispatch semantics;
- tests bite retained execution rather than source existence;
- all 59 preservation paths and inherited manifests/maps/unions reproduce;
- acceptance and governance-delivery envelopes are closed and anti-replay;
  and
- a full fresh exact-head Gate 5 remains mandatory after corrective delivery.

Only after that review may the owner separately authorize V13 status-only
acceptance. No next gate is derived or implied by this authoring record.
