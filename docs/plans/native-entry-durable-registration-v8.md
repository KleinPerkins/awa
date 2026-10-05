# Native Entry Durable Registration

- **Version:** v8
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-03
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v7.md`](native-entry-durable-registration-v7.md),
  preserved byte-identically at promoted SHA-256
  `dddae47b0840f5f25f375a92bf3736a654e095549b9e9d7f3c68c6360b230384`
  and accepted normalized digest
  `88eb649abe56f790bc24c7ef84fca777b36a89f44dd444fa66969202a19cec4d`.
- **Inherited authority:** accepted, frozen v6 SHA-256
  `ee8e4fcadd2951fcf3b4260aa5a4672ef98247a2839d7ad53a7ea2d6e02f6a47`,
  normalized digest
  `1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452`;
  accepted, frozen v5 SHA-256
  `4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b`,
  normalized digest
  `f4d222435da9c7eb323d0e4c92fe0997f88beb92c56a85dad7cd96704361be94`,
  receipt hash
  `c27746a232275380bfca5cba110d4533813cdc4e9b4a3710629a9c34742706a6`;
  and immutable [ADR 0026](../adr/0026-durable-registration-authority-hardening.md)
  SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Source baseline:** live `origin/main`
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`.
- **Current stopped branch:**
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`.
- **Current authorities:** ACTIVE enrollment
  `885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4`,
  receipt
  `a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411`,
  owner-signers v1
  `9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e`,
  and owner-signers v2
  `690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3`.
- **Preservation:** pre-v7 Body C manifest
  `9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a`;
  stopped C-RUNTIME working manifest
  `4cec4be5dd0d48316ea5a4d829a2be26c1eb3e43cdeff91c6aa513f995178081`.

> **Governance stop:** this draft authorizes only this file and its DRAFT
> README index row. It authorizes no implementation, staging, commit, push,
> PR, build, qualification key, owner-key access/signing, native prompt,
> installation, publication, release, activation, R0/R1/C1/R2, or rollout.

---

## 1. Valid stop, bounded successor, and inheritance

Independent adjudication correctly returned `VALID_STOP`. Accepted v7 proves
the protected private runtime and observation-only reconciliation boundary but
does not define where installed product bytes live, how they reach the child,
the complete FD8 launch authority, retained-resource import, sealed host
inputs, crash-transactional current/audit publication, complete QUALIFY
orchestration, exact reconciliation classifier outputs, or ambient-shell
startup closure. Those omissions are executable authority, not commentary.
V7 itself requires a successor for a required 54th path, unspecified schema,
or unresolved import race.

V8 changes only those boundaries. It inherits every unaffected v7/v6/v5/ADR
invariant, including the Astral source lock, runtime build/qualification,
root/private-runtime ownership, owner-signing separation, qualification-only
synthetic trust, observation-only later reconciliation, two serial bodies,
runnerless verification, and separately gated release/rollout.

The smallest demonstrated delta is six paths: four successor contracts plus
the existing schema module and its test. There is no third body, importer
module, daemon, database table, receipt v5, new signing namespace, or product
path in argv/environment.

---

## 2. Verified baseline and byte preservation

### 2.1 Ground truth

Before acceptance or any later implementation gate require:

- local `HEAD` and `origin/main` equal the source baseline;
- branch remains
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`;
- v7/v6/v5/ADR and current enrollment/receipt/signer bytes equal header
  hashes;
- index-before-v8 SHA-256 equals
  `988d8af79d56d5af0e5b717ba0dc62e09f0a8f2eee793db7696d21ea42355537`;
- index is empty of staged entries; and
- no build, key, prompt, privileged operation, install, release, or external
  mutation occurred.

### 2.2 Exact stopped C-RUNTIME working manifest

The 55-path v8 C-RUNTIME ceiling currently contains 51 regular files and four
intentional absent successor contracts. Bind it as:

```text
SHA256(
  ASCII("awa-registration-v8-c-runtime-working-manifest/v1") || 0x00 ||
  for each path below sorted by UTF-8 bytes:
    UTF8(path) || 0x00 || ASCII(kind) || 0x00 ||
    ASCII(mode_or_dash) || 0x00 || ASCII(sha256_or_dash) || LF
) =
4cec4be5dd0d48316ea5a4d829a2be26c1eb3e43cdeff91c6aa513f995178081
```

`kind` is exactly `REGULAR|ABSENT`. A regular record uses
`format(stat.S_IMODE(lstat(path).st_mode), "03o")` and SHA-256 of exact bytes;
an absent record uses `ABSENT|-|-` and requires `lexists(path) == false`.
Regular inputs must be owner-UID, nlink-one, non-symlink files whose pre-open
`lstat`, `open(O_NOFOLLOW)`, `fstat`, post-read `fstat`, and visible-path
rebind identify one object. Exact records:

```text
Makefile|REGULAR|644|b7fc90e778adaaa1e3bf5ba2f276ace726d0e73aa29dbe13ee39e9e04386a9f0
build/private-runtime/README.md|REGULAR|644|eb110cd893e7f0d0e7e44a6aa0a79e0e588ce2596fb997fa688e0427c9fc29b7
build/private-runtime/build.sh|REGULAR|644|01398c80fe32a81656c21805e84b7880594619bd047c633639e4a29871a78f3f
build/private-runtime/manifest.py|REGULAR|644|a0c8173497ed9af647b77e1016254cb16d7fd170a73326f4b12f1639c56f8711
build/private-runtime/sources.lock.json|REGULAR|644|a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72
contracts/awa-contract.v1.json|REGULAR|644|408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9
contracts/awa-contract.v2.json|REGULAR|644|db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a
contracts/awa-contract.v3.json|ABSENT|-|-
contracts/awa-registration-admin-audit.v1.json|REGULAR|644|a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a
contracts/awa-registration-admin-audit.v2.json|ABSENT|-|-
contracts/awa-registration-owner-signers.v1|REGULAR|644|9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e
contracts/awa-registration-owner-signers.v2|REGULAR|644|690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3
contracts/awa-registration-platform-bootstrap.v1.json|REGULAR|644|4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c
contracts/awa-registration-platform-bootstrap.v2.json|ABSENT|-|-
contracts/awa-registration-private-runtime.v1.json|REGULAR|644|f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321
contracts/awa-registration-private-runtime.v2.json|ABSENT|-|-
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
engine/tests/test_platform_bootstrap.py|REGULAR|644|2eeef6994be0220e29c287407fa96ae88c5480eb8c3e55851cc1210730e1aed8
engine/tests/test_private_runtime_build.py|REGULAR|644|9f8e7ba71f6bcc85eb43e7de46823a15b5f066ae23e13adfa124c562f3cb2548
engine/tests/test_private_runtime_installer.py|REGULAR|644|172a3ac4583fe5d021e4dd6256159aabea4c874b97c39cd96c20d153ce11a61a
engine/tests/test_registration_deployment_authority_c.py|REGULAR|644|65f13b9dea4be82d79be6c2a88f65d78c33b63a2f4dba61d387cbb8899394397
engine/tests/test_registration_host_c.py|REGULAR|644|77bc561261f91f0c531bef76e5223de7c517a0b51119347e23ecd1e2baf04870
engine/tests/test_registration_independence_c.py|REGULAR|644|67afb34dd89baf5ddbfa8bd983e0f907f98a1d184630435b250909f1e4892780
engine/tests/test_registration_installer_c.py|REGULAR|644|e89582f0f3093dac208c9bf549d05e151f64023d8e3b870da436c45c141a2a79
engine/tests/test_registration_launcher_c.py|REGULAR|644|88bfba9381eca437cf137918331190a66c0f96f9e8179a129f6cd96ff98c7230
engine/tests/test_registration_packaging_c.py|REGULAR|644|3475a18fcde25bb4202547ffece30c25e4ac1113348ab9e1320143386b03ed94
engine/tests/test_registration_parent_death.py|REGULAR|644|7c7916a673e67acd93751949963dffb569983378b2a401dd74db2e79da656a1c
engine/tests/test_registration_privileged_installer.py|REGULAR|644|2bf3cdd47a6e72990657ae7b57d142e205d83968860362d930fff2ff89b9cd9c
engine/tests/test_registration_profile.py|REGULAR|644|f2566f41c2a55d010a3d96f059bdd8b7132d788c98f2d0b401520f1b55cbdb7a
engine/tests/test_registration_projection_c.py|REGULAR|644|97fb257b5b109ee0690305cc0e505e5af822066b30a73fa0ee59d4c6f92e97d4
engine/tests/test_registration_receiver_c.py|REGULAR|644|0cbb0ccb09a1ee0c5bc799ca009a6474f9aab53a18e9a7de0d86740e1856ff4d
engine/tests/test_registration_schema.py|REGULAR|644|5f0c0f9af532964b27a6bd220c5097f4bee04027f6608ec24c3ab90e23bf0d4b
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

The manifest corrects the reported 44/49 estimate: the v8 ceiling is 55,
with 51 current regular files and four explicit absent contract outputs.
Acceptance changes none of these states or bytes. A later implementation GO
must name this digest and the prior Body C digest, then produce a per-path
`PRESERVE|COMPLETE|SUPERSEDE` report; blanket replacement is forbidden.

---

## 3. Product closure and canonical pointer

The fixed product root is `/Library/Application Support/AWA/product/`.
`versions/<bundle_generation>-<bundle_digest>/` is immutable after no-replace
publication. `current.v1` is a canonical regular file, never a symlink.
Root, ancestry, versions, pointer, and payload are root:wheel; directories are
0755 and every retained product source/resource/authority regular file is 0444;
trusted files are nlink one and no path component is group/other writable.

Every installed version is a closed openat-relative tree rooted at a retained
O_DIRECTORY descriptor for
`versions/<bundle_generation>-<bundle_digest>`. Its exact layout is:

```text
<each import-manifest relative_path>                         0444
authority/                                                  0755
authority/import-manifest.json                              0444
authority/host-authority.json                               0444
authority/writer-capability.json                            0444
authority/bundle-manifest.json                              0444
authority/bundle-projection.json                            0444
authority/direct-receipt.json                               0444
authority/owner-gate.json                                   0444
authority/owner-gate.sig                                    0444
authority/owner-signers                                     0444
```

The version root and every payload package directory implied by an import
relative path are 0755. No other directory, regular file, device, socket,
FIFO, hard link, symlink, alternate data, or case/NFC alias is allowed.
`authority/owner-signers` is byte-identical to
`contracts/awa-registration-owner-signers.v2` at accepted hash
`690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3`;
it is the only signer/metadata file parent owner-gate verification needs.
All opens use the retained version-directory fd, fixed relative components,
`O_NOFOLLOW`, and post-open regular/directory, owner, mode, nlink, dev/inode,
size, and hash checks. Absolute reconstruction is diagnostic only and never
an authority open.

`awa-registration-product-current/v1` has exactly:

```text
schema,selection_epoch,bundle_generation,bundle_relative_dir,bundle_digest,
bundle_projection_hash,
direct_receipt_digest,owner_gate_digest,import_manifest_hash,
host_authority_digest,runtime_current_digest,
predecessor_product_current_digest,product_current_digest
```

`schema` is exact; `selection_epoch` and `bundle_generation` are positive
unsigned decimal strings;
`bundle_relative_dir` is exactly
`versions/<bundle_generation>-<bundle_digest>` with no other component; every
digest is lowercase 64-hex, except `predecessor_product_current_digest` is
JSON null only for selection epoch 1. The relative directory is at most 256
UTF-8 bytes and the complete canonical object is at most 8,192 bytes. Domain:

```text
product_current_digest =
  SHA256(ASCII("awa-registration-product-current/v1") || 0x00 ||
         JCS(object_without_product_current_digest) || LF)
