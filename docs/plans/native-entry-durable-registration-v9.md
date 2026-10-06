# Native Entry Durable Registration

- **Version:** v9
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-03
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v8.md`](native-entry-durable-registration-v8.md),
  preserved byte-identically at SHA-256
  `1009c3f2e950fcf88adc1f2a862e7127c9d8bb36001389e6ed22bed347a3e770`
  and normalized digest
  `4d673c3d552a0f2a3db6b15e56bccbbe07ee5a485f1ce4ad91f673edeb8b2586`.
- **Inherited authority:** accepted v7 SHA-256
  `dddae47b0840f5f25f375a92bf3736a654e095549b9e9d7f3c68c6360b230384`,
  normalized digest
  `88eb649abe56f790bc24c7ef84fca777b36a89f44dd444fa66969202a19cec4d`;
  accepted v6 SHA-256
  `ee8e4fcadd2951fcf3b4260aa5a4672ef98247a2839d7ad53a7ea2d6e02f6a47`,
  normalized digest
  `1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452`;
  accepted v5 SHA-256
  `4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b`;
  and immutable [ADR 0026](../adr/0026-durable-registration-authority-hardening.md)
  SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Source baseline:** live `HEAD` and `origin/main`
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`.
- **Continuation branch:**
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`.
- **Source lock:**
  `a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72`.
- **Preservation:** pre-v7 Body C manifest
  `9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a`;
  stopped v8 C-RUNTIME manifest after tests-first work
  `d8fce3ac9215d9d608a546305996ade4f2175f8de2c014f7fa261f9b0f28a9f6`.

> **Governance stop:** this draft authorizes only this new file and its DRAFT
> README row. It authorizes no implementation, contract-file creation,
> staging, commit, push, PR, build, packet, key access/generation/signing,
> native prompt, privileged operation, installation, publication, release,
> activation, R0/R1/C1/R2, external mutation, or rollout.

---

## 1. Valid stop and smallest successor

Independent adjudication returned `VALID_STOP`. Accepted v8 bundle-manifest v2
has this exact infeasible authority:

1. its field set includes `bundle_relative_dir`;
2. that value must equal
   `versions/<generation>-<bundle_digest>`; and
3. `bundle_digest` hashes the canonical manifest excluding only the direct
   `bundle_digest` field.

Therefore the SHA-256 preimage contains the digest being solved. Accepted v8
defines no template, secondary digest, or exclusion that can construct that
fixed point. V9 does not reinterpret frozen v8. It makes bundle-manifest v2
historical parse-and-refuse authority and introduces only bundle-manifest v3.

Every unaffected v8/v7/v6/v5/ADR requirement remains normative exactly as
written. If this delta and an inherited clause conflict, this plan replaces
only the exact v2 bundle field/domain/path derivation and the four successor
static-contract pins stated below; otherwise the inherited clause wins.
Receipt-v4, owner-gate-v3, product-current-v1, runtime-current-v2,
bundle-projection-v2, host-authority-v2, import-manifest-v2, launch-context-v2,
admin transaction-v1, admin receipt-v2, packet-v2, reconciliation, POSIX
startup closure, qualification confinement, and all operation/outcome matrices
remain unchanged.

The smallest demonstrated delta is exactly four new contract files. There is
no receipt-v5, gate-v4, new executable module, test file, daemon, database
table, signing namespace, body, or rollout action.

---

## 2. Bundle-manifest v3 and derived directory

### 2.1 Exact schema and digest

`awa-registration-bundle-manifest/v3` has exactly:

```text
schema,generation,bundle_entry_plain_hash,installed_file_hash,
import_manifest_hash,host_authority_digest,records,record_count,
aggregate_size,bundle_digest
```

It is accepted-v8 bundle-manifest v2 with only `bundle_relative_dir` removed.
Every v8 record schema, kind/domain, exact payload-plus-three-authority
membership, ordering, uniqueness, mode, size, count, aggregate bound,
receiver plain-hash rule, installed-tree allowlist, and downstream exclusion
remains exact. The schema value is
`awa-registration-bundle-manifest/v3`.

```text
bundle_digest =
  SHA256(ASCII("awa-registration-bundle-manifest/v3") || 0x00 ||
         JCS(object_without_bundle_digest) || LF)
```

The digest preimage contains no path derived from `bundle_digest`. Validators
reject extra `bundle_relative_dir`, missing/extra fields, v2 schema, or the v2
digest domain. Bundle-manifest v2 may be parsed only to return typed refusal
`BUNDLE_MANIFEST_V2_FIXED_POINT`; it never authorizes publication, recovery,
selection, launch, qualification success, or packet acceptance.

### 2.2 Exact post-digest derivation

After validating v3 and reproducing `bundle_digest`, derive:

```text
bundle_relative_dir =
  UTF8("versions/") || UTF8(generation) || UTF8("-") || ASCII(bundle_digest)
