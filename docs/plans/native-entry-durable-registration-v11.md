# Native Entry Durable Registration

- **Version:** v11
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-05
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v10.md`](native-entry-durable-registration-v10.md),
  preserved byte-identically at SHA-256
  `6eb266c7e88f7aa26444f554fab7cc288e8973a89666f7bd8d8664290a1ecc8a`
  and normalized digest
  `3b6e7f9a34000f2581eee3550839be46359f4e78fabcce97d260f4ee74854bd3`.
- **Inherited authority:** accepted v10 index SHA-256
  `d6d359c1971c6b7df0f2c5b16f96671398aaa0cd15d91425040b0af592dff8ea`;
  accepted v9 plan SHA-256
  `69110832b1acb00e7250dd4b5b0420354b023e46f204d9ee521f48f3eb33f525`;
  accepted v8 plan SHA-256
  `1009c3f2e950fcf88adc1f2a862e7127c9d8bb36001389e6ed22bed347a3e770`;
  immutable [ADR 0026](../adr/0026-durable-registration-authority-hardening.md)
  SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Repository / delivery:** `KleinPerkins/awa`; continuation branch
  `impl/native-entry-durable-registration-v7-runtime-bootstrap`; Draft PR
  [#183](https://github.com/KleinPerkins/awa/pull/183), exact head
  `86c9d4e6672ad6c88ec6bfebadd3b0ffa481e6e0`, base and `origin/main`
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`.
- **Source lock:**
  `a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72`.

> **Governance stop:** this draft authorizes only this new plan file and its
> DRAFT README row. It authorizes no implementation, test, contract, staging,
> commit, push, PR mutation, build, packet preparation/finalization, key
> access/generation/signing, native prompt, privileged operation, acceptance,
> readiness, merge, release, publication, installation, activation,
> R0/R1/C1/R2, external mutation or rollout.

---

## 1. Purpose and frozen baseline

Independent adjudication returned `BLOCKED-CONFIRMED` after v10 C-RUNTIME
delivery, PR-head review and preserved-workspace verification. V11 is the
smallest successor that closes only:

1. the inherited packet-before-key sequencing contradiction; and
2. exact-head packet-index v1 emission/acceptance despite accepted packet-v2
   authority.

All other ADR 0026 and accepted v10/v9/v8/v7 requirements remain normative.
V11 adds no contract, persistent architecture, receipt, owner gate, runtime
field, privilege mechanism, production operation, release action or rollout
body.

The accepted/local authority bindings are exact; the labels below do not
claim that every bound local byte is already materialized in the PR tree:

```text
accepted v10 plan       6eb266c7e88f7aa26444f554fab7cc288e8973a89666f7bd8d8664290a1ecc8a
accepted v10 index      d6d359c1971c6b7df0f2c5b16f96671398aaa0cd15d91425040b0af592dff8ea
accepted v10 normalized 3b6e7f9a34000f2581eee3550839be46359f4e78fabcce97d260f4ee74854bd3
full scope              64 / 2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334
C-RUNTIME scope         60 / 7a1c9ef2fdddad6f2cddb81c49c6a41f9b1cf28841759e60ac4bd24eaecbe5d0
C-FINAL scope           24 / 1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8
v9 implemented          59 / e7576bba802cfb06822f0bd54f436e1e7a7596a7db8c3cde445cb5d94ac3c0f7
v10 stopped             60 / d08a51aa577536022466982314bab8f2483ab0bbf48f68bb176e819b9d6380f6
v10 final               60 / 1bfbb92572e8d325bcd157bbad56fcec5acb09953ae2f7c8bcbfe2b7421a6b97
inherited subset        20 / 5b20759388fac04217583a8208d30615204bd4c641227731316ff72ee923a8d6
delivered subset        21 / ee6857d00304af4b024d118dcf8e750586451b1aafc0d9aea3904d2d7e3e1496
kernel-off test         3d56140fe33f34c46232ae2f29cb89e4fcd229ff17c3dab7df16e8f2ed3fd6ef
v10 one-path binding    02e326050f26c04efb16ad15e993de335a3e0cba92b0887b4bc4060998df3fd9
semantic inventory     a3bd2b76246d2ebb48af502da847c42e113292b84be69b955b6adacdadbdd2b0
```

PR #183 remains Draft and auto-merge remains unarmed. Bugbot reported no
bugs and Security Review reported no medium/high/critical findings against
PR head `86c9d4e6672ad6c88ec6bfebadd3b0ffa481e6e0`; they do not clear its
complete-tree gap. Kernel, registration, runtime/contracts, freeze,
`make verify-pre-pr` and `make verify` passed in the preserved local
60-path workspace, not a clean checkout of that incomplete Git tree. Those
are useful local-byte evidence, not reproducible exact-head clearance. Any
corrective head makes both review and verification evidence stale and
requires fresh clean-head runs.

### 1.1 Independent-review state adjudication

The review's local-preservation and PR-tree observations describe different
artifacts:

- **scope ceiling:** accepted V10's 60-path C-RUNTIME list bounds paths that
  may participate; it does not by itself assert that a Git tree contains
  every path;
- **working manifest:** `60 /
  1bfbb92572e8d325bcd157bbad56fcec5acb09953ae2f7c8bcbfe2b7421a6b97`
  binds the complete local 60-path bytes after V10;
- **delivery subset:** `21 /
  ee6857d00304af4b024d118dcf8e750586451b1aafc0d9aea3904d2d7e3e1496`
  binds only paths staged in the prior delivery, not a complete-tree
  manifest;
- **tracked PR delta:** `origin/main...86c9d4e...` contains those exact 21
  paths, but a changed-path subset cannot prove complete exact-head runtime
  authority; and