```

Every duplicated digest must equal the retained object. Selection epoch must
be exactly predecessor selection epoch + 1. Bundle generation is immutable
authority copied from bundle/receipt/gate and never renumbered on selection.
INSTALL Q1 is selection epoch 1/bundle generation 1; UPDATE Q2 is epoch
2/generation 2; authorized ROLLBACK Q1 is epoch 3/generation 1 and reuses
byte-identical Q1 bundle/receipt/gate/version bytes. Rollback requires the
target version remain retained, owner-authorized rollback operation, exact
predecessor pointer, and target equality; it never republishes or mutates Q1.
An unauthorized target-generation decrease, selection-epoch gap, same bundle
generation with changed authority, unknown predecessor, absent retained
version, or directory mismatch refuses.
Publication writes an O_EXCL same-directory temporary, fsyncs file, reopens
and revalidates it, then uses `renameatx_np(RENAME_EXCL)` for first install or
`renameatx_np(RENAME_SWAP)` for replacement, fsyncs the parent, and retains
the swapped predecessor until ledger COMMITTED. Launch accepts only exact
head/current/receipt equality under §8.

After every successful COMMITTED selection, retention protects exactly the
currently selected bundle and the immediately preceding committed
selection's bundle when distinct. UPDATE Q2 therefore retains Q1; ROLLBACK Q1
retains Q2. This two-selection floor persists through crashes and until the
next successful COMMITTED selection. Only after that later COMMITTED head is
fsynced and reopened may pruning remove versions that are neither current nor
its immediate committed predecessor. Authorized REMOVE may remove all
versions only after exclusive admin/current/version locks, zero retained
launcher descriptors, durable removal inventory, and its external-ledger
commit. A version with an active shared lock, retained directory/file
descriptor, unresolved transaction reference, or packet evidence reference
is never pruned. Crash before prune leaves extra safe versions; crash during
prune resumes only from the committed head/inventory and never infers
completion.

`awa-registration-private-runtime-current/v2` has exactly:

```text
schema,runtime_epoch,active_manifest_sha256,previous_manifest_sha256,
active_release_envelope_digest,installed_at_wall_ns,capability_digest,
qualification_packet_digest,predecessor_runtime_current_digest,
runtime_current_digest
```

Runtime epoch and wall time are unsigned decimal strings; epoch starts at 1
and advances exactly by one when runtime selection changes. Previous manifest
and predecessor current are null only at epoch 1 and otherwise lowercase
64-hex; all other digest fields are lowercase 64-hex.
`qualification_packet_digest` must be packet-v2. Domain
`awa-registration-private-runtime-current/v2`; digest excludes
`runtime_current_digest`. Runtime-current contains no admin receipt, ledger
head, admin transaction, product-current, or launch-context digest. Its
immutable bytes are upstream of admin receipt/head and may be selected by a
transaction without depending on that transaction.

Historical `awa-registration-runtime/v1`, `runtime-config.json`,
`AWA_REGISTRATION_RUNTIME_CONFIG`, `AWA_REGISTRATION_BUNDLE_ROOT`, and
`AWA_REGISTRATION_ACTIVE_BUNDLE` may be parsed only to emit a typed refusal.
They never select or authorize execution.

---

## 4. Import, bundle, projection, and host authorities

All JSON authorities use UTF-8 JCS plus one LF, no duplicate keys, floats,
BOM, CR, NUL, or insignificant whitespace. Unless overridden:

```text
digest = SHA256(ASCII(domain) || 0x00 ||
                JCS(object_without_its_digest_field) || LF)
```

### 4.1 Import manifest v2

`awa-registration-import-manifest/v2` has exactly
`schema,records,record_count,aggregate_size,import_manifest_hash`.
Records are UTF-8 `relative_path` sorted and have exactly:

```text
kind,logical_name,relative_path,owner_module,fd_target,mode,size,sha256
```

- `kind` is `PACKAGE_INITIALIZER|MODULE|RESOURCE`.
- PACKAGE_INITIALIZER logical names are importable package names and paths
  end `/__init__.py`; MODULE logical names are importable non-package module
  names and paths end `.py`.
- RESOURCE `logical_name` is `<owner_module>:<resource_name>`.
  `resource_name` matches `[A-Za-z0-9][A-Za-z0-9._-]{0,255}`, contains no
  slash, and the pair `(owner_module,resource_name)` is unique.
  `owner_module` is an included MODULE; the owner module's parent package
  initializer must also be included. Resource path is derived, never chosen:
  replace dots in the owner's package (all logical-name components except the
  final component) with `/`, append `/`, then exact `resource_name`.
- Exactly one mandatory SQL resource maps
  `owner_module=engine.registration_schema`,
  `resource_name=registration_schema.sql`,
  `logical_name=engine.registration_schema:registration_schema.sql`,
  `relative_path=engine/registration_schema.sql`. No second record may share
  its owner/name or path.
- `fd_target` is a decimal integer >=16; mode is exact three-octal ASCII
  `"444"`;
  size is an unsigned decimal string; hash is lowercase 64-hex.
- Logical names are 1..512 UTF-8 bytes; relative paths are 1..4,096 bytes,
  contain no empty/dot/dot-dot/NUL component, and are unique under exact bytes
  and Unicode NFC; owner module is JSON null for PACKAGE_INITIALIZER/MODULE
  and non-null only for RESOURCE.
- Record count is 1..505, each size is 1..8,388,608, aggregate size is
  1..67,108,864, and totals must equal records.

Domain `awa-registration-import-manifest/v2`; digest excludes
`import_manifest_hash`.

### 4.2 Bundle manifest and projection v2

`awa-registration-bundle-manifest/v2` has exactly:

```text
schema,generation,bundle_relative_dir,bundle_entry_plain_hash,
installed_file_hash,import_manifest_hash,host_authority_digest,records,
record_count,aggregate_size,bundle_digest
```

Each path-sorted record has exactly
`relative_path,kind,mode,size,sha256`; kind is
`PACKAGE_INITIALIZER|MODULE|RESOURCE|AUTHORITY`. It contains exactly one
payload record, byte-identical in path/kind/mode/size/hash, for every import
manifest record, plus exactly these three authority records:
`authority/import-manifest.json`,
`authority/host-authority.json`, and
`authority/writer-capability.json`. Authority modes are `0444`; Python/data
payload modes are `0444`; no writable or executable file is valid. Relative
paths and `(kind,relative_path)` are unique and records are sorted by UTF-8
relative-path bytes. Required payload/authority omission, additional record,
alias, duplicate, case/NFC collision, metadata mismatch, or unlisted byte
refuses. The generation/path rules match §3.

```text
bundle_entry_plain_hash =
  SHA256(ASCII("awa-registration-bundle-entry-plain/v1") || 0x00 ||
         UTF8("engine.registration_receiver") || 0x00 ||
         exact retained engine/registration_receiver.py bytes)
```

The receiver MODULE record `sha256` is raw
`SHA256(exact retained engine/registration_receiver.py bytes)`; the two values
therefore bind the same byte preimage under deliberately distinct formulas
and validators must reproduce both. `installed_file_hash` remains the
accepted receipt candidate hash and is distinct from both. The bundle digest
binds every full record, including each raw `sha256`, plus
`bundle_entry_plain_hash`. Domain
`awa-registration-bundle-manifest/v2`; digest excludes `bundle_digest`.
Records are 1..512, paths are bounded as import paths, each record is at most
8 MiB, and exact aggregate/count fields must not exceed 64 MiB/512. The
bundle-manifest membership is this upstream payload-plus-three-authority set,
not the full installed-tree allowlist. The closed installed tree additionally
allows only
`authority/bundle-manifest.json`,
`authority/bundle-projection.json`,
`authority/direct-receipt.json`, `authority/owner-gate.json`,
`authority/owner-gate.sig`, and `authority/owner-signers` at the exact §3
roles/modes. These downstream/static-verification files are excluded from
bundle records and `bundle_digest`: the manifest cannot hash itself;
projection/receipt/gate/signature are downstream; owner-signers is separately
fixed by its accepted contract hash. Bundle also excludes runtime/product
currents, admin receipt/transaction/head, qualification packet, and launch
context. Every byte absent from either the exact upstream record set or this
closed downstream allowlist refuses.

`awa-registration-bundle-projection/v2` has exactly:

```text
schema,generation,bundle_digest,import_manifest_hash,host_authority_digest,
candidate_digest,installed_file_hash,wrapper_runtime_hash,
projection_file_generation,protocol_generation,bundle_projection_hash
```

Generation fields are positive unsigned decimal strings; all other values
after `schema` are lowercase 64-hex except those generation fields. Domain
`awa-registration-bundle-projection/v2`; digest excludes
`bundle_projection_hash`.

### 4.3 Host authority v2

`awa-registration-host-authority/v2` has exactly:

```text
schema,registration_db_path,writer_capability_path,profile_targets,inventory,
proof_parent,projection_parent,legacy_parent,host_tick_receipt_path,
profile_hash,runtime_capability_hash,writer_binary_hash,
writer_capability_hash,tool_inventory_hash,hook_projection_hash,
hook_matcher_mode,hook_matcher_hash,projection_file_generation,
protocol_generation,installer_identity_hash,installer_capability_hash,
storage_dev,host_authority_digest
```

`writer_capability_path` is the exact openat-relative string
`authority/writer-capability.json`; it is never absolute and must freshly
identify the FD15 retained authority under the selected version directory.
Every other host path is a canonical absolute path with no
empty/dot/dot-dot component and 1..4,096 UTF-8 bytes. `profile_targets`
contains exactly these ten records in
this order, each exactly once:

```text
state_parent|directory|0700
db|file|0600
wal|file|0600
shm|file|0600
proof_parent|directory|0700
projection_parent|directory|0700
legacy_parent|directory|0700
root|directory|0700
git_dir|directory|0700
git_common|directory|0700
```

Each record has exactly `role,path,kind,mode`; mode is a four-octal string and
all ten canonical paths are distinct. `db.path == registration_db_path`;
`state_parent.path == dirname(registration_db_path)`; `wal.path ==
registration_db_path + "-wal"`; `shm.path == registration_db_path + "-shm"`;
proof/projection/legacy target paths exactly equal the corresponding host
fields; root is the canonical worktree root; git_dir and git_common are the
canonical live Git descriptor paths measured for that root. None may be
caller-selected through environment or launch context. `profile_targets_hash` is a required
recomputation, not an extra host field:

```text
SHA256(ASCII("awa-registration-profile-targets/v1") || 0x00 ||
       JCS(profile_targets))
```

Live `profile_hash` remains exactly:

```text
SHA256(ASCII("awa-registration-profile/v2") || 0x00 ||
       JCS(exact measured awa-registration-profile/v2 object))
```

with no LF. Its descriptor-binding records must have those exact ten roles in
that order and freshly equal every target path/kind/mode/dev/inode/nlink
measurement.

`inventory` contains 1..512 records, each exactly
`event,server_or_empty,discriminator,role,serializer_schema`. `event` and
`discriminator` match `[A-Za-z0-9][A-Za-z0-9._:-]{0,255}`;
`server_or_empty` is empty or matches that grammar; `serializer_schema`
matches `[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}`; discriminator contains none of
`*+?[](){}|\^$`; role is `ordinary|task_launch`, with both roles present.
The observable key is exactly
`(event,server_or_empty,discriminator,serializer_schema)` and is unique.
Records are ordered by their canonical JCS bytes, not caller order.

```text
tool_inventory_hash =
  SHA256(ASCII("awa-registration-tool-inventory/v1") || 0x00 ||
         JCS(JCS-byte-sorted inventory records))
```

There is no terminal LF in either live profile/inventory digest preimage.
Parent fields are canonical absolute paths or JSON null according to accepted
profile mode; no empty sentinel is allowed. `hook_matcher_mode` is exactly
`ENUMERATED`; generation and `storage_dev` are unsigned decimal strings;
hashes/digests are lowercase 64-hex. The canonical host object is at most
1 MiB. Domain `awa-registration-host-authority/v2`; digest excludes
`host_authority_digest`.

Bundle manifest binds host authority; projection repeats it; direct receipt
v4 and owner gate v3 remain byte-for-byte/schema-for-schema as accepted v7
and bind the exact bundle, projection, and import digests already in their
field sets. Host authority is therefore transitively bound through
bundle→projection→receipt body→gate without adding a receipt/gate field.
Product current is deliberately downstream of the final receipt/gate and
cannot feed back into either. Before READY and GO, direct values and every
transitive bundle/import/host/product/runtime/receipt/gate relation must be
freshly equal, including a new descriptor measurement reproducing
`profile_hash`, exact target records, inventory observable keys, and
`tool_inventory_hash`. Mutation vectors cover target role/order/path/kind/
mode, missing/duplicate target, inventory key/role/domain/order, parents,
storage device, and every duplicated hash. Any need to alter receipt-v4 or
gate-v3 fields/digest domains is a receipt-v5/gate-v4 stop, not authorized.

---

## 5. Complete FD topology and launch context v2

The exact child targets are:

```text
3 control
4 private runtime manifest
5 import manifest v2
6 owner gate v3
7 private-runtime current
8 launch context v2
9 product current
10 product bundle directory
11 bundle manifest v2
12 bundle projection v2
13 direct receipt v4
14 host authority v2
15 writer capability
16+ every PACKAGE_INITIALIZER/MODULE/RESOURCE descriptor in relative-path
    UTF-8 order
