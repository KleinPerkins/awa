# Native Entry Durable Registration

- **Version:** v12
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-05
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v11.md`](native-entry-durable-registration-v11.md),
  SHA-256
  `fcd98e5173d5ec705e6998f1673a6ed693c8e4625ef2f669a06db60e83577c4f`,
  normalized digest
  `d980681d19994b1a7c5426408d5a99c4542e2248f82f7e87fad55da40b04fc52`.
- **Inherited authority:** V11 index
  `9f403c0a9f2c4e79fea25ba5e2765591a19b0dd46b93d1d490c52647b1a62447`;
  V11 acceptance envelope
  `cf8f3621802fbc16abb5466a2daf11e5559591ad75a79deb787163ce36234ba9`;
  V10 plan
  `6eb266c7e88f7aa26444f554fab7cc288e8973a89666f7bd8d8664290a1ecc8a`;
  ADR 0026
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Repository / delivery:** `KleinPerkins/awa`; branch
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`; Draft PR
  [#183](https://github.com/KleinPerkins/awa/pull/183); exact head
  `8e03121155decd45128ae9babcbfc5d25a156c9a`, tree
  `1a8f9863c10c044b982c6fe820ceb84ffe14e540`, parent
  `19d3c6c96dc1d231fe60bc497d42c81f23923d78`, base and `origin/main`
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`.
- **Source lock:**
  `a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72`.

> **Governance stop:** this draft authorizes only this plan file and its one
> DRAFT README row. It authorizes no implementation, test, contract, accepted
> plan or ADR edit; staging, commit, push or PR mutation; build, packet, key,
> signature, native prompt or privilege; readiness or merge; actual R0;
> release, install, activation or rollout.

---

## 1. Purpose and adjudication

V11 delivered a 60-path C-RUNTIME tree, but the exact head does not implement
the accepted V8/V9 product-import authority. The production generator emits
caller-rooted `awa-registration-import-manifest/v1`; the available v2 model is
caller-enumerated, has no canonical parser and permits omission of host and
hook-runtime bytes. The production bootstrap and child still open and consume
v1 through the old five-authority-FD launch. The receiver and host retain
config-v1/filesystem authority reads, and the historical launcher still
executes v1. The packet/root-admin path does not carry or validate the accepted
product authority assets. These are production defects; tests or prose alone
cannot close them.

V12 is a sequencing correction, not a redesign. It reopens the smallest
complete existing production and test owners needed to implement the already
accepted receiver-rooted import-manifest v2, acyclic bundle-manifest v3,
bundle-projection v2, DIRECT receipt v4 / owner-gate v3 binding, retained-byte
launch and exact product publication. It also advances the already-started
four-field hook ABI and inert R0 harness closure into C-RUNTIME.

V11 remains accepted and immutable. V12 remains DRAFT. No predecessor is
superseded now.

---

## 2. Fresh exact state

Drafting preflight reproduced:

```text
branch                    impl/native-entry-durable-registration-v7-runtime-bootstrap
base / origin/main        03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d
local / remote / PR head  8e03121155decd45128ae9babcbfc5d25a156c9a
HEAD tree                 1a8f9863c10c044b982c6fe820ceb84ffe14e540
HEAD parent               19d3c6c96dc1d231fe60bc497d42c81f23923d78
PR #183                   OPEN, Draft, base main, auto-merge unarmed
PR checks                 no checks reported; absence is not success
staging                   empty
```

The exact full porcelain status is five records:

```text
 M docs/plans/README.md
 M engine/registration_hook_runtime.py
 M engine/tests/test_registration_hook_runtime_c.py
 M live-verify/native-entry-durable-registration-r0.py
?? docs/plans/native-entry-durable-registration-v12.md
```

Its accepted raw-byte framing is:

```text
count   5
SHA256(exact stdout bytes)
        022a235f70d9b849e6716a1398a93236c367826b326c33648672eab831c13f0c
```

An extra transient or persistent record refuses acceptance. In particular,
`.cursor/hooks/state/continual-learning.json` is not ignored or excluded from
this binding.

The three protected implementation inputs remain:

| Path | Working SHA-256 | HEAD SHA-256 |
|---|---|---|
| `engine/registration_hook_runtime.py` | `10f6048738a031a48ccf75f76965ad7993792140253b9997d6cf55c56d5b6c9a` | `60ceb74f28aca5de24e811d4ac21933c3ec95c7e8c1ad2b111d352b48e6df3e0` |
| `engine/tests/test_registration_hook_runtime_c.py` | `0c4be2717f64818778fdcc6e686814d8066944a5e7a7575eb4e17c5753e26e0d` | `8955ce00f434df74fbad5cc15e09a88dc973be8a4e98b19b37bdc68a34774731` |
| `live-verify/native-entry-durable-registration-r0.py` | `5b9a7c7f76f921644526933260927b2f57c6c8fc95be594620dfd15df2ce5997` | `6e933d022751ce5a60803923b027dae9bb446cb5fbd45cf1ba6ee4d6d1dd9052` |

V11 delivery measurements remain:

```text
delivery delta                 35 (20 added, 15 modified, 0 deleted)
runtime manifest               60 / 83fdd8cc870f4f4012ad8330aa10a613c2ac0796c0219f22e213e187cf530bf9
materialization map            55 / 576cc1614774cffc269b0575726a16e5d98fb16eaf4cc23e7049e14b8d68a355
current PR union               63 / dbf70d6e608353aac2e6ba87832be0eff9490807f4d7b6dd5312a86c9a2e4de9
V10-final preservation         52 / 52 exact
base-equal exclusions           5 / 5 exact
```

---

## 3. Closed corrective set and dispositions

For every path-only set:

```text
SHA256(ASCII(domain) || 0x00 || each sorted UTF8(path) || LF)
```

### 3.1 Corrective edit ceiling — 22

```text
domain  awa-registration-v12-c-runtime-corrective-scope/v1
count   22
digest  ab45f49d527c4575d6f54704109af3a03e46c7961029150c0d5e294bf6eccf88
```

```text
engine/registration_hook_runtime.py
engine/registration_host.py
engine/registration_installer.py
engine/registration_launcher.py
engine/registration_privileged_installer.py
engine/registration_projection.py
engine/registration_receiver.py
engine/tests/test_kernel_off_matrix.py
engine/tests/test_platform_bootstrap.py
engine/tests/test_private_runtime_installer.py
engine/tests/test_registration_deployment_authority_c.py
engine/tests/test_registration_hook_runtime_c.py
engine/tests/test_registration_host_c.py
engine/tests/test_registration_installer_c.py
engine/tests/test_registration_launcher_c.py
engine/tests/test_registration_packaging_c.py
engine/tests/test_registration_privileged_installer.py
engine/tests/test_registration_receiver_c.py
kernel/bin/awa-private-runtime-admin.py
kernel/bin/awa-registration-bootstrap.py
kernel/bin/awa-registration-child.py
live-verify/native-entry-durable-registration-r0.py
```

Production/harness subset:

```text
domain  awa-registration-v12-production-correction-scope/v1
count   11
digest  bff120944736390d2bcfeca6b8fda857dc0b11012867aba69c68f4a67feffb52
```

Tests-first subset:

```text
domain  awa-registration-v12-tests-first-scope/v1
count   11
digest  673fc7e96b13ff45d51b378ac1a29d446fd4a84b781b8eee0a77613da9e5b99c
```

### 3.2 Path-by-path necessity and disposition

| Path | Disposition | Required correction |
|---|---|---|
| `engine/registration_projection.py` | `SUPERSEDE` | Give import-manifest v2 canonical parse/validation, mandatory receiver-rooted transitive closure, exact counts/sizes/FDs/resources, and complete bundle-manifest v3 record validation; retain v1/v2 historical bytes only as parse-and-refuse evidence. |
| `engine/registration_installer.py` | `SUPERSEDE` | Replace caller-selected v1 generation and v1 immutable bundle construction with generator-owned receiver-rooted static closure, resource inclusion, host/hook transitivity, v2/v3/v2/v4/v3 construction and exact hash propagation. |
| `engine/registration_receiver.py` | `SUPERSEDE` | Remove dynamic `__import__` and old config/filesystem launch authority; accept only parsed retained authorities/resources and pass them without rereading paths. |
| `engine/registration_host.py` | `SUPERSEDE` | Consume the passed host authority, receipt, inventory and writer capability; remove environment-selected config and product-authority reopen; preserve four-field exact matching. |
| `engine/registration_hook_runtime.py` | `SUPERSEDE` | Complete immutable four-field invocation propagation, including exact MCP server and serializer identity. |
| `engine/registration_launcher.py` | `SUPERSEDE` | Convert historical config-v1/import-v1 execution to explicit parse-and-refuse; accepted launch is bootstrap/child retained-byte only. |
| `engine/registration_privileged_installer.py` | `SUPERSEDE` | Bind the exact v2/v3 product assets into packet-root and product-authority evidence, validate duplicated receipt/gate hashes, and model paired runtime/product publication without inventing a new schema. |
| `kernel/bin/awa-private-runtime-admin.py` | `SUPERSEDE` | Consume exact packet-bound product assets, require bundle v3 and import v2, reject bundle v2/v1/import v1 execution, and publish runtime/product authorities under the accepted transactional contract. |
| `kernel/bin/awa-registration-bootstrap.py` | `SUPERSEDE` | Replace v1/five-FD launch consumption with accepted runtime-current v2, product-current, FD3–15+ topology, v2 import/v3 bundle validation and exact retained descriptors. |
| `kernel/bin/awa-registration-child.py` | `SUPERSEDE` | Independently validate all fixed/dynamic descriptors and accepted schemas, install retained importer/deny finder, request receiver first only after GO, and pass parsed immutable authorities/resources. |
| `live-verify/native-entry-durable-registration-r0.py` | `SUPERSEDE` | Complete truthful inert harness v2 `--check` and side-effect-free `--run` refusal. |
| `engine/tests/test_registration_deployment_authority_c.py` | `COMPLETE` | Bite receiver-rooted closure, caller-enumeration refusal, host/hook omission, canonical v2/v3 validation, wrong entry/version and receipt/gate hash disagreement. |
| `engine/tests/test_registration_installer_c.py` | `COMPLETE` | Replace successful v1 bundle fixtures with exact v2/v3 authority construction/publication and omission/mutation refusals. |
| `engine/tests/test_registration_receiver_c.py` | `COMPLETE` | Prove parsed retained-authority injection and zero environment/path authority reread. |
| `engine/tests/test_registration_host_c.py` | `COMPLETE` | Prove passed sealed host authority only and independent four-field mismatch refusal. |
| `engine/tests/test_registration_hook_runtime_c.py` | `COMPLETE` | Add direct MCP/subagent serializer assertions, exact object calls typing and fail-closed identity tests. |
| `engine/tests/test_registration_launcher_c.py` | `COMPLETE` | Replace config-v1 success vectors with parse-and-refuse/unreachable historical vectors. |
| `engine/tests/test_kernel_off_matrix.py` | `COMPLETE` | Update only exact approved bootstrap/admin lock and descriptor semantic records required by fixed FD3–15 and dynamic FD16+ topology; preserve every negative family and exact scanner semantic. |
| `engine/tests/test_platform_bootstrap.py` | `COMPLETE` | Bite FD3–15+, dynamic descriptor bounds/order, v2/v3 schemas, v1/v2 mismatch, first receiver import, parent/child remeasurement and filesystem fallback. |
| `engine/tests/test_private_runtime_installer.py` | `COMPLETE` | Bite atomic paired runtime/product current publication, v3-only product assets, recovery and retention in the accepted admin state machine. |
| `engine/tests/test_registration_privileged_installer.py` | `COMPLETE` | Bite packet inclusion/equality of every product authority asset and root-admin rejection of omitted, v1/v2, stale or cross-bound records. |
| `engine/tests/test_registration_packaging_c.py` | `COMPLETE` | Add subprocess-equality assertions for every inert R0 field and `--run` refusal; assert accepted product paths package and historical v1/config execution is unreachable. |

Tests must change first and fail against the then-current production bytes.
Runtime and tests deliver atomically.

### 3.3 Delivered-byte preservation

Nineteen of the 22 paths reopen delivered V11 bytes:

```text
domain  awa-registration-v12-reopened-v11-scope/v1
count   19
digest  4819b7db08310eaa7c6d8191fe2f8fc512bc3aeb078baefd4c876937087a0aa0
```

The other 41 delivered paths are byte-exact `PRESERVE`:

```text
domain  awa-registration-v12-v11-preservation-scope/v1
count   41
digest  ed94977c8482aaa7b12015661a58a0ee59a5e5d942d31aa03e1966c3f47aaa67
```

```text
Makefile
build/private-runtime/README.md
build/private-runtime/build.sh
build/private-runtime/manifest.py
build/private-runtime/sources.lock.json
contracts/awa-contract.v1.json
contracts/awa-contract.v2.json
contracts/awa-contract.v3.json
contracts/awa-contract.v4.json
contracts/awa-registration-admin-audit.v1.json
contracts/awa-registration-admin-audit.v2.json
contracts/awa-registration-admin-audit.v3.json
contracts/awa-registration-owner-signers.v1
contracts/awa-registration-owner-signers.v2
contracts/awa-registration-platform-bootstrap.v1.json
contracts/awa-registration-platform-bootstrap.v2.json
contracts/awa-registration-platform-bootstrap.v3.json
contracts/awa-registration-private-runtime.v1.json
contracts/awa-registration-private-runtime.v2.json
contracts/awa-registration-private-runtime.v3.json
contracts/awa-registration-privileged-envelope.v1.json
engine/registration_profile.py
engine/registration_schema.py
engine/tests/registration_body_c_fixtures.py
engine/tests/test_contract_schemas.py
engine/tests/test_install_lib.py
engine/tests/test_private_runtime_build.py
engine/tests/test_registration_independence_c.py
engine/tests/test_registration_parent_death.py
engine/tests/test_registration_profile.py
engine/tests/test_registration_projection_c.py
engine/tests/test_registration_schema.py
engine/tests/test_registration_store.py
engine/tests/test_verify_lane.py
install.sh
kernel/bin/awa-registration-entrypoint.sh
kernel/bin/awa-registration-receiver.sh
kernel/bin/awa-registration-tick.sh
kernel/checks/awa-contract-freeze.sh
kernel/hooks/awa-registration-admission.sh
kernel/hooks/awa-registration-startup.sh
```

### 3.4 Inspected exclusions

These plausible candidates require no corrective edit:

- `engine/registration_schema.py`: already obtains SQL through
  `importlib.resources`; the retained resource provider makes those existing
  bytes authoritative.
- `engine/registration_profile.py`: already supplies the ten exact host target
  values; sealing and transport belong to projection/installer/host.
- `engine/tests/test_registration_projection_c.py`: already bites receipt-v4 /
  gate-v3 body/final branching; new import/bundle production vectors belong to
  deployment-authority tests.
- `engine/tests/test_registration_schema.py`: existing schema semantics remain;
  retained SQL transport bites in platform-bootstrap tests.
- `engine/tests/test_registration_parent_death.py`: watchdog semantics remain
  unchanged and platform-bootstrap owns descriptor/GO integration.
- `install.sh`, `build/private-runtime/*`, `Makefile`: existing whole-tree
  packaging and test lanes include every corrected path; no v1/v2 schema logic
  is encoded there.
- `kernel/bin/awa-registration-entrypoint.sh` and the four hook/tick/receiver
  shell paths: they already route to the fixed bootstrap without selecting
  product paths or schemas.
- all contracts: accepted v3/v4 bytes already require import v2, bundle v3,
  fixed FD11 v3 and v1/v2 execution refusal; changing them would create an
  unauthorized schema redesign.
- desktop UAT remains deferred and unchanged.

---

## 4. Accepted authority implemented by the correction

### 4.1 Import closure

The generator has no caller-selected entry list. Its first and only root is
`engine.registration_receiver`. It resolves static AWA imports recursively,
adds every parent package initializer, includes
`engine.registration_schema:registration_schema.sql`, orders records by
relative-path UTF-8 bytes, assigns contiguous FD16+, and emits only canonical
`awa-registration-import-manifest/v2`.

Dynamic product imports, unresolved relative imports, duplicate path/name/FD,
missing receiver/host/hook/schema/resource, wrong owner/path, extra product
byte or bounds mismatch refuse. Receiver's current `__import__("hashlib")` is
replaced by an ordinary static stdlib import; no dynamic-product exception or
allowlist is added.

`ImportManifestV2.from_bytes` and construction apply the same canonical,
count, aggregate, mandatory-closure and self-digest validation. A
caller-enumerated object that omits host or hook runtime is invalid.

### 4.2 Bundle, receipt and owner gate

Bundle-manifest v3 contains the exact import records plus exact import,
host-authority and writer-capability authority records. It binds receiver plain
bytes, installed-file hash, import-manifest hash and host-authority digest.
Bundle-projection v2 repeats the accepted upstream values. DIRECT receipt v4
and owner-gate v3 retain their accepted fields and must agree exactly on
bundle, projection, import, installed, wrapper and packet authority. The
receipt body hash branches before the gate; final receipt binds the gate.
Bundle-manifest v2 is parsed only to refuse its fixed-point authority.

The packet and root admin transport these exact bytes by role and hash. Neither
reconstructs, substitutes or silently upgrades them. Product current selects
the derived `versions/<generation>-<bundle_digest>` directory. Runtime and
product currents publish atomically under the accepted transaction; actual
installation remains separately gated.

### 4.3 Launch and receiver

Bootstrap opens and retains:

```text
3 control
4 private runtime manifest
5 import manifest v2
6 owner gate v3
7 private-runtime current v2
8 launch context v2
9 product current
10 product bundle directory
11 bundle manifest v3
12 bundle projection v2
13 direct receipt v4
14 host authority v2
15 writer capability
16+ every PACKAGE_INITIALIZER/MODULE/RESOURCE in manifest order
```

Parent and child independently validate canonical schemas, all cross-hashes,
roles, modes, sizes, vnode identity, link count, FD order/count/aggregate and
remeasurement at READY and GO. Any bootstrap/child version mismatch refuses.
The child installs the retained importer and AWA deny finder only after GO.
The first requested module is exactly `engine.registration_receiver`; Python
executes `engine` first, then receiver, then only declared dependencies.
Filesystem product fallback, config-v1, product path in argv/environment and
authority reread refuse.

Receiver passes parsed immutable launch context, host authority, receipt, gate,
currents, projection, manifest, writer capability and retained resource
provider. Host uses those objects directly.

### 4.4 Four-field invocation

The immutable invocation is exactly:

```text
event
server_or_empty
discriminator
serializer_schema
```

MCP events propagate exact nonempty `mcp_server_name`; non-MCP events propagate
empty server. `subagentStart` propagates `cursor-subagent/v1`; other permission
events propagate `cursor-permission/v1`. Host matches all four fields and gets
role only from the sealed inventory. There is no discriminator fallback,
wildcard, request role or host-side inference. `FakeService.calls` is
`list[ObservableInvocation]`.

### 4.5 Inert R0

`--check` emits v2, `executed:false`, `predeployment_evidence:"absent"`,
`rollout_stage:"NONE"`, empty cuts, the exact accepted 19-barrier catalog,
all completeness booleans false, all evidence/manifest hashes null,
`external_write_observer:"unavailable"`,
`claim_scope:"FINITE_GOVERNED_SURFACES_AND_OBSERVED_TARGETS"`,
`final_r0_requires_merged_exact_head:true` and
`live_state_changed:false`.

`--run` without separately supplied future authority/signature exits nonzero
with the same inert claims and no prompt, privilege, process, protocol,
install, receiver or live-state action. Subprocess tests compare the full
object, stderr/exit and before/after governed state.

Actual R0 preserves accepted V5 order:

```text
owner GO binds known merged head, interpreter, throwaway scope,
barriers and evidence policy
-> construct and measure fixture
-> emit exact owner-gate bytes
-> obtain detached owner signature
-> remeasure
-> execute
```

Future fixture roots, manifests, gate hashes and signatures are outputs after
GO, never pre-GO inputs.

---

## 5. Exact inherited and resulting sets

The full implementation ceiling remains the accepted V10:

```text
domain  awa-registration-v10-implementation-scope/v1
count   64
digest  2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334
```

V12 C-RUNTIME is that exact 64-path sorted set minus only deferred desktop UAT:

```text
domain  awa-registration-v12-c-runtime-scope/v1
count   63
digest  4bc9ddb451db26c3187d828ee1a69b9739a402943797386e3f5261b2c6ff518c
excluded live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
```

The inherited C-FINAL set remains exact:

```text
domain  awa-registration-v7-c-final-scope/v1
count   24
digest  1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8
```

All 22 corrective paths are already inside the 64-path ceiling. No new
implementation path is added.

The five base-equal exclusions remain:

```text
contracts/awa-contract.v1.json
engine/tests/test_install_lib.py
engine/tests/test_registration_profile.py
engine/tests/test_registration_store.py
engine/tests/test_verify_lane.py
```

Therefore the exact sorted runtime materialization set remains the C-RUNTIME
set minus those five:

```text
domain  awa-registration-v12-c-runtime-materialization-scope/v1
count   58
digest  8f096b940fb1855f68fb9e0f8cef49887930176ec0a807e04c590e7c48e77dcd
```

Governance delivery remains:

```text
domain  awa-registration-v12-governance-delivery-scope/v1
count   9
digest  424c09fd47932eb45e9c20bbc3539802381771472ad733628b95a81f2dc62d15
```

```text
docs/plans/README.md
docs/plans/native-entry-durable-registration-v10.md
docs/plans/native-entry-durable-registration-v11.md
docs/plans/native-entry-durable-registration-v12.md
docs/plans/native-entry-durable-registration-v5.md
docs/plans/native-entry-durable-registration-v6.md
docs/plans/native-entry-durable-registration-v7.md
docs/plans/native-entry-durable-registration-v8.md
docs/plans/native-entry-durable-registration-v9.md
```

Only README and V12 change at governance delivery; V5–V11 are preservation
records. The eventual PR union remains the disjoint union of 58 runtime and
nine governance paths:

```text
domain  awa-registration-v12-final-pr-scope/v1
count   67
digest  4e9a7429d6023f561b2b2232ebc1326407ac486fa3ebbd4d9e7b82307b7f5787
```

Runtime-record framing remains:

```text
SHA256(
  ASCII("awa-registration-v10-c-runtime-working-manifest/v1") || 0x00 ||
  each sorted path || 0x00 || "REGULAR" || 0x00 ||
  three-digit lower-octal mode || 0x00 || file SHA256 || LF
)
```

The exact drafting candidate, using the three protected working bytes and HEAD
for every other C-RUNTIME path, remains:

```text
candidate runtime manifest     63 / 8e2f609d8c9d1506fbf556d8e103573ceaa7610d3ac5c9ab7dd672c2d2690c5e
candidate materialization map  58 / 434631423551d9af99a98d1cea14710ef7230ec49f25f823c966f22262acf130
```

These are starting-candidate measurements, not predicted delivery outputs.
Final corrected hashes, commits, trees, manifests, maps, receipts, review IDs,
packet roots, keys, signatures and prompt evidence are outputs and must be
recomputed.

---

## 6. Acceptance ledger

| ID | Required evidence | Refusal |
|---|---|---|
| V12-A01 | Generator-owned receiver root; exact recursive host/hook/schema/resource closure; no caller enumeration | Omission, alternate root or dynamic product import |
| V12-A02 | Canonical import-v2 parser and bundle-v3 parser independently bite fields, order, counts, bounds, digest and mandatory records | Create-only validation or permissive parse |
| V12-A03 | Bundle v3 → projection v2 → receipt v4 body → gate v3 → final receipt exact hash agreement | v2 execution, fixed point, stale duplicate or receipt v5 |
| V12-A04 | Packet/root admin include and validate exact product authority assets; paired product/runtime current publication is atomic | Opaque evidence-only claim, omitted asset or partial current |
| V12-A05 | FD3–15+ exact topology; parent/child independent schema and descriptor verification at READY/GO | Five-FD v1 launch, mismatch or path authority |
| V12-A06 | Retained importer requests receiver first; host/hook/schema/resource imports are bound; filesystem fallback and config-v1 refuse | Unbound transitive byte or old launcher success |
| V12-A07 | Direct four-field MCP/server/subagent serializer tests and typed invocation calls bite independently | Discriminator-only or inferred identity |
| V12-A08 | Full subprocess equality for inert R0 check and run refusal; no actual R0 | Missing false/null field, fabricated evidence or side effect |
| V12-A09 | Exact 22-path ceiling, 19 reopened paths, 41 preserved delivered paths, 63/58/67 sets and five base-equal exclusions reproduce | Scope escape or preserved drift |
| V12-A10 | Complete fresh exact-head Gate 5 repeats after every head/assertion change | Overlay, stale review/check or missing lane |

No existing assertion may be deleted, weakened, skipped, renamed or converted
to existence-only checking.

---

## 7. Serial non-transitive gates

1. **V12 acceptance:** only the three status/index substitutions in §9.
2. **`V12-GOVERNANCE-DELIVER`:** bind accepted plan/index/normalized hashes,
   predecessor hashes, exact head/tree/parent/base/branch, Draft/unarmed PR,
   exact nine-path governance set and two-path delta; stage/commit/push only
   README and V12. No readiness or implementation.
3. **`V12-C-RUNTIME-TESTS-FIRST`:** bind the governance head, source lock,
   exact 64/63/24/22/11/11/19/41 scopes, all starting hashes and protected
   inputs; edit only the eleven test paths and observe expected failures.
4. **`V12-C-RUNTIME-CORRECTIVE-IMPLEMENT`:** after tests fail correctly, edit
   only the eleven production/harness paths; preserve all other bytes.
5. **`V12-C-RUNTIME-CORRECTIVE-DELIVER`:** bind final 22 hashes, exact final
   63-record tree manifest, 58-record map, 67-path union and preservation;
   stage/commit/push only those paths to the existing Draft PR.
6. **`V12-C-RUNTIME-GATE-5`:** fresh focused authority/import/bootstrap/
   child/host/hook/packet/admin/launcher/receiver/R0 tests; all inherited
   registration/contract/freeze suites; py_compile and shell syntax;
   `make verify-pre-pr`; `make verify`; exact diff/status/scope/manifests;
   fresh Bugbot and Security Review. No actual R0, prompt, key, privilege,
   release or install.
7. **`V12-C-RUNTIME-QUALIFICATION-PREPARE`:** bind clean reviewed head/PR and
   absent fresh user-owned packet root; exactly two clean local builds, one
   disposable qualification-only synthetic keypair, Q1/Q2 and packet-v2
   material. No owner key, prompt, privilege or final packet.
8. **`V12-C-RUNTIME-PRIVILEGED-QUALIFICATION`:** one separate GO permits
   exactly one native SecurityAgent prompt and one privilege attempt against
   only the disposable qualification root.
9. **`V12-C-RUNTIME-PACKET-FINALIZE`:** bind successful qualification;
   capture accepted evidence, delete/close disposable private key and prove
   absence; create evidence-index v2, packet-v2 and `FINALIZE_READBACK`.
10. **`V12-C-RUNTIME-PACKET-ACCEPT`:** bind all packet/head/PR/source/scope
    bytes and authorize one nonmutating `ACCEPT_READBACK`.
11. **`V12-C-RUNTIME-READY`:** after an explicit owner GO naming the immutable
    packet and fresh Gate 5, authorize one `READY_READBACK`; the owner
    `KleinPerkins` is the sole Draft-to-Ready transition actor. This execution
    agent never marks ready. After the owner transition, the reviewer App alone
    approves, arms native auto-merge and merges; no agent assigns those actions
    elsewhere.
12. **C-FINAL:** starts only from merged C-RUNTIME live main under its own
    24-path implementation/delivery/Gate-5/qualification/readiness gates;
    desktop UAT remains deferred there.
13. **Actual R0:** separate post-merge GO and sequence in §4.5.
14. **Release/tag/publication:** separate exact artifact/revision GO.
15. **Installation:** separate released-artifact/target GO.
16. **Host activation:** separate installed-artifact/host-wiring GO.
17. **R1 canary:** separate live-target GO.
18. **C1 clearance:** evidence only.
19. **R2 rollout:** separate rollout GO.

Qualification order is fixed:

```text
PREPARE -> exactly one privileged prompt -> FINALIZE -> ACCEPT -> READY
```

No gate implies the next. No mixed V11/V12 gate or fallback exists.

---

## 8. Stops and unknown outputs

Stop for any path outside the 22-path correction; any drift in 41 preserved
runtime paths, predecessor plans/ADRs/contracts or protected inputs; any extra
full-status record; nonempty staging; PR/head/base drift; caller-selected or
incomplete import closure; bundle v1/v2/config-v1 execution; ignored authority;
receipt v5; a new packet schema, digest domain, key authority, privilege
mechanism or rollout stage; failed/stale Gate 5; unauthorized native prompt,
actual R0, release, install, activation or rollout.

Unknown future corrected hashes, commits, trees, manifests, maps, test receipts,
review IDs, packet roots, packet/index digests, readbacks, keys, signatures,
fixture roots and prompt evidence are outputs, never guessed inputs.

---

## 9. Exact status-only acceptance

Only a future exact owner acceptance envelope may:

1. change this status to
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. change the V12 README row to
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-05`;
3. change only the V11 README row to
   `SUPERSEDED BY V12 — 2026-10-05`.

No plan/ADR byte changes. Acceptance authorizes no staging, Git/PR mutation,
governance delivery or downstream action.

### 9.1 Normalization and promotion simulation

```text
SHA256(
  ASCII("awa-registration-v12-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

Replace exactly one plan status line with:

```text
- **Status:** __AWA_V12_STATUS__
```

Replace exactly one V12 DRAFT/accepted row with:

```text
| `native-entry-durable-registration-v12.md` | __AWA_V12_INDEX_STATUS__ | Corrective authority successor to accepted v11; closes receiver-rooted import-manifest v2, bundle-manifest v3, retained launch, four-field hook ABI and inert R0 before exact-head qualification. |
```

Replace exactly one V11 accepted/superseded row with:

```text
| `native-entry-durable-registration-v11.md` | __AWA_V12_PREDECESSOR_INDEX_STATUS__ | Minimal packet-authority successor to accepted v10; replaces packet-before-key with dependency-correct qualification preparation and upgrades exact-head packet producer/consumer authority from historical v1 to accepted v2. |
```

Each includes one LF. Zero, duplicate, mixed, CRLF, NUL or nonexact context
refuses.

Simulation is in memory:

1. hash exact draft plan/index;
2. apply only the three substitutions to copies;
3. hash simulated promoted plan/index;
4. normalize draft and promoted pairs independently;
5. require byte-identical normalized preimages and digest; and
6. prove every non-status byte unchanged.

### 9.2 Closed external envelope

`full_status_count` and `full_status_sha256` are computed over the exact,
unmodified stdout bytes from this command with no pathspec:

```text
LC_ALL=C git -c core.quotePath=true status --porcelain=v1 --untracked-files=all
```

`staging_empty:true` requires exact empty stdout from:

```text
git diff --cached --name-only --
```

The parser requires the top-level key set to equal the closed template below
exactly and requires
`schema == "awa-registration-v12-plan-acceptance-go/v1"` before reading
`authorized` or any authorized action. Unknown, missing or duplicate keys,
wrong schema, noncanonical JCS, a sixth status record or nonempty staging
refuses before mutation.

The external canonical JCS object has exactly:

```json
{"accepted_v10_plan_sha256":"6eb266c7e88f7aa26444f554fab7cc288e8973a89666f7bd8d8664290a1ecc8a","accepted_v11_acceptance_envelope_digest":"cf8f3621802fbc16abb5466a2daf11e5559591ad75a79deb787163ce36234ba9","accepted_v11_index_sha256":"9f403c0a9f2c4e79fea25ba5e2765591a19b0dd46b93d1d490c52647b1a62447","accepted_v11_normalized_digest":"d980681d19994b1a7c5426408d5a99c4542e2248f82f7e87fad55da40b04fc52","accepted_v11_plan_sha256":"fcd98e5173d5ec705e6998f1673a6ed693c8e4625ef2f669a06db60e83577c4f","action":"ACCEPT_PLAN_V12","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","authorized":true,"authorized_actions":["MARK_V11_INDEX_SUPERSEDED","PROMOTE_V12_INDEX_STATUS","PROMOTE_V12_PLAN_STATUS"],"authorized_by":"KleinPerkins","auto_merge_armed":false,"base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","branch":"impl/native-entry-durable-registration-v7-runtime-bootstrap","c_final_scope_count":24,"c_final_scope_hash":"1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8","c_runtime_scope_count":63,"c_runtime_scope_hash":"4bc9ddb451db26c3187d828ee1a69b9739a402943797386e3f5261b2c6ff518c","candidate_materialization_map_count":58,"candidate_materialization_map_digest":"434631423551d9af99a98d1cea14710ef7230ec49f25f823c966f22262acf130","candidate_runtime_manifest_count":63,"candidate_runtime_manifest_digest":"8e2f609d8c9d1506fbf556d8e103573ceaa7610d3ac5c9ab7dd672c2d2690c5e","corrective_scope_count":22,"corrective_scope_hash":"ab45f49d527c4575d6f54704109af3a03e46c7961029150c0d5e294bf6eccf88","current_final_pr_scope_count":63,"current_final_pr_scope_hash":"dbf70d6e608353aac2e6ba87832be0eff9490807f4d7b6dd5312a86c9a2e4de9","delivered_materialization_map_count":55,"delivered_materialization_map_digest":"576cc1614774cffc269b0575726a16e5d98fb16eaf4cc23e7049e14b8d68a355","delivered_runtime_manifest_count":60,"delivered_runtime_manifest_digest":"83fdd8cc870f4f4012ad8330aa10a613c2ac0796c0219f22e213e187cf530bf9","denied_implications":["ACCESS_GENERATE_OR_SIGN_WITH_ANY_KEY","ALTER_PRESERVED_WORK","BUILD_OR_PUBLISH","COMMIT_PUSH_OR_MUTATE_PR","GOVERNANCE_DELIVER","IMPLEMENT_OR_DELIVER","INVOKE_NATIVE_AUTHORIZATION_PROMPT","MUTATE_EXTERNAL_STATE","PACKET_PREPARE_FINALIZE_OR_ACCEPT","PRIVILEGED_OPERATION","READY_OR_MERGE","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_ACTUAL_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","eventual_final_pr_scope_count":67,"eventual_final_pr_scope_hash":"4e9a7429d6023f561b2b2232ebc1326407ac486fa3ebbd4d9e7b82307b7f5787","exact_head":"8e03121155decd45128ae9babcbfc5d25a156c9a","exact_head_parent":"19d3c6c96dc1d231fe60bc497d42c81f23923d78","exact_head_tree":"1a8f9863c10c044b982c6fe820ceb84ffe14e540","full_scope_count":64,"full_scope_hash":"2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334","full_status_count":5,"full_status_sha256":"022a235f70d9b849e6716a1398a93236c367826b326c33648672eab831c13f0c","governance_delivery_scope_count":9,"governance_delivery_scope_hash":"424c09fd47932eb45e9c20bbc3539802381771472ad733628b95a81f2dc62d15","materialization_scope_count":58,"materialization_scope_hash":"8f096b940fb1855f68fb9e0f8cef49887930176ec0a807e04c590e7c48e77dcd","normalized_digest":"<reviewed lowercase 64-hex>","pr_number":183,"pr_state":"DRAFT","preserved_v11_scope_count":41,"preserved_v11_scope_hash":"ed94977c8482aaa7b12015661a58a0ee59a5e5d942d31aa03e1966c3f47aaa67","production_correction_scope_count":11,"production_correction_scope_hash":"bff120944736390d2bcfeca6b8fda857dc0b11012867aba69c68f4a67feffb52","promoted_index_sha256":"<reviewed lowercase 64-hex>","promoted_plan_sha256":"<reviewed lowercase 64-hex>","reopened_v11_scope_count":19,"reopened_v11_scope_hash":"4819b7db08310eaa7c6d8191fe2f8fc512bc3aeb078baefd4c876937087a0aa0","repository":"KleinPerkins/awa","schema":"awa-registration-v12-plan-acceptance-go/v1","source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","staging_empty":true,"starting_head_hashes":{"engine/registration_hook_runtime.py":"60ceb74f28aca5de24e811d4ac21933c3ec95c7e8c1ad2b111d352b48e6df3e0","engine/registration_host.py":"57d1c0d956ff76a8a129d1563663161dd3e22c1e835c703a3d767516faf4aaf5","engine/registration_installer.py":"e6fc894f0ddf1900acdcaff196238c32ec914c045756274ea29b4521f1d057e4","engine/registration_launcher.py":"807e0d50922c47bde638ed9bab70e784f9787a526e2cf45828982dfae346979f","engine/registration_privileged_installer.py":"03e313ee43c5fd1defd78e521393c11238bca914e8f271e53701bbc7aeb450f5","engine/registration_projection.py":"3d08bbc7cc6c2d2598df212db9c563d186852de2403207c55b256e5ea6e73f42","engine/registration_receiver.py":"49925ba2687f01b88bbf26c0fc15ee9c1db48aa1ea63ca50f332952ff3111831","engine/tests/test_kernel_off_matrix.py":"3d56140fe33f34c46232ae2f29cb89e4fcd229ff17c3dab7df16e8f2ed3fd6ef","engine/tests/test_platform_bootstrap.py":"71fc98555dd75fbf4c6510ae183d07873427fc106f4c30f15098bc437c744280","engine/tests/test_private_runtime_installer.py":"172a3ac4583fe5d021e4dd6256159aabea4c874b97c39cd96c20d153ce11a61a","engine/tests/test_registration_deployment_authority_c.py":"a71ad98bf6050b49dc3a9f49a03910a29b13640e0f7b7b5d94fbae59f0ef6222","engine/tests/test_registration_hook_runtime_c.py":"8955ce00f434df74fbad5cc15e09a88dc973be8a4e98b19b37bdc68a34774731","engine/tests/test_registration_host_c.py":"77bc561261f91f0c531bef76e5223de7c517a0b51119347e23ecd1e2baf04870","engine/tests/test_registration_installer_c.py":"e89582f0f3093dac208c9bf549d05e151f64023d8e3b870da436c45c141a2a79","engine/tests/test_registration_launcher_c.py":"88bfba9381eca437cf137918331190a66c0f96f9e8179a129f6cd96ff98c7230","engine/tests/test_registration_packaging_c.py":"4413aafa597b2fbc9a48df31b5af81baa5ec74960c1bfb41d167795d146c3031","engine/tests/test_registration_privileged_installer.py":"f76693e9eb82266eb1ffebb0d4193ace288da57702dbb91989f7a971720a4463","engine/tests/test_registration_receiver_c.py":"0cbb0ccb09a1ee0c5bc799ca009a6474f9aab53a18e9a7de0d86740e1856ff4d","kernel/bin/awa-private-runtime-admin.py":"b09d8db7896855f25e15c0f41aa54f63ebf22b9e0b07649fee1413924b65f8a2","kernel/bin/awa-registration-bootstrap.py":"88d3793b8f66ef8868e68d499f3beaa4af0d60b78cf14dde996590703b473c5d","kernel/bin/awa-registration-child.py":"884ae7d618dd5907829c1750e98fb7c3f38b52e35a5bcf6ce7b5fa59e3d65dc1","live-verify/native-entry-durable-registration-r0.py":"6e933d022751ce5a60803923b027dae9bb446cb5fbd45cf1ba6ee4d6d1dd9052"},"starting_working_hashes":{"engine/registration_hook_runtime.py":"10f6048738a031a48ccf75f76965ad7993792140253b9997d6cf55c56d5b6c9a","engine/registration_host.py":"57d1c0d956ff76a8a129d1563663161dd3e22c1e835c703a3d767516faf4aaf5","engine/registration_installer.py":"e6fc894f0ddf1900acdcaff196238c32ec914c045756274ea29b4521f1d057e4","engine/registration_launcher.py":"807e0d50922c47bde638ed9bab70e784f9787a526e2cf45828982dfae346979f","engine/registration_privileged_installer.py":"03e313ee43c5fd1defd78e521393c11238bca914e8f271e53701bbc7aeb450f5","engine/registration_projection.py":"3d08bbc7cc6c2d2598df212db9c563d186852de2403207c55b256e5ea6e73f42","engine/registration_receiver.py":"49925ba2687f01b88bbf26c0fc15ee9c1db48aa1ea63ca50f332952ff3111831","engine/tests/test_kernel_off_matrix.py":"3d56140fe33f34c46232ae2f29cb89e4fcd229ff17c3dab7df16e8f2ed3fd6ef","engine/tests/test_platform_bootstrap.py":"71fc98555dd75fbf4c6510ae183d07873427fc106f4c30f15098bc437c744280","engine/tests/test_private_runtime_installer.py":"172a3ac4583fe5d021e4dd6256159aabea4c874b97c39cd96c20d153ce11a61a","engine/tests/test_registration_deployment_authority_c.py":"a71ad98bf6050b49dc3a9f49a03910a29b13640e0f7b7b5d94fbae59f0ef6222","engine/tests/test_registration_hook_runtime_c.py":"0c4be2717f64818778fdcc6e686814d8066944a5e7a7575eb4e17c5753e26e0d","engine/tests/test_registration_host_c.py":"77bc561261f91f0c531bef76e5223de7c517a0b51119347e23ecd1e2baf04870","engine/tests/test_registration_installer_c.py":"e89582f0f3093dac208c9bf549d05e151f64023d8e3b870da436c45c141a2a79","engine/tests/test_registration_launcher_c.py":"88bfba9381eca437cf137918331190a66c0f96f9e8179a129f6cd96ff98c7230","engine/tests/test_registration_packaging_c.py":"4413aafa597b2fbc9a48df31b5af81baa5ec74960c1bfb41d167795d146c3031","engine/tests/test_registration_privileged_installer.py":"f76693e9eb82266eb1ffebb0d4193ace288da57702dbb91989f7a971720a4463","engine/tests/test_registration_receiver_c.py":"0cbb0ccb09a1ee0c5bc799ca009a6474f9aab53a18e9a7de0d86740e1856ff4d","kernel/bin/awa-private-runtime-admin.py":"b09d8db7896855f25e15c0f41aa54f63ebf22b9e0b07649fee1413924b65f8a2","kernel/bin/awa-registration-bootstrap.py":"88d3793b8f66ef8868e68d499f3beaa4af0d60b78cf14dde996590703b473c5d","kernel/bin/awa-registration-child.py":"884ae7d618dd5907829c1750e98fb7c3f38b52e35a5bcf6ce7b5fa59e3d65dc1","live-verify/native-entry-durable-registration-r0.py":"5b9a7c7f76f921644526933260927b2f57c6c8fc95be594620dfd15df2ce5997"},"tests_first_scope_count":11,"tests_first_scope_hash":"673fc7e96b13ff45d51b378ac1a29d446fd4a84b781b8eee0a77613da9e5b99c"}
```

Only the externally submitted object replaces placeholders. Its digest is:

```text
SHA256(
  ASCII("awa-registration-v12-plan-acceptance-envelope/v1") || 0x00 ||
  JCS(concrete_external_envelope) || LF
)
```

The envelope authorizes only the three status/index promotions. Denied
implications are closed by the governance stop and serial gates; acceptance
does not authorize governance delivery or anything downstream.

Immediately before any promotion, rerun the two commands above and recompute
every envelope field from live sources. Require exact equality for the closed
key set and schema; all accepted authority hashes; branch, local/remote/PR
head, tree, parent and base; Draft/unarmed PR; source lock; full status and
staging; every scope set/count/digest; delivered and starting-candidate
manifests/maps; starting HEAD and working hashes; draft/promoted plan/index
hashes; draft/promoted normalized-byte equality and normalized digest; and
denied implications. Perform the three substitutions only after that immediate
revalidation. Any mismatch or sixth status record refuses before mutation.

---

## 10. Standalone refinement record

1. **Facts:** live Git/GitHub/hash state and source authority were re-read;
   the former three-path premise was removed.
2. **Gaps:** production generation, projection, packet/admin transport,
   bootstrap/child, receiver/host, historical launcher, four-field ABI and
   inert R0 now have biting owners.
3. **Subtraction:** no new implementation path, schema, domain, receipt, key,
   privilege, stage or service was added; 42 full-ceiling paths stay
   out of corrective edits.
4. **Under-scope:** acceptance, governance delivery, tests-first production
   correction, exact delivery, fresh Gate 5, qualification, readiness,
   C-FINAL, actual R0, release, install, activation and rollout remain separate.

Independent re-review corrections are incorporated, but no acceptance
clearance is claimed. The acceptance envelope remains PRE-REVIEW and must not
be submitted until its 22-path closure and all exact hashes are revalidated.