```

`generation` remains a positive unsigned decimal string. The result is one
relative two-component path, at most 256 UTF-8 bytes, with no empty, dot,
dot-dot, slash-bearing generation, normalization alias, or alternate spelling.
It is not a bundle-manifest field and is never accepted from a caller.

The immutable version directory, product-current
`bundle_relative_dir`, directory FD10, FD11 bundle bytes, projection v2,
direct receipt-v4, owner gate-v3, retained-version inventory, transaction
assets, packet evidence, qualification Q1/Q2, and recovery all independently
derive the same string from the already-validated generation and digest.
Any supplied/stored path is equality evidence only; mismatch refuses before
selection or launch. All openat-relative ownership, mode, no-symlink,
nlink-one, descriptor, READY/GO, retention, rollback, and pruning checks from
v8 remain unchanged.

### 2.3 Downstream compatibility

No receipt-v5 or gate-v4 is required. Accepted receipt-v4 and gate-v3 already
bind `bundle_digest`, `bundle_projection_hash`, `import_manifest_hash`, and
immutable bundle generation through their accepted fields and transitive
authority. Product-current-v1 remains downstream and binds both
`bundle_relative_dir` and `bundle_digest`; it now proves the deterministic
derivation instead of feeding the digest.

Bundle-projection-v2 remains schema-for-schema unchanged. It accepts only a
validated v3 bundle digest. Any implementation finding that receipt-v4,
gate-v3, projection-v2, or another downstream accepted field/domain must
change is an immediate successor stop, not authority to expand v9.

---

## 3. Acyclic authority DAG

```text
public source lock + exact SLSA attestation
  └─ deterministic runtime builds/qualification
      ├─ Q1/Q2 fixture bytes → packet-root indexes → packet v2
      └─ runtime manifest/capability/signature inventory/packet v2
          └─ owner-signed runtime envelope
              └─ immutable runtime version → runtime-current v2

product import/resource bytes + host authority + writer capability
  ├─ import-manifest v2
  └─ bundle-manifest v3 object without bundle_digest
      └─ bundle_digest
          ├─ derive versions/<generation>-<bundle_digest>
          └─ bundle-projection v2
              └─ direct receipt-v4 body
                  └─ owner gate-v3 + detached signature
                      └─ final direct receipt-v4

runtime-current v2 + derived bundle directory + bundle/projection/import/host
  + final receipt/gate
  └─ product-current v1

request/context + exact 16-contract set + exact recovery assets
  └─ asset-index v1
      └─ immutable transaction ancestry → admin receipt v2 → admin head v1

head/current/receipt equality + retained descriptors
  └─ launch-context v2 → READY → GO → retained-byte import