```

Path mapping is exact: FD5 =
`authority/import-manifest.json`; FD6 = `authority/owner-gate.json`; FD9 =
root `current.v1`; FD10 = the selected version directory; FD11 =
`authority/bundle-manifest.json`; FD12 =
`authority/bundle-projection.json`; FD13 =
`authority/direct-receipt.json`; FD14 =
`authority/host-authority.json`; FD15 =
`authority/writer-capability.json`; FD16+ = each exact import-manifest
relative path. FD4 is the private-runtime manifest under the separately
retained runtime-version descriptor and FD7 is private-runtime current.
Before spawn, parent verifies exact `authority/owner-gate.sig` over FD6 bytes
with exact `authority/owner-signers`, retains both verification descriptors
through GO, and checks their vnode/event state again at READY and GO. Neither
is passed as a child authority fd. Any path/role/mode/hash mismatch or extra
installed byte refuses.

`awa-registration-launch-context/v2` has exactly:

```text
schema,route,nonce,expected_parent_pid,exact_head,runtime_manifest_sha256,
runtime_current_digest,product_current_digest,bundle_digest,
bundle_projection_hash,direct_receipt_digest,owner_gate_digest,
import_manifest_hash,host_authority_digest,writer_capability_hash,
control_fd,runtime_manifest_fd,import_manifest_fd,owner_gate_fd,
runtime_current_fd,launch_context_fd,product_current_fd,bundle_directory_fd,
bundle_manifest_fd,bundle_projection_fd,direct_receipt_fd,host_authority_fd,
writer_capability_fd,descriptor_records,descriptor_count,descriptor_bytes,
launch_context_digest
```

`route` is `ADMISSION|RECEIVER|STARTUP|TICK`; nonce is 64 lowercase hex;
parent PID and all fd/count/byte fields are unsigned decimal strings; exact
head is 40 lowercase hex; authority values are lowercase 64-hex. Fixed fd
values are decimal `"3"` through `"15"` matching the table.

Each descriptor record has exactly:

```text
fd,role,kind,logical_name,relative_path,owner_module,mode,size,sha256,
st_dev,st_ino,st_nlink
```

`role` is
`PRODUCT_CURRENT|PRODUCT_BUNDLE_DIRECTORY|BUNDLE_MANIFEST|
BUNDLE_PROJECTION|DIRECT_RECEIPT|HOST_AUTHORITY|WRITER_CAPABILITY|
PACKAGE_INITIALIZER|MODULE|RESOURCE`. Records cover every target from fd 9
through `15 + import_record_count`. For fd 10, kind is `DIRECTORY`,
logical_name/owner_module/size/sha256 are JSON null, relative path equals the
product-current bundle directory, mode is exactly `0755`, and dev/inode/nlink are
unsigned decimal strings. Fds 9 and 11..15 are `REGULAR`, use their exact
fixed role as logical_name, have null owner_module, bind canonical installed
relative paths and exact mode/size/hash/dev/inode/nlink-one. Import records
are `REGULAR`, repeat the corresponding manifest values, and require nlink
`"1"`. Descriptor fds are unique and contiguous from 9 through
`15 + import_record_count`; no gap, duplicate, role mismatch, null outside
the directory rule, extra fd, or integer/decimal-string confusion is allowed.
`descriptor_count` is `7 + import_record_count`, is at most 512, and bytes
exactly total all regular records. Thus import records are at most 505. FD8
canonical JCS+LF is at most 1,048,576 bytes. Each regular record is at most
8 MiB and aggregate regular bytes are at most 64 MiB.

Domain `awa-registration-launch-context/v2`; digest excludes
`launch_context_digest`. No downstream READY/GO/import result is a launch
context field.

Before file actions, every source fd is duplicated collision-free to a unique
fd >= `16 + import_record_count`; sources, targets, cycles, occupied targets,
EMFILE, partial action construction, and close failures are tested. Spawn uses
only `POSIX_SPAWN_CLOEXEC_DEFAULT`; fixed targets remain open and every high/
unrelated fd closes. Product paths appear in neither argv nor environment.
Parent and child independently re-fstat and re-hash every retained regular
descriptor and revalidate directory identity at READY and GO; change/event/
short-read/extra/missing authority refuses.

---

## 6. Retained-byte importer and sealed receiver entry

Before READY, child bootstrap reads and hashes every retained import/resource
record into bounded immutable bytes. After GO it installs one in-memory
`MetaPathFinder`/`Loader` pair:

- only manifest PACKAGE_INITIALIZER and MODULE names resolve;
- `get_filename` returns `awa-retained://<sha256>/<logical_name>`;
- `get_code` compiles retained UTF-8 source with that synthetic filename,
  optimization 0, `dont_inherit=True`; `.pyc`, marshal, bytecode cache writes,
  extension modules from product, and source filesystem opens are forbidden;
- package specs set `submodule_search_locations` to an immutable synthetic
  sequence; module specs set it null; `__loader__`, `__spec__`,
  `__package__`, and `__path__` follow importlib contracts;
- relative imports resolve only through included parent packages; missing
  parent/package/module, duplicate name/path, source decode/compile error,
  namespace package, dynamic path extension, or import outside the manifest
  refuses before receiver effects;
- the loader's ResourceReader/Traversable provider exposes only RESOURCE
  records owned by the requesting module/package, with read-only bytes,
  deterministic UTF-8 name order, no path traversal, and no filesystem path;
- `engine.registration_schema` obtains `registration_schema.sql` only through
  `importlib.resources`; product code never reopens product source/resource
  paths; and
- the first requested entry module is exactly
  `engine.registration_receiver`; Python necessarily executes the
  manifest-declared `engine` PACKAGE_INITIALIZER first, then receiver, then
  only receiver dependencies declared in the manifest. The `engine`
  initializer is mandatory, unique, has logical name `engine` and path
  `engine/__init__.py`, and no other product module may execute before it and
  receiver in that order.

Bootstrap removes cwd, empty-string, product root, user site, and overlay
entries from `sys.path`; disables site customization and filesystem fallback;
and installs a deny finder ahead of ordinary PathFinder for every AWA product
namespace. Python stdlib and qualified private-runtime dependencies remain
available only from the owner-authorized runtime closure.

After import, bootstrap calls one receiver entry with parsed immutable
launch-context, host-authority, receipt, gate, current, projection, manifest,
and writer-capability objects plus retained resource provider. Receiver and
host accept no environment-selected config and do not reread authority paths.
Ignored authority bytes, invented launch-v1, config-v1 execution, filesystem
fallback, or a path leak is a refusal.

---

## 7. Non-circular authority DAG

```text
public source lock + attestation
  └─ deterministic runtime builds/qualification
      ├─ Q1/Q2 fixture manifest/envelope/signature bytes
      │   └─ packet-root index
      │       └─ packet v2
      └─ runtime manifest + capability + signature inventory + packet v2
          └─ owner-signed runtime release envelope
              └─ immutable runtime version
                  └─ private-runtime current v2

product import/resource bytes + host authority + signer/enrollment
  ├─ import manifest v2
  └─ bundle manifest v2
      └─ bundle projection v2
          └─ direct receipt-v4 body
              └─ owner gate-v3 + detached owner signature
                  └─ owner_gate_digest
direct receipt-v4 body + owner_gate_digest
  └─ final direct_receipt_digest

runtime current v2 + bundle/projection/import/host + final receipt + gate
  └─ product current v1

mode-bound qualification nonce + request/context + exact recovery assets
  └─ immutable asset index + pre-head/current state
      └─ immutable PREPARED → FILES_PUBLISHED → CURRENT_PUBLISHED
      ├─ semantic REFUSED/FAILED → downstream audit receipt (no head)
      └─ admin receipt v2
          └─ immutable RECEIPT_PUBLISHED → COMMITTED
              └─ admin head v1

admin-head-equal runtime/product currents + final receipt/gate
  └─ invocation-only launch context v2
      └─ retained descriptors → READY → GO
          └─ engine initializer → receiver → declared dependencies
```

Cycle exclusions are exact:

- runtime manifest/release/current exclude admin transaction/receipt/head,
  product receipt/gate/current, launch context, and observed launch evidence;
- import manifest excludes bundle/projection/receipt/gate/currents/launch;
- host authority excludes bundle/projection/receipt/gate/currents/launch;
- bundle excludes projection/receipt/gate/currents/launch;
- projection excludes receipt/gate/currents/launch;
- receipt body excludes `owner_gate_digest`, final receipt digest, product
  current, launch context, and observations;
- owner gate binds receipt-body hash but excludes `owner_gate_digest`, final
  receipt digest, product current, launch context, and observations;
- product current may bind final receipt/gate/runtime/product authorities but
  excludes admin transaction/receipt/head, launch context and observations;
- asset index binds only sorted request recovery records and mode nonce; it
  excludes transaction/phase/result/receipt/head digests;
- PREPARED through CURRENT_PUBLISHED transactions exclude admin receipt/head;
  admin receipt may bind the CURRENT_PUBLISHED transaction and exact currents;
  RECEIPT_PUBLISHED/COMMITTED may then bind admin receipt; head binds only the
  final COMMITTED transaction, exact currents, and receipt;
- semantic REFUSED/FAILED transactions exclude admin receipt/head and their
  downstream receipt binds them; pre-PREPARED receipts use transaction null;
- no transaction binds a successor transaction; each binds only its immediate
  predecessor phase digest; no current binds transaction, admin receipt, or
  head; and head is never an input to an immutable current/receipt body; and
- launch context binds upstream immutable digests but excludes READY/GO/import
  and direct/shadow observed evidence.

Expected denial vectors are generated before signing from expected upstream
authorities. Staged direct/shadow observations compare later and never feed
back into signed expected vectors or any upstream digest. Regenerate all
bundle, A09/A10, denial, receipt, pointer, and readiness vectors from this DAG.

---

## 8. Transactional admin ledger and audit v2

Production ledger root is `/Library/Application Support/AWA-admin/v2/`;
qualification uses
`/Library/Application Support/AWA-qualification-<qualification_nonce>-admin/v2/`.
Both are root:wheel 0755, regular/nlink-one/no-symlink closures. Exact paths:

```text
head.v1
transactions/sha256/<transaction_digest>.json
transactions/by-request/<request_id>.current
receipts/<receipt_digest>.json
staging/sha256/<first-two-hex>/<sha256>.blob
asset-indexes/sha256/<asset_index_digest>.json
```

`awa-registration-admin-transaction/v1` has exactly:

```text
schema,mode,request_id,operation,target_root,qualification_nonce,
pre_head_digest,
pre_runtime_current_digest,pre_product_current_digest,
target_runtime_manifest_sha256,target_bundle_digest,target_bundle_generation,
target_selection_epoch,target_direct_receipt_digest,request_digest,
context_digest,asset_records,asset_index_digest,phase,outcome,
published_paths,cleanup_paths,
reason_code,admin_receipt_digest,result_runtime_current_digest,
result_product_current_digest,predecessor_transaction_digest,
started_wall_ns,updated_wall_ns,transaction_digest
```

Phase is exactly
`PREPARED|FILES_PUBLISHED|CURRENT_PUBLISHED|RECEIPT_PUBLISHED|COMMITTED|
FAILED|REFUSED`; outcome is `null|SUCCESS|FAILED|REFUSED`. Mode is
`PRODUCTION|QUALIFY`; operation is
`INSTALL|UPDATE|ROLLBACK|REMOVE|QUALIFY`. Request ID is 64 lowercase hex;
generation/epoch/times are unsigned decimal strings; path arrays are distinct
UTF-8 sorted canonical absolute paths. `qualification_nonce` is exact JCS
null for PRODUCTION and exactly 64 lowercase hex for QUALIFY. Every phase in
one request repeats mode/request/operation/root/qualification-nonce/request/context/
asset-index values byte-for-byte. QUALIFY parent and all four child requests
repeat the same nonce bound in qualification root/context; a different child
nonce/root refuses. Domain
`awa-registration-admin-transaction/v1`; exact formula:

```text
transaction_digest =
  SHA256(ASCII("awa-registration-admin-transaction/v1") || 0x00 ||
         JCS(transaction_without_transaction_digest) || LF)
transaction_bytes = JCS(full_transaction) || LF
```

The resulting bytes exist only at
`transactions/sha256/<transaction_digest>.json`, mode 0444. Existing digest
paths are reopened and byte-compared; they are never replaced.

`awa-registration-admin-transaction-pointer/v1` has exactly
`schema,request_id,transaction_digest,phase,pointer_digest`; its digest uses
that schema domain and excludes `pointer_digest`. The only mutable transaction
name is `transactions/by-request/<request_id>.current`, whose bytes are this
JCS+LF pointer. It is an atomic latest-phase locator, never phase evidence.

Each `asset_records` member has exactly
`role,logical_name,content_path,size,mode,sha256,signature_digest,request_id,
qualification_nonce,context_digest`. Role is exactly one of:

```text
REQUEST
CONTEXT
STATIC_CONTRACT_SET
ADMIN_ENTRYPOINT
PRIVATE_RUNTIME_MANIFEST
PRIVATE_RUNTIME_RELEASE_ENVELOPE
PRIVATE_RUNTIME_RELEASE_SIGNATURE
PRIVATE_RUNTIME_ARCHIVE
QUALIFICATION_PACKET
IMPORT_MANIFEST
HOST_AUTHORITY
WRITER_CAPABILITY
BUNDLE_MANIFEST
BUNDLE_PROJECTION
DIRECT_RECEIPT
OWNER_GATE
OWNER_GATE_SIGNATURE
OWNER_SIGNERS
PRODUCT_PAYLOAD
RUNTIME_CURRENT_TARGET
PRODUCT_CURRENT_TARGET
REMOVE_INVENTORY
QUALIFICATION_ALLOWED_SIGNERS
Q1_MANIFEST
Q1_ENVELOPE
Q1_SIGNATURE
Q2_MANIFEST
Q2_ENVELOPE
Q2_SIGNATURE
PACKET_ROOT_INDEX
BOUND_INPUT_INDEX
```

`logical_name` is exact role for singleton roles; PRODUCT_PAYLOAD uses its
import relative path and STATIC_CONTRACT_SET uses the contract relative path.
`content_path` must equal the ledger-root
content-addressed staging formula shown above for `sha256`; size is
1..8,388,608 decimal and mode is exact four-octal.
`signature_digest` is the matching detached-signature asset SHA-256 for
PRIVATE_RUNTIME_RELEASE_ENVELOPE, OWNER_GATE, Q1_ENVELOPE, and Q2_ENVELOPE,
and JCS null for every other role; detached-signature roles are separately
present and uniquely paired. The
request ID, qualification nonce (including PRODUCTION null), and context
digest exactly equal the transaction. Records sort by
`(role UTF-8,logical_name UTF-8)`; that pair and content path are unique,
count is 1..512, and aggregate size is at most 64 MiB.

`awa-registration-admin-asset-index/v1` has exactly:

```text
schema,mode,request_id,operation,qualification_nonce,record_count,
aggregate_size,records,asset_index_digest
```

Mode/operation/qualification nonce follow the transaction domains; count/aggregate are
unsigned decimal strings exactly equal to records; `records` is the complete
array above in canonical sort order. The `(role,logical_name)` pair is unique;
each SHA-256 maps to exactly one content path.
Byte-identical content may be referenced by distinct roles only with that
identical path/hash; no duplicate role/logical-name record or one-path/
different-hash alias is valid. Exact formula:

```text
asset_index_digest =
  SHA256(ASCII("awa-registration-admin-asset-index/v1") || 0x00 ||
         JCS(index_without_asset_index_digest) || LF)
asset_index_bytes = JCS(full_index) || LF
```

The index excludes transaction/phase/receipt/head/result digests and therefore
cannot create a fixed point. Every transaction phase contains the exact index
digest and repeats byte-identical `asset_records`; mismatch refuses. The index
is immutable mode 0444 at
`asset-indexes/sha256/<asset_index_digest>.json`.

Required sets are exact:

- INSTALL and UPDATE:
  common `REQUEST,CONTEXT,STATIC_CONTRACT_SET,ADMIN_ENTRYPOINT` plus
  `PRIVATE_RUNTIME_MANIFEST,PRIVATE_RUNTIME_RELEASE_ENVELOPE,
  PRIVATE_RUNTIME_RELEASE_SIGNATURE,PRIVATE_RUNTIME_ARCHIVE,
  QUALIFICATION_PACKET,IMPORT_MANIFEST,
  HOST_AUTHORITY,WRITER_CAPABILITY,BUNDLE_MANIFEST,BUNDLE_PROJECTION,
  DIRECT_RECEIPT,OWNER_GATE,OWNER_GATE_SIGNATURE,OWNER_SIGNERS` and one
  PRODUCT_PAYLOAD for every import record;
- ROLLBACK:
  common plus `RUNTIME_CURRENT_TARGET,PRODUCT_CURRENT_TARGET,DIRECT_RECEIPT,
  OWNER_GATE,OWNER_GATE_SIGNATURE,OWNER_SIGNERS`; every target version byte is
  also revalidated from the retained immutable version, not caller paths;
- REMOVE:
  common plus `REMOVE_INVENTORY,RUNTIME_CURRENT_TARGET,
  PRODUCT_CURRENT_TARGET`;
- QUALIFY parent:
  common plus `QUALIFICATION_ALLOWED_SIGNERS,Q1_MANIFEST,Q1_ENVELOPE,
  Q1_SIGNATURE,Q2_MANIFEST,Q2_ENVELOPE,Q2_SIGNATURE,PACKET_ROOT_INDEX,
  BOUND_INPUT_INDEX`; its child INSTALL/UPDATE substitutes the selected
  Q1/Q2 manifest/envelope/signature triplet for
  PRIVATE_RUNTIME_MANIFEST/PRIVATE_RUNTIME_RELEASE_ENVELOPE/
  PRIVATE_RUNTIME_RELEASE_SIGNATURE, references those exact parent asset
  digests, and requires every remaining applicable product role. Child
  ROLLBACK/REMOVE use their exact ordinary sets against retained Q1/Q2
  authorities under QUALIFY mode.

For every INSTALL, UPDATE, ROLLBACK, REMOVE, QUALIFY parent, and QUALIFY child,
`STATIC_CONTRACT_SET` is the same exact 12-record set—there are no
operation-specific omissions or additions. Each logical name is its exact
contract-relative path and each appears exactly once:

| logical path | SHA-256 |
|---|---|
| `contracts/awa-contract.v1.json` | `408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9` |
| `contracts/awa-contract.v2.json` | `db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a` |
| `contracts/awa-contract.v3.json` | `fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9` |
| `contracts/awa-registration-admin-audit.v1.json` | `a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a` |
| `contracts/awa-registration-admin-audit.v2.json` | `b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2` |
| `contracts/awa-registration-owner-signers.v1` | `9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e` |
| `contracts/awa-registration-owner-signers.v2` | `690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3` |
| `contracts/awa-registration-platform-bootstrap.v1.json` | `4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c` |
| `contracts/awa-registration-platform-bootstrap.v2.json` | `404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9` |
| `contracts/awa-registration-private-runtime.v1.json` | `f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321` |
| `contracts/awa-registration-private-runtime.v2.json` | `91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8` |
| `contracts/awa-registration-privileged-envelope.v1.json` | `7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034` |

Set equality—not subset inclusion—is required: cardinality 12, exact sorted
logical paths, exact hashes, no aliases, and no extra record. The admin v2
static contract freezes the 12 paths/cardinality/equality rule but not its own
hash values, avoiding a static self-hash fixed point; this reviewed table and
the umbrella v3 mandatory hashes provide the concrete values.

No omitted, additional, wrong-operation, duplicate, or caller-discovered role
is valid.

The phase/outcome null matrix is exact:

| phase | outcome | predecessor | asset index | admin receipt | result currents | reason |
|---|---|---|---|---|---|---|
| PREPARED | null | null | required | null | null/null | null |
| FILES_PUBLISHED | null | PREPARED | required | null | null/null | null |
| CURRENT_PUBLISHED | null | FILES_PUBLISHED | required | null | operation matrix | null |
| RECEIPT_PUBLISHED | null | CURRENT_PUBLISHED | required | required | repeat CURRENT_PUBLISHED | null |
| COMMITTED | SUCCESS | RECEIPT_PUBLISHED | required | required | repeat CURRENT_PUBLISHED | `OK` |
| REFUSED | REFUSED | PREPARED or later nonreceipt phase | required | null | null/null | refusal enum |
| FAILED | FAILED | latest nonreceipt phase | required | null | exact durable partial state | failure enum |

PREPARED is the sole initial phase and therefore the sole phase whose
`predecessor_transaction_digest` is null. Every later immutable phase binds
the immediately preceding phase digest. PREPARED/FILES_PUBLISHED/
CURRENT_PUBLISHED/REFUSED/FAILED never bind an admin receipt. For success,
the audit receipt binds CURRENT_PUBLISHED; RECEIPT_PUBLISHED binds that
receipt; COMMITTED binds RECEIPT_PUBLISHED. For semantic refusal/failure, the
REFUSED/FAILED phase is published first and the downstream audit receipt
binds that terminal transaction; no successor transaction points back to that
receipt. Thus transaction↔receipt cycles are impossible.

Every transaction row above requires one lowercase 64-hex
`asset_index_digest`, equal across the phase chain and to the immutable index;
there is no post-PREPARED null case. Mode nonce is likewise invariant:
PRODUCTION transaction and every asset record use JCS null; QUALIFY
transaction and every asset record use the same exact 64-lowercase-hex value.

Result-current nullability is exact: PREPARED/FILES_PUBLISHED/REFUSED are both
null; CURRENT_PUBLISHED and its success descendants require both for
INSTALL/UPDATE/ROLLBACK, both null for REMOVE and QUALIFY parent; FAILED
requires each digest iff that exact current was durably published before the
failure, otherwise null. Mixed one-null/one-present values are valid only for
a demonstrably one-current-published failure boundary and must match
`partial_stage_state`; all other mixed values refuse.

Operation fields combine with every applicable phase exactly:

| operation | pre head/currents | target runtime/bundle/generation/epoch/direct receipt | CURRENT_PUBLISHED result currents | new-version publication |
|---|---|---|---|---|
| INSTALL | null/null/null | all required | both required | required |
| UPDATE | all required | all required | both required | required |
| ROLLBACK | all required | all required | both required | null; retained target only |
| REMOVE | all required | all null | both null | null |
| QUALIFY parent | all null | all null | both null | null; child rows govern |

REFUSED always has null result currents and no new version; FAILED follows the
durable partial-state rule above; CANCELLED has no transaction object.

`pre_head_digest` and both pre-current digests are required for
UPDATE/ROLLBACK/REMOVE and null for first INSTALL/QUALIFY. INSTALL/UPDATE/
ROLLBACK require target runtime, bundle, bundle generation, selection epoch,
and direct receipt; REMOVE requires pre-state and sets all target fields null;
QUALIFY parent target fields are null while its child lifecycle transactions
use their actual INSTALL/UPDATE/ROLLBACK/REMOVE row. `published_paths` and
`cleanup_paths` are empty arrays until observed, never null. Reason is null
before terminal, then required. No empty or sentinel digest is valid.