- **preserved local work:** at this V11 drafting entry, all 60 C-RUNTIME paths
  exist locally; 59 reproduce the V10 stopped manifest and the remaining
  kernel-off test reproduces its accepted final hash. The 40-entry preserved
  status was therefore present, not absent or reverted. Any older
  pre-delivery snapshot is stale for this drafting run.

The review's complete-tree result is nevertheless a real closure gap. Direct
`git ls-tree`/blob measurement of PR head
`86c9d4e6672ad6c88ec6bfebadd3b0ffa481e6e0` against the V10 final manifest
finds 26 exact, 14 differing and 20 absent paths. In particular,
`engine/tests/test_registration_privileged_installer.py` and
`kernel/bin/awa-private-runtime-admin.py` are absent. Against base
`03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`, exactly five of the 60 final
records are already byte-equal:

```text
contracts/awa-contract.v1.json
engine/tests/test_install_lib.py
engine/tests/test_registration_profile.py
engine/tests/test_registration_store.py
engine/tests/test_verify_lane.py
```

Therefore a qualification-capable corrective head must materialize the
complete 60-record runtime tree. Its base delta is exactly the other 55
paths, not because the implementation scope expands to 55, but because 52
already-completed local paths must finally be delivered byte-identically
alongside the three reopened corrective paths. V11 forbids blanket staging:
the delivery gate must enumerate and hash all 55 records, prove the other
five equal base, and prove complete 60-record tree equality. It may not sweep
any path outside that closed set into the PR.

---

## 2. Two exact blockers

### 2.1 Packet-before-key contradiction

Accepted v8 §9.1 requires Q1/Q2 manifests, envelopes and synthetic signatures
to be immutable packet-root blobs. The Q1/Q2 envelopes bind
`qualification_allowed_signers_digest`; accepted v7 §5.1 defines that
contract from the one-use synthetic Ed25519 public key. Therefore the
packet-root index cannot be finalized before the key and signatures exist.

Accepted v8 §13 nevertheless orders:

```text
V8-C-RUNTIME-PACKET
V8-C-RUNTIME-QUALIFICATION-KEY
V8-C-RUNTIME-PRIVILEGED-QUALIFICATION
V8-C-RUNTIME-PACKET-ACCEPT
```

There is no accepted pre-key partial packet schema, path set or completion
state. Treating `PACKET` as an incomplete preparation step would invent
authority; treating it as final packet generation would require the later
key and privileged evidence. V11 replaces, rather than overlaps, the first
two gates as specified in §6.

### 2.2 Exact-head v1 emission and acceptance

At exact head `86c9d4e6672ad6c88ec6bfebadd3b0ffa481e6e0`,
`engine/registration_privileged_installer.py`, SHA-256
`8b9f10ee8f07be1c47a683b5f96481d44d0b7b7b6e1d332738ba79890fb6a231`,
emits these literals in `QualificationPacketBuilder.finalize_packet_root`
and `finalize`:

```text
awa-registration-private-runtime-qualification-packet-root-index/v1
awa-registration-private-runtime-qualification-packet-root/v1
awa-registration-private-runtime-qualification-bound-input-index/v1
awa-registration-private-runtime-qualification-bound-input-root/v1
awa-registration-private-runtime-qualification-evidence-index/v1
awa-registration-private-runtime-qualification-evidence-root/v1
```

It returns the three indexes and blobs but does not construct canonical
`packet.json` or its packet-v2 digest.

The installed consumer
`kernel/bin/awa-private-runtime-admin.py`, SHA-256
`b25db3fa68685a6639ee2de056110f3b8ef0f600deb95c7966fd6d887fa5711b`,
accepts only packet-root-index `/v1` and recomputes only packet-root `/v1` in
`parse_privileged_context`.

The existing coverage
`engine/tests/test_registration_privileged_installer.py`, SHA-256
`16b1b2a28fed29c4da28d3c18143b8a9d5402a5a8487e56dd2331902d46c222f`,
asserts structural relationships but not the accepted v2 schema/domain
literals, canonical final packet, or v1 refusal.

Accepted v8 §9.1 is contrary and controlling: packet-v1 is
historical-verification/parse-and-refuse only; all three index schemas and
domains use `/v2`; final schema/domain is exactly
`awa-registration-private-runtime-qualification/v2`; unknown, missing,
duplicate or v1 authority refuses. V9 changes only bundle-manifest authority
to v3 and expands static-contract set equality to sixteen. No new static
contract or schema file is required.

---

## 3. Smallest closed corrective scope

The exact corrective implementation ceiling is:

```text
engine/registration_privileged_installer.py
engine/tests/test_registration_privileged_installer.py
kernel/bin/awa-private-runtime-admin.py
```

```text
SHA256(
  ASCII("awa-registration-v11-c-runtime-corrective-scope/v1") || 0x00 ||
  each sorted UTF8(path) || LF
) = 51689c4a7453221585ec0b9b35788b5f763b31da4f98c1aa4be7e305c25e39c3
```

| Path | Disposition | Exact bounded work |
|---|---|---|
| `engine/registration_privileged_installer.py` | `SUPERSEDE` | Replace only packet-index v1 runtime emission with accepted v2 literals; complete canonical packet-v2 construction and exact directory serialization; preserve every unrelated installer/admin/static-contract behavior. |
| `kernel/bin/awa-private-runtime-admin.py` | `SUPERSEDE` | Replace only packet-root-index v1 runtime acceptance/domain verification with exact v2 and explicit v1 refusal; preserve every unrelated root lifecycle, request, context, audit and signature behavior. |
| `engine/tests/test_registration_privileged_installer.py` | `COMPLETE` | Add tests-first exact v2 producer/consumer/final-packet vectors, all v1 schema/domain refusal mutations, sixteen-contract equality, gate ordering and canonical output layout; preserve every existing assertion. |