```

Exact exclusions:

- bundle-manifest v3 excludes `bundle_relative_dir`, projection, receipt,
  gate, all currents, admin authorities, packet and launch context;
- the derived directory is not a digest input; it is a pure function of
  validated `generation` and `bundle_digest`;
- projection/receipt/gate remain downstream and exclude product current,
  admin authorities, launch context and observations as frozen in v8;
- product current may bind the derived path and upstream digests but remains
  excluded from every upstream immutable authority;
- transaction/asset-index/current/receipt/head exclusions and immutable phase
  ancestry remain exactly v8; and
- launch context remains invocation-only and excludes READY/GO/import results.

There is no self-reference, transaction↔receipt cycle, current↔receipt cycle,
head↔current cycle, packet fixture fixed point, or expected/observed evidence
feedback. All bundle, pointer, receipt, gate, denial, qualification and
readiness vectors regenerate with the v3 domain.

---

## 4. Exact static-contract set

Every INSTALL, UPDATE, ROLLBACK, REMOVE and QUALIFY PREPARED asset index must
contain exact set equality over these 16 logical paths and exact SHA-256
values. There is no operation-specific subset:

```text
contracts/awa-contract.v1.json|408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9
contracts/awa-contract.v2.json|db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a
contracts/awa-contract.v3.json|fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9
contracts/awa-contract.v4.json|f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3
contracts/awa-registration-admin-audit.v1.json|a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a
contracts/awa-registration-admin-audit.v2.json|b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2
contracts/awa-registration-admin-audit.v3.json|f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa
contracts/awa-registration-owner-signers.v1|9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e
contracts/awa-registration-owner-signers.v2|690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3
contracts/awa-registration-platform-bootstrap.v1.json|4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c
contracts/awa-registration-platform-bootstrap.v2.json|404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9
contracts/awa-registration-platform-bootstrap.v3.json|ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0
contracts/awa-registration-private-runtime.v1.json|f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321
contracts/awa-registration-private-runtime.v2.json|91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8
contracts/awa-registration-private-runtime.v3.json|29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84
contracts/awa-registration-privileged-envelope.v1.json|7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034
```

Records are sorted by UTF-8 logical path, each path occurs once, cardinality
is exactly 16, and every record duplicates request id, context digest and
mode-bound qualification nonce exactly as frozen in v8. The immutable asset
index binds the path/hash records; it excludes its own digest and all
transaction/receipt/head fields. The admin v3 static file records paths,
cardinality and dynamic hash authority, not its own hash, avoiding a static
contract fixed point. The plan, request/context, asset index and acceptance
envelope bind the concrete 16 hashes.

All prior contracts remain byte-identical historical/transitive authority.
V8's four absent future v2/v3 files remain implementation outputs under the
later GO; v9 adds four more absent successor outputs. None is created by plan
acceptance.

---

## 5. Exact successor contract bytes

Each block is canonical JCS plus exactly one LF. These are reviewed future
bytes, intentionally absent until a separate V9-C-RUNTIME-IMPLEMENT GO.

### 5.1 `contracts/awa-registration-private-runtime.v3.json`

```json
{"bundle_manifest_schema":"awa-registration-bundle-manifest/v3","bundle_manifest_v2_execution":"PARSE_AND_REFUSE_SHA256_FIXED_POINT","bundle_relative_dir_derivation":"versions/<generation>-<bundle_digest>","bundle_relative_dir_in_digest_preimage":false,"inheritance_rule":"Every awa-registration-private-runtime/v2 behavior remains required except bundle-manifest/v3 replaces only the circular bundle-manifest/v2 field set, digest domain, and derived directory rule.","predecessor_sha256":"91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8","schema":"awa-registration-private-runtime/v3","successor_of":"awa-registration-private-runtime/v2"}
```

SHA-256:
`29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84`.

### 5.2 `contracts/awa-registration-platform-bootstrap.v3.json`

```json
{"bundle_manifest_schema":"awa-registration-bundle-manifest/v3","bundle_manifest_v2_execution":"PARSE_AND_REFUSE_SHA256_FIXED_POINT","fixed_fd_11_schema":"awa-registration-bundle-manifest/v3","inheritance_rule":"Every awa-registration-platform-bootstrap/v2 behavior remains required except FD11 and transitive bundle validation require bundle-manifest/v3 and reject bundle-manifest/v2.","predecessor_sha256":"404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9","schema":"awa-registration-platform-bootstrap/v3","successor_of":"awa-registration-platform-bootstrap/v2"}
```

SHA-256:
`ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0`.

### 5.3 `contracts/awa-registration-admin-audit.v3.json`

```json
{"bundle_manifest_schema":"awa-registration-bundle-manifest/v3","bundle_manifest_v2_execution":"PARSE_AND_REFUSE_SHA256_FIXED_POINT","inheritance_rule":"Every awa-registration-admin-audit/v2 behavior remains required except recovery assets and transaction validation require bundle-manifest/v3 and the exact 16-member static contract set.","predecessor_sha256":"b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2","schema":"awa-registration-admin-audit/v3","static_contract_hash_authority":"REQUEST_CONTEXT_ASSET_INDEX","static_contract_set_cardinality":16,"static_contract_set_equality_required":true,"static_contract_set_paths":["contracts/awa-contract.v1.json","contracts/awa-contract.v2.json","contracts/awa-contract.v3.json","contracts/awa-contract.v4.json","contracts/awa-registration-admin-audit.v1.json","contracts/awa-registration-admin-audit.v2.json","contracts/awa-registration-admin-audit.v3.json","contracts/awa-registration-owner-signers.v1","contracts/awa-registration-owner-signers.v2","contracts/awa-registration-platform-bootstrap.v1.json","contracts/awa-registration-platform-bootstrap.v2.json","contracts/awa-registration-platform-bootstrap.v3.json","contracts/awa-registration-private-runtime.v1.json","contracts/awa-registration-private-runtime.v2.json","contracts/awa-registration-private-runtime.v3.json","contracts/awa-registration-privileged-envelope.v1.json"],"successor_of":"awa-registration-admin-audit/v2"}
```

SHA-256:
`f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa`.

### 5.4 `contracts/awa-contract.v4.json`

```json
{"contract":"awa-kernel-contract","forbidden":["BUNDLE_MANIFEST_V2_EXECUTION","SHA256_FIXED_POINT_AUTHORITY"],"inheritance_rule":"Every awa-contract/v3 behavior remains required except bundle-manifest/v3 replaces only circular bundle-manifest/v2 authority and expands the exact static contract set to 16.","mandatory_contract_sha256":{"contracts/awa-registration-admin-audit.v3.json":"f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v3.json":"ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0","contracts/awa-registration-private-runtime.v3.json":"29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"},"owner_gate_schema":"awa-registration-owner-gate/v3","predecessor_path":"contracts/awa-contract.v3.json","predecessor_sha256":"fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9","receipt_schema":"awa-registration-direct-receipt/v4","schema":"awa-contract/v4","static_contract_set_cardinality":16,"successor_of":"awa-contract/v3","version":4}
```

SHA-256:
`f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3`.

The top-level `mandatory_contract_sha256` map has exactly five keys: admin
audit v3, owner-signers v2, platform bootstrap v3, private runtime v3, and
privileged envelope v1. It is complete authority, not a merge with v3.

---

## 6. Closed scope and preservation

### 6.1 Full 63-path ceiling

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
engine/registration_hook_runtime.py
engine/registration_host.py
engine/registration_installer.py
engine/registration_launcher.py
engine/registration_privileged_installer.py
engine/registration_profile.py
engine/registration_projection.py
engine/registration_receiver.py
engine/registration_schema.py
engine/tests/registration_body_c_fixtures.py
engine/tests/test_contract_schemas.py
engine/tests/test_install_lib.py
engine/tests/test_platform_bootstrap.py
engine/tests/test_private_runtime_build.py
engine/tests/test_private_runtime_installer.py
engine/tests/test_registration_deployment_authority_c.py
engine/tests/test_registration_hook_runtime_c.py
engine/tests/test_registration_host_c.py
engine/tests/test_registration_independence_c.py
engine/tests/test_registration_installer_c.py
engine/tests/test_registration_launcher_c.py
engine/tests/test_registration_packaging_c.py
engine/tests/test_registration_parent_death.py
engine/tests/test_registration_privileged_installer.py
engine/tests/test_registration_profile.py
engine/tests/test_registration_projection_c.py
engine/tests/test_registration_receiver_c.py
engine/tests/test_registration_schema.py
engine/tests/test_registration_store.py
engine/tests/test_verify_lane.py
install.sh
kernel/bin/awa-private-runtime-admin.py
kernel/bin/awa-registration-bootstrap.py
kernel/bin/awa-registration-child.py
kernel/bin/awa-registration-entrypoint.sh
kernel/bin/awa-registration-receiver.sh
kernel/bin/awa-registration-tick.sh
kernel/checks/awa-contract-freeze.sh
kernel/hooks/awa-registration-admission.sh
kernel/hooks/awa-registration-startup.sh
live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
live-verify/native-entry-durable-registration-r0.py
```