Structural/authentication/request failures before a canonical PREPARED object
exists are exactly `ARGUMENT_INVALID,AUTHORITY_INVALID,CONTEXT_MISMATCH,
MODE_ROOT_MISMATCH,NONCE_REPLAY,OPERATION_INVALID,PACKET_ROOT_MISMATCH,
SIGNATURE_INVALID`. They emit a root/client audit receipt with
`transaction_digest` JCS null, no transaction pointer, both result currents
null, `asset_index_digest` JCS null, mode-bound qualification nonce, and no
runtime/product/transaction/head mutation; the receipt is the sole root write
when root started. `STATE_INVALID,EPOCH_MISMATCH,LOCKED` are root
semantic refusals only after valid PREPARED; they publish immutable REFUSED
then its downstream receipt. A filesystem/internal/audit failure before
PREPARED likewise has null transaction digest; after PREPARED it publishes
immutable FAILED then its downstream receipt. Receipt digest is always
computed only after its final transaction-digest/null choice is fixed.
CANCELLED is also pre-PREPARED and has both transaction and asset-index
digests null; its qualification nonce still follows mode.

`awa-registration-admin-head/v1` has exactly
`schema,epoch,last_request_id,transaction_digest,runtime_current_digest,
product_current_digest,receipt_digest,predecessor_head_digest,head_digest`;
epoch is positive unsigned decimal; predecessor is null only at epoch 1.
Domain excludes `head_digest`.

Commit order is exact:

1. Copy every retained request asset to its immutable content-addressed
   staging path with O_NOFOLLOW/O_EXCL, fsync/reopen/revalidate bytes,
   metadata, signature, qualification nonce, request and context; fsync each
   staging parent. Construct the exact sorted asset index, O_EXCL write its
   digest path, fsync/reopen/revalidate it and every referenced asset, then
   fsync the asset-index directory. Only then publish PREPARED binding both
   records and index digest through the immutable-phase procedure below.
2. No-replace publish/reopen/revalidate/fsync immutable runtime/product files
   from those recorded staging paths; publish immutable FILES_PUBLISHED.
3. Under exclusive runtime/product/admin locks, verify pre-head/current/
   receipt and freshly reopened assets; atomically publish runtime/product
   current; fsync files/directories; publish immutable CURRENT_PUBLISHED.
4. No-replace publish the complete durable root receipt and reopen/revalidate/
   fsync it. SUCCESS publishes immutable RECEIPT_PUBLISHED. A semantic
   refusal/failure instead publishes immutable REFUSED/FAILED first, then a
   downstream receipt binding it, and stops.
5. SUCCESS publishes immutable COMMITTED, then publishes head pointing to that exact
   transaction/currents/receipt using the current swap protocol and fsyncs.
   REFUSED never advances head. FAILED before CURRENT_PUBLISHED leaves the
   prior head/current launchable; FAILED at/after CURRENT_PUBLISHED leaves
   head/current unequal and launch blocked for successor-authorized repair.

Immutable-phase publication computes canonical bytes/digest, O_EXCL writes
`transactions/sha256/<digest>.json`, fsyncs, reopens/revalidates, fsyncs the
sha256 directory, then writes a same-directory O_EXCL temporary pointer,
fsyncs/reopens it, atomically replaces
`transactions/by-request/<request_id>.current`, fsyncs the by-request
directory, and reopens pointer and immutable phase before the next mutation.
Crash before pointer replacement leaves the prior phase current; recovery may
advance only after validating the uniquely linked immutable successor. Crash
after pointer replacement recovers from that exact phase. Immutable phase
bytes are never replaced, deleted while referenced, or inferred from pointer
contents.

Launch requires exact equality among head, committed transaction, runtime
current, product current, and receipt. It opens
`transactions/sha256/<head.transaction_digest>.json`, requires COMMITTED,
then traverses exact predecessor digests through RECEIPT_PUBLISHED,
CURRENT_PUBLISHED, FILES_PUBLISHED, and PREPARED, whose predecessor is null.
Every object is canonical, digest-addressed, request/context/asset-equal, and
phase/operation-consistent; COMMITTED/RECEIPT_PUBLISHED repeat the admin
receipt digest, that receipt transaction equals CURRENT_PUBLISHED, and
head/chain/receipt repeat identical result-current digests. The by-request
pointer must equal COMMITTED but is not authority. A nonterminal active
request or head/current mismatch blocks launch and enters recovery; a terminal
REFUSED/FAILED-before-current request does not replace the prior equal head.
FDs never survive restart. Recovery O_NOFOLLOW-opens only
the exact asset-index digest path in PREPARED, verifies its canonical digest
and byte-identical transaction records, then O_NOFOLLOW-opens only the exact
content-addressed paths in that index. It revalidates regular file,
nlink one, root ownership, exact mode/size/hash/signature/qualification
nonce/request/context and operation role before any write. Missing, drifted, ambiguous,
aliased, or unbound assets publish durable FAILED; recovery never searches
another path, accepts caller replacements, or infers success from destination
state. It may finish only the uniquely proven next phase. Every crash between
every write/rename/fsync/reopen and each staging/publish/current/receipt/head/
cleanup operation is deterministic and restart-tested in production and
qualification ledgers.

An unreferenced staging blob or asset index left before PREPARED is never
authority. Under the exclusive admin lock, cleanup may remove it only after
complete transaction/receipt/head/index reference enumeration and exact
content-address validation; uncertainty retains it and records refusal.

Audit receipt v2 has exactly:

```text
schema,mode,receipt_origin,request_id,operation,requested_uid,target_root,
qualification_nonce,
packet_root_digest,qualification_context_digest,
qualification_allowed_signers_digest,pre_epoch,post_epoch,
pre_runtime_current_digest,pre_product_current_digest,
runtime_current_digest,product_current_digest,target_runtime_manifest_sha256,
target_bundle_digest,target_bundle_generation,target_selection_epoch,
target_direct_receipt_digest,previous_version,current_version,new_version,
q1_envelope_digest,q1_manifest_sha256,q2_envelope_digest,q2_manifest_sha256,
target_release_envelope_digest,envelope_sha256,request_digest,context_digest,
asset_index_digest,owner_signature_sha256,
synthetic_signature_sha256,state_machine_terminal,outcome,reason_code,
predecessor_audit_digest,root_receipt_link_digest,transaction_digest,
partial_stage_state,cleanup_digest,installed_paths_hash,
removed_paths_hash,started_wall_ns,completed_wall_ns,receipt_digest
```

Domain `awa-registration-admin-audit-receipt/v2`; digest excludes
`receipt_digest`:

```text
receipt_digest =
  SHA256(ASCII("awa-registration-admin-audit-receipt/v2") || 0x00 ||
         JCS(receipt_without_receipt_digest) || LF)
receipt_bytes = JCS(full_receipt) || LF
```

Receipt construction fixes every field in the displayed order, including
transaction JCS null or exact immutable phase digest, before this formula;
the receipt is then published and may be referenced by a later success
transaction. The operation/outcome matrix remains the accepted v7 20-row
matrix with these exact substitutions: `pre_current_digest` expands to the
two pre-current fields; target generation becomes distinct
`target_bundle_generation,target_selection_epoch`; target receipt becomes
`target_direct_receipt_digest`; pointer values are immutable version
identifiers; transaction/current fields are required only after their phase
exists. SUCCESS requires all applicable target/current/
transaction fields, `OK`, `NONE` partial state, cleanup and path hashes;
REFUSED requires request/pre-state, refusal code, null post/target-result, and
transaction null only for the exact pre-PREPARED codes or immutable REFUSED
otherwise; FAILED requires request/pre-state, failure code, transaction null
only before PREPARED or immutable FAILED otherwise, exact partial fields and cleanup, with post/current
only if CURRENT_PUBLISHED; CANCELLED is client-only, has no transaction/head/
root receipt/post/current/partial/cleanup/path hashes. Production requires
owner signature and null qualification/synthetic/Q1/Q2 fields; QUALIFY is the
inverse. INSTALL pre currents/versions are null; UPDATE/ROLLBACK/REMOVE require
them; REMOVE target/new/current is null; QUALIFY parent target/current fields
are null and links four child receipts. Every absent value is JCS null. No
success exists until COMMITTED head equality.

Receipt qualification nonce is JCS null in PRODUCTION and exact lowercase
64-hex in QUALIFY for every outcome, including CANCELLED and pre-PREPARED
terminal results. Receipt asset-index nullability is exact and
operation-independent:

| receipt condition | `transaction_digest` | `asset_index_digest` |
|---|---|---|
| SUCCESS | required CURRENT_PUBLISHED phase | required, equals phase/chain |
| semantic REFUSED/FAILED after PREPARED | required terminal phase | required, equals phase |
| structural/auth/request REFUSED/FAILED before PREPARED | null | null |
| CANCELLED/NO_ROOT_PROCESS | null | null |

Any mixed transaction/index presence, nonce/mode mismatch, or receipt/index/
transaction record mismatch refuses.

Receipt origins are `CLIENT_AUTH|ROOT_ADMIN`; terminals are
`FAILED_CLEANED|FAILED_RESIDUE|NO_ROOT_PROCESS|REFUSED_BEFORE_WRITE|
SUCCESS_COMMITTED`; partial states are
`NONE|STAGED_UNPUBLISHED|VERSION_PUBLISHED|CURRENT_PUBLISHED|
REMOVAL_IN_PROGRESS`. Refusal codes are exactly
`ARGUMENT_INVALID,AUTHORITY_INVALID,CONTEXT_MISMATCH,EPOCH_MISMATCH,LOCKED,
MODE_ROOT_MISMATCH,NONCE_REPLAY,OPERATION_INVALID,PACKET_ROOT_MISMATCH,
SIGNATURE_INVALID,STATE_INVALID`; failure codes are exactly
`AUDIT_FAILED,CLEANUP_FAILED,FILESYSTEM_FAILED,INTERNAL_FAILED,SPAWN_FAILED`.

For zero-context generation, `P` means both pre-current digests plus
`previous_version`; `T` means runtime manifest, bundle digest/generation,
selection epoch, and direct receipt; `R` means both result-current digests,
post epoch, current/new version; `X` means transaction digest; and `C` means
partial state/cleanup/path hashes. `R`/`N` below mean required/null; `P*` means
the exact current-published subset is required and all not-yet-published
members are null. The 20 rows are:

| operation/outcome | P | T | R | X | C | reason |
|---|---:|---:|---:|---:|---:|---|
| INSTALL/SUCCESS | N | R | R | R | R | `OK` |
| INSTALL/REFUSED | N | R | N | N pre-PREPARED/R semantic | R | refusal enum |
| INSTALL/FAILED | N | R | P* | N pre-PREPARED/R after | R | failure enum |
| INSTALL/CANCELLED | N | R | N | N | N | `AUTH_CANCELLED` |
| UPDATE/SUCCESS | R | R | R | R | R | `OK` |
| UPDATE/REFUSED | R | R | N | N pre-PREPARED/R semantic | R | refusal enum |
| UPDATE/FAILED | R | R | P* | N pre-PREPARED/R after | R | failure enum |
| UPDATE/CANCELLED | R | R | N | N | N | `AUTH_CANCELLED` |
| ROLLBACK/SUCCESS | R | R | R; new version N | R | R | `OK` |
| ROLLBACK/REFUSED | R | R | N | N pre-PREPARED/R semantic | R | refusal enum |
| ROLLBACK/FAILED | R | R | P*; new version N | N pre-PREPARED/R after | R | failure enum |
| ROLLBACK/CANCELLED | R | R | N | N | N | `AUTH_CANCELLED` |
| REMOVE/SUCCESS | R | N | currents/current/new N; post epoch R | R | R | `OK` |
| REMOVE/REFUSED | R | N | N | N pre-PREPARED/R semantic | R | refusal enum |
| REMOVE/FAILED | R | N | P* | N pre-PREPARED/R after | R | failure enum |
| REMOVE/CANCELLED | R | N | N | N | N | `AUTH_CANCELLED` |
| QUALIFY/SUCCESS | N | N | parent currents/versions N; post epoch `"4"` | R | R | `OK` |
| QUALIFY/REFUSED | N | N | N | N pre-PREPARED/R semantic | R | refusal enum |
| QUALIFY/FAILED | N | N | P* | N pre-PREPARED/R after | R | failure enum |
| QUALIFY/CANCELLED | N | N | N | N | N | `AUTH_CANCELLED` |