`SUPERSEDE` applies only to the listed v1 packet behavior, never blanket file
replacement. No reopened path is `PRESERVE`; every other path in the accepted
64/60/24 ceilings is implicitly and byte-exactly `PRESERVE`. A fourth path,
new contract/schema file, production field, receipt-v5, owner-gate-v4 or
broader refactor is a stop requiring a successor decision.

### 3.1 Closed delivery materialization set

Implementation edits remain limited to the three paths above. Corrective
delivery must materialize exactly this 55-path base delta:

```text
Makefile
build/private-runtime/README.md
build/private-runtime/build.sh
build/private-runtime/manifest.py
build/private-runtime/sources.lock.json
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
engine/tests/test_kernel_off_matrix.py
engine/tests/test_platform_bootstrap.py
engine/tests/test_private_runtime_build.py
engine/tests/test_private_runtime_installer.py
engine/tests/test_registration_deployment_authority_c.py
engine/tests/test_registration_host_c.py
engine/tests/test_registration_independence_c.py
engine/tests/test_registration_installer_c.py
engine/tests/test_registration_launcher_c.py
engine/tests/test_registration_packaging_c.py
engine/tests/test_registration_parent_death.py
engine/tests/test_registration_privileged_installer.py
engine/tests/test_registration_projection_c.py
engine/tests/test_registration_receiver_c.py
engine/tests/test_registration_schema.py
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
```

```text
SHA256(
  ASCII("awa-registration-v11-c-runtime-materialization-scope/v1") || 0x00 ||
  each sorted UTF8(path) || LF
) = cfadb027765271d70d1bd8959d1b7a4c31da6ec69a5c66d5ae3cb94911298814
```

Of these, the three §3 paths take their future reviewed corrective hashes.
The other 52 are `PRESERVE` and must equal their exact V10 final-manifest
records; no edit to them is authorized. Together with the five base-equal
records in §1.1, the delivered head must reproduce all 60 paths, modes and
hashes under the V10 final-manifest framing, replacing only the three reopened
hashes in a successor final manifest. The future three hashes, successor
60-record manifest digest, 55-path materialization map digest and corrected
head are deliberately unknown until implementation; they are bound only by
the corrective delivery GO.

### 3.2 Closed governance-delivery scope

Plan acceptance changes only the three status/index surfaces in §8.1 and
still authorizes no Git or PR mutation. A later separately authorized
governance-delivery gate materializes exactly:

```text
docs/plans/README.md
docs/plans/native-entry-durable-registration-v5.md
docs/plans/native-entry-durable-registration-v6.md
docs/plans/native-entry-durable-registration-v7.md
docs/plans/native-entry-durable-registration-v8.md
docs/plans/native-entry-durable-registration-v9.md
docs/plans/native-entry-durable-registration-v10.md
docs/plans/native-entry-durable-registration-v11.md
```

```text
SHA256(
  ASCII("awa-registration-v11-governance-delivery-scope/v1") || 0x00 ||
  each sorted UTF8(path) || LF
) = 5bdf67d9370823d49a5479518ecee0db622d96c24706d35b2ebab0e3177c3975
```

V5–V10 remain byte-identical at:

```text
v5  4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b
v6  ee8e4fcadd2951fcf3b4260aa5a4672ef98247a2839d7ad53a7ea2d6e02f6a47
v7  dddae47b0840f5f25f375a92bf3736a654e095549b9e9d7f3c68c6360b230384
v8  1009c3f2e950fcf88adc1f2a862e7127c9d8bb36001389e6ed22bed347a3e770
v9  69110832b1acb00e7250dd4b5b0420354b023e46f204d9ee521f48f3eb33f525
v10 6eb266c7e88f7aa26444f554fab7cc288e8973a89666f7bd8d8664290a1ecc8a
```

The README and V11 bytes must equal the exact promoted hashes in the accepted
V11 envelope; their only draft-to-promoted edits are §8.1. The governance
delivery scope is disjoint from the 55-path runtime materialization scope and
grants no implementation, build, key, signing, prompt, packet, privilege,
readiness, merge, release, install, activation, R0/R1/C1/R2 or rollout
authority.

After both deliveries, the complete PR delta against base is exactly the
disjoint union of these eight governance paths and the 55 runtime paths:

```text
SHA256(
  ASCII("awa-registration-v11-final-pr-scope/v1") || 0x00 ||
  each sorted UTF8(path) || LF
) = dbf70d6e608353aac2e6ba87832be0eff9490807f4d7b6dd5312a86c9a2e4de9
```

Its cardinality is exactly 63. Governance paths never enter the runtime
manifest; runtime paths never enter governance delivery.

---

## 4. Exact packet-v2 correction

### 4.1 One literal table

Producer, consumer and tests use exactly:

| Role | Schema | Digest domain |
|---|---|---|
| packet root index | `awa-registration-private-runtime-qualification-packet-root-index/v2` | `awa-registration-private-runtime-qualification-packet-root/v2` |
| bound input index | `awa-registration-private-runtime-qualification-bound-input-index/v2` | `awa-registration-private-runtime-qualification-bound-input-root/v2` |
| evidence index | `awa-registration-private-runtime-qualification-evidence-index/v2` | `awa-registration-private-runtime-qualification-evidence-root/v2` |
| final packet | `awa-registration-private-runtime-qualification/v2` | `awa-registration-private-runtime-qualification/v2` |

Any `/v1`, unknown version, mixed schema/domain, missing/extra field,
noncanonical bytes, digest mismatch, unsorted/duplicate record, role-set
drift, blob mismatch or packet-root cycle refuses on the V11 runtime path.
Historical packet-v1 bytes may be retained only as explicit negative
parse-and-refuse fixtures and never authorize prepare, privilege, finalize,
acceptance, release or launch.