```text
SHA256(
  ASCII("awa-registration-v9-implementation-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) = 885a2a5561dcc285ed2372171f9593dcbde706c3da7c6dc8d9a16d79e17d1830
```

### 6.2 C-RUNTIME 59-path ceiling

C-RUNTIME is the full list minus exactly:

```text
engine/registration_hook_runtime.py
engine/tests/test_registration_hook_runtime_c.py
live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
live-verify/native-entry-durable-registration-r0.py
```

```text
SHA256(
  ASCII("awa-registration-v9-c-runtime-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) = 31c0b9e23865ccf2b372b39c75432ce837490f9407e46398f013d89694b0ec59
```

C-FINAL remains the accepted-v7 24-path ceiling/hash
`1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8`.
No third body is authorized. Continue transparently on the existing branch;
acceptance does not rename or mutate it.

### 6.3 Exact 59-record stopped-work manifest

The algorithm is:

```text
SHA256(
  ASCII("awa-registration-v9-c-runtime-working-manifest/v1") || 0x00 ||
  for each C-RUNTIME path sorted by UTF-8 bytes:
    UTF8(path) || 0x00 || ASCII(kind) || 0x00 ||
    ASCII(mode_or_dash) || 0x00 || ASCII(sha256_or_dash) || LF
) = 5868a4214eb425ba556babc7b02cc3e64bb40c1060da3e2fb7e71a6046bab8d6
```

`kind` is `REGULAR|ABSENT`; mode/hash rules and descriptor-safe measurement
are exactly v8 §2.2. The 59 records are:

```text
Makefile|REGULAR|644|b7fc90e778adaaa1e3bf5ba2f276ace726d0e73aa29dbe13ee39e9e04386a9f0
build/private-runtime/README.md|REGULAR|644|eb110cd893e7f0d0e7e44a6aa0a79e0e588ce2596fb997fa688e0427c9fc29b7
build/private-runtime/build.sh|REGULAR|644|01398c80fe32a81656c21805e84b7880594619bd047c633639e4a29871a78f3f
build/private-runtime/manifest.py|REGULAR|644|a0c8173497ed9af647b77e1016254cb16d7fd170a73326f4b12f1639c56f8711
build/private-runtime/sources.lock.json|REGULAR|644|a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72
contracts/awa-contract.v1.json|REGULAR|644|408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9
contracts/awa-contract.v2.json|REGULAR|644|db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a
contracts/awa-contract.v3.json|ABSENT|-|-
contracts/awa-contract.v4.json|ABSENT|-|-
contracts/awa-registration-admin-audit.v1.json|REGULAR|644|a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a
contracts/awa-registration-admin-audit.v2.json|ABSENT|-|-
contracts/awa-registration-admin-audit.v3.json|ABSENT|-|-
contracts/awa-registration-owner-signers.v1|REGULAR|644|9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e
contracts/awa-registration-owner-signers.v2|REGULAR|644|690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3
contracts/awa-registration-platform-bootstrap.v1.json|REGULAR|644|4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c
contracts/awa-registration-platform-bootstrap.v2.json|ABSENT|-|-
contracts/awa-registration-platform-bootstrap.v3.json|ABSENT|-|-
contracts/awa-registration-private-runtime.v1.json|REGULAR|644|f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321
contracts/awa-registration-private-runtime.v2.json|ABSENT|-|-
contracts/awa-registration-private-runtime.v3.json|ABSENT|-|-
contracts/awa-registration-privileged-envelope.v1.json|REGULAR|644|7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034
engine/registration_host.py|REGULAR|644|57d1c0d956ff76a8a129d1563663161dd3e22c1e835c703a3d767516faf4aaf5
engine/registration_installer.py|REGULAR|644|e6fc894f0ddf1900acdcaff196238c32ec914c045756274ea29b4521f1d057e4
engine/registration_launcher.py|REGULAR|644|807e0d50922c47bde638ed9bab70e784f9787a526e2cf45828982dfae346979f
engine/registration_privileged_installer.py|REGULAR|644|350f30b97b02038c8f17ebc1a4ba8a30a581ccaaf779f87f4b3ed6ca23d36997
engine/registration_profile.py|REGULAR|644|889ff613c38567e862e16a84be56a0a35e16be2369371d0ce1ba31c8a458bf4a
engine/registration_projection.py|REGULAR|644|f296cdae42656ab8ec0c322c7eb91eb99d8cd3f3825e8406599cd4d0d2638f99
engine/registration_receiver.py|REGULAR|644|49925ba2687f01b88bbf26c0fc15ee9c1db48aa1ea63ca50f332952ff3111831
engine/registration_schema.py|REGULAR|644|0f79bc14fb5553a9553443094d55fed89a1fe91825c1857b851bc2c4eaa18b67
engine/tests/registration_body_c_fixtures.py|REGULAR|644|e07736b0ecde2e268fd9256c56705874719e8a335d8ef698d9d943f9c160f978
engine/tests/test_contract_schemas.py|REGULAR|644|4a7945c586eb791f073562a63c305eda7532a0cf1cb45c239f0617c7ce248c69
engine/tests/test_install_lib.py|REGULAR|644|901cb72233426c993a5986ede683798ce5c386732bd0148f5ee2aaba28aae1e3
engine/tests/test_platform_bootstrap.py|REGULAR|644|71fc98555dd75fbf4c6510ae183d07873427fc106f4c30f15098bc437c744280
engine/tests/test_private_runtime_build.py|REGULAR|644|9f8e7ba71f6bcc85eb43e7de46823a15b5f066ae23e13adfa124c562f3cb2548
engine/tests/test_private_runtime_installer.py|REGULAR|644|172a3ac4583fe5d021e4dd6256159aabea4c874b97c39cd96c20d153ce11a61a
engine/tests/test_registration_deployment_authority_c.py|REGULAR|644|a71ad98bf6050b49dc3a9f49a03910a29b13640e0f7b7b5d94fbae59f0ef6222
engine/tests/test_registration_host_c.py|REGULAR|644|77bc561261f91f0c531bef76e5223de7c517a0b51119347e23ecd1e2baf04870
engine/tests/test_registration_independence_c.py|REGULAR|644|67afb34dd89baf5ddbfa8bd983e0f907f98a1d184630435b250909f1e4892780
engine/tests/test_registration_installer_c.py|REGULAR|644|e89582f0f3093dac208c9bf549d05e151f64023d8e3b870da436c45c141a2a79
engine/tests/test_registration_launcher_c.py|REGULAR|644|88bfba9381eca437cf137918331190a66c0f96f9e8179a129f6cd96ff98c7230
engine/tests/test_registration_packaging_c.py|REGULAR|644|4413aafa597b2fbc9a48df31b5af81baa5ec74960c1bfb41d167795d146c3031
engine/tests/test_registration_parent_death.py|REGULAR|644|7c7916a673e67acd93751949963dffb569983378b2a401dd74db2e79da656a1c
engine/tests/test_registration_privileged_installer.py|REGULAR|644|16b1b2a28fed29c4da28d3c18143b8a9d5402a5a8487e56dd2331902d46c222f
engine/tests/test_registration_profile.py|REGULAR|644|f2566f41c2a55d010a3d96f059bdd8b7132d788c98f2d0b401520f1b55cbdb7a
engine/tests/test_registration_projection_c.py|REGULAR|644|97fb257b5b109ee0690305cc0e505e5af822066b30a73fa0ee59d4c6f92e97d4
engine/tests/test_registration_receiver_c.py|REGULAR|644|0cbb0ccb09a1ee0c5bc799ca009a6474f9aab53a18e9a7de0d86740e1856ff4d
engine/tests/test_registration_schema.py|REGULAR|644|ac60e4917428d684c98d1bbb14c55c160eb73489bca687d77e7700162b45dfc5
engine/tests/test_registration_store.py|REGULAR|644|218c625eb9f27c8f2ffd73f491515b60942e5435c03d6f99de05d63d176d5a7d
engine/tests/test_verify_lane.py|REGULAR|644|ff7bd13e5c1bfb376204044a178ff8df20e2f423bc7a87753de6b37a8bfa7e09
install.sh|REGULAR|755|2d7a276b318d4d1162045398f0e65e652fdd0ab181c0af1a5be836f44fc6383a
kernel/bin/awa-private-runtime-admin.py|REGULAR|644|b25db3fa68685a6639ee2de056110f3b8ef0f600deb95c7966fd6d887fa5711b
kernel/bin/awa-registration-bootstrap.py|REGULAR|644|40084b7c92c56a08b7150decb7dc9b99bc2d1df9254182db7e185c6775141499
kernel/bin/awa-registration-child.py|REGULAR|644|ddaa6d7dafab44950a578ab32fe92b9e899e7d3488e0862cc9b068e0fc9ee7ed
kernel/bin/awa-registration-entrypoint.sh|REGULAR|644|df891a65255e8d55357b6374a0188fd207f576a67bfc8c1d27315a97c397c82e
kernel/bin/awa-registration-receiver.sh|REGULAR|755|8017a0f470335ab607fb9876f747cadde79905cc6eb06bba9d7f34d99d05a416
kernel/bin/awa-registration-tick.sh|REGULAR|755|765ddc3cf86a53f5cb0072c4f6abeef0bbcb542878e38766cd691b649b8d1fbb
kernel/checks/awa-contract-freeze.sh|REGULAR|755|09f3f0b479f121f5a5e13633d396015d64b2fea1409b80ea046055cef99bda07
kernel/hooks/awa-registration-admission.sh|REGULAR|755|2b7a6246cd42b4143c70246b6e8c6c1c77fe4670abc8995103939bd08423df65
kernel/hooks/awa-registration-startup.sh|REGULAR|755|e5032177badc8c48bf0f04f6c9a253cd0a456815770ce984ee31f535632b35fe
```