REFUSED is before runtime/product mutation and therefore `C` contains
`partial_stage_state=NONE`, cleanup digest, and empty-list path hashes.
FAILED's `P*` is non-null only for exact phases already durably published.
Q1 child INSTALL selects epoch 1/generation 1; Q2 child UPDATE selects epoch
2/generation 2; child ROLLBACK selects epoch 3/generation 1 without changing
Q1 bytes; child REMOVE commits epoch 4 with no selected product current.
CANCELLED remains a client-only `NO_ROOT_PROCESS` receipt and never appears as
a root transaction.

REMOVE keeps ledger/inventory outside the removed product/runtime root, takes
exclusive active-version locks, publishes durable phases/receipt/head, removes
the root admin path last, and reports success only after external ledger
COMMITTED. Partial removal is FAILED with exact residue inventory, never
inferred success. Its external ledger and content-addressed recovery assets
survive removal until COMMITTED retention expiry; qualification uses the
identical schema/order and proves complete expiry/cleanup after packet capture.

---

## 9. QUALIFY, reconciliation, and ambient-shell closure

### 9.1 Complete qualification orchestration

Accepted-v7 packet-v1 bytes and meaning are immutable, but packet-v1 is
historical-verification/parse-and-refuse only for v8. V8 uses exactly
`awa-registration-private-runtime-qualification/v2`; its packet-root,
bound-input, and evidence index schemas/domains are the accepted v1 names
with `/v2`, and preserve the three-index anti-cycle: packet-root blobs first,
root-bound request/context blobs second, observed evidence last. Packet v2
has exactly:

```text
schema,repository,exact_head,packet_root_index_digest,packet_root_digest,
bound_input_index_digest,source_lock,github_attestation,normalizer_source,
signing_recipe_source,capability,compile_options,builds,byte_comparison,
selected_build_id,final_archives,sbom_license_inventory,
relocation_load_image_evidence,registration_test_evidence,
full_test_evidence,qualification_allowed_signers,qualification_fixtures,
privileged_qualification_context,preprompt_rejection_evidence,
admin_qualification_evidence,parent_death_evidence,executed_identities,
securityagent_result,private_key_deletion,product_authority_evidence,
fd_topology_evidence,retained_import_evidence,
transaction_recovery_evidence,shell_startup_evidence,
evidence_index_digest,evidence_root_digest,packet_digest
```

All accepted-v7 nested field sets, domains, sorting and bounds remain exact
unless replaced below. `packet_digest` excludes itself and is:

```text
SHA256(ASCII("awa-registration-private-runtime-qualification/v2") || 0x00 ||
       JCS(packet_without_packet_digest) || LF)
```

Repository is `KleinPerkins/awa`, exact head is 40 lowercase hex,
packet-root index digest equals packet-root digest, and evidence-index digest
equals evidence-root digest. Unknown/missing/duplicate fields or any v1
schema/domain in a v8 runtime release refuses.

Packet-root binds exact bytes for four v8 contracts, product/import/bundle/
projection/host/runtime-current/product-current schema vectors, retained
importer inputs including SQL, all five scripts, complete admin transaction/
receipt/head vectors and staging blobs, Q1/Q2 fixtures, and
exact implementation head. Bound-input index binds request/context/FD maps.
Evidence index binds SecurityAgent result, executed identities, Q1 install →
Q2 update → Q1 rollback → remove, every transaction fault/recovery, root
receipts/head equality, retained import/resource tests, shell sentinels,
cleanup/no-residue, synthetic private-key deletion, and exact public-key
preimage. Missing/reordered/cyclic/unknown blob or digest refuses.

The five added packet records are exact:

- `product_authority_evidence`:
  `schema,product_current,bundle_manifest,bundle_projection,import_manifest,
  host_authority,direct_receipt,owner_gate,installed_layout,retention_cases,
  equality_results,digest`;
- `fd_topology_evidence`:
  `schema,launch_context,source_fd_map,target_fd_map,fault_cases,
  ready_measurements,go_measurements,digest`;
- `retained_import_evidence`:
  `schema,manifest_digest,first_import,package_cases,module_cases,
  relative_import_cases,resource_cases,filesystem_open_trace,
  bytecode_write_trace,digest`;
- `transaction_recovery_evidence`:
  `schema,production_fixture,qualification_fixture,fault_cases,
  recovery_cases,immutable_phase_chains,by_request_pointer_cases,
  preprepared_null_transaction_cases,asset_role_operation_cases,
  nonce_mode_cases,static_contract_set_cases,asset_index_cases,
  result_receipts,head_current_receipt_equalities,remove_evidence,digest`; and
- `shell_startup_evidence`:
  `schema,script_hashes,sentinel_cases,executed_startup_files,
  inherited_environment,product_prebootstrap_imports,digest`.

Each `schema` is the field name with underscores changed to hyphens under
`awa-registration-<name>/v1`; each digest uses that schema as its domain and
excludes `digest`. Arrays are in declared test-vector order, blob-bearing
values are evidence-index records, hashes are lowercase 64-hex, zero-count
observations are decimal string `"0"`, and any unknown/missing/duplicate field
refuses. Equality result records have exactly
`left_role,right_role,left_digest,right_digest,equal`, with `equal:true`.
Fault/case records have exactly
`case_id,input_digest,expected_outcome,observed_outcome,evidence_digest` and
are sorted by case ID.

Accepted-v7 Q1/Q2
`awa-private-runtime-qualification-release-envelope/v1` remains byte- and
meaning-identical with exactly
`schema,repository,mode,exact_head,qualification_nonce,qualification_root,
fixture_id,epoch,runtime_archive_sha256,fixture_manifest_digest,marker_sha256,
qualification_allowed_signers_digest,release_envelope_digest`. It neither
contains nor interprets `qualification_packet_digest`. Q1/Q2 manifests,
envelopes, and synthetic signatures are immutable packet-root blobs whose
hashes feed packet-v2; packet-v2 can never feed back into a fixture, avoiding
a fixed point.

Only the later production
`awa-private-runtime-release-envelope/v1`, runtime-current v2, direct receipt
v4, and owner gate v3 authorities whose exact accepted fields explicitly
include `qualification_packet_digest` may bind final packet-v2. Packet
indexes and acceptance vectors validate that later binding. Existing
receipt-v4/gate-v3 bytes bind it through their explicit accepted fields; if a
new field/domain is needed, stop for receipt-v5/gate-v4. Qualification
fixture validators reject an added packet-digest field as noncanonical.

Sequence remains: nonprivileged packet generation first; separate exact
qualification-key GO permits one disposable synthetic key; separate exact
one-prompt GO permits only the bound disposable root; packet acceptance is
separate and authorizes no publication/install.

### 9.2 Exact reconciliation classifier

`classify_parent` returns exactly
`ABSENT|LIVE_EXACT|ZOMBIE|PIDVERSION_MISMATCH|AMBIGUOUS`. Only ABSENT, ZOMBIE,
or PIDVERSION_MISMATCH enters nonce scan. Any read/permission error, changing
observation, incomplete start identity, duplicate relation, or unclassified
state is AMBIGUOUS.

Nonce scan returns exactly `NONE|ONE_EXACT|AMBIGUOUS`. Only ONE_EXACT may be
observed for the accepted-v7 bounded natural-exit interval; it is never
signalled/adopted/continued. NONE permits current-boot refusal unless natural
exit is proven from a previously ONE_EXACT candidate or verified boot change
permits prior-boot archival. AMBIGUOUS refuses. Accepted-v7 exact operator
copy and reboot cleanup boundary remain unchanged.

### 9.3 Five POSIX shell entries

These five scripts use byte-exact first line `#!/bin/sh`, POSIX syntax only,
and absolute commands:

```text
kernel/bin/awa-registration-entrypoint.sh
kernel/bin/awa-registration-receiver.sh
kernel/bin/awa-registration-tick.sh
kernel/hooks/awa-registration-admission.sh
kernel/hooks/awa-registration-startup.sh
```

No shebang uses `/usr/bin/env`; no Bash feature or startup path is allowed.
Before product execution each script unsets `BASH_ENV`, `ENV`, every
`PYTHON*`/`DYLD*` name, locale, cwd-derived and AWA legacy config/bundle
variables, then sets only `PATH=/usr/bin:/bin`, `LANG=C`, `LC_ALL=C` and
invokes the absolute root entrypoint. Sentinel tests inject hostile `ENV`,
`BASH_ENV`, shell functions, aliases, PATH, IFS, locale, cwd, and legacy AWA
variables and prove no startup file/source/product code runs before verified
bootstrap.

---

## 10. Exact static successor contracts

Embedded bytes are canonical JCS plus one LF. They are future file bytes, not
present implementation.

### 10.1 `contracts/awa-registration-private-runtime.v2.json`

```json
{"admin_root":"/Library/Application Support/AWA-admin/v2","bundle_directory_fd_target":10,"bundle_directory_mode":"0755","bundle_manifest_schema":"awa-registration-bundle-manifest/v2","bundle_projection_schema":"awa-registration-bundle-projection/v2","host_authority_schema":"awa-registration-host-authority/v2","import_manifest_schema":"awa-registration-import-manifest/v2","launch_context_schema":"awa-registration-launch-context/v2","max_descriptor_bytes":8388608,"max_descriptor_count":512,"max_descriptor_total_bytes":67108864,"predecessor_sha256":"f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321","product_current_path":"/Library/Application Support/AWA/product/current.v1","product_current_schema":"awa-registration-product-current/v1","product_install_root":"/Library/Application Support/AWA/product","product_version_authority_paths":["authority/import-manifest.json","authority/host-authority.json","authority/writer-capability.json","authority/bundle-manifest.json","authority/bundle-projection.json","authority/direct-receipt.json","authority/owner-gate.json","authority/owner-gate.sig","authority/owner-signers"],"product_versions_path":"/Library/Application Support/AWA/product/versions","qualification_packet_schema":"awa-registration-private-runtime-qualification/v2","retention_committed_selection_floor":2,"runtime_current_schema":"awa-registration-private-runtime-current/v2","schema":"awa-registration-private-runtime/v2","selection_epoch_field":"selection_epoch","successor_of":"awa-registration-private-runtime/v1","transaction_pointer_schema":"awa-registration-admin-transaction-pointer/v1","transaction_schema":"awa-registration-admin-transaction/v1"}
```

SHA-256:
`91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8`.

### 10.2 `contracts/awa-registration-platform-bootstrap.v2.json`

```json
{"authority_fd_targets":[4,5,6,7,8,9,10,11,12,13,14,15],"bundle_directory_mode":"0755","descriptor_fd_floor":16,"fd8_max_bytes":1048576,"fixed_fd_paths":{"10":".","11":"authority/bundle-manifest.json","12":"authority/bundle-projection.json","13":"authority/direct-receipt.json","14":"authority/host-authority.json","15":"authority/writer-capability.json","5":"authority/import-manifest.json","6":"authority/owner-gate.json","9":"/Library/Application Support/AWA/product/current.v1"},"fixed_fd_roles":{"10":"PRODUCT_BUNDLE_DIRECTORY","11":"BUNDLE_MANIFEST","12":"BUNDLE_PROJECTION","13":"DIRECT_RECEIPT_V4","14":"HOST_AUTHORITY_V2","15":"WRITER_CAPABILITY","3":"CONTROL","4":"PRIVATE_RUNTIME_MANIFEST","5":"IMPORT_MANIFEST_V2","6":"OWNER_GATE_V3","7":"PRIVATE_RUNTIME_CURRENT_V2","8":"LAUNCH_CONTEXT_V2","9":"PRODUCT_CURRENT"},"importer_first_executed_package":"engine","importer_first_requested_module":"engine.registration_receiver","importer_mode":"RETAINED_BYTES_ONLY","later_reconciler_mode":"OBSERVATION_ONLY","launch_context_schema":"awa-registration-launch-context/v2","max_descriptor_bytes":8388608,"max_descriptor_count":512,"max_descriptor_total_bytes":67108864,"owner_gate_signature_path":"authority/owner-gate.sig","owner_signers_path":"authority/owner-signers","predecessor_sha256":"4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c","product_path_in_argv_or_environment_allowed":false,"qualification_packet_schema":"awa-registration-private-runtime-qualification/v2","reconciliation_parent_states":["ABSENT","LIVE_EXACT","ZOMBIE","PIDVERSION_MISMATCH","AMBIGUOUS"],"reconciliation_scan_states":["ABSENT","ZOMBIE","PIDVERSION_MISMATCH"],"required_spawn_flags":["POSIX_SPAWN_CLOEXEC_DEFAULT"],"routes":["entrypoint","admission","receiver","startup","tick"],"schema":"awa-registration-platform-bootstrap/v2","script_interpreter":"/bin/sh","shell_startup_environment_forbidden":["BASH_ENV","ENV"],"source_fd_floor_formula":"16+IMPORT_RECORD_COUNT","source_fd_minimum":16,"successor_of":"awa-registration-platform-bootstrap/v1"}
```