### 4.2 Canonical directory and final packet

One gate-bound fresh user-owned local output root contains exactly:

```text
packet-root-index.json
bound-input-index.json
inputs/sha256/<lowercase_sha256>
evidence-index.json
evidence/sha256/<lowercase_sha256>
packet.json
```

Every relative path, mode `0444`, regular-file/link-count-one requirement,
indexed-blob record field set, content-address relation, declared blob
encoding, size, sorting rule and three-index anti-cycle remains exactly
accepted v7 §7.1 as replaced only by v8's `/v2` schemas/domains. Prepare
writes packet-root and bound-input material only after all root dependencies
exist. Finalize writes evidence and `packet.json` only after privileged
evidence and key-deletion proof exist. No transport archive is authority.

Final `packet.json` has exactly, in accepted order:

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

`repository` is `KleinPerkins/awa`; `exact_head` is the corrective delivered
40-hex head; packet-root-index digest equals packet-root digest;
evidence-index digest equals evidence-root digest. The digest is:

```text
SHA256(
  ASCII("awa-registration-private-runtime-qualification/v2") || 0x00 ||
  JCS(packet_without_packet_digest) || LF
)
```

Packet bytes are `JCS(packet_with_packet_digest) || LF`. The five v8 evidence
records, all inherited nested field sets/domains/orders/bounds, exact Q1/Q2
fixture envelope v1 with no packet-digest field, and every refusal remain
unchanged.

### 4.3 Complete static-contract set

Packet root, request/context asset index, producer and tests require set
equality with exactly this canonical map:

```json
{"contracts/awa-contract.v1.json":"408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9","contracts/awa-contract.v2.json":"db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a","contracts/awa-contract.v3.json":"fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9","contracts/awa-contract.v4.json":"f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3","contracts/awa-registration-admin-audit.v1.json":"a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a","contracts/awa-registration-admin-audit.v2.json":"b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2","contracts/awa-registration-admin-audit.v3.json":"f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa","contracts/awa-registration-owner-signers.v1":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v1.json":"4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c","contracts/awa-registration-platform-bootstrap.v2.json":"404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9","contracts/awa-registration-platform-bootstrap.v3.json":"ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0","contracts/awa-registration-private-runtime.v1.json":"f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321","contracts/awa-registration-private-runtime.v2.json":"91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8","contracts/awa-registration-private-runtime.v3.json":"29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"}
```

Omission, addition, duplicate, changed hash, subset/merge semantics, stale
12-member authority or bundle-manifest-v2 execution refuses.

### 4.4 Non-circular two-digest protocol

The two digests are typed, temporally distinct and never interchangeable:

- `packet_root_digest` is exactly the packet-root-index v2 `index_digest`.
  It exists before the native prompt and authorizes only immutable packet-root
  blobs plus the root-bound request/context/FD inputs. The privileged request,
  privileged context, QUALIFY release envelopes, admin qualification audit
  and prompt gate bind this value.
- `qualification_packet_digest` is exactly final packet-v2
  `packet_digest`. It exists only after privileged evidence, evidence-index
  v2 and private-key deletion proof are complete. Packet acceptance,
  production release/runtime-current/direct-receipt/owner-gate authority and
  readiness bind this value.

The current production comparison
`release["qualification_packet_digest"] == request["packet_root_digest"]`
is explicitly `SUPERSEDED`. A production release's owner-signed
`qualification_packet_digest` is validated against the separately accepted,
descriptor-read-back packet-v2 result before a production privileged request
may be constructed. Root request/context validation continues to verify its
own `packet_root_digest`; it neither substitutes that root for the final
packet nor infers final packet acceptance from root equality. QUALIFY fixtures
remain acyclic and contain no final packet digest.

Both values are required to be lowercase 64-hex and carry explicit role at
every API boundary. Supplying root as final, final as root, swapping them,
reusing one value for both roles, binding a final packet before evidence, or
using either without its exact index/packet preimage refuses. No new field is
added to `awa-registration-privileged-request/v1` or the qualification
fixture envelope; doing so is a successor-schema stop.

### 4.5 Descriptor-safe independent read-back

The producer path implements a canonical packet-v2 writer and a separate
read-back verifier within the same file; the test path exercises both.

The writer receives one gate-bound absent output root. It opens the trusted
existing parent directory with `O_RDONLY|O_DIRECTORY|O_CLOEXEC`, validates
its descriptor identity, and performs every descendant operation relative to
that descriptor. It creates the root and `inputs`, `inputs/sha256`,
`evidence`, `evidence/sha256` directories with descriptor-relative
`mkdir`/`open` operations, rejects preexistence, symlinks and `..`, opens each
new directory with `O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW`, checks
current-user ownership, and sets/rechecks mode `0700`.

PREPARE is the sole root/directory creator and publishes only packet-root,
bound-input and input-blob files. FINALIZE descriptor-opens that existing
prepared root, first revalidates its exact prepared entry/blob/index set and
bound digests, and then adds only evidence blobs, `evidence-index.json` and
`packet.json` with the same exclusive rules. Neither phase may replace or
rewrite a prior leaf.