This is 51 regular files and eight intentional absent contracts. The five
tests-first paths are preserved exactly:

```text
engine/tests/test_platform_bootstrap.py|71fc98555dd75fbf4c6510ae183d07873427fc106f4c30f15098bc437c744280
engine/tests/test_registration_deployment_authority_c.py|a71ad98bf6050b49dc3a9f49a03910a29b13640e0f7b7b5d94fbae59f0ef6222
engine/tests/test_registration_packaging_c.py|4413aafa597b2fbc9a48df31b5af81baa5ec74960c1bfb41d167795d146c3031
engine/tests/test_registration_privileged_installer.py|16b1b2a28fed29c4da28d3c18143b8a9d5402a5a8487e56dd2331902d46c222f
engine/tests/test_registration_schema.py|ac60e4917428d684c98d1bbb14c55c160eb73489bca687d77e7700162b45dfc5
```

A later implementation GO must bind the 59-path scope/hash, this exact working
manifest, the prior Body C manifest, accepted v8 and the four successor bytes.
Completion must report each path as `PRESERVE|COMPLETE|SUPERSEDE`; an absent
successor contract becomes `COMPLETE`. Blanket replacement or loss of any
existing byte is forbidden.

---

## 7. Tests, vectors, gates and stops

### 7.1 Required local evidence

Carry every V8-A01..V8-A15 row forward, replacing bundle-manifest v2 execution
with v3 and static-set 12 with 16. Add:

| ID | Required evidence | Refusal |
|---|---|---|
| V9-A01 | Reproduce all four embedded JCS+LF bytes/hashes; all 16 static path/hash records, cardinality and set equality | Drift, subset, self-hash inference, or absent predecessor |
| V9-A02 | v2 parses only to `BUNDLE_MANIFEST_V2_FIXED_POINT`; v2 can never publish, recover, select, qualify or launch | Any v2 execution authority |
| V9-A03 | v3 exact fields/domain; digest reproduces before directory derivation; extra `bundle_relative_dir` refuses | Fixed point, field drift, or alternate preimage |
| V9-A04 | Derive one exact directory from generation+digest; product-current/FD10/version inventory/recovery/packet all freshly equal it | Caller-selected path, alias, mismatch, or stale equality |
| V9-A05 | Regenerate bundle/projection/receipt-v4/gate-v3/pointer/Q1/Q2/denial/readiness vectors without receipt/gate bump | Stale v2 vector or receipt-v5/gate-v4 need |
| V9-A06 | Reproduce 63/59/24 scopes, 59-record working manifest, five preserved test hashes and per-path disposition | Scope escape or work loss |