SHA-256:
`404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9`.

### 10.3 `contracts/awa-registration-admin-audit.v2.json`

```json
{"absent_value":"JCS_NULL","admin_root":"/Library/Application Support/AWA-admin/v2","asset_index_path_template":"/Library/Application Support/AWA-admin/v2/asset-indexes/sha256/<asset_index_digest>.json","asset_index_required_from_phase":"PREPARED","asset_index_schema":"awa-registration-admin-asset-index/v1","asset_record_fields":["role","logical_name","content_path","size","mode","sha256","signature_digest","request_id","qualification_nonce","context_digest"],"cancelled_receipt_origin":"CLIENT_ONLY","digest_domain":"awa-registration-admin-audit-receipt/v2","digest_excludes":["receipt_digest"],"fields":["schema","mode","receipt_origin","request_id","operation","requested_uid","target_root","qualification_nonce","packet_root_digest","qualification_context_digest","qualification_allowed_signers_digest","pre_epoch","post_epoch","pre_runtime_current_digest","pre_product_current_digest","runtime_current_digest","product_current_digest","target_runtime_manifest_sha256","target_bundle_digest","target_bundle_generation","target_selection_epoch","target_direct_receipt_digest","previous_version","current_version","new_version","q1_envelope_digest","q1_manifest_sha256","q2_envelope_digest","q2_manifest_sha256","target_release_envelope_digest","envelope_sha256","request_digest","context_digest","asset_index_digest","owner_signature_sha256","synthetic_signature_sha256","state_machine_terminal","outcome","reason_code","predecessor_audit_digest","root_receipt_link_digest","transaction_digest","partial_stage_state","cleanup_digest","installed_paths_hash","removed_paths_hash","started_wall_ns","completed_wall_ns","receipt_digest"],"head_path":"/Library/Application Support/AWA-admin/v2/head.v1","launch_equality_required":["head_digest","transaction_digest","runtime_current_digest","product_current_digest","receipt_digest"],"modes":["PRODUCTION","QUALIFY"],"operations":["INSTALL","UPDATE","ROLLBACK","REMOVE","QUALIFY"],"outcomes":["SUCCESS","REFUSED","FAILED","CANCELLED"],"partial_stage_states":["NONE","STAGED_UNPUBLISHED","VERSION_PUBLISHED","CURRENT_PUBLISHED","REMOVAL_IN_PROGRESS"],"phases":["PREPARED","FILES_PUBLISHED","CURRENT_PUBLISHED","RECEIPT_PUBLISHED","COMMITTED","FAILED","REFUSED"],"predecessor_sha256":"a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a","preprepared_transaction_null_reason_codes":["ARGUMENT_INVALID","AUTHORITY_INVALID","CONTEXT_MISMATCH","MODE_ROOT_MISMATCH","NONCE_REPLAY","OPERATION_INVALID","PACKET_ROOT_MISMATCH","SIGNATURE_INVALID"],"product_pointer_fields":["selection_epoch","bundle_generation"],"production_qualification_nonce":"JCS_NULL","qualification_admin_root_template":"/Library/Application Support/AWA-qualification-<qualification_nonce>-admin/v2","qualification_nonce_pattern":"^[0-9a-f]{64}$","reason_codes":["ARGUMENT_INVALID","AUDIT_FAILED","AUTH_CANCELLED","AUTHORITY_INVALID","CLEANUP_FAILED","CONTEXT_MISMATCH","EPOCH_MISMATCH","FILESYSTEM_FAILED","INTERNAL_FAILED","LOCKED","MODE_ROOT_MISMATCH","NONCE_REPLAY","OK","OPERATION_INVALID","PACKET_ROOT_MISMATCH","SIGNATURE_INVALID","SPAWN_FAILED","STATE_INVALID"],"receipt_mode":"0444","receipt_owner_group":"wheel","receipt_owner_uid":0,"receipt_path_template":"/Library/Application Support/AWA-admin/v2/receipts/<receipt_digest>.json","recovery_asset_path_template":"/Library/Application Support/AWA-admin/v2/staging/sha256/<first-two-hex>/<sha256>.blob","recovery_asset_roles":["REQUEST","CONTEXT","STATIC_CONTRACT_SET","ADMIN_ENTRYPOINT","PRIVATE_RUNTIME_MANIFEST","PRIVATE_RUNTIME_RELEASE_ENVELOPE","PRIVATE_RUNTIME_RELEASE_SIGNATURE","PRIVATE_RUNTIME_ARCHIVE","QUALIFICATION_PACKET","IMPORT_MANIFEST","HOST_AUTHORITY","WRITER_CAPABILITY","BUNDLE_MANIFEST","BUNDLE_PROJECTION","DIRECT_RECEIPT","OWNER_GATE","OWNER_GATE_SIGNATURE","OWNER_SIGNERS","PRODUCT_PAYLOAD","RUNTIME_CURRENT_TARGET","PRODUCT_CURRENT_TARGET","REMOVE_INVENTORY","QUALIFICATION_ALLOWED_SIGNERS","Q1_MANIFEST","Q1_ENVELOPE","Q1_SIGNATURE","Q2_MANIFEST","Q2_ENVELOPE","Q2_SIGNATURE","PACKET_ROOT_INDEX","BOUND_INPUT_INDEX"],"runtime_current_schema":"awa-registration-private-runtime-current/v2","schema":"awa-registration-admin-audit/v2","static_contract_set_cardinality":12,"static_contract_set_equality_required":true,"static_contract_set_paths":["contracts/awa-contract.v1.json","contracts/awa-contract.v2.json","contracts/awa-contract.v3.json","contracts/awa-registration-admin-audit.v1.json","contracts/awa-registration-admin-audit.v2.json","contracts/awa-registration-owner-signers.v1","contracts/awa-registration-owner-signers.v2","contracts/awa-registration-platform-bootstrap.v1.json","contracts/awa-registration-platform-bootstrap.v2.json","contracts/awa-registration-private-runtime.v1.json","contracts/awa-registration-private-runtime.v2.json","contracts/awa-registration-privileged-envelope.v1.json"],"successor_of":"awa-registration-admin-audit/v1","terminals":["FAILED_CLEANED","FAILED_RESIDUE","NO_ROOT_PROCESS","REFUSED_BEFORE_WRITE","SUCCESS_COMMITTED"],"transaction_digest_path_template":"/Library/Application Support/AWA-admin/v2/transactions/sha256/<transaction_digest>.json","transaction_fields":["schema","mode","request_id","operation","target_root","qualification_nonce","pre_head_digest","pre_runtime_current_digest","pre_product_current_digest","target_runtime_manifest_sha256","target_bundle_digest","target_bundle_generation","target_selection_epoch","target_direct_receipt_digest","request_digest","context_digest","asset_records","asset_index_digest","phase","outcome","published_paths","cleanup_paths","reason_code","admin_receipt_digest","result_runtime_current_digest","result_product_current_digest","predecessor_transaction_digest","started_wall_ns","updated_wall_ns","transaction_digest"],"transaction_pointer_path_template":"/Library/Application Support/AWA-admin/v2/transactions/by-request/<request_id>.current","transaction_pointer_schema":"awa-registration-admin-transaction-pointer/v1","transaction_receipt_field":"target_direct_receipt_digest","transaction_schema":"awa-registration-admin-transaction/v1"}
```

SHA-256:
`b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2`.

### 10.4 `contracts/awa-contract.v3.json`

```json
{"contract":"awa-kernel-contract","forbidden":["AMBIENT_SHELL_STARTUP","CONFIG_V1_EXECUTION","FILESYSTEM_PRODUCT_IMPORT","INFERRED_AUDIT_SUCCESS","LATER_RECONCILER_SIGNAL","PATH_RUNTIME_SELECTION","PRODUCT_PATH_IN_ARGV_OR_ENV","RECEIPT_V5","UNSEALED_HOST_AUTHORITY"],"inheritance_rule":"Every awa-contract/v2 behavior remains required unless an exact v3 field replaces only product-byte transport, launch authority, transactional admin publication, retained-byte import, reconciliation classification, or shell startup closure.","mandatory_contract_sha256":{"contracts/awa-registration-admin-audit.v2.json":"b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v2.json":"404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9","contracts/awa-registration-private-runtime.v2.json":"91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"},"predecessor_path":"contracts/awa-contract.v2.json","predecessor_sha256":"db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a","product_import":"RETAINED_BYTES_ONLY","product_root":"/Library/Application Support/AWA/product","qualification_packet_schema":"awa-registration-private-runtime-qualification/v2","receipt_schema":"awa-registration-direct-receipt/v4","runtime_current_schema":"awa-registration-private-runtime-current/v2","schema":"awa-contract/v3","successor_of":"awa-contract/v2","transactional_admin_required":true,"version":3}
```

SHA-256:
`fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9`.

The exact six operative successor/static authority hashes are these four plus
unchanged privileged-envelope v1
`7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034`
and owner-signers v2
`690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3`.

---

## 11. Closed scope and two bodies

### 11.1 Full 59-path ceiling

```text
Makefile
build/private-runtime/README.md
build/private-runtime/build.sh
build/private-runtime/manifest.py
build/private-runtime/sources.lock.json
contracts/awa-contract.v1.json
contracts/awa-contract.v2.json
contracts/awa-contract.v3.json
contracts/awa-registration-admin-audit.v1.json
contracts/awa-registration-admin-audit.v2.json
contracts/awa-registration-owner-signers.v1
contracts/awa-registration-owner-signers.v2
contracts/awa-registration-platform-bootstrap.v1.json
contracts/awa-registration-platform-bootstrap.v2.json
contracts/awa-registration-private-runtime.v1.json
contracts/awa-registration-private-runtime.v2.json
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
  ASCII("awa-registration-v8-implementation-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) = 714d7d02f9a5e1aca8c800c74303a1eebb6d6b1a46de140bb6ff19b3198ff3ac
```

### 11.2 C-RUNTIME 55-path ceiling and continuation branch

The exact sorted C-RUNTIME list is §11.1 minus:

```text
engine/registration_hook_runtime.py
engine/tests/test_registration_hook_runtime_c.py
live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
live-verify/native-entry-durable-registration-r0.py
```

It therefore equals the exact 55 records in §2.2:

```text
SHA256(
  ASCII("awa-registration-v8-c-runtime-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) = 29c0401fb82088e02818a1cfcb7a62bcbb2eca44c2364dc23698bb45f4ec99b4
```

Continue transparently on existing branch
`impl/native-entry-durable-registration-v7-runtime-bootstrap`; renaming would
obscure the preserved work and adds no authority. V8 acceptance does not
switch or mutate it. The later implementation GO names v8 digest, this branch,
live base, 55-path scope/hash, working manifest, and prior Body C manifest.

C-FINAL remains accepted-v7's 24-path ceiling/hash
`1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8`
and starts only after C-RUNTIME merges. No third body is authorized.

---

## 12. Acceptance and regression ledger