Each file is created relative to its trusted parent descriptor with
`O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW`, initially owner-only. The
writer enforces the verifier's record-count, per-file and aggregate bounds
before creation, rejects replacement or an existing leaf, verifies the opened
object is a regular current-user-owned file with `st_nlink == 1`, uses a
complete short-write/EINTR-safe loop, applies exact mode `0444` with `fchmod`, calls
`fsync`, closes, then reopens with
`O_RDONLY|O_CLOEXEC|O_NOFOLLOW` and verifies bytes and metadata from the new
descriptor. After publishing children it `fsync`s each modified directory
descriptor from the content directories upward through the output root and
finally the trusted parent. It performs no path-based reopen, rename,
overwrite or replacement. Unsupported flags/syscalls or any incomplete
write/fsync/close/reopen leaves no success result and stops; the algorithm
does not promise cleanup after uncertain durability.

The independent verifier:

1. receives the exact output root plus expected repository, exact head and
   root/bound/evidence/final digests, opens the trusted parent, and reaches
   every descendant only by descriptor-relative opens with the flags above;
2. requires the root and both content directory levels to be stable,
   current-user-owned mode-`0700` directories and performs before/after entry
   enumeration at each level;
3. requires the root entry set to equal exactly
   `packet-root-index.json,bound-input-index.json,inputs,evidence-index.json,
   evidence,packet.json`, with no symlink, hard link, device, socket, FIFO,
   extra entry or path escape;
4. opens every file descriptor-relatively with `O_RDONLY|O_CLOEXEC|O_NOFOLLOW`
   and requires regular file, `st_nlink == 1`, current-user ownership and mode
   `0444`;
5. classifies the four fixed authority filenames
   `packet-root-index.json,bound-input-index.json,evidence-index.json,
   packet.json` as `JCS_LF` by contract; their closed top-level schemas contain
   no `encoding` field and any such extra field refuses. Each is at most
   16 MiB and must satisfy strict UTF-8 with no BOM/NUL/CR, exactly one
   terminal LF, duplicate-key rejection, accepted bounded JSON value
   types/numbers and byte equality with `JCS(parsed_value) || LF`;
6. for each indexed blob record, parses declared size as canonical unsigned
   decimal before reading; one blob is at most 512 MiB, all indexed blobs
   together at most 2 GiB and each index at most 4,096 records; it streams
   non-JSON content in chunks no larger than 1 MiB, reads exactly the declared
   size with an EINTR-safe loop, rejects short/extra data, and always
   recomputes exact byte length and SHA-256 before applying only that blob
   record's declared encoding:
   - `BINARY`: bytes are opaque; no UTF-8, LF or JSON rule is applied;
   - `UTF8`: strict UTF-8 with no BOM or NUL; re-encoding must reproduce the
     original bytes exactly; no terminal-LF or Unicode-normalization rule is
     inferred;
   - `UTF8_LF`: the `UTF8` rules plus no CR, at least one byte, and exactly one
     terminal LF (the byte before it, if present, is not LF); internal LF is
     allowed;
   - `JCS_LF`: strict UTF-8 with no BOM/NUL/CR, exactly one terminal LF,
     duplicate-key rejection, accepted bounded JSON value types/numbers, and
     byte equality with canonical `JCS(parsed_value) || LF`;
   a blob role/media type with the wrong declared encoding refuses;
7. validates all four exact §4.1 schemas/domains and complete field sets,
   rejects every v1/mixed/unknown value, recomputes all three index digests
   and final packet digest, and proves packet-root/evidence-root equalities;
8. requires exact role partition and sorting; every index path must be
   normalized and content-addressed under its one allowed directory, every
   referenced blob must exist exactly once with matching size/hash/mode/media
   type/encoding/root binding, and every unreferenced or cross-index blob
   refuses;
9. reopens and hashes all sixteen §4.3 contract blobs and requires exact set
   equality; verifies allowed-signers, Q1/Q2 envelopes/manifests/signatures,
   privileged evidence and private-key deletion proof through their accepted
   nested schemas and digest relations; and
10. validates final `packet.json` field order/set, exact-head/repository,
   index-digest bindings and all accepted v8 nested records, then closes and
   descriptor-safely reopens every authority file once more and performs a
   second stable directory scan before returning success.

Writer and reader share only bounded descriptor helpers, SHA-256 and the
canonical JCS primitive. The reader does not call the builder, finalizer,
writer or trust their returned objects/digests; it owns separate literal
schema/domain/field/role/static-set manifests. Tests create corrupt packet
directories directly, independently of the writer, and mutate each field,
version, domain, role, path, blob relation, metadata property and digest so a
self-consistent writer defect cannot automatically teach the reader to
accept it.

Successful read-back returns one canonical in-memory record with exactly:

```text
schema,repository,exact_head,packet_root_digest,bound_input_index_digest,
evidence_root_digest,qualification_packet_digest,packet_file_count,
input_blob_count,evidence_blob_count,static_contract_set_equal,verified,
verifier_digest
```

Schema/domain is
`awa-registration-private-runtime-qualification-readback/v1`; counts are
unsigned decimal strings; both booleans are true; `verifier_digest` excludes
itself and uses the standard
`SHA256(schema || NUL || JCS(record_without_verifier_digest) || LF)` framing.
This result is not written inside the packet directory and cannot create a
packet cycle. FINALIZE computes `FINALIZE_READBACK` only after publication is
durable. PACKET-ACCEPT must run a fresh non-mutating descriptor-safe
reopen/recompute to produce `ACCEPT_READBACK`; READY must independently do the
same to produce `READY_READBACK`. `ACCEPT_READBACK` and `READY_READBACK` must
each be byte-identical to `FINALIZE_READBACK`. A saved result is evidence of
an earlier observation, never fresh verification. Mutation, replacement,
permission/link/type drift, blob substitution or added/removed entry between
any two gates makes the later gate refuse. Each later gate binds both the
fresh result bytes/digest and the required equality to
`FINALIZE_READBACK`.

---

## 5. Tests-first corrective implementation

The later implementation starts by making existing tests fail against current
v1 behavior, then changes the two production paths. Required evidence:

| ID | Required evidence | Refusal |
|---|---|---|
| V11-A01 | Producer emits all three exact `/v2` index schemas/domains and canonical bytes; consumer accepts the exact v2 root index | Any v1/mixed/unknown runtime authority |
| V11-A02 | Every schema/domain independently mutated to `/v1`, unknown, absent, extra or mismatched refuses in producer/consumer/finalizer | Permissive version or inferred domain |
| V11-A03 | Final `packet.json` exact field set/order, JCS+LF bytes and digest reproduce; packet/root/evidence equalities and three-index anti-cycle bite | Missing final packet, cycle or digest inference |
| V11-A04 | Exact 16-contract set and bundle-manifest-v3 vectors pass; omission/addition/duplicate/hash/v2-execution mutations refuse | Stale static authority |
| V11-A05 | Prepare cannot finalize before key/signers/Q1/Q2 exist; privilege cannot start before root/bound indexes; finalize cannot run before privilege result and key-deletion proof | Reintroduced sequencing overlap |
| V11-A06 | Existing qualification fixture, installed-admin context, lifecycle, audit, recovery, v10 semantic inventory and all unrelated tests remain unchanged/passing | Assertion loss or scope escape |
| V11-A07 | Exact 3-path edit scope plus closed 55-path materialization set produce a clean head whose complete 60-record tree matches the successor manifest; 52 delivered preserved paths and five base-equal paths reproduce V10 bytes | Fourth edit path, incomplete head or preserved-byte drift |
| V11-A08 | Root/final digests are distinct typed inputs throughout; root-as-final, final-as-root, swapped-value and one-value-for-both vectors refuse in prepare, admin-context, production-release, acceptance and ready seams | Digest substitution or inherited equality |
| V11-A09 | Safe writer fault fixtures cover preexisting/symlinked leaves, short writes, EINTR, chmod/fsync/close/reopen/directory-fsync failure and metadata drift; independent read-back directly corrupts every schema/domain/field/role/path/blob/static-set/metadata/digest family and v1 variant | Replacement, partial publication, self-validation or path race |
| V11-A10 | Fixed authority filenames have implicit JCS_LF and reject an `encoding` field; indexed BINARY, UTF8, UTF8_LF and JCS_LF blob vectors enforce their distinct exact rules plus universal size/hash bounds; `FINALIZE_READBACK`, fresh `ACCEPT_READBACK` and fresh `READY_READBACK` are byte-equal, while every between-gate mutation/substitution/permission/link/type/name case refuses | Top-level encoding field, blob-encoding conflation or stale verification |

Run the focused existing test module first, then packet/admin/registration
focused suites, contract/schema/freeze checks, `py_compile`, relevant shell
syntax, `make verify-pre-pr`, `make verify`, exact diff/scope/manifest/status
checks, Bugbot and Security Review. No assertion may be weakened, skipped or
renamed to pass.

---

## 6. Correct dependency gates

These gates are serial and non-transitive:

1. **V11 acceptance:** documentation status/index promotion only.
2. **`V11-GOVERNANCE-DELIVER`:** separate exact owner GO binds repository,
   branch, existing Draft PR #183/unarmed state, current pre-delivery head,
   accepted V11 plan/index/normalized hashes, the exact eight-path §3.2 scope,
   all six frozen predecessor hashes and exact promoted V11/README hashes.
   After revalidating staging empty, it authorizes explicit staging of only
   those eight paths, exactly one governance commit, one push of this branch
   and update of the existing Draft PR. It may not mark ready or arm/merge.
   The resulting governance commit/head and exact eight-path Git delta are
   outputs, not plan-acceptance inputs; they must be verified locally/remotely
   and bound by the next gate. Post-delivery verification also proves every
   non-governance local record/status entry remained unchanged and the
   complete local V10 runtime manifest still reproduces.
3. **`V11-C-RUNTIME-CORRECTIVE-IMPLEMENT`:** exact external GO binds accepted
   V11 authority plus the verified governance-delivery head/delta, repository,
   branch, Draft PR/unarmed state, base, source lock, accepted V10 bindings,
   3-path scope and each starting path hash, the 55-path materialization set
   and complete local V10 final manifest. It authorizes tests-first edits only
   in §3; the other 52 materialization paths are read-only preservation
   inputs.
4. **`V11-C-RUNTIME-CORRECTIVE-DELIVER`:** separate exact GO binds the final
   three corrected hashes, exact 55-path runtime base-delta map/digest, successor
   60-record complete-tree manifest/digest and passing local verification.
   Before staging, each of the 52 preserved materialization records must equal
   V10 and the five excluded records must equal base. It authorizes explicit
   staging of only the 55 named paths, one commit/push and update of only Draft
   PR #183. The delivered head must reproduce all 60 records from Git objects
   without any working-tree overlay, preserve the eight governance blobs from
   the prior head, and make the complete PR delta exactly the 63-path union
   hash in §3.2. Draft/unarmed remains mandatory.
5. Fresh exact-head Bugbot, Security Review and all §5 checks pass. Prior
   head reviews are stale for the corrective head.
6. **`V11-C-RUNTIME-QUALIFICATION-PREPARE`:** separate exact GO binds the
   reviewed corrective head/PR/source/scope plus one exact fresh user-owned
   packet output root and authorizes exactly two local clean nonpublishing
   builds, one disposable qualification-only synthetic Ed25519 keypair,
   exact dynamic allowed-signers contract, Q1/Q2 manifests/envelopes/
   signatures, all packet-root blobs/index, all root-bound request/context/FD
   blobs and bound-input index. It authorizes no owner-key access/signing,
   native prompt, privileged operation, evidence-index finalization,
   `packet.json`, publication, production install or head change.