Focused tests must cover v2 refusal; v3 missing/extra/reordered fields; changed
domain; v2 bytes under v3 schema and vice versa; derived-path generation,
digest, separator, case, NFC and traversal mutations; FD10/FD11 swap; product
pointer mismatch; retained Q1 rollback equality; every transaction/recovery
asset role carrying v3; exact static-set omission/addition/duplicate/hash
mutation; and qualification packet indexes carrying v3 bytes without a packet
fixed point.

Then run all focused registration tests, complete registration suite,
contract/schema/freeze/scope/static/manifest reproduction, `py_compile`,
`sh -n`, `make verify-pre-pr`, `make verify`, diff checks, Bugbot and Security
review. Privileged qualification and rollout evidence remain separately gated.

### 7.2 Exact sequencing

1. V9 acceptance: documentation status/index promotion only.
2. `V9-C-RUNTIME-IMPLEMENT`: exact anti-replay GO bound to promoted v9,
   source/base/branch, 59-path scope and working manifest.
3. Complete C-RUNTIME locally with synthetic, nonprivileged fixtures only.
4. `V9-C-RUNTIME-DELIVER`: separate exact changed-subset/final-manifest GO.
5. Draft PR delivery, full review and nonprivileged packet generation.
6. Separate qualification-key GO.
7. Separate one-prompt disposable qualification GO.
8. Packet acceptance.
9. Readiness/merge gate.
10. C-FINAL begins only from merged C-RUNTIME live main under its inherited
    gates.

Acceptance, implementation and delivery never imply one another.

### 7.3 Explicit stops

Stop for receipt-v5/gate-v4 need; any fifth new path; scope escape; changed
importer or dynamic-FD feasibility; v3 path/digest cycle; nonexact 16-contract
membership; asset-index/transaction/receipt fixed point; lost transaction
ancestry; inferred audit success; path/config leakage; later-process
signalling; private/owner-key access; build/prompt/install before its gate;
authority, working-manifest or source drift; or any inherited contradiction.
A stop requires a successor decision, never improvisation.

---

## 8. Exact v9 plan acceptance

### 8.1 Status-only authority

Exact-byte owner acceptance authorizes only:

1. this plan status:
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. v9 index status:
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-03`;
3. v8 index status:
   `SUPERSEDED BY V9 — 2026-10-03`.

It authorizes no implementation, contract creation, build, delivery, key,
signing, prompt, privileged operation, installation, publication, release,
activation, R0/R1/C1/R2, external mutation or rollout.

### 8.2 Anti-replay normalization

```text
SHA256(
  ASCII("awa-registration-v9-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

Replace exactly one DRAFT/ACCEPTED plan status line with:

```text
- **Status:** __AWA_V9_STATUS__
```

Replace exactly one v9 DRAFT/ACCEPTED index row with:

```text
| `native-entry-durable-registration-v9.md` | __AWA_V9_INDEX_STATUS__ | Minimal fixed-point successor to accepted v8; replaces only circular bundle-manifest v2 with acyclic v3 derivation and expands the exact static set to 16. |
```

Replace exactly one v8 accepted/superseded index row with:

```text
| `native-entry-durable-registration-v8.md` | __AWA_V9_PREDECESSOR_INDEX_STATUS__ | Bounded product-closure successor to accepted v7; seals retained-byte import, closed version retention, immutable admin ancestry, acyclic packet-v2 qualification, and exact startup/reconciliation. |
```

Each replacement includes one LF. Zero, duplicate, mixed, non-UTF-8, CRLF,
NUL or non-exact context refuses. Simulated draft and promoted bytes must
normalize identically.

### 8.3 Exact owner envelope shape

External acceptance is one canonical JCS object with exactly:

```json
{"accepted_index_sha256":"ad1d0f0d57bc6eb97c48bff39b077360ebb6bd6547e2b4df6360b8091874fbf0","accepted_v8_normalized_digest":"4d673c3d552a0f2a3db6b15e56bccbbe07ee5a485f1ce4ad91f673edeb8b2586","accepted_v8_plan_sha256":"1009c3f2e950fcf88adc1f2a862e7127c9d8bb36001389e6ed22bed347a3e770","action":"ACCEPT_PLAN_V9","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","authorized":true,"authorized_actions":["MARK_V8_INDEX_SUPERSEDED","PROMOTE_V9_INDEX_STATUS","PROMOTE_V9_PLAN_STATUS"],"authorized_by":"KleinPerkins","branch":"impl/native-entry-durable-registration-v7-runtime-bootstrap","c_final_scope_count":24,"c_final_scope_hash":"1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8","current_receipt_sha256":"a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411","denied_implications":["ACCESS_OR_GENERATE_KEY_OR_SIGN","ALTER_PRESERVED_WORK","BUILD_OR_PUBLISH","COMMIT_PUSH_OR_OPEN_PR","CREATE_SUCCESSOR_CONTRACT_FILES","IMPLEMENT_OR_DELIVER","INVOKE_NATIVE_AUTHORIZATION_PROMPT","MUTATE_EXTERNAL_STATE","PRIVILEGED_OPERATION","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","enrollment_hash":"885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4","live_base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","new_c_runtime_scope_count":59,"new_c_runtime_scope_hash":"31c0b9e23865ccf2b372b39c75432ce837490f9407e46398f013d89694b0ec59","new_full_scope_count":63,"new_full_scope_hash":"885a2a5561dcc285ed2372171f9593dcbde706c3da7c6dc8d9a16d79e17d1830","normalized_digest":"<reviewed lowercase 64-hex>","old_c_runtime_scope_count":55,"old_c_runtime_scope_hash":"29c0401fb82088e02818a1cfcb7a62bcbb2eca44c2364dc23698bb45f4ec99b4","old_full_scope_count":59,"old_full_scope_hash":"714d7d02f9a5e1aca8c800c74303a1eebb6d6b1a46de140bb6ff19b3198ff3ac","owner_signers_v1_sha256":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","owner_signers_v2_sha256":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","pre_v7_body_c_manifest_hash":"9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a","promoted_index_sha256":"<reviewed lowercase 64-hex>","promoted_plan_sha256":"<reviewed lowercase 64-hex>","repository":"KleinPerkins/awa","schema":"awa-registration-v9-plan-acceptance-go/v1","source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","static_contract_hashes":{"contracts/awa-contract.v1.json":"408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9","contracts/awa-contract.v2.json":"db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a","contracts/awa-contract.v3.json":"fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9","contracts/awa-contract.v4.json":"f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3","contracts/awa-registration-admin-audit.v1.json":"a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a","contracts/awa-registration-admin-audit.v2.json":"b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2","contracts/awa-registration-admin-audit.v3.json":"f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa","contracts/awa-registration-owner-signers.v1":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v1.json":"4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c","contracts/awa-registration-platform-bootstrap.v2.json":"404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9","contracts/awa-registration-platform-bootstrap.v3.json":"ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0","contracts/awa-registration-private-runtime.v1.json":"f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321","contracts/awa-registration-private-runtime.v2.json":"91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8","contracts/awa-registration-private-runtime.v3.json":"29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"},"static_contract_set_count":16,"stopped_v8_working_manifest_count":55,"stopped_v8_working_manifest_hash":"d8fce3ac9215d9d608a546305996ade4f2175f8de2c014f7fa261f9b0f28a9f6","tests_first_hashes":{"engine/tests/test_platform_bootstrap.py":"71fc98555dd75fbf4c6510ae183d07873427fc106f4c30f15098bc437c744280","engine/tests/test_registration_deployment_authority_c.py":"a71ad98bf6050b49dc3a9f49a03910a29b13640e0f7b7b5d94fbae59f0ef6222","engine/tests/test_registration_packaging_c.py":"4413aafa597b2fbc9a48df31b5af81baa5ec74960c1bfb41d167795d146c3031","engine/tests/test_registration_privileged_installer.py":"16b1b2a28fed29c4da28d3c18143b8a9d5402a5a8487e56dd2331902d46c222f","engine/tests/test_registration_schema.py":"ac60e4917428d684c98d1bbb14c55c160eb73489bca687d77e7700162b45dfc5"},"working_manifest_count":59,"working_manifest_hash":"5868a4214eb425ba556babc7b02cc3e64bb40c1060da3e2fb7e71a6046bab8d6"}
```

Placeholders are replaced only in the external submitted envelope. Its digest
is:

```text
SHA256(
  ASCII("awa-registration-v9-plan-acceptance-envelope/v1") || 0x00 ||
  JCS(concrete_external_envelope) || LF
)
```

Immediately before promotion, recompute every accepted authority, draft and
promoted hash, normalized equivalence, scopes, 16 static hashes, both working
manifests, five test hashes, branch/base/staging, and denied implication.
Mismatch refuses with no mutation.

---

## 9. Standalone four-pass review

### Pass 1 — facts

The accepted v8 plan/index, ADR, source lock, HEAD/origin-main, branch, prior
Body C authority, 55-path stopped manifest and five tests-first hashes were
measured from current bytes. The v2 fixed point follows directly from its
field set, path rule and digest exclusion.

### Pass 2 — closure

V3 removes only the recursive field, uses a new digest domain, derives the
directory after digest validation, keeps all downstream equality checks, and
rejects v2 for execution. The 16-member set binds every predecessor and
successor contract without embedding a contract's own hash in itself.

### Pass 3 — subtraction

Four contract paths are added; no production or test path is added. Receipt,
gate, projection, current, admin, packet, importer, reconciliation and shell
schemas do not change. Existing tests are preserved rather than rewritten.

### Pass 4 — under-scope proof

The 63/59 scopes are exactly accepted v8's lists plus four successor
contracts. The stopped manifest is exactly current v8 55-path state plus four
ABSENT records. Remaining uncertainty is implementation evidence: validators
must reproduce v3 and derived-path equality under the later GO. Any need to
broaden schemas or paths is a stop.