| ID | Required evidence | Refusal |
|---|---|---|
| V8-A01 | Four embedded successor files and six operative static hashes reproduce exact bytes; all predecessor hashes exact | Omission, inferred field, mutation, or hash drift |
| V8-A02 | Exact version tree paths/modes/closed allowlist; immutable bundle generation versus selection epoch; two-selection retention floor; Q1→Q2→Q1 predecessor; lock/descriptor/crash/prune vectors | Extra byte, premature prune, Q1 republish, downgrade, path swap, mutable version, pointer gap, or stale current |
| V8-A03 | Exact resource owner/name/path grammar and SQL mapping; upstream bundle membership versus closed downstream authorities; signer metadata; ten ordered profile targets; inventory roles/keys/order/digests; projection/host vectors | Missing/extra resource or version member, downstream digest cycle, duplicate module/path/key, path-only host input, unsealed host input, or stale vector |
| V8-A04 | FD3–FD15 exact roles and installed paths; parent retained gate-signature/signers verification; 16+ contiguous sorted records; 512/8MiB/64MiB/FD8 bounds; collision/EMFILE/re-fstat/hash faults | Gap, path/role mismatch, path argv/env, inherited fd, target close, or bound bypass |
| V8-A05 | Retained package initializer→requested receiver→declared dependency order; relative import; synthetic specs; ResourceReader/Traversable SQL bytes; hostile cwd/site/sys.path; zero reopen/fallback/bytecode | Filesystem import/resource, undeclared/wrong-order import, cache write, namespace extension, or path leak |
| V8-A06 | Fresh bundle→projection→receipt-v4→gate-v3→final receipt→product-current equality, including cycle-free runtime-current v2 and host/runtime/product authority | Receipt v5, current↔receipt or transaction↔receipt cycle, ignored authority, or stale duplicated value |
| V8-A07 | Branched DAG/full admin branch exclusion tests and regenerated bundle/A09/A10/denial/receipt/pointer/readiness vectors | Downstream feedback, linearized authority, placeholder, or observed digest feedback |
| V8-A08 | Immutable phase chain/pointer; production-null versus QUALIFY nonce equality; exact 12-contract set; canonical asset index required from PREPARED; phase×operation×outcome and pre-PREPARED null receipt matrix; full traversal and every index/asset/write/fsync/recovery fault | Nonce ambiguity, subset contract acceptance, index fixed point/drift, mutable ancestry, receipt cycle, arbitrary rediscovery, inferred success, or partial launch |
| V8-A09 | REMOVE ledger/inventory survives removed root; admin path last; external COMMITTED head before success | Self-deleted evidence, premature success, residue omission, or active removal |
| V8-A10 | Complete packet-v2 three-index authority; packet-v1 refusal; immutable Q1/Q2 fixture-envelope-v1 field set with no packet digest; Q1 epoch1/gen1→Q2 epoch2/gen2→Q1 epoch3/gen1 lifecycle; SecurityAgent/key-deletion/cleanup evidence | Fixture fixed point, added fixture field, v1 packet acceptance, missing blob, owner-key access, incomplete orchestration, or residue |
| V8-A11 | Five-state parent classifier and nonce tri-state; only absent/zombie/mismatch scan; observation-only later invocation; natural-exit/reboot resolution | Permission/read ambiguity classified absent, later signal/adoption, same-boot clearance, or false activity |
| V8-A12 | All five scripts `/bin/sh` POSIX; hostile ENV/BASH_ENV/PATH/IFS/locale/cwd/legacy variables invoke no startup/product code | `/usr/bin/env`, Bash, ambient startup, inherited config, or sentinel execution |
| V8-A13 | Exact 55-path current-work report and prior Body C digest; per-path preserve/complete/supersede; no valid work loss | Blanket overwrite, unbound byte, absent-file confusion, or scope escape |
| V8-A14 | Focused profile/projection/host/installer/launcher/receiver/schema/parent-death/privilege/packaging tests; all accepted v7 cross-body/fault tests unchanged | Weakened assertion, omitted transitive vector, or threshold change |
| V8-A15 | Registration full suite, `make verify-pre-pr`, py_compile, `sh -n`, install/freeze/contracts, exact diff/cached/scope audit, Bugbot and Security Review | Required lane skipped, runner introduced, unrelated edit, or dirty delivery |

Generated hashes/vectors must come from exact bytes, never placeholders.
Historical config/runtime authority tests become parse-and-refuse tests.

---

## 13. Gates and sequencing

1. **V8 acceptance:** documentation status/index promotion only.
2. **`V8-C-RUNTIME-IMPLEMENT`:** exact external GO names accepted v8 digest,
   branch, live base, 55-path scope/hash, working manifest, prior Body C
   manifest, and tests-first ceiling.
3. Complete locally; no prompt/build/sign/install beyond separately named
   authority.
4. **`V8-C-RUNTIME-DELIVER`:** exact changed subset and one Draft PR only.
5. Exact-head Bugbot, Security Review, focused/full verification; Draft and
   auto-merge unarmed.
6. **`V8-C-RUNTIME-PACKET`:** nonprivileged packet generation only.
7. **`V8-C-RUNTIME-QUALIFICATION-KEY`:** one disposable synthetic key only;
   no owner key or prompt.
8. **`V8-C-RUNTIME-PRIVILEGED-QUALIFICATION`:** one exact bound native prompt
   at disposable root only.
9. **`V8-C-RUNTIME-PACKET-ACCEPT`:** packet/evidence acceptance only.
10. **`V8-C-RUNTIME-READY`:** exact head/packet/reviews/checks; reviewer App
    alone may approve, arm native auto-merge, and merge.
11. C-FINAL begins from merged C-RUNTIME live main under its own accepted-v7
    implementation/delivery/readiness gates.

Release/tag/publication, owner signing, production install, Skills pointer,
host activation, R0/R1/C1/R2, and rollout remain separately gated.

Implementation stops for a seventh new path, receipt-v5 need, importer
infeasibility, dynamic-FD failure, inferred audit success, path/config leak,
later-process signalling, mutable/lost transaction ancestry, an unlisted
version byte or unprovable retention/prune state, fixture-envelope field
drift/fixed point, nonce-mode ambiguity, nonexact static-contract membership,
asset-index drift/fixed point, private/owner-key access, build/prompt/install before its
gate, authority drift, working-manifest drift, or any inherited
contradiction. Each requires a successor decision, not improvisation.

---

## 14. Exact v8 plan acceptance

### 14.1 Status-only authority

Exact-byte owner acceptance authorizes only:

1. this status line:
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. v8 index status:
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-03`;
3. v7 index status:
   `SUPERSEDED BY V8 — 2026-10-03`.

It authorizes no implementation, build, delivery, key, signing, prompt,
privileged operation, install, publication, release, activation, or rollout.

### 14.2 Anti-replay normalization

```text
SHA256(
  ASCII("awa-registration-v8-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

Replace exactly one DRAFT/ACCEPTED status line with:

```text
- **Status:** __AWA_V8_STATUS__
```

Replace exactly one v8 DRAFT/ACCEPTED row with:

```text
| `native-entry-durable-registration-v8.md` | __AWA_V8_INDEX_STATUS__ | Bounded product-closure successor to accepted v7; seals retained-byte import, closed version retention, immutable admin ancestry, acyclic packet-v2 qualification, and exact startup/reconciliation. |
```

Replace exactly one v7 ACCEPTED/superseded row with:

```text
| `native-entry-durable-registration-v7.md` | __AWA_V8_PREDECESSOR_INDEX_STATUS__ | Protected private-runtime successor to accepted v6; binds exact SLSA source authority, observation-only pre-import residue refusal, exact executed-byte qualification, qualification-only trust, and a separately gated root-confined disposable native privilege proof. |
```

Each replacement includes one LF. Zero/duplicate/mixed/non-UTF-8/CRLF/NUL or
non-exact context refuses. Simulated promotion must reproduce identical
normalized bytes/digest.

### 14.3 Exact owner acceptance envelope

External acceptance is one JCS object with exactly:

```json
{"accepted_v5_file_sha256":"4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b","accepted_v5_normalized_digest":"f4d222435da9c7eb323d0e4c92fe0997f88beb92c56a85dad7cd96704361be94","accepted_v6_file_sha256":"ee8e4fcadd2951fcf3b4260aa5a4672ef98247a2839d7ad53a7ea2d6e02f6a47","accepted_v6_normalized_digest":"1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452","accepted_v7_file_sha256":"dddae47b0840f5f25f375a92bf3736a654e095549b9e9d7f3c68c6360b230384","accepted_v7_normalized_digest":"88eb649abe56f790bc24c7ef84fca777b36a89f44dd444fa66969202a19cec4d","action":"ACCEPT_PLAN_V8","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","authorized":true,"authorized_actions":["MARK_V7_INDEX_SUPERSEDED","PROMOTE_V8_INDEX_STATUS","PROMOTE_V8_PLAN_STATUS"],"authorized_by":"KleinPerkins","current_receipt_sha256":"a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411","denied_implications":["ACCESS_OWNER_PRIVATE_KEY_OR_OWNER_SIGN","ALTER_PRESERVED_WORK","BUILD_OR_PUBLISH","COMMIT_PUSH_OR_OPEN_PR","GENERATE_QUALIFICATION_KEY","IMPLEMENT_OR_DELIVER","INVOKE_NATIVE_AUTHORIZATION_PROMPT","MUTATE_EXTERNAL_STATE","PRIVILEGED_OPERATION","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","enrollment_hash":"885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4","live_base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","new_c_runtime_scope_count":55,"new_c_runtime_scope_hash":"29c0401fb82088e02818a1cfcb7a62bcbb2eca44c2364dc23698bb45f4ec99b4","new_full_scope_count":59,"new_full_scope_hash":"714d7d02f9a5e1aca8c800c74303a1eebb6d6b1a46de140bb6ff19b3198ff3ac","normalized_digest":"<reviewed lowercase 64-hex>","old_c_runtime_scope_count":49,"old_c_runtime_scope_hash":"704fabc0e15f2a87a9902ea8d6ded4c3b0fe0c29112870fa0ceb0bbb9300ede6","old_full_scope_count":53,"old_full_scope_hash":"7466d991a3448ae15f9fcb6032c7a31d87010c1d466ef2d134edf0d60e6c29b2","owner_signers_v1_sha256":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","owner_signers_v2_sha256":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","pre_v7_body_c_manifest_hash":"9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a","repository":"KleinPerkins/awa","schema":"awa-registration-v8-plan-acceptance-go/v1","source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","static_contract_hashes":{"contracts/awa-contract.v3.json":"fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9","contracts/awa-registration-admin-audit.v2.json":"b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v2.json":"404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9","contracts/awa-registration-private-runtime.v2.json":"91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"},"working_manifest_count":55,"working_manifest_hash":"4cec4be5dd0d48316ea5a4d829a2be26c1eb3e43cdeff91c6aa513f995178081"}
```

The three placeholders are replaced only in the external envelope. Digest:

```text
SHA256(
  ASCII("awa-registration-v8-plan-acceptance-envelope/v1") || 0x00 ||
  JCS(concrete_external_envelope) || LF
)
```

Revalidate all frozen authorities, six static hashes, source/scope/manifests,
branch/base, draft hashes, normalized equivalence, and denied implications
immediately before promotion.

---

## 15. Fresh standalone four-pass review

### Pass 1 — facts

Live/base, accepted hashes, branch, empty index, 51-present/4-absent 55-path
working state, and prior Body C manifest were independently measured. The stop
is real: current v7 code cannot derive a complete retained product/resource
closure, sealed launch context, or durable admin success from accepted
authority.

### Pass 2 — gaps closed

V8 freezes product current/version location, complete import/bundle/projection/
host schemas, FD3–FD15+ topology, retained-byte importer/resource behavior,
acyclic authority, immutable digest-addressed admin ancestry, pre-PREPARED
null-transaction receipts, mode-bound recovery nonce, exact 12-contract set,
immutable recovery asset index, exact version-tree retention/pruning,
packet-v2 without Q-fixture feedback, full QUALIFY evidence, five-state
reconciliation, POSIX shell startup closure, preservation, tests, and serial gates.

### Pass 3 — subtraction

Only six paths are added. Existing launcher/bootstrap/child/installer modules
own the implementation; schema SQL uses the existing schema module. No third
body, importer module, daemon, DB table, receipt v5, alternate runtime,
Developer ID, runner, or service is introduced.

### Pass 4 — demonstrated under-scope

The 59/55 lists contain every demonstrated transitive contract/vector/test
owner. Existing test files cover importer, FD, admin, packet, shell, and
reconciliation deltas; the two schema paths close retained SQL authority.
Any seventh path or incompatible receipt/importer requirement is an explicit
stop. Residual uncertainty is implementation evidence—not plan ambiguity:
dynamic FD behavior under the exact head, retained importlib compatibility,
fault-complete immutable-chain recovery and retention pruning, and disposable
SecurityAgent qualification.