7. **`V11-C-RUNTIME-PRIVILEGED-QUALIFICATION`:** separate exact one-prompt GO
   binds repository, Draft PR, exact head/scope, output root, packet-root and
   bound-input digests, qualification nonce/root, allowed-signers digest,
   Q1/Q2 envelope/manifest digests, context digest and request ID. It permits
   one native SecurityAgent prompt only against the disposable bound
   qualification root and no production root/second prompt.
8. **`V11-C-RUNTIME-PACKET-FINALIZE`:** separate exact GO binds the successful
   privilege result and all preceding digests. It authorizes capture of the
   accepted evidence set, close/unlink/absence proof for the disposable
   private key, evidence-index v2, canonical final `packet.json` v2 and one
   descriptor-safe read-back verification only. It emits the canonical
   read-back result outside the packet directory. It authorizes no acceptance,
   publication, installation or head change.
9. **`V11-C-RUNTIME-PACKET-ACCEPT`:** separate exact GO names packet,
   packet-root, bound-input, evidence-root, privileged-evidence, head, PR,
   source-lock, scope and `FINALIZE_READBACK` bytes/digest. It authorizes one
   fresh non-mutating descriptor-safe recomputation `ACCEPT_READBACK`,
   requires `ACCEPT_READBACK == FINALIZE_READBACK`, checks typed packet-root
   versus final qualification-packet roles and accepts evidence only.
10. **`V11-C-RUNTIME-READY`:** separate exact GO names the same immutable
    root/final packet, `FINALIZE_READBACK` and `ACCEPT_READBACK`, complete
    60-record Git-tree manifest, exact head plus clean fresh reviews/checks.
    It authorizes one fresh non-mutating recomputation `READY_READBACK`,
    requires `READY_READBACK == FINALIZE_READBACK`, and only then lets the
    reviewer App alone approve, arm native auto-merge and merge. Agents never
    mark ready, arm, disable or merge without this gate and never call
    auto-merge.
11. C-FINAL starts only from the merged corrective C-RUNTIME live-main commit
    under its inherited separate implementation/delivery/readiness gates.

For the V11 runtime head, inherited standalone `V8-C-RUNTIME-PACKET` and
`V8-C-RUNTIME-QUALIFICATION-KEY` are explicitly `SUPERSEDED` by
`V11-C-RUNTIME-QUALIFICATION-PREPARE`. They have no independent, additive,
fallback or replay authority. The inherited privileged, acceptance and ready
names are replaced by the exact V11 names above so no mixed-version gate can
authorize work.

Draft acceptance, governance delivery, implementation, corrective delivery, build,
synthetic-key generation/signing, owner-key access/signing, native prompt,
privileged operation, packet preparation, finalization, evidence acceptance,
readiness, merge, release/tag/publication, production install, Skills
binding, host activation, R0/R1/C1/R2 and rollout remain distinct. No gate
implies another.

---

## 7. Stops and non-goals

Stop for a fourth implementation path; new static contract/schema; receipt-v5
or owner-gate-v4 need; packet field/domain change; inability to produce exact
v2 while refusing v1; incomplete final packet; fixed point; key before
PREPARE; prompt before its exact gate; second prompt; owner/private-key
access; production-root access; build/publication/install outside its gate;
scope, source, head, plan, manifest, review or preserved-byte drift; or any
inherited v10/v9/v8/v7/ADR contradiction.

V11 does not redesign registration, alter accepted runtime semantics, modify
C-FINAL, create a transport archive, add a daemon/runner/dependency, change
owner signing, publish or install anything, or authorize R0/R1/C1/R2.
Governance delivery stops for a ninth path, any V5–V10 byte drift, a
non-promoted README/V11 preimage, staged residue, non-Draft/armed PR, or any
attempt to combine governance and runtime delivery.

---

## 8. Exact V11 acceptance

### 8.1 Status-only promotion

Only a later exact owner acceptance GO may:

1. change this plan status to
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. change the V11 README row to
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-05`;
3. change only the V10 README row to
   `SUPERSEDED BY V11 — 2026-10-05`.

The accepted V10 plan file and every predecessor/ADR byte remain unchanged.
Draft creation does not mark V10 superseded. Acceptance performs only these
local status replacements and authorizes no staging, commit, push or PR
mutation; only the later `V11-GOVERNANCE-DELIVER` GO can deliver them.

### 8.2 Anti-replay normalization

```text
SHA256(
  ASCII("awa-registration-v11-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

Replace exactly one complete DRAFT/ACCEPTED plan status line with:

```text
- **Status:** __AWA_V11_STATUS__
```

Replace exactly one complete V11 DRAFT/ACCEPTED index row with:

```text
| `native-entry-durable-registration-v11.md` | __AWA_V11_INDEX_STATUS__ | Minimal packet-authority successor to accepted v10; replaces packet-before-key with dependency-correct qualification preparation and upgrades exact-head packet producer/consumer authority from historical v1 to accepted v2. |
```

Replace exactly one complete V10 accepted/superseded index row with:

```text
| `native-entry-durable-registration-v10.md` | __AWA_V11_PREDECESSOR_INDEX_STATUS__ | Minimal semantic-inventory successor to accepted v9; adds only the kernel-off matrix test to distinguish accepted registration locks/ABI layout from forbidden worktree locks and immutable-flag operations. |
```

Each replacement includes one LF. Zero, duplicate, mixed, non-UTF-8, CRLF,
NUL or non-exact context refuses. Simulated draft and promoted bytes must
normalize identically.

### 8.3 Exact owner envelope shape

External acceptance is one canonical JCS object with exactly:

`entry_status_sha256` is over the exact stdout bytes of
`LC_ALL=C git -c core.quotePath=true status --porcelain=v1
--untracked-files=all`; count is its LF-delimited record count.
`staging_empty:true` requires exact empty stdout from
`git diff --cached --name-only --`. These bind the verified drafting-entry
state, not a future governance-delivery head or delta.

```json
{"accepted_v10_index_sha256":"d6d359c1971c6b7df0f2c5b16f96671398aaa0cd15d91425040b0af592dff8ea","accepted_v10_normalized_digest":"3b6e7f9a34000f2581eee3550839be46359f4e78fabcce97d260f4ee74854bd3","accepted_v10_plan_sha256":"6eb266c7e88f7aa26444f554fab7cc288e8973a89666f7bd8d8664290a1ecc8a","action":"ACCEPT_PLAN_V11","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","authorized":true,"authorized_actions":["MARK_V10_INDEX_SUPERSEDED","PROMOTE_V11_INDEX_STATUS","PROMOTE_V11_PLAN_STATUS"],"authorized_by":"KleinPerkins","auto_merge_armed":false,"base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","branch":"impl/native-entry-durable-registration-v7-runtime-bootstrap","c_final_scope_count":24,"c_final_scope_hash":"1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8","c_runtime_scope_count":60,"c_runtime_scope_hash":"7a1c9ef2fdddad6f2cddb81c49c6a41f9b1cf28841759e60ac4bd24eaecbe5d0","corrective_scope_count":3,"corrective_scope_hash":"51689c4a7453221585ec0b9b35788b5f763b31da4f98c1aa4be7e305c25e39c3","delivered_subset_count":21,"delivered_subset_digest":"ee6857d00304af4b024d118dcf8e750586451b1aafc0d9aea3904d2d7e3e1496","denied_implications":["ACCESS_GENERATE_OR_SIGN_WITH_ANY_KEY","ALTER_PRESERVED_WORK","BUILD_OR_PUBLISH","COMMIT_PUSH_OR_MUTATE_PR","IMPLEMENT_OR_DELIVER","INVOKE_NATIVE_AUTHORIZATION_PROMPT","MUTATE_EXTERNAL_STATE","PACKET_PREPARE_FINALIZE_OR_ACCEPT","PRIVILEGED_OPERATION","READY_OR_MERGE","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","entry_status_count":41,"entry_status_sha256":"b9fa66fd5c4837b0b066cd9f9912955b2876fd11877afd0f04007434e67a522b","exact_head":"86c9d4e6672ad6c88ec6bfebadd3b0ffa481e6e0","final_manifest_count":60,"final_manifest_hash":"1bfbb92572e8d325bcd157bbad56fcec5acb09953ae2f7c8bcbfe2b7421a6b97","final_pr_scope_count":63,"final_pr_scope_hash":"dbf70d6e608353aac2e6ba87832be0eff9490807f4d7b6dd5312a86c9a2e4de9","full_scope_count":64,"full_scope_hash":"2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334","governance_delivery_scope_count":8,"governance_delivery_scope_hash":"5bdf67d9370823d49a5479518ecee0db622d96c24706d35b2ebab0e3177c3975","materialization_scope_count":55,"materialization_scope_hash":"cfadb027765271d70d1bd8959d1b7a4c31da6ec69a5c66d5ae3cb94911298814","normalized_digest":"<reviewed lowercase 64-hex>","pr_head_manifest_differing_count":14,"pr_head_manifest_exact_count":26,"pr_head_manifest_missing_count":20,"pr_number":183,"pr_state":"DRAFT","promoted_index_sha256":"<reviewed lowercase 64-hex>","promoted_plan_sha256":"<reviewed lowercase 64-hex>","repository":"KleinPerkins/awa","schema":"awa-registration-v11-plan-acceptance-go/v1","source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","staging_empty":true,"starting_path_hashes":{"engine/registration_privileged_installer.py":"8b9f10ee8f07be1c47a683b5f96481d44d0b7b7b6e1d332738ba79890fb6a231","engine/tests/test_registration_privileged_installer.py":"16b1b2a28fed29c4da28d3c18143b8a9d5402a5a8487e56dd2331902d46c222f","kernel/bin/awa-private-runtime-admin.py":"b25db3fa68685a6639ee2de056110f3b8ef0f600deb95c7966fd6d887fa5711b"}}
```

Placeholders are replaced only in the externally submitted envelope. Its
receipt-independent digest is:

```text
SHA256(
  ASCII("awa-registration-v11-plan-acceptance-envelope/v1") || 0x00 ||
  JCS(concrete_external_envelope) || LF
)
```

Before promotion, recompute every accepted authority, branch/head/base/PR
Draft/unarmed state, source lock, 64/60/24 scopes, current local final
manifest, delivered subset, exact entry-status bytes/count/hash and empty
staging, PR-tree 26/14/20 classification, 3-path edit scope, 8-path governance
scope, 55-path materialization scope, 63-path final-PR scope, starting hashes, draft/promoted
plan/index hashes, normalization equivalence and every denied implication.
Any mismatch refuses without mutation. Future governance commit/head/delta,
corrected path hashes/head, successor 60-record manifest, 55-path delivery-map
digest, packet/index digests and read-back-result digests are deliberately
absent because their preimages do not yet exist; the later applicable gates
must bind them exactly.

---

## 9. Review provenance

This draft records the independently adjudicated authority stop and current
source inspection; it does not claim independent review clearance. A fresh
review must verify that the three-path ceiling is complete, packet-v2
producer/consumer/finalization is exact, v1 refuses, PREPARE removes all
packet/key overlap, encoding-specific writer/read-back behavior is
descriptor-safe, all three gates reverify fresh bytes, governance delivery is
closed/disjoint, and no accepted V10 behavior is weakened.
