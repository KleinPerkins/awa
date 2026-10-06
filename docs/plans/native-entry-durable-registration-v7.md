# Native Entry Durable Registration

- **Version:** v7
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-03
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v6.md`](native-entry-durable-registration-v6.md),
  preserved byte-identically at SHA-256
  `ee8e4fcadd2951fcf3b4260aa5a4672ef98247a2839d7ad53a7ea2d6e02f6a47`
  and accepted normalized digest
  `1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452`.
- **Inherited authority:** accepted, frozen
  [`native-entry-durable-registration-v5.md`](native-entry-durable-registration-v5.md),
  SHA-256
  `4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b`,
  accepted normalized digest
  `f4d222435da9c7eb323d0e4c92fe0997f88beb92c56a85dad7cd96704361be94`,
  and accepted-v5 receipt hash
  `c27746a232275380bfca5cba110d4533813cdc4e9b4a3710629a9c34742706a6`.
- **Architecture authority:** accepted, immutable
  [ADR 0026](../adr/0026-durable-registration-authority-hardening.md), SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Source baseline:** live `origin/main`
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`, the merge commit for
  [Body B PR #182](https://github.com/KleinPerkins/awa/pull/182).
- **Owner-key enrollment:** current ACTIVE enrollment hash
  `885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4`;
  current receipt SHA-256
  `a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411`;
  current allowed-signers contract SHA-256
  `9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e`.
- **Preserved incomplete Body C work:** 23 path/mode/content records, domain
  `awa-registration-v7-body-c-working-manifest/v1`, digest
  `9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a`.
- **Version discipline:** v7 replaces only accepted-v5/v6 assumptions that
  select Homebrew, platform, or another external Python as AWA's product
  runtime and the directly dependent launcher/config authority. Every
  unaffected accepted-v5/v6 invariant remains mandatory.

**Goal:** use a normalized, owner-authorized, root-owned private CPython
runtime for AWA product code while a fixed root-owned bootstrap under absolute
`/usr/bin/python3 -I -S -B` performs only standard-library verification and
spawn supervision.

> **Governance stop:** this mutable draft authorizes only this file and its
> existing DRAFT index row. It authorizes no implementation, build, native
> authorization prompt, staging, commit, push, PR, owner-private-key access or
> owner signing,
> publication, privileged production operation, installation, activation,
> R0/R1/C1/R2, or rollout.

---

## 1. Conflict, decision, and minimality

Accepted v5 requires refusal before the first unverified AWA product import,
an exact interpreter capability, owner-signed deployment authority, immutable
bundle bytes, and separately gated rollout. The incomplete Body C work proved
that a path plus file digest cannot remain authoritative across a later
`exec`: the measured vnode can differ from the mapped executable even when the
visible path is restored. Homebrew remains user-replaceable, and platform
Python does not satisfy the product capability or registration-SQLite floor.

V7 therefore adopts the smallest architecture that closes the executable
identity boundary without weakening accepted invariants:

1. one root-owned immutable entrypoint and standard-library-only parent,
   executed by absolute `/usr/bin/python3 -I -S -B`;
2. one normalized, owner-signed private CPython runtime in a content-addressed
   root-owned version directory;
3. ordinary `posix_spawn` with `POSIX_SPAWN_CLOEXEC_DEFAULT`, an active-version
   shared lock, retained descriptors/kqueues, child parent-death control, and
   nonce-bound `READY → GO → IMPORT_READY`, plus durable reconciliation for
   the narrow pre-watchdog parent-death window; and
4. one deterministic native-authorization path for install/update/rollback/
   removal, with no credentials handled by AWA and no root process after an
   operation.

The parent verifies authority before spawn. The child can execute only bytes
already protected by the owner-signed immutable closure, immediately proves
the expected parent relationship, arms an EOF watchdog, and blocks before any
AWA product import. Mapped-vnode/CDHash observation is a supplemental
post-spawn check, not the source of executable authority. An active-version
shared lock prevents the selected version from mutating or being removed.
Darwin provides no atomic parent-death binding before that watchdog arms. A
child stranded in that interval is inert owner-authorized runtime/bootstrap
code. A later invocation never signals it: AWA remains inactive until natural
exit or reboot. V7 does not claim zero orphan or bounded process cleanup; only
record retention, observation wait, and operator behavior are bounded.

Anything smaller restores a user-controlled executable race, uses platform
Python as the product runtime, or permits product import before parent
authorization. Anything larger—a daemon, setuid helper, alternate runtime,
Developer ID requirement, updater service, paid runner, or duplicated
ecosystem authority—is not demonstrated. SQL, store, admission, hook policy,
owner identity, protocol modes, and rollout remain inherited.

---

## 2. Verified baseline and preserved Body C work

### 2.1 Ground truth

Before any later gate, independently require:

- local `HEAD`, local `origin/main`, and live GitHub `refs/heads/main` at
  `03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d`;
- accepted v5/v6, ADR 0026, current enrollment, receipt, and signer contract at
  the header hashes;
- no private runtime release, privileged production install, host activation,
  or rollout;
- platform Python used only for standard-library verification/spawn
  supervision and never ordinary AWA product code or registration SQLite; and
- the current working tree and index preserved exactly until a separately
  accepted implementation gate.

### 2.2 Exact Body C working manifest

The incomplete Body C bytes remain bound by:

```text
SHA256(
  ASCII("awa-registration-v7-body-c-working-manifest/v1") || 0x00 ||
  for each exact path below, sorted by UTF-8 path bytes:
    UTF8(path) || 0x00 ||
    ASCII(format(stat.S_IMODE(lstat(path).st_mode), "03o")) || 0x00 ||
    ASCII(SHA256(exact_file_bytes)) || LF
) =
9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a
```

Every input must be an owner-UID regular file with `st_nlink == 1`, never a
symlink. Pre-open `lstat`, `open(O_NOFOLLOW)`, `fstat`, post-read `fstat`, and
visible-path rebind must identify the same object. Exact paths:

```text
engine/registration_hook_runtime.py
engine/registration_host.py
engine/registration_installer.py
engine/registration_launcher.py
engine/registration_projection.py
engine/registration_receiver.py
engine/tests/registration_body_c_fixtures.py
engine/tests/test_registration_deployment_authority_c.py
engine/tests/test_registration_hook_runtime_c.py
engine/tests/test_registration_host_c.py
engine/tests/test_registration_independence_c.py
engine/tests/test_registration_installer_c.py
engine/tests/test_registration_launcher_c.py
engine/tests/test_registration_packaging_c.py
engine/tests/test_registration_projection_c.py
engine/tests/test_registration_receiver_c.py
install.sh
kernel/bin/awa-registration-receiver.sh
kernel/bin/awa-registration-tick.sh
kernel/checks/awa-contract-freeze.sh
kernel/hooks/awa-registration-admission.sh
kernel/hooks/awa-registration-startup.sh
live-verify/native-entry-durable-registration-r0.py
```

V7 acceptance changes none of these bytes. A later C-RUNTIME implementer must
produce a per-path preserve/reuse/supersede report; it may port only after the
gate names this manifest. No blanket application is permitted.

---

## 3. Public source authority and deterministic private runtime

### 3.1 Exact source lock

Plan acceptance binds only the public upstream source pin below and this
architecture. `build/private-runtime/sources.lock.json` must be exactly these
JCS+LF bytes:

```json
{"artifact_name":"cpython-3.14.8+20261003-aarch64-apple-darwin-install_only.tar.gz","artifact_sha256":"d15291f940cfecd2e54010d5e37d2e03aa192f076a65d26ab741372fff2dabfe","artifact_size":26798928,"artifact_url":"https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.14.8%2B20261003-aarch64-apple-darwin-install_only.tar.gz","attestation_build_type":"https://actions.github.io/buildtypes/workflow/v1","attestation_builder_id":"https://github.com/astral-sh/python-build-standalone/.github/workflows/release.yml@refs/heads/main","attestation_bundle_jcs_lf_sha256":"71ee6bcb100ad2474d01dce968125fa631f2e28616c21ddf67364d2ef7ca94d3","attestation_bundle_jcs_lf_size":222485,"attestation_bundle_media_type":"application/vnd.dev.sigstore.bundle.v0.3+json","attestation_certificate_issuer":"CN=sigstore-intermediate,O=sigstore.dev","attestation_certificate_sha256":"d522acb7449a9df10fa7de091d41d3b446eac4cf66e659db9ce04051b160d6e4","attestation_certificate_size":1926,"attestation_event_name":"workflow_dispatch","attestation_oidc_issuer":"https://token.actions.githubusercontent.com","attestation_payload_sha256":"82c1743abde7af6fe24ebc5e06b45cc653af68fad4b0ef1fcb7b2ea20179e0ce","attestation_payload_size":159656,"attestation_payload_type":"application/vnd.in-toto+json","attestation_predicate_type":"https://slsa.dev/provenance/v1","attestation_rejected_predicate_types":["https://in-toto.io/attestation/release/v0.2"],"attestation_run_invocation":"https://github.com/astral-sh/python-build-standalone/actions/runs/37118919715/attempts/1","attestation_selection_rule":"EXACTLY_ONE_MATCHING_SLSA_PROVENANCE_V1","attestation_subject_count":896,"attestation_subject_name":"cpython-3.14.8-aarch64-apple-darwin-install_only-20261002T2049.tar.gz","attestation_subject_sha256":"d15291f940cfecd2e54010d5e37d2e03aa192f076a65d26ab741372fff2dabfe","attestation_workflow_name":"Release","attestation_workflow_path":".github/workflows/release.yml","attestation_workflow_ref":"refs/heads/main","attestation_workflow_repository":"https://github.com/astral-sh/python-build-standalone","attestation_workflow_sha":"5e46737f6480fc315ebfea83866910cbfcc772f0","build_features":["pgo","lto"],"full_build_archive_name":"cpython-3.14.8+20261003-aarch64-apple-darwin-pgo+lto-full.tar.zst","full_build_archive_sha256":"6bb6e246d6c2bdfef5b33e833541c232d99afb37b67a08872f233649f4b64ca7","full_build_archive_size":61659605,"full_build_archive_url":"https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.14.8%2B20261003-aarch64-apple-darwin-pgo%2Blto-full.tar.zst","github_attestation_repository":"astral-sh/python-build-standalone","metadata_schema":8,"openssl_version":"3.5.9","python_json_path":"python/PYTHON.json","python_json_sha256":"f05da8e52bc798b76f0076589925008695029b1c910793decf9b42246088bd78","python_json_size":136799,"python_json_terminal_lf":false,"python_version":"3.14.8","schema":"awa-private-runtime-source-lock/v1","sha256sums_artifact_line":"d15291f940cfecd2e54010d5e37d2e03aa192f076a65d26ab741372fff2dabfe  cpython-3.14.8+20261003-aarch64-apple-darwin-install_only.tar.gz","sha256sums_name":"SHA256SUMS","sha256sums_sha256":"d629718db5cfecb28494e6ba83386ee9a1205975493f904392dac2e3fe5f8813","sha256sums_size":128236,"sha256sums_url":"https://github.com/astral-sh/python-build-standalone/releases/download/20261003/SHA256SUMS","sqlite_version":"3.53.1","target_triple":"aarch64-apple-darwin","upstream_published_at":"2026-10-03T14:56:28Z","upstream_release":"20261003","upstream_release_commit":"5e46737f6480fc315ebfea83866910cbfcc772f0","upstream_repository":"astral-sh/python-build-standalone"}
```

SHA-256:

```text
a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72
```

Arrays retain displayed order; object keys are UTF-8 bytewise sorted by JCS.
There is no BOM, CR, insignificant whitespace, or extra LF. The GitHub
attestation selector queries the exact artifact digest, decodes every DSSE
payload, filters the exact SLSA-v1 predicate and frozen issuer/workflow/
subject identity above, and requires exactly one match. Zero or multiple
matches fail closed. The observed release-v0.2 record is never authority.
The selected bundle authority is exactly `JCS(bundle)||LF`, size `222485`,
SHA-256 `71ee6bcb100ad2474d01dce968125fa631f2e28616c21ddf67364d2ef7ca94d3`.
Independent validators must reproduce it. The named 61,659,605-byte full
build archive—not an undefined “provenance companion”—contains exact raw
`python/PYTHON.json` bytes of size 136,799 and the displayed hash.

### 3.2 Build and normalization algorithm

The local, runnerless build:

1. downloads only the exact named URLs, checks every size and SHA-256,
   deterministically selects and verifies the exact SLSA-v1 GitHub attestation,
   rejects release-v0.2 as authority, and checks the full build archive,
   `SHA256SUMS` line, and raw `python/PYTHON.json`;
2. extracts into a fresh private root with no symlink/hardlink/device/path
   traversal and an exact archive-entry allowlist;
3. normalizes ownership-independent metadata, removes disallowed files, and
   emits one sorted full payload manifest;
4. removes each existing Mach-O signature, then invokes fixed
   `/usr/bin/codesign` with
   `--force --sign - --timestamp=none --identifier
   org.awa.runtime.<sha256(relative UTF-8 path)>`, in descending path depth
   then UTF-8 path order;
5. emits capability, compile-options, signature-inventory, SBOM/license,
   manifest, transcript, and canonical archive records; and
6. repeats in a second clean root and requires byte-identical outputs.

The qualification toolchain is codesign project `codesign-83.100.6`, exact
`/usr/bin/codesign` SHA-256
`3635f18db517033a4786ea7ddb0acc1801e642eaf6171e208e24cb9a1922f518`,
CLT `27.0.0.0.1788430756`, and SDK `27.0`. Any mismatch stops. Build scripts,
normalizer source, and signing-recipe source become exact-head qualification
preimages; this draft does not fabricate their future hashes.

Manifest records are sorted by relative-path UTF-8 bytes and have exactly
`path,mode,size,sha256,macho`. For every entry:

```text
mode = format(stat.S_IMODE(lstat(path).st_mode), "03o")
record_bytes =
  UTF8(path) || 0x00 || ASCII(mode) || 0x00 ||
  ASCII(decimal_size) || 0x00 || ASCII(lowercase_sha256) || 0x00 ||
  ASCII("0" | "1") || LF
```

Every manifest object is a regular file with `st_nlink == 1`; no symlink is
accepted anywhere in the archive or installed closure. Directory enumeration
and record order are UTF-8 bytewise. The object manifest uses JCS+LF and also
binds the record-framing digest.

### 3.3 Capability and dependency authority

`awa-registration-python-capability/v1` has exactly the accepted-v5 23 keys:

```text
schema,platform,os_build,python_implementation,python_version,
required_python_apis,sqlite_runtime_version,sqlite_source_id,
sqlite_compile_options_hash,sqlite_vfs_name,journal_mode,synchronous,
fullfsync,checkpoint_fullfsync,foreign_keys,
connection_setconfig_available,sqlite_dbconfig_defensive_available,
defensive,trusted_schema,locking_mode,nofollow_available,
checkpoint_on_close,probe_program_hash
```

`required_python_apis` is exactly this bytewise-sorted array:

```text
fcntl.flock
os.O_NOFOLLOW
os.fstat
sqlite3.Connection.setconfig
sqlite3.SQLITE_DBCONFIG_DEFENSIVE
sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE
```

Exact accepted-v5 value semantics are:

```text
schema="awa-registration-python-capability/v1"
platform="darwin"
os_build=<nonempty exact probe string, at most 128 UTF-8 bytes>
python_implementation="CPython"
python_version="3.14.8"
required_python_apis=<exact array above>
sqlite_runtime_version="3.53.1"
sqlite_source_id=<nonempty exact probe string, at most 512 UTF-8 bytes>
sqlite_compile_options_hash=<compile-options object digest>
sqlite_vfs_name="unix"
journal_mode="wal"
synchronous="full"
fullfsync=true
checkpoint_fullfsync=true
foreign_keys=true
connection_setconfig_available=true
sqlite_dbconfig_defensive_available=true
defensive=true
trusted_schema=false
locking_mode="normal"
nofollow_available=true
checkpoint_on_close=false
probe_program_hash=<exact qualification probe source digest>
```

The private runtime also reports OpenSSL `3.5.9` in build metadata, not as a
24th capability key. `THREADSAFE=1` may appear only in the distinct
`awa-registration-sqlite-compile-options/v1` sorted `options` array; no
`threadsafe` capability field exists. That array contains distinct exact
SQLite strings, includes `ENABLE_FTS5` and exactly one `THREADSAFE=1`, and
contains no other `THREADSAFE` value; both independent builds must emit the
same complete array and digest.

The build and launcher call one canonical measurement implementation. It
opens and retains the selected Python descriptor, verifies root ancestry and
the manifest, acquires the version shared lock, and derives capability,
compile-options, and executable records internally. The capability probe is
the hash-bound private Python invoked with `-I -S -B` and a fixed environment;
it imports only standard-library capability modules, uses only in-memory or
private throwaway SQLite, emits exact JCS+LF, and performs no product write.
No caller-supplied capability object is trusted.

The one source is `kernel/bin/awa-registration-bootstrap.py`, a stdlib-only
program with no `engine` import. Installation copies those exact bytes to
`/Library/Application Support/AWA/bootstrap/v1/bootstrap.py`; both hashes are
bound by the AWA/install manifests. Build tooling and the unprivileged
installer execute its bounded measurement subcommand as a subprocess rather
than reimplementing or caller-populating records. Normal launch executes the
installed copy directly under platform Python. The fixed probe source is an
exact constant in that file and its digest is emitted in capability authority.

The measurement protocol performs pre-probe `fstat`, probes while retaining
the executable/version descriptors and kqueues, performs full post-probe
`fstat`, reopens/revalidates every visible path and ancestor, and checks the
active `current.v1` record before accepting. It closes every descriptor in a
deterministic all-close cleanup that preserves the primary error and records
secondary cleanup errors. Bounded tests swap at measurement→probe, during
probe, probe→config/build, and probe→import, including persistent and
swap-back variants; every mismatch fails closed.

Only private-root, `/System/Library`, and `/usr/lib` images are allowed.
Relocation under two roots and loaded-image evidence are qualification packet
inputs. Rpaths or images outside those roots stop.

### 3.4 Non-authoritative feasibility evidence

Two prior disposable builds established feasibility: 12 Mach-O files passed
strict codesign; 837 payload records were byte-identical; two relocation
roots each loaded 350 images with zero dependency escape; registration tests
were 264/264; `make verify-pre-pr` reported 1694 pass/15 skip; parent-death
and zero-pre-GO-import prototypes passed, including inert pre-watchdog
persistence/reconciliation rather than atomic termination; and no owner
private key was used.

The following prior throwaway values are explicitly **non-authoritative** and
must not appear in the source lock, plan-acceptance envelope, release
authority, or readiness evidence unless independently regenerated from the
exact implementation head:

```text
normalizer dfe895bbd86cf1701bfb92ece40e11dc7e4d7471aa37c96bb5b4b7667be76b79
signing recipe b385d454ea6eee6264069cf7e8380f000f31238ec5e077d6345f6a54f5ead603
signature inventory 5eaaec5ebc55ae38fd10a763babdcb788cb893580d7182b52231e59798c2b489
manifest eb9dd875a35d2971480093fbaf219bb8e15f650bbda02097fc8c983d023c96fd
build transcript 09cbbe44eb16044e9a5fdcd1c4eb3c8ef02e6d7fbe9ca5d487bf9620c330715d
archive 3cc80580833f45f56872b0dbdc0e37b50403bab5becbb0c4bddc7481ca56f257
archive size 99450880
capability 4d966501227b5b8806ef7df7fb3132510764c90c387ee917886487fd4d9af5aa
compile options 097c868c0aa49a7efec117d137bbfd7749573f0be75ad8368131b107636f5e9e
```

Generated archives, manifests, SBOM/license bundles, transcripts, packets,
and owner signatures are future release/qualification assets, never committed
blobs. GitHub Actions runners remain prohibited; PR verification checks code,
contracts, deterministic fixtures, and synthetic keys.

The later release asset set is exactly:

```text
awa-private-runtime-<manifest_sha256>.tar.gz
awa-private-runtime-<manifest_sha256>.manifest.json
awa-private-runtime-<manifest_sha256>.signature-inventory.json
awa-private-runtime-<manifest_sha256>.sbom.spdx.json
awa-private-runtime-<manifest_sha256>.licenses.tar
awa-private-runtime-<manifest_sha256>.build-transcript.jsonl
awa-private-runtime-<manifest_sha256>.release-envelope.json
awa-private-runtime-<manifest_sha256>.release-envelope.sig
awa-private-runtime-sources.lock.json
```

Every name is derived only after qualification creates
`manifest_sha256`. The owner signature is produced externally only at its
later signing gate. The committed source lock is copied byte-for-byte into
the named release asset; no generated archive or evidence blob is committed.

---

## 4. Installed closure and pre-import execution protocol

### 4.1 Fixed installed paths and filesystem authority

```text
/Library/Application Support/AWA/bin/awa-registration
/Library/Application Support/AWA/bin/awa-private-runtime-admin
/Library/Application Support/AWA/bootstrap/v1/bootstrap.py
/Library/Application Support/AWA/bootstrap/v1/child.py
/Library/Application Support/AWA/runtime/versions/<manifest-sha256>/
/Library/Application Support/AWA/runtime/current.v1
```

All installed objects and ancestors are root:wheel, directories `0755`,
executables/bootstrap `0555`, and data/manifests/licenses `0444`. Trusted
regular files have `st_nlink == 1`; the closure contains no symlinks and no
group/other writable component. `current.v1` is a canonical regular JCS+LF
file, never a symlink. A version directory is immutable after no-replace
publication.

The active lock path is
`/Library/Application Support/AWA/runtime/locks/<manifest_sha256>.lock`.
Every launcher acquires and retains a shared lock before selection; the admin
path requires the exclusive lock before rollback/removal. A selected or active
version is never mutated or removed. At most the active and one previous
version remain.

### 4.2 Wrapper and parent boundary

All admission, receiver, startup, and tick wrappers invoke only absolute
`/Library/Application Support/AWA/bin/awa-registration` plus one closed route
token. The untrusted `~/dev` overlay does no runtime selection or verification.
Skills remains a release-descriptor pointer; cpp receives no runtime bytes or
duplicated authority.

The root-owned entrypoint contains no product import. It executes exactly:

```text
/usr/bin/env -i LANG=C LC_ALL=C PATH=/usr/bin:/bin \
  /usr/bin/python3 -I -S -B \
  "/Library/Application Support/AWA/bootstrap/v1/bootstrap.py" <route>
```

Before importing any AWA product module, the standard-library parent:

1. validates its own absolute platform interpreter, entrypoint, bootstrap,
   child bootstrap, root ownership/modes/links, and every ancestor;
2. verifies static contract and AWA bundle owner signatures through fixed
   `/usr/bin/ssh-keygen`;
3. opens and retains `current.v1`, the selected version, runtime/AWA manifests,
   exact private Python, child bootstrap, and bundle files; acquires the shared
   active-version lock and kqueues every visible identity;
4. runs the common capability measurement from §3.3 and rebinds all paths;
5. creates a nonce-bound control socket and authority descriptors; and
6. invokes ordinary `posix_spawn` for the actual private
   `Python.app/Contents/MacOS/Python` with only
   `POSIX_SPAWN_CLOEXEC_DEFAULT`.

Platform Python imports no `engine.*`, opens no registration SQLite, and
never computes product state. Config-v1/external-interpreter authority is
refused before product import; there is no compatibility fallback.

### 4.3 Descriptor and spawn rules

Fixed child targets are control fd `3` and authority fds `4,5,6,7,8`.
Before file actions, every source descriptor is duplicated with
`F_DUPFD_CLOEXEC` to a collision-free fd `>=10`. File actions `dup2` those
high sources to the fixed targets. Fixed targets are never closed. Every
high source and unrelated descriptor is explicitly closed in parent and child
according to ownership after spawn. Failure to enumerate, duplicate, map, or
close is fatal.

Spawn argv is exactly:

```text
<verified-private-python-absolute-path>
-I
-S
-B
/Library/Application Support/AWA/bootstrap/v1/child.py
--route
<admission|receiver|startup|tick>
--expected-parent-pid
<unsigned-decimal-parent-pid>
--nonce
<64-lowercase-hex>
```

The same nonce is the generated value of
`AWA_REGISTRATION_SPAWN_NONCE`; argv and environment must agree exactly.
No config or product path appears in argv. FD 4 carries the exact runtime
manifest, fd 5 the AWA import manifest, fd 6 the signed release/owner-gate
authority, fd 7 the canonical current record, and fd 8 the route-bound launch
record; each is a retained regular-file descriptor whose JCS+LF bytes were
already verified by the parent. The child revalidates those exact bytes.

The environment is rebuilt, not inherited:
`LANG=C`, `LC_ALL=C`, `PATH=/usr/bin:/bin`, and the generated
`AWA_REGISTRATION_SPAWN_NONCE=<64-lowercase-hex>`; all other `PYTHON*`,
`DYLD*`, user-controlled locale/PATH, cwd authority, site customization, and
external rpaths are absent. Python and every helper path are absolute.

Deterministic tests cover source already at each target, target occupied,
source/target cycles, duplicate sources, low/high collisions, `EMFILE`,
partial file-action construction, spawn failure, parent-close failure,
child-close failure, and unexpected inherited descriptors. No test may
special-case the expected ordering.

### 4.4 Parent-death, durable spawn intent, and import barriers

Before spawn, the parent writes, file-fsyncs, atomically publishes, and
parent-directory-fsyncs one canonical `awa-registration-spawn-intent/v1`
`PREPARED` record. Its exact fields are defined in §6.7 and bind nonce, route,
private executable path/hash, runtime version/manifest, shared-lock identity,
parent PID/pidversion, boot identity, and null child/mapped identity.
The directory is derived without environment input as
`<getpwuid(uid).pw_dir>/.local/share/awa/registration-runtime/spawn-intents/v1`,
must be an invoking-UID-owned `0700` no-symlink ancestry, and each nonce-named
record is a regular nlink-one `0600` file. User tampering can only cause
refusal, never grant launch authority.
Only after that durable record exists may `posix_spawn` run. After return, the
parent atomically advances the same record to `SPAWNED` with child PID,
pidversion, and mapped identity when observable. Parent death before this
second publication is recoverable by nonce scan because the nonce is already
in child argv and environment.

The child startup sequence is:

1. execute only the owner-authorized private Python, its startup/stdlib, and
   the installed child bootstrap;
2. parse fixed authority fds, expected parent PID, route, and nonce;
3. require `getppid() == expected_parent_pid`;
4. arm a dedicated control-EOF watchdog whose only terminal action before
   normal completion is immediate `_exit`;
5. require the parent PID again;
6. verify retained authority descriptors and emit nonce-bound `READY`;
7. block reading the control fd without importing AWA product code;
8. on exact `GO`, recheck parent PID, descriptors, manifests, lock identity,
   nonce, and control liveness;
9. emit `IMPORT_READY`; then and only then perform the first product import.

The original parent retains its control fd for the child lifetime. While its
direct parent-child relationship and retained process identity remain
continuous, that supervising parent alone may signal and reap its direct
child. After the watchdog arms, EOF, PID mismatch,
timeout, duplicate/out-of-order/replayed nonce, kqueue event, current-pointer
change, descriptor drift, malformed output, or child/parent death kills the
direct child and reports refusal. This authority never transfers to a later
process. After `READY`, the parent checks the mapped vnode and CDHash as
supplemental evidence, rechecks all retained descriptors/events/`current.v1`,
then sends `GO`.

Darwin has no atomic parent-death guarantee between `posix_spawn` and watchdog
arm. If the parent dies there, the child may remain stopped in inert,
owner-authorized Python/stdlib/child-bootstrap code. It can never receive
`GO`, import AWA product code, or be adopted for continuation. Every admission,
receiver, startup, and tick entry reconciles spawn intents before normal work:

1. load at most 64 nonterminal records without rewriting, pruning, signalling,
   or enumerating children; refuse on overflow, malformed records, unknown
   residue, or an unreadable/unstable record;
2. classify the recorded parent first. Read
   `proc_pidinfo(PROC_PIDTBSDINFO)` twice around parent path/start/UID checks
   and compare the recorded PID plus exact `pidversion`. The only states are
   `EXACT_LIVE`, `ABSENT`, `ZOMBIE`, `PIDVERSION_MISMATCH`, and `AMBIGUOUS`.
   Permission errors, short reads, unavailable start identity, changing
   observations, or any unclassified state are `AMBIGUOUS` and refuse without
   touching the intent or any process;
3. for `EXACT_LIVE`, perform only read-only coherence checks. `PREPARED` may
   have no published child or one exact nonce-bound child in flight.
   `SPAWNED|READY|GO|PRODUCT` requires exactly one child whose PID/pidversion,
   PPID, nonce argv/environment, private executable, mapped vnode, and route
   equal the intent. A coherent healthy pair—including authorized product
   execution—is left byte-for-byte and process-for-process untouched. A
   forged relation, duplicate child, or incoherence refuses without mutation.
   This invocation never changes from the live-parent branch to an
   absent-parent conclusion if the parent exits during its scan; watchdog/EOF
   or a later entry observes that transition;
4. for `ABSENT`, `ZOMBIE`, or `PIDVERSION_MISMATCH`, enumerate only the
   invoking UID through fixed
   `proc_listpids(PROC_UID_ONLY)`, inspect
   `proc_pidinfo(PROC_PIDTBSDINFO)` including PID, UID, and
   `pbi_start_tvsec/pbi_start_tvusec`,
   `proc_pidpath`, bounded
   `proc_pidinfo(PROC_PIDREGIONPATHINFO)` for mapped vnode identity,
   `sysctl(KERN_PROCARGS2)`, and
   supplemental `csops(CS_OPS_CDHASH)`;
5. observation is the reconciler's only process action. It never calls
   `kill`, `pkill`, `proc_terminate`, `posix_spawn`, or another signal,
   adoption, continuation, or process-control API. Exactly one stable nonce +
   absolute private executable + mapped vnode + PID-version +
   recorded-parent relation match is a `CONFIRMED_INERT_CANDIDATE`; missing,
   partial, duplicated, changing, unreadable, forged, or PID-reuse-uncertain
   identity is `AMBIGUOUS_RESIDUE`. Both leave every process and nonterminal
   record untouched and refuse all new AWA product work;
6. for a `CONFIRMED_INERT_CANDIDATE`, the reconciler may observe for exactly
   5,000 milliseconds, polling the fixed read-only APIs no more frequently
   than every 100 milliseconds. If the candidate disappears naturally,
   reopen/re-hash the unchanged intent, reclassify the parent, and require a
   complete nonce scan with no current-boot match before atomically recording
   `NATURAL_EXIT_RECONCILED`, fsyncing the record and parent directory, and
   continuing. Any changed, replacement, ambiguous, or persistent result
   leaves the record untouched and refuses; and
7. refusal emits one exact plain message. A confirmed persistent candidate
   says: `Interrupted AWA bootstrap residue was detected. AWA remains inactive.
   Wait for the process to exit or restart the Mac.` Ambiguous, unreadable,
   forged, duplicate, stale, or PID-reuse-uncertain state says: `AWA found
   ambiguous interrupted-bootstrap state. AWA remains inactive. Restart the
   Mac before trying again.` No message claims process termination or bounded
   cleanup.

Darwin exposes no `pbi_pidversion` field. V7's exact lowercase-hex
`pidversion` is therefore:

```text
SHA256(
  ASCII("awa-darwin-pidversion/v1") || 0x00 ||
  ASCII(decimal_pid) || 0x00 ||
  ASCII(decimal_pbi_start_tvsec) || 0x00 ||
  ASCII(decimal_pbi_start_tvusec) || 0x00 ||
  ASCII(boot_identity)
)
```

If either start-time component is unavailable, pidversion is JSON null and an
otherwise exact match remains ambiguous/refused.

`PREPARED` records with no published PID use the same nonce scan. Nonterminal
records are never age-pruned. Terminal records are retained for seven days,
then oldest-first pruned while keeping at most 64; every rewrite and deletion
is fsynced. From fixed `sysctlbyname("kern.boottime")`:

```text
boot_identity =
  SHA256(ASCII("awa-darwin-boot-identity/v1") || 0x00 ||
         ASCII(decimal_tv_sec) || 0x00 || ASCII(decimal_tv_usec))
```

A verified changed boot identity proves prior-boot PIDs cannot survive. Only
after rereading the prior-boot record, confirming the current boot differs,
and confirming no current-boot record or process matches its nonce may the
reconciler archive it and publish `REBOOT_CLEARED`. A same-boot record is
never cleared merely because its PID is absent. Reboot is the guaranteed
cleanup boundary.
No new daemon or launchd job is added. If later host activation wires existing
startup/tick launchd entry, it invokes this same reconciliation first. With no
next entry, one inert private-Python/bootstrap process may persist until
natural exit or reboot; there is intentionally no zero-orphan or bounded
process-cleanup claim.

Tests deterministically run concurrent routes against PREPARED, SPAWNED,
READY, GO, and authorized PRODUCT phases and prove an exact live
parent/child pair is untouched. They also SIGSTOP/stall before watchdog arm,
kill the parent before PID publication and at every barrier, force parent exit
during each scan/recheck, and cover observation-only no-signal proof, natural
exit, persistent residue/refusal, child death, timeout, EOF, replay/order,
kqueue/current drift, A↔B probe/import swaps, parent and child PID reuse,
forged relations/nonces, ambiguous/unreadable parent identity, multiple
children, same-boot refusal, no-next-invocation persistence, and verified
new-boot clearance. A syscall spy asserts that every later reconciler issues
zero kill/signal/process-control calls. Process-spy/import-trace proves zero
pre-GO AWA import. This narrow rule supersedes any inherited unconditional
no-orphan or later-process cleanup wording while preserving the actual safety
invariant: no unauthorized product import and no interference with another
live supervised route.

---

## 5. Privileged lifecycle

### 5.1 Initial pathless bootstrap

The unprivileged client creates exact request assets under fixed names derived
from decimal UID and a 64-character lowercase-hex request ID:

```text
/private/var/tmp/awa-private-runtime-envelope-<uid>-<request_id>.json
/private/var/tmp/awa-private-runtime-envelope-<uid>-<request_id>.json.archive
/private/var/tmp/awa-private-runtime-envelope-<uid>-<request_id>.json.manifest.json
/private/var/tmp/awa-private-runtime-envelope-<uid>-<request_id>.json.sig
```

All are user-owned regular files, mode `0600`, link count one. No path is
accepted from argv or envelope content.

Initial install executes fixed `/usr/bin/osascript` with one generated
AppleScript `-e` source and variable argv limited to `<decimal_uid>` and
`<64_lower_hex_request_id>`. Let:

```text
B = exact reviewed UTF-8/LF inline-bootstrap source bytes
E = RFC4648_BASE64(B), with no whitespace
P = ASCII("import base64;exec(compile(base64.b64decode('") ||
    E ||
    ASCII("'),'<awa-inline-bootstrap>','exec'))")
SQ(x) = ASCII("'") || replace(x, ASCII("'"), ASCII("'\"'\"'")) || ASCII("'")
```

`B` and the resulting AppleScript/template bytes are C-RUNTIME exact-head
qualification preimages, not plan-acceptance preimages. The AppleScript source
is generated from exactly:

```applescript
on run argv
  if (count of argv) is not 2 then error "AWA_ARGV_REFUSED" number 1708
  set uidText to item 1 of argv
  set requestText to item 2 of argv
  set pyCode to "<P>"
  set commandText to "/usr/bin/env -i LANG=C LC_ALL=C /usr/bin/python3 -I -S -B -c " & quoted form of pyCode & " " & quoted form of uidText & " " & quoted form of requestText
  try
    do shell script commandText with administrator privileges
  on error errorMessage number errorNumber
    if errorNumber is -128 then error "AWA_AUTH_CANCELLED" number 1708
    error "AWA_AUTH_FAILED" number 1708
  end try
end run
```

`<P>` means the AppleScript-literal encoding of exact `P`: backslash becomes
`\\`, double quote becomes `\"`, and no other byte is transformed; `P` is
ASCII and contains neither CR nor NUL. Tests require AppleScript `quoted form
of` output to equal `SQ` above byte-for-byte. Invocation is exactly:

```text
/usr/bin/osascript -l AppleScript -e <INITIAL_SCRIPT> -- <uid> <request_id>
```

The resulting shell argv is exactly:

```text
/usr/bin/env -i LANG=C LC_ALL=C /usr/bin/python3 -I -S -B -c P uid request_id
```

No path, operation, password, TTY, shell fragment, environment value, or
arbitrary argument is caller-controlled. SecurityAgent owns authentication;
AWA never receives, stores, logs, or forwards a credential. Cancellation and
authentication failure are distinct fixed non-success results and authorize
no write.

Before any native prompt, the exact-head implementation runs one pure
`validate_privileged_request` path over production-prefix, cross-nonce/root,
owner-namespace, malformed-field, expiry, signature-shape, and packet/context
mismatch vectors. The pure validator accepts already-captured bytes and scalar
facts and returns only canonical `ALLOW|REFUSE` data. Its test process denies
write-capable `open`, `chmod/chown`, `mkdir`, `rename/link/unlink`, `fsync`,
`fork/exec/posix_spawn`, `kill`, AppleScript/SecurityAgent, and every
privileged syscall; any attempted dispatch fails the test. Path-remapped
temporary-directory harnesses may exercise extraction/state transitions, but
never a production or alternate `/Library/Application Support` root. These
pre-prompt tests and their syscall-denial trace are packet evidence.

Running as root, `B` validates the two arguments again, derives all four paths,
opens each with `O_NOFOLLOW`, and retains descriptors. It requires regular
file/link-count-one/request-UID/mode/size bounds; stable pre/post `fstat`;
visible-path and ancestor rebind; and no kqueue event. It reads each retained
descriptor once into bounded memory, uses only those bytes thereafter,
verifies the owner signature via fixed `/usr/bin/ssh-keygen`, validates the
release envelope, archive, manifest, source lock, and every extraction record,
then stages under the fixed target root.

Before any write, `B` makes one structural mode decision. `PRODUCTION`
requires the static owner-signers-v2 contract, production namespace, and
target exactly `/Library/Application Support/AWA`; any qualification contract
or namespace refuses. `QUALIFY` requires the exact dynamic
`awa-registration-qualification-allowed-signers/v1` contract from §6.7,
operation `QUALIFY`, and target exactly
`/Library/Application Support/AWA-qualification-<bound qualification_nonce>`;
any owner namespace, production target/prefix, cross-nonce root, Q1/Q2 digest
mismatch, exact-head mismatch, or packet-root mismatch refuses before writes.
There is no mode inference from a path and no fallback between trust anchors.
The qualification root process is constructed with only the one bound root;
it checks equality again before syscall dispatch and exits on mismatch.
`PRIVILEGED-QUALIFICATION GO` authorizes no invocation—positive or
negative—against production, a second nonce/root, or any other root. Rejection
behavior for those inputs is established only by the pure/path-remapped
pre-prompt tests above.

Extraction rejects absolute/empty/dot/dot-dot/NUL/non-UTF-8/duplicate/case-
collision paths, links, devices, FIFOs, sockets, extra records, mode drift,
size drift, and hash drift. Publication uses same-filesystem staging, file and
directory fsync, reopen/revalidation, and atomic no-replace publication.
The root admin entrypoint is installed last. A crash before that point leaves
no callable privileged admin path; recovery recognizes only signed,
request-bound residue.

### 5.2 Update, rollback, and removal

After initial install, the client uses only immutable root-owned:

```text
/Library/Application Support/AWA/bin/awa-private-runtime-admin
```

The AppleScript template has the same fixed error handler and constructs:

```applescript
on run argv
  if (count of argv) is not 3 then error "AWA_ARGV_REFUSED" number 1708
  set operationText to item 1 of argv
  set uidText to item 2 of argv
  set requestText to item 3 of argv
  set adminPath to "/Library/Application Support/AWA/bin/awa-private-runtime-admin"
  set commandText to "/usr/bin/env -i LANG=C LC_ALL=C " & quoted form of adminPath & " " & quoted form of operationText & " " & quoted form of uidText & " " & quoted form of requestText
  try
    do shell script commandText with administrator privileges
  on error errorMessage number errorNumber
    if errorNumber is -128 then error "AWA_AUTH_CANCELLED" number 1708
    error "AWA_AUTH_FAILED" number 1708
  end try
end run
```

Its exact parsed command is:

```text
/usr/bin/env -i LANG=C LC_ALL=C \
  '/Library/Application Support/AWA/bin/awa-private-runtime-admin' \
  SQ(operation) SQ(uid) SQ(request_id)
```

Invocation is exactly:

```text
/usr/bin/osascript -l AppleScript -e <ADMIN_SCRIPT> -- \
  <INSTALL|UPDATE|ROLLBACK|REMOVE|QUALIFY> <uid> <request_id>
```

The operation must be one exact enum token; UID/request rules are unchanged.
The root admin re-derives and retained-opens request assets, redoes every
owner-signature/manifest/race check before writes, and never trusts a caller
path or detached capability. The displayed immutable absolute admin path and
AppleScript are production-only. Inside the one already-authorized QUALIFY
root process, later steps execute retained
`<qualification_root>/bin/awa-private-runtime-admin` bytes directly as root;
no second shell, AppleScript, prompt, or caller-supplied path is used.

The state machine is:

```text
ABSENT --INSTALL(epoch=1)--> ACTIVE
ACTIVE --UPDATE(epoch+1,new manifest)--> ACTIVE
ACTIVE --ROLLBACK(epoch+1,retained previous)--> ACTIVE
ACTIVE --REMOVE(epoch+1)--> REMOVED
```

`current.v1` carries a strictly increasing epoch and predecessor digest.
Version publication is no-replace; current publication is temp-write,
file-fsync, parent-fsync, atomic replace, reopen/revalidate, parent-fsync.
Update retains active plus one previous version. Rollback can select only that
signed previous version. Admin takes the exclusive version lock before
retirement and refuses while any launcher holds it. Unknown residue, epoch
ambiguity, stale request, missing predecessor, or partial audit state refuses.
Recovery rolls forward only an exact signed, request-bound terminal step; it
never infers success.

Every terminal attempt emits a canonical audit receipt under §6.5. Root
closes all descriptors, drops all temporary state, and exits. REMOVE retires
product paths first and the root admin entrypoint last. There is no daemon,
setuid helper, sudo/password fallback, Developer ID assumption, arbitrary
shell/path argument, or root process after completion.

### 5.3 Same-user races and failure semantics

The requesting user can rewrite a path it owns, so path stability alone is
not authority. Root operates only on bytes read from retained descriptors
whose pre/post metadata and event state agree; all derived digests and
extraction use those captured bytes. A same-user rewrite during read,
signature verification, extraction, staging, or publication trips size/
metadata/event/rebind checks and refuses. Reusing a request ID, mixing sibling
assets, swapping then restoring, or changing owner/mode/link count refuses.

`CANCELLED`, `REFUSED`, `FAILED`, and `SUCCESS` are disjoint. A client-side
SecurityAgent cancellation has a canonical `CLIENT_AUTH` evidence receipt,
never a fabricated root receipt, and is never success. Once root starts, every
terminal result attempts a `ROOT_ADMIN` audit receipt; receipt failure prevents
success. Cleanup attempts all closes/removals, preserves the primary error,
and reports secondary failures without converting refusal to success.

### 5.4 Exact operation/outcome matrix

Every privileged request and audit uses the fields and enums in §§6.5–6.7.
There are no empty-string, all-zero, or sentinel hashes: absence is JSON
`null`. In the matrix below:

- `R` = required non-null and valid for the field domain;
- `N` = exact JCS `null`;
- `T` = operation target triple
  `target_release_envelope_digest,target_manifest_sha256,target_epoch`;
- `P` = result pointer triple
  `previous_manifest_sha256,current_manifest_sha256,new_manifest_sha256`;
- `Q` = qualification tuple
  `qualification_context_digest,qualification_allowed_signers_digest,
  q1_envelope_digest,q1_manifest_sha256,q2_envelope_digest,
  q2_manifest_sha256`;
- `L` = receipt links
  `predecessor_audit_digest,root_receipt_link_digest`;
- `PARTIAL` means `current_manifest_sha256` is required only when
  `partial_stage_state == "CURRENT_PUBLISHED"` and otherwise null; the other
  two `P` values retain the request-defined pre/target values stated below.

`schema`, request/UID/root/mode/operation, `packet_root_digest`,
`envelope_sha256`, origin/terminal/outcome/reason, and both timestamps are
`R` in every audit. Production records require
`owner_signature_sha256` and set `synthetic_signature_sha256`, both
qualification digests, and every `Q` field to null. QUALIFY parent/child
records invert that rule: owner signature is null; synthetic signature,
qualification context/allowed-signers, and every `Q` field are required.
Root-started records require both installed/removed path hashes, including the
digest of an empty list; cancelled records set both null.

For `CANCELLED`, origin is `CLIENT_AUTH`, terminal is `NO_ROOT_PROCESS`,
post epoch, installed/removed paths, `L`, partial stage, and cleanup are `N`;
the applicable owner/synthetic request signature and all target/request
preconditions remain copied exactly.
For every root-started result origin is `ROOT_ADMIN`, terminal is `R`,
partial state and cleanup digest are `R`, and `L` is `R` except the first
record's predecessor is `N`. `root_receipt_link_digest` binds the production
request or parent QUALIFY request. `pre_epoch` is `"0"` for INSTALL/QUALIFY and
required from current state for UPDATE/ROLLBACK/REMOVE. Qualification child
audits use their actual operation row, mode QUALIFY, and therefore require
`Q`; the QUALIFY row is the parent orchestration receipt.

| operation/outcome | pre current | T | P | Q | reason | post epoch | partial/cleanup |
|---|---:|---:|---:|---:|---|---:|---|
| INSTALL/SUCCESS | N | R | `N,R,R` | N production/R qualification | `OK` | R=`target_epoch` | `NONE`,R |
| INSTALL/REFUSED | N | R | `N,N,N` | N production/R qualification | refusal code | N | `NONE`,R |
| INSTALL/FAILED | N | R | `N,PARTIAL,R` iff published else `N,N,N` | N production/R qualification | failure code | R iff current published else N | R,R |
| INSTALL/CANCELLED | N | R | `N,N,N` | N production/R qualification | `AUTH_CANCELLED` | N | N,N |
| UPDATE/SUCCESS | R | R | `R,R,R` | N production/R qualification | `OK` | R=`target_epoch` | `NONE`,R |
| UPDATE/REFUSED | R | R | `R,N,N` | N production/R qualification | refusal code | N | `NONE`,R |
| UPDATE/FAILED | R | R | `R,PARTIAL,R` iff version published else `R,N,N` | N production/R qualification | failure code | R iff current published else N | R,R |
| UPDATE/CANCELLED | R | R | `R,N,N` | N production/R qualification | `AUTH_CANCELLED` | N | N,N |
| ROLLBACK/SUCCESS | R | R | `R,R,N` | N production/R qualification | `OK` | R=`target_epoch` | `NONE`,R |
| ROLLBACK/REFUSED | R | R | `R,N,N` | N production/R qualification | refusal code | N | `NONE`,R |
| ROLLBACK/FAILED | R | R | `R,PARTIAL,N` | N production/R qualification | failure code | R iff current published else N | R,R |
| ROLLBACK/CANCELLED | R | R | `R,N,N` | N production/R qualification | `AUTH_CANCELLED` | N | N,N |
| REMOVE/SUCCESS | R | N,N,R | `R,N,N` | N production/R qualification | `OK` | R=`target_epoch` | `NONE`,R |
| REMOVE/REFUSED | R | N,N,R | `R,N,N` | N production/R qualification | refusal code | N | `NONE`,R |
| REMOVE/FAILED | R | N,N,R | `R,PARTIAL,N` | N production/R qualification | failure code | R iff current published else N | R,R |
| REMOVE/CANCELLED | R | N,N,R | `R,N,N` | N production/R qualification | `AUTH_CANCELLED` | N | N,N |
| QUALIFY/SUCCESS | N | N | `N,N,N` | R | `OK` | R=`"4"` | `NONE`,R |
| QUALIFY/REFUSED | N | N | `N,N,N` | R | refusal code | N | `NONE`,R |
| QUALIFY/FAILED | N | N | `N,PARTIAL,N` | R | failure code | R iff current published else N | R,R |
| QUALIFY/CANCELLED | N | N | `N,N,N` | R | `AUTH_CANCELLED` | N | N,N |

For successful production operations, `previous_manifest_sha256` is the
active manifest before the operation; `current_manifest_sha256` is the active
manifest after it; `new_manifest_sha256` is non-null only for newly published
INSTALL/UPDATE. INSTALL requires target epoch `"1"`; UPDATE/ROLLBACK/REMOVE
require target epoch `pre_epoch+1`. QUALIFY is one parent operation whose four
child root audits are fixed in §7: Q1 INSTALL yields epoch 1/current Q1/
previous null; Q2 UPDATE yields epoch 2/current Q2/previous Q1; ROLLBACK yields
epoch 3/current Q1/previous Q2; REMOVE yields epoch 4/current/previous null.
The parent QUALIFY success is emitted only after cleanup and links all four
receipts. Terminal mapping is exact:
SUCCESS/`SUCCESS_COMMITTED`, REFUSED/`REFUSED_BEFORE_WRITE`,
FAILED/`FAILED_CLEANED|FAILED_RESIDUE`, and
CANCELLED/`NO_ROOT_PROCESS`. Refusal codes are exactly
`ARGUMENT_INVALID,AUTHORITY_INVALID,CONTEXT_MISMATCH,EPOCH_MISMATCH,LOCKED,
MODE_ROOT_MISMATCH,NONCE_REPLAY,OPERATION_INVALID,PACKET_ROOT_MISMATCH,
SIGNATURE_INVALID,STATE_INVALID`; failure codes are exactly
`AUDIT_FAILED,CLEANUP_FAILED,FILESYSTEM_FAILED,INTERNAL_FAILED,SPAWN_FAILED`.

---

## 6. Static contracts and dynamic schemas

### 6.1 Framing shared by every JSON authority

Static and dynamic JSON uses the repository's bounded JCS subset: UTF-8,
lexicographically sorted object keys, displayed array order, no duplicate
keys, booleans distinct from integers, no floats, no BOM/CR/NUL or
insignificant whitespace, and exactly one terminal LF. Unless stated
otherwise:

```text
digest = SHA256(ASCII(domain) || 0x00 || JCS(object_without_digest) || LF)
```

Lowercase SHA-256 fields are exactly 64 hex characters; decimal integer
strings match `0|[1-9][0-9]*` and are bounded to unsigned 64-bit; paths are
absolute or relative as explicitly stated and contain no NUL, empty, `.`, or
`..` component.

### 6.2 `contracts/awa-contract.v2.json`

V1 remains byte-identical at SHA-256
`408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9`.
V2 is an exact successor overlay: every v1 behavior remains required except
the registration runtime entry boundary explicitly replaced below.

```json
{"contract":"awa-kernel-contract","forbidden":["GITHUB_ACTIONS_RUNNER","PATH_RUNTIME_SELECTION","PLATFORM_PYTHON_PRODUCT_CODE","OWNER_PRIVATE_KEY_ACCESS","QUALIFICATION_KEY_AT_PRODUCTION_ROOT","SETUID_HELPER","UNCONDITIONAL_NO_ORPHAN_CLAIM"],"inheritance_rule":"Every awa-contract/v1 behavior remains required unless an exact v2 field below replaces only the registration runtime entry boundary.","mandatory_contract_sha256":{"contracts/awa-registration-admin-audit.v1.json":"a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a","contracts/awa-registration-owner-signers.v1":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v1.json":"4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c","contracts/awa-registration-private-runtime.v1.json":"f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"},"platform_python_role":"STDLIB_VERIFY_AND_SPAWN_ONLY","predecessor_path":"contracts/awa-contract.v1.json","predecessor_sha256":"408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9","private_runtime_required":true,"privileged_operations":["INSTALL","UPDATE","ROLLBACK","REMOVE","QUALIFY"],"registration_entrypoint":"/Library/Application Support/AWA/bin/awa-registration","registration_runtime":"PROTECTED_PRIVATE","schema":"awa-contract/v2","successor_of":"awa-contract/v1","version":2}
```

SHA-256:

```text
db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a
```

### 6.3 `contracts/awa-registration-private-runtime.v1.json`

```json
{"active_lock_protocol":"SHARED_PARENT_EXCLUSIVE_ADMIN","allowed_dependency_roots":["PRIVATE_RUNTIME_ROOT","/System/Library","/usr/lib"],"capability_schema":"awa-registration-python-capability/v1","current_path":"/Library/Application Support/AWA/runtime/current.v1","github_actions_runners_allowed":false,"install_root":"/Library/Application Support/AWA","object_modes":{"data":"444","directory":"755","executable":"555"},"owner_group":"wheel","owner_signature_namespace":"awa-private-runtime-release-envelope-v1","owner_uid":0,"previous_version_retention":1,"python_relative_path":"Python.app/Contents/MacOS/Python","regular_file_nlink":1,"release_envelope_schema":"awa-private-runtime-release-envelope/v1","runtime_manifest_schema":"awa-private-runtime-manifest/v1","schema":"awa-registration-private-runtime/v1","signature_inventory_schema":"awa-private-runtime-signature-inventory/v1","source_lock_schema":"awa-private-runtime-source-lock/v1","symlinks_allowed":false,"version_lock_path_template":"/Library/Application Support/AWA/runtime/locks/<manifest_sha256>.lock","versions_path":"/Library/Application Support/AWA/runtime/versions"}
```

SHA-256:

```text
f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321
```

### 6.4 `contracts/awa-registration-platform-bootstrap.v1.json`

```json
{"authority_fd_targets":[4,5,6,7,8],"barriers":["READY","GO","IMPORT_READY"],"boot_identity_api":"sysctlbyname(kern.boottime)","bootstrap_path":"/Library/Application Support/AWA/bootstrap/v1/bootstrap.py","child_path":"/Library/Application Support/AWA/bootstrap/v1/child.py","control_eof_fatal_after_watchdog":true,"control_fd_target":3,"darwin_process_apis":["csops(CS_OPS_CDHASH)","proc_listpids(PROC_UID_ONLY)","proc_pidinfo(PROC_PIDTBSDINFO)","proc_pidpath","proc_pidinfo(PROC_PIDREGIONPATHINFO)","sysctl(KERN_PROCARGS2)"],"entrypoint_path":"/Library/Application Support/AWA/bin/awa-registration","expected_parent_pid_required":true,"fixed_environment":{"LANG":"C","LC_ALL":"C","PATH":"/usr/bin:/bin"},"fixed_targets_never_closed":true,"forbidden_environment_prefixes":["DYLD_","PYTHON"],"forbidden_spawn_flags":["POSIX_SPAWN_START_SUSPENDED"],"healthy_live_parent_action":"LEAVE_UNTOUCHED","inherited_environment_keys":[],"intent_phases":["PREPARED","SPAWNED","READY","GO","PRODUCT","TERMINAL"],"later_reconciler_mode":"OBSERVATION_ONLY","later_reconciler_process_control_allowed":false,"operator_messages":{"ambiguous":"AWA found ambiguous interrupted-bootstrap state. AWA remains inactive. Restart the Mac before trying again.","confirmed_inert":"Interrupted AWA bootstrap residue was detected. AWA remains inactive. Wait for the process to exit or restart the Mac."},"original_parent_direct_child_signal":"SIGKILL","original_parent_direct_child_signal_requires_continuous_identity":true,"pidversion_domain":"awa-darwin-pidversion/v1","platform_python_argv":["/usr/bin/python3","-I","-S","-B","/Library/Application Support/AWA/bootstrap/v1/bootstrap.py"],"platform_python_path":"/usr/bin/python3","platform_python_product_code_allowed":false,"platform_ssh_keygen_path":"/usr/bin/ssh-keygen","pre_watchdog_orphan_claim_allowed":false,"product_import_before_go_allowed":false,"reboot_clears_inert_process":true,"reboot_is_guaranteed_cleanup_boundary":true,"reconcile_before_every_route":true,"reconcile_max_pids":4096,"reconcile_outcomes":["HEALTHY_PAIR_PRESERVED","NATURAL_EXIT_RECONCILED","RESIDUE_REFUSED","REBOOT_CLEARED"],"reconcile_parent_first":true,"reconcile_parent_observations_minimum":2,"reconcile_parent_states":["EXACT_LIVE","ABSENT","ZOMBIE","PIDVERSION_MISMATCH","AMBIGUOUS"],"reconcile_poll_minimum_milliseconds":100,"reconcile_wait_milliseconds":5000,"required_spawn_flags":["POSIX_SPAWN_CLOEXEC_DEFAULT"],"routes":["admission","receiver","startup","tick"],"schema":"awa-registration-platform-bootstrap/v1","source_fd_minimum":10,"spawn_api":"posix_spawn","spawn_intent_directory_mode":"700","spawn_intent_file_mode":"600","spawn_intent_max_live_records":64,"spawn_intent_path_template":"<getpwuid(uid).pw_dir>/.local/share/awa/registration-runtime/spawn-intents/v1/<nonce>.json","spawn_intent_schema":"awa-registration-spawn-intent/v1","spawn_nonce_environment_key":"AWA_REGISTRATION_SPAWN_NONCE","terminal_retention_days":7,"unrelated_high_fds_closed":true}
```

SHA-256:

```text
4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c
```

### 6.5 Privilege contracts

`contracts/awa-registration-privileged-envelope.v1.json`:

```json
{"arbitrary_path_arguments_allowed":false,"arbitrary_shell_arguments_allowed":false,"archive_path_suffix":".archive","bootstrap_encoding":"RFC4648_BASE64","bootstrap_execution":["/usr/bin/python3","-I","-S","-B","-c"],"credential_input_allowed":false,"envelope_max_bytes":1048576,"envelope_min_bytes":2,"envelope_mode":"600","envelope_owner":"REQUESTED_UID","envelope_path_template":"/private/var/tmp/awa-private-runtime-envelope-<requested_uid>-<request_id>.json","fixed_environment":{"LANG":"C","LC_ALL":"C"},"initial_osascript_argv":["/usr/bin/osascript","-l","AppleScript","-e","INITIAL_SCRIPT","--","REQUESTED_UID","REQUEST_ID"],"initial_shell_argv":["/usr/bin/env","-i","LANG=C","LC_ALL=C","/usr/bin/python3","-I","-S","-B","-c","INLINE_BOOTSTRAP_CODE","REQUESTED_UID","REQUEST_ID"],"initial_transport":"PATHLESS_INLINE_OSASCRIPT","manifest_path_suffix":".manifest.json","modes":["PRODUCTION","QUALIFY"],"operations":["INSTALL","UPDATE","ROLLBACK","REMOVE","QUALIFY"],"osascript_path":"/usr/bin/osascript","outcome_matrix_schema":"awa-registration-privileged-outcome-matrix/v1","owner_signature_namespace":"awa-private-runtime-release-envelope-v1","production_rejects_qualification_anchor":true,"production_root":"/Library/Application Support/AWA","python_path":"/usr/bin/python3","qualification_admin_relative_path":"bin/awa-private-runtime-admin","qualification_namespace":"awa-private-runtime-qualification-release-v1","qualification_nonce_pattern":"[0-9a-f]{64}","qualification_root_template":"/Library/Application Support/AWA-qualification-<qualification_nonce>","request_id_pattern":"[0-9a-f]{64}","request_schema":"awa-registration-privileged-request/v1","requested_uid_pattern":"0|[1-9][0-9]{0,9}","root_admin_path":"/Library/Application Support/AWA/bin/awa-private-runtime-admin","schema":"awa-registration-privileged-envelope/v1","shell_path":"/bin/sh","signature_path_suffix":".sig","ssh_keygen_path":"/usr/bin/ssh-keygen","subsequent_osascript_argv":["/usr/bin/osascript","-l","AppleScript","-e","ADMIN_SCRIPT","--","OPERATION","REQUESTED_UID","REQUEST_ID"],"subsequent_shell_argv":["/usr/bin/env","-i","LANG=C","LC_ALL=C","/Library/Application Support/AWA/bin/awa-private-runtime-admin","OPERATION","REQUESTED_UID","REQUEST_ID"],"subsequent_transport":"ROOT_ADMIN_ENTRYPOINT"}
```

SHA-256:

```text
7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034
```

`contracts/awa-registration-admin-audit.v1.json`:

```json
{"absent_value":"JCS_NULL","digest_domain":"awa-registration-admin-audit-receipt/v1","digest_excludes":["receipt_digest"],"fields":["schema","mode","receipt_origin","request_id","operation","requested_uid","target_root","packet_root_digest","qualification_context_digest","qualification_allowed_signers_digest","pre_epoch","post_epoch","pre_current_digest","target_release_envelope_digest","target_manifest_sha256","target_epoch","previous_manifest_sha256","current_manifest_sha256","new_manifest_sha256","q1_envelope_digest","q1_manifest_sha256","q2_envelope_digest","q2_manifest_sha256","envelope_sha256","owner_signature_sha256","synthetic_signature_sha256","state_machine_terminal","outcome","reason_code","predecessor_audit_digest","root_receipt_link_digest","partial_stage_state","cleanup_digest","installed_paths_hash","removed_paths_hash","started_wall_ns","completed_wall_ns","receipt_digest"],"jcs_lf_required":true,"modes":["PRODUCTION","QUALIFY"],"operations":["INSTALL","UPDATE","ROLLBACK","REMOVE","QUALIFY"],"outcome_matrix_schema":"awa-registration-privileged-outcome-matrix/v1","outcomes":["SUCCESS","REFUSED","FAILED","CANCELLED"],"partial_stage_states":["NONE","STAGED_UNPUBLISHED","VERSION_PUBLISHED","CURRENT_PUBLISHED","REMOVAL_IN_PROGRESS"],"production_receipt_directory":"/Library/Application Support/AWA/runtime/audit","qualification_receipt_directory_template":"/Library/Application Support/AWA-qualification-<qualification_nonce>/runtime/audit","reason_codes":["ARGUMENT_INVALID","AUDIT_FAILED","AUTH_CANCELLED","AUTHORITY_INVALID","CLEANUP_FAILED","CONTEXT_MISMATCH","EPOCH_MISMATCH","FILESYSTEM_FAILED","INTERNAL_FAILED","LOCKED","MODE_ROOT_MISMATCH","NONCE_REPLAY","OK","OPERATION_INVALID","PACKET_ROOT_MISMATCH","SIGNATURE_INVALID","SPAWN_FAILED","STATE_INVALID"],"receipt_mode":"444","receipt_origins":["CLIENT_AUTH","ROOT_ADMIN"],"receipt_owner_group":"wheel","receipt_owner_uid":0,"receipt_schema":"awa-registration-admin-audit-receipt/v1","schema":"awa-registration-admin-audit/v1","terminals":["FAILED_CLEANED","FAILED_RESIDUE","NO_ROOT_PROCESS","REFUSED_BEFORE_WRITE","SUCCESS_COMMITTED"]}
```

SHA-256:

```text
a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a
```

### 6.6 Signer contracts

Current v1 must be delivered byte-identically for historical owner-gate-v2
verification. Its exact one-line LF-terminated bytes are:

```text
KleinPerkins namespaces="awa-registration-owner-gate-v2" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE+scgn2qp86lkQWcVDpJ+SXT/pVF0DntlxGVnmnFyEp
```

SHA-256:

```text
9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e
```

Successor `contracts/awa-registration-owner-signers.v2` exact one-line
LF-terminated bytes are:

```text
KleinPerkins namespaces="awa-private-runtime-release-envelope-v1,awa-registration-owner-gate-v3" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE+scgn2qp86lkQWcVDpJ+SXT/pVF0DntlxGVnmnFyEp
```

SHA-256:

```text
690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3
```

AWA invokes fixed public verification only. It never locates, prompts for,
opens, receives, or uses the owner's private key. Test signatures use
ephemeral synthetic keys outside production namespaces.
`OWNER_PRIVATE_KEY_ACCESS` means any access to or use of production owner-key
material, including owner signing. It does not prohibit the one-use synthetic
qualification key allowed only by the exact `QUALIFY` mode, nonce, disposable
root, and qualification namespace in §6.7; that key is structurally incapable
of owner or production authorization.

### 6.7 Complete dynamic successor schemas

Each field set below is exact; extra/missing fields refuse.

**Current record — `awa-private-runtime-current/v1`.** Exact fields:
`schema,epoch,active_manifest_sha256,previous_manifest_sha256,
active_release_envelope_digest,installed_at_wall_ns,installer_audit_digest,
predecessor_current_digest,current_digest`. `epoch` and wall time are unsigned
decimal strings; `previous_manifest_sha256` is lowercase 64-hex or JSON null;
all other digest fields are lowercase 64-hex. Epoch starts at `"1"` and
strictly increments. Domain `awa-private-runtime-current/v1`; digest excludes
`current_digest`.

**Successor key enrollment — `awa-registration-owner-key-enrollment/v2`.** Exact
fields: `schema,principal,namespaces,key_algorithm,public_key_sha256,
openssh_fingerprint,allowed_signers_relative_path,
allowed_signers_path_hash,allowed_signers_contract_hash,authorized`.
Principal is exactly `KleinPerkins`; namespaces are exactly
`["awa-private-runtime-release-envelope-v1",
"awa-registration-owner-gate-v3"]`; algorithm is `ssh-ed25519`; relative
path is exactly `contracts/awa-registration-owner-signers.v2`; hashes are
lowercase 64-hex; fingerprint is the exact OpenSSH SHA256 fingerprint; and
`authorized` is true. `allowed_signers_path_hash` is
`SHA256(ASCII("awa-registration-owner-signers-path/v1") || 0x00 ||
UTF8(relative_path))`. Domain
`awa-registration-owner-key-enrollment/v2`; its digest is over the complete
object because it has no self-digest field.

For the exact v2 signer bytes, values are:

```text
public_key_sha256=ccc9283906c612aed388f23bf5ef26f16a0a780926a447dbe8c7e71a94b4df63
openssh_fingerprint=SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M
allowed_signers_path_hash=e0adbc96112fc8d029c8837988eb70bf4e8b0bb747daaa41d8899ce8013a712b
allowed_signers_contract_hash=690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3
```

`public_key_sha256` hashes the RFC4253/OpenSSH wire blob decoded from the
line's base64 field; the fingerprint is base64(SHA256(wire blob)) without
padding and with the `SHA256:` prefix.

**Successor key authorization —
`awa-registration-owner-key-authorization/v2`.** Exact fields:
`schema,repository,authorized_by,action,principal,namespaces,key_algorithm,
public_key_sha256,openssh_fingerprint,allowed_signers_relative_path,
allowed_signers_path_hash,allowed_signers_contract_hash,
key_enrollment_digest,acceptance_normalized_digest,authorization_nonce,
authorized`. Repository/authorizer are `KleinPerkins/awa`/`KleinPerkins`;
action is `ENROLL`; signer fields equal the v2 enrollment; acceptance digest
is the accepted v7 normalized digest; nonce is one-use lowercase 64-hex; and
`authorized` is true. Domain
`awa-registration-owner-key-authorization/v2`; its digest is over the
complete object.

**Successor key current — `awa-registration-owner-key-current/v2`.** Exact
fields: `schema,sequence,status,principal,namespaces,key_algorithm,
public_key_sha256,openssh_fingerprint,allowed_signers_relative_path,
allowed_signers_path_hash,allowed_signers_contract_hash,
key_enrollment_digest,owner_authorization_digest,
previous_enrollment_hash,created_wall_ns,enrollment_hash`. Sequence/time are
unsigned decimal strings; status is `ACTIVE|REVOKED`; signer fields equal the
enrollment; predecessor is the current v1 enrollment hash
`885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4`;
all other hashes are lowercase 64-hex. Domain
`awa-registration-owner-key-current/v2`; digest excludes `enrollment_hash`.
The v2 signer-contract hash is
`690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3`.
V1 remains valid only for historical owner-gate-v2 verification and cannot
authorize a v3 gate or private-runtime release.

**Qualification-only allowed signers —
`awa-registration-qualification-allowed-signers/v1`.** A one-use synthetic
Ed25519 keypair may be generated locally only after the exact-head
`V7-C-RUNTIME-QUALIFY` gate and before the privilege prompt. It is not the
owner key and cannot authorize production. The exact contract fields are:

```text
schema,mode,repository,exact_head,qualification_nonce,qualification_root,
principal,namespaces,key_algorithm,public_key_openssh,
public_key_wire_sha256,openssh_fingerprint,allowed_signers_line,
allowed_signers_sha256,contract_digest
```

`mode="QUALIFY"`, repository is `KleinPerkins/awa`, principal is
`AWAQualification`, namespaces is exactly
`["awa-private-runtime-qualification-release-v1"]`, and algorithm is
`ssh-ed25519`. Nonce is 64 lowercase hex; root is exactly
`/Library/Application Support/AWA-qualification-<nonce>`; head is the exact
C-RUNTIME 40-hex head. `public_key_openssh` is exactly
`ssh-ed25519 <RFC4253-base64>` with no comment; wire hash/fingerprint follow
§6.6. `allowed_signers_line` is exactly
`AWAQualification namespaces="awa-private-runtime-qualification-release-v1" `
plus `public_key_openssh` plus LF; its SHA-256 is
`allowed_signers_sha256`. Remaining digests are lowercase 64-hex.

```text
contract_digest =
  SHA256(ASCII("awa-registration-qualification-allowed-signers/v1") ||
         0x00 || JCS(contract_without_contract_digest) || LF)
contract_bytes = JCS(full_contract) || LF
```

The exact public bytes/fingerprint, contract bytes/digest, nonce/root/head,
both Q1/Q2 envelope/manifests (which bind this contract digest), and the
separately computed packet root are
duplicated byte-equal in the pre-prompt context and privileged request.
Production mode/root and every
production operation structurally reject this schema, principal, namespace,
and signature before writes. QUALIFY rejects owner namespaces and any
cross-root/cross-nonce value before writes.

**Qualification fixture manifest and envelope.**
`awa-registration-qualification-fixture-manifest/v1` has exactly
`schema,fixture_id,epoch,runtime_archive_sha256,marker,manifest_digest`;
`marker` has exactly `path,mode,size,sha256`, where path/mode are
`qualification/MARKER`/`"0444"`, size is `"21"`, and hash is the exact Q1/Q2
value in §7.2. Fixture ID/epoch are Q1/`"1"` or Q2/`"2"`. Domain equals the
schema and digest excludes `manifest_digest`.

`awa-private-runtime-qualification-release-envelope/v1` has exactly
`schema,repository,mode,exact_head,qualification_nonce,
qualification_root,fixture_id,epoch,runtime_archive_sha256,
fixture_manifest_digest,marker_sha256,
qualification_allowed_signers_digest,release_envelope_digest`. Repository is
`KleinPerkins/awa`, mode is `QUALIFY`, all bindings duplicate the dynamic
contract/context, and fixture/epoch/marker values select exactly Q1 or Q2.
Domain equals the schema; digest excludes `release_envelope_digest`. The
detached synthetic signature covers exact `JCS(envelope)||LF` under namespace
`awa-private-runtime-qualification-release-v1`. Production release schema,
root, and namespace reject this successor structurally.

**Privileged request — `awa-registration-privileged-request/v1`.** Exact
fields:

```text
schema,mode,operation,requested_uid,request_id,target_root,
packet_root_digest,qualification_context_digest,
qualification_allowed_signers_digest,pre_current_digest,
target_release_envelope_digest,target_manifest_sha256,target_epoch,
previous_manifest_sha256,current_manifest_sha256,new_manifest_sha256,
q1_envelope_digest,q1_manifest_sha256,q2_envelope_digest,q2_manifest_sha256,
created_wall_ns,expires_wall_ns,request_digest
```

Mode and operation use the static enums; request UID is bounded decimal;
request ID is 64 lowercase hex; target root is exactly production or the
bound qualification root. Every absent value is JSON null according to
§5.4; no omitted field is accepted. Hashes are lowercase 64-hex; epochs/times
are unsigned decimal strings with expiry greater than creation and a maximum
15-minute interval. Domain `awa-registration-privileged-request/v1`; digest
excludes `request_digest`. Reuse, expiry, target/pre-current/packet/context/
trust-anchor mismatch refuses. Native authorization permits only execution;
the applicable signed release authority permits only the exact payload.
The request's previous/current/new values are expected pre/postconditions
under §5.4; the audit repeats observed values and equality is required for
SUCCESS.

**Spawn intent — `awa-registration-spawn-intent/v1`.** Exact fields:

```text
schema,phase,nonce,route,private_executable_path,
private_executable_sha256,runtime_manifest_sha256,version_lock_identity,
parent_pid,parent_pidversion,child_pid,child_pidversion,mapped_vnode_dev,
mapped_vnode_ino,boot_identity,prepared_wall_ns,published_wall_ns,
terminal_reason,intent_digest
```

Phase is `PREPARED|SPAWNED|READY|GO|PRODUCT|TERMINAL`; route is the four-token wrapper enum;
nonce is 64 lowercase hex; path is the manifest-bound private executable;
hashes and non-null pidversions are lowercase 64-hex; PID/dev/inode/times are
unsigned decimal strings. In PREPARED, all child/mapped/published/terminal
fields are JSON null. SPAWNED requires child PID, a pidversion or explicit
JSON null, and published time; mapped fields are both decimal or both null.
READY/GO/PRODUCT retain the same child identity and record the highest
completed barrier before the next action. TERMINAL requires one exact reason
`NORMAL_EXIT|NATURAL_EXIT_RECONCILED|REBOOT_CLEARED|SPAWN_FAILED`;
child/mapped values retain their prior values or remain null. A persistent or
ambiguous current-boot residue remains nonterminal and blocks new work.
Domain
`awa-registration-spawn-intent/v1`; digest excludes `intent_digest`.

**Release envelope — `awa-private-runtime-release-envelope/v1`.** Exact
fields: `schema,repository,exact_head,source_lock_sha256,
normalizer_source_sha256,signing_recipe_source_sha256,capability_digest,
sqlite_compile_options_hash,runtime_manifest_sha256,
signature_inventory_sha256,archive_sha256,archive_size,sbom_sha256,
license_inventory_sha256,qualification_packet_digest,minimum_epoch,
release_envelope_digest`. Repository is exactly `KleinPerkins/awa`; exact
head is 40 lowercase hex; every digest is lowercase 64-hex; archive size and
minimum epoch are positive unsigned decimal strings. Domain
`awa-private-runtime-release-envelope/v1`; digest excludes
`release_envelope_digest`. The detached owner signature is not a JSON field;
`ssh-keygen -Y verify` verifies exact `JCS(envelope)||LF` under namespace
`awa-private-runtime-release-envelope-v1`.

**Direct receipt — `awa-registration-direct-receipt/v4`.** Exact fields:

```text
schema,owner_mode,deployment_scope,candidate_digest,schema_hash,profile_hash,
runtime_capability_hash,writer_binary_hash,writer_capability_hash,
tool_inventory_hash,hook_projection_hash,hook_matcher_mode,hook_matcher_hash,
installed_file_hash,projection_file_generation,protocol_generation,
wrapper_runtime_hash,installer_identity_hash,installer_capability_hash,
owner_gate_digest,canonical_root_hash,member_id,bundle_generation,
bundle_digest,bundle_projection_hash,import_manifest_hash,source_lock_sha256,
runtime_release_envelope_digest,runtime_manifest_sha256,
signature_inventory_sha256,capability_digest,qualification_packet_digest,
denial_proof_vector_hash,bootstrap_contract_hash,
private_runtime_contract_hash,privileged_envelope_contract_hash,
admin_audit_contract_hash,allowed_signers_contract_path_hash,
allowed_signers_contract_hash,signer_public_key_sha256,signer_fingerprint,
key_enrollment_digest,key_current_enrollment_hash,harness_root_hash
```

Schema/owner mode are exactly `awa-registration-direct-receipt/v4`/`DIRECT`;
scope is `R0_THROWAWAY|R1_CANARY|R2_DIRECT`; matcher mode is `ENUMERATED`;
the three generation fields are positive unsigned decimal strings; every
field ending `_hash`, `_sha256`, or `_digest` is lowercase 64-hex except the
three scope fields below; signer fingerprint is
`SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M`.
For R0, only `harness_root_hash` is non-null; for R1, only
`canonical_root_hash` and `member_id` are non-null; for R2, all three are
null. Every non-null scope value is lowercase 64-hex.

`DIRECT_BODY_FIELDS` is that exact field set minus `owner_gate_digest`.

```text
direct_receipt_body_hash =
  SHA256(ASCII("awa-registration-direct-receipt-authority/v3") || 0x00 ||
         JCS(exact DIRECT_BODY_FIELDS object))

direct_receipt_digest =
  SHA256(ASCII("awa-registration-direct-receipt/v4") || 0x00 ||
         JCS(exact full receipt object) || LF)
```

The latter is the final receipt digest and necessarily includes
`owner_gate_digest`.

**Owner gate — `awa-registration-owner-gate/v3`.** Exact fields:

```text
schema,repository,authorized_by,deployment_scope,direct_receipt_body_hash,
candidate_digest,bundle_digest,bundle_projection_hash,import_manifest_hash,
source_lock_sha256,runtime_release_envelope_digest,runtime_manifest_sha256,
signature_inventory_sha256,capability_digest,qualification_packet_digest,
denial_proof_vector_hash,installed_file_hash,wrapper_runtime_hash,
bootstrap_contract_hash,private_runtime_contract_hash,
privileged_envelope_contract_hash,admin_audit_contract_hash,
installer_identity_hash,installer_capability_hash,
allowed_signers_contract_path_hash,allowed_signers_contract_hash,
signer_public_key_sha256,signer_fingerprint,key_enrollment_digest,
key_current_enrollment_hash,accepted_v6_normalized_digest,
implementation_exact_head,canonical_root_hash,member_id,harness_root_hash,
authorized
```

Schema/repository/authorizer are exactly
`awa-registration-owner-gate/v3`, `KleinPerkins/awa`, and `KleinPerkins`;
scope and nullable scope fields follow the receipt rules; `authorized` is
true; head is 40 lowercase hex; fingerprint is the exact value above; and
every remaining value is lowercase 64-hex. `bundle_digest` is the AWA bundle
manifest authority; `denial_proof_vector_hash` is the signed expected vector,
never observed execution. `accepted_v6_normalized_digest` is exactly
`1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452`;
source lock and the four contract hashes equal §§3.1 and 6.3–6.5; runtime,
capability, signature inventory, and qualification values equal the accepted
packet/release envelope; enrollment values equal the ACTIVE v2 current
record; and every duplicated receipt/gate field must be byte-equal.

```text
owner_gate_digest =
  SHA256(ASCII("awa-registration-owner-gate/v3") || 0x00 || JCS(gate))
gate_bytes = JCS(gate) || LF
```

`owner_gate_digest` is not a gate field; it is inserted into the receipt.
The detached signature verifies exact `gate_bytes` under
`awa-registration-owner-gate-v3`.

**Admin audit receipt — `awa-registration-admin-audit-receipt/v1`.** It has
exactly the 38 fields listed by the static audit contract and obeys the full
§5.4 matrix. Mode/origin/operation/outcome/reason/partial state are exact
static enums; UID/epochs/times are unsigned decimal strings (`pre_epoch` may
be `"0"`); `target_root` is an exact authorized root; every absent value is
JSON null; all present hashes are lowercase 64-hex. `installed_paths_hash`
and `removed_paths_hash` use domain `awa-registration-admin-paths/v1` over
sorted UTF-8 paths, each followed by LF. `cleanup_digest` binds the exact
sorted removed/residual paths and secondary cleanup failures. Receipt domain
is the static contract domain; digest excludes `receipt_digest`.

Old external-interpreter/config-v1 records may be read only to classify and
refuse. There is no migration that treats them as private-runtime authority.
An authoritative live legacy deployment is a stop requiring a successor
decision. New mandatory runtime/bootstrap/privilege fields live only in v2
and the successor schemas; v1 meaning is not mutated.

---

## 7. Exact-head C-RUNTIME qualification packet

### 7.1 Packet framing and field set

After C-RUNTIME Draft delivery and review, qualification produces one
canonical directory; no transport archive is authority. Any archive is a
byte-preserving convenience whose hash is evidence only. The directory has:

```text
packet-root-index.json
bound-input-index.json
inputs/sha256/<lowercase_sha256>
evidence-index.json
evidence/sha256/<lowercase_sha256>
packet.json
```

Every path is relative, normalized UTF-8, unique, a regular file with
`st_nlink == 1`, mode `0444`, and no symlink/escape. Blob paths are
content-addressed and their basename must equal their bytes' SHA-256. A
packet-root blob record has exactly
`path,role,domain,size,sha256,mode,media_type,encoding`; an evidence blob
record has those fields plus `packet_root_digest`. Size is an unsigned decimal
string, mode is `"0444"`, encoding is one of
`BINARY|UTF8|UTF8_LF|JCS_LF`, and records sort by UTF-8 `path`, then `role`.

`packet-root-index.json` has exactly `schema,records,index_digest`, schema
`awa-registration-private-runtime-qualification-packet-root-index/v1`, and:

```text
index_digest =
  SHA256(ASCII("awa-registration-private-runtime-qualification-packet-root/v1")
         || 0x00 || JCS(index_without_index_digest) || LF)
packet_root_digest = index_digest
```

No packet-root blob contains `packet_root_digest`; this exact anti-cycle rule
is mechanically checked. After that root is final, `bound-input-index.json`
records the exact pre-prompt context and privileged request bytes, each of
which contains `packet_root_digest`. It has exactly
`schema,packet_root_digest,records,index_digest`, schema
`awa-registration-private-runtime-qualification-bound-input-index/v1`, and
the analogous domain ending `bound-input-root/v1`. Its records have the
packet-root blob fields plus `packet_root_digest`.

`evidence-index.json` has that same root-bound shape, schema
`awa-registration-private-runtime-qualification-evidence-index/v1`, and
domain ending `evidence-root/v1`. Every evidence blob/record duplicates the
`packet_root_digest`; mismatch refuses. This three-index shape prevents a
cycle: immutable executable/fixture bytes are frozen first, root-bound
request/context bytes second, and observed results last.

The two input indexes together must contain canonical blobs for exact inline bootstrap `B`;
initial/admin AppleScript sources; initial/admin shell and argv templates;
the exact initial command rendering and exact INSTALL/UPDATE/ROLLBACK/REMOVE/
QUALIFY admin renderings; privileged request/context assets; qualification
allowed-signers contract; installed admin, entrypoint, platform bootstrap,
and child bytes; every §6 static contract; source-lock bytes; selected
attestation bundle, decoded payload, DER certificate, `SHA256SUMS`, and raw
`python/PYTHON.json`; and both Q1/Q2 manifests, release envelopes, and
synthetic signatures. The request/context roles belong only to the bound-input
index. `AUTHORIZATION_RESULT,OPERATION_STDOUT,OPERATION_STDERR,
CLEANUP_RESULT,SECURITYAGENT_STDOUT,
SECURITYAGENT_STDERR,PARENT_DEATH_EVIDENCE,
PARENT_DEATH_SYSCALL_TRACE,PARENT_DEATH_OPERATOR_MESSAGES` belong only to the
evidence index; all other roles belong only to the packet-root index. Role
names are exactly:

```text
INLINE_BOOTSTRAP_B,INITIAL_APPLESCRIPT,ADMIN_APPLESCRIPT,
INITIAL_SHELL_TEMPLATE,ADMIN_SHELL_TEMPLATE,INITIAL_COMMAND,
ADMIN_INSTALL_COMMAND,ADMIN_UPDATE_COMMAND,ADMIN_ROLLBACK_COMMAND,
ADMIN_REMOVE_COMMAND,ADMIN_QUALIFY_COMMAND,PRIVILEGED_REQUEST,
PRIVILEGED_CONTEXT,QUALIFICATION_ALLOWED_SIGNERS,ROOT_ADMIN,
ROOT_ENTRYPOINT,PLATFORM_BOOTSTRAP,CHILD_BOOTSTRAP,STATIC_CONTRACT,
SOURCE_LOCK,ATTESTATION_BUNDLE,ATTESTATION_PAYLOAD,
ATTESTATION_CERTIFICATE,SHA256SUMS,PYTHON_JSON,Q1_MANIFEST,Q1_ENVELOPE,
Q1_SIGNATURE,Q2_MANIFEST,Q2_ENVELOPE,Q2_SIGNATURE,NORMALIZER_SOURCE,
SIGNING_RECIPE_SOURCE,BUILD_MANIFEST,BUILD_SIGNATURE_INVENTORY,
BUILD_TRANSCRIPT,BUILD_ARCHIVE,BUILD_SBOM,BUILD_LICENSE_INVENTORY,
TEST_STDOUT,TEST_STDERR,TREE_COMPARISON,ARCHIVE_COMPARISON,LOADED_IMAGES,
DEPENDENCY_ESCAPES,AUTHORIZATION_RESULT,OPERATION_STDOUT,OPERATION_STDERR,
PURE_VALIDATOR_REJECTION_EVIDENCE,PARENT_DEATH_EVIDENCE,CLEANUP_RESULT,
PARENT_DEATH_SYSCALL_TRACE,PARENT_DEATH_OPERATOR_MESSAGES,
SECURITYAGENT_STDOUT,SECURITYAGENT_STDERR
```

`packet.json` schema is
`awa-registration-private-runtime-qualification/v1`. Its body has exactly:

```text
schema,repository,exact_head,packet_root_index_digest,packet_root_digest,
bound_input_index_digest,source_lock,github_attestation,normalizer_source,
signing_recipe_source,
capability,compile_options,builds,byte_comparison,selected_build_id,
final_archives,sbom_license_inventory,relocation_load_image_evidence,
registration_test_evidence,full_test_evidence,
qualification_allowed_signers,qualification_fixtures,
privileged_qualification_context,preprompt_rejection_evidence,
admin_qualification_evidence,parent_death_evidence,
executed_identities,securityagent_result,private_key_deletion,
evidence_index_digest,evidence_root_digest
```

The final packet adds exactly `packet_digest`; repository is
`KleinPerkins/awa`, head is the C-RUNTIME 40-hex commit,
`packet_root_index_digest == packet_root_digest`, and
`evidence_index_digest == evidence_root_digest`.

```text
packet_digest =
  SHA256(ASCII("awa-registration-private-runtime-qualification/v1") ||
         0x00 || JCS(packet_body) || LF)
packet_bytes = JCS(packet_body + packet_digest) || LF
```

Every inline object or blob is bound by one of the three indexes and the packet
digest. Arrays retain the exact orders below; records otherwise use their
stated sort. No future value is supplied before its preimage exists.

### 7.2 Nested records

- `source_lock` has exactly `object,blob,sha256`; object and blob equal §3.1
  JCS+LF and its recomputed hash.
- `github_attestation` has exactly
  `repository,artifact_name,artifact_sha256,release,selection_rule,
  matching_record_count,predicate_type,payload_type,bundle_media_type,
  oidc_issuer,certificate_issuer,subject_name,subject_sha256,subject_count,
  build_type,builder_id,workflow_repository,workflow_name,workflow_path,
  workflow_ref,workflow_sha,event_name,run_invocation,bundle,payload,
  certificate,verification_command,rejected_records,verified,digest`.
  Values equal §3.1; matching count is `"1"`; rejected records contain the
  one observed release-v0.2 predicate and can never be authority; bundle,
  payload, and certificate are input blob records. The selector queries exact
  artifact SHA-256, decodes every DSSE payload, applies every exact identity
  constraint, and requires exactly one SLSA-v1 record. Command is an exact
  string array and `verified` is true. Domain
  `awa-private-runtime-github-attestation/v1`; digest excludes `digest`.
  Canonical bundle serialization is exact JCS+LF; validators must reproduce
  size 222485 and hash
  `71ee6bcb100ad2474d01dce968125fa631f2e28616c21ddf67364d2ef7ca94d3`.
- `normalizer_source` and `signing_recipe_source` are blob records for exact
  source bytes. Their hashes become release-envelope fields.
- `capability` has exactly `object,digest`; object has exactly the 23 keys in
  §3.3 and digest domain `awa-registration-python-capability/v1`.
- `compile_options` has exactly `object,digest`; object has exactly
  `schema,options`, options are distinct UTF-8-bytewise sorted strings, and
  digest domain is `awa-registration-sqlite-compile-options/v1`.
- `builds` has exactly two records sorted by `build_id`. Each has exactly
  `build_id,clean_root_id,toolchain,manifest,signature_inventory,transcript,
  archive,sbom,license_inventory,registration_tests,full_tests`.
  `build_id` is `"A"` or `"B"`, root ID is a nonsecret lowercase 64-hex hash,
  transcript/archive/SBOM/license fields are blob records, and test fields are
  test records below.
- Each `toolchain` has exactly
  `codesign_path,codesign_project,codesign_sha256,clt_version,sdk_version,
  target_triple`; values must equal §3.2.
- Each `manifest` has exactly `object,digest`; object has exactly
  `schema,source_lock_sha256,normalizer_source_sha256,
  signing_recipe_source_sha256,record_framing_digest,records`. Each record has
  exactly `path,mode,size,sha256,macho` and follows §3.2; records are sorted by
  path. Domain `awa-private-runtime-manifest/v1`.
- Each `signature_inventory` has exactly `object,digest`; object has exactly
  `schema,records`; each path-sorted record has exactly
  `path,identifier,cdhash,adhoc,strict_valid`; booleans must both be true.
  Domain `awa-private-runtime-signature-inventory/v1`.
- A test record has exactly
  `command,exit_code,passed,failed,skipped,stdout,stderr,started_wall_ns,
  completed_wall_ns,digest`; command is an exact string array, counts/times
  are unsigned decimal strings, exit is `"0"`, and stdout/stderr are blob
  records. Domain `awa-private-runtime-test-evidence/v1`; digest excludes
  `digest`.
- `byte_comparison` has exactly
  `schema,build_a_manifest_sha256,build_b_manifest_sha256,
  build_a_archive_sha256,build_b_archive_sha256,tree_comparison,
  archive_comparison,equal,digest`; both comparison values are blob records
  and `equal` must be true. Domain
  `awa-private-runtime-byte-comparison/v1`; digest excludes `digest`.
- `selected_build_id` is exactly `"A"` after equality; selection adds no
  preference because A/B bytes must match.
- `final_archives` is exactly the two build archive blob records in A/B order.
- `sbom_license_inventory` has exactly
  `schema,build_a_sbom_sha256,build_b_sbom_sha256,
  build_a_license_inventory_sha256,build_b_license_inventory_sha256,equal,
  digest`; equality must be true. Domain
  `awa-private-runtime-sbom-license-comparison/v1`; digest excludes `digest`.
- `relocation_load_image_evidence` is exactly two records sorted by
  `relocation_id`, each with exactly
  `relocation_id,root_hash,command,loaded_image_count,
  loaded_images,dependency_escapes,exit_code,digest`; root is a nonsecret hash,
  command an exact string array, loaded/escape evidence blob records, count
  unsigned decimal, exit `"0"`, and escape records must be empty.
  Domain `awa-private-runtime-relocation-evidence/v1`; digest excludes
  `digest`.
- `registration_test_evidence` and `full_test_evidence` are exact test records
  for the selected build. They must also equal their selected build records.
- `qualification_allowed_signers` has exactly `object,blob,digest`; object and
  digest obey §6.7, blob is the exact full contract JCS+LF, and all three are
  byte-consistent.
- `qualification_fixtures` has exactly
  `schema,qualification_nonce,qualification_root,runtime_archive_sha256,
  q1,q2,digest`. Q1/Q2 each have exactly
  `fixture_id,epoch,marker_relative_path,marker_bytes_base64,marker_size,
  marker_sha256,build_a_manifest_sha256,build_b_manifest_sha256,
  manifest_sha256,release_envelope_digest,synthetic_signature_sha256`.
  Fixture IDs are `Q1`,`Q2`; epochs are `"1"`,`"2"`; marker path is
  `qualification/MARKER`. Q1 bytes are
  `AWA-QUALIFICATION-Q1\n` / base64
  `QVdBLVFVQUxJRklDQVRJT04tUTEK`, size `"21"`, SHA-256
  `c01efa502dabedbfe5d9d1a7cfff4f186e74d99ffa2e9f9c6c1a9fa8b529e541`.
  Q2 substitutes `Q2`, base64
  `QVdBLVFVQUxJRklDQVRJT04tUTIK`, and SHA-256
  `6b80282df498fa05da5ff173e56e701c54cc093841041c10cc4a47e4fe657fc3`.
  Each fixture is assembled independently from builds A and B and its two
  manifests must be byte-identical. Q1/Q2 manifests, version digests,
  envelopes, and signatures must differ; the runtime archive may be shared.
  Domain `awa-registration-qualification-fixtures/v1`; digest excludes
  `digest`.
- `privileged_qualification_context` has exactly `object,digest`. The object
  has exactly
  `schema,repository,exact_head,source_lock_sha256,c_runtime_scope_hash,
  packet_root_digest,qualification_nonce,qualification_root,
  qualification_allowed_signers_digest,qualification_public_key_wire_sha256,
  qualification_public_key_fingerprint,q1_release_envelope_digest,
  q1_manifest_sha256,q2_release_envelope_digest,q2_manifest_sha256,
  build_a_manifest_sha256,build_b_manifest_sha256,build_a_archive_sha256,
  build_b_archive_sha256,byte_comparison_digest,registration_test_digest,
  full_test_digest`. Every duplicated value must be byte-equal to the input
  indexes, trust contract, fixtures, and GO. Domain
  `awa-registration-privileged-qualification-context/v1`; digest is computed
  over the complete context object. It exists before any native prompt and
  breaks any packet/admin digest cycle.
- `preprompt_rejection_evidence` has exactly
  `schema,exact_head,validator_source_sha256,cases,
  syscall_denial_trace,path_remapped_harness,digest`. Cases are sorted by
  case ID and cover production-prefix, cross-nonce/root, owner-namespace,
  malformed request, expiry, signature shape, and packet/context mismatch.
  Each has exactly `case_id,input_digest,decision,reason_code` and decision
  `REFUSE`. The syscall trace proves zero write/exec/spawn/kill/AppleScript/
  privileged dispatch; the optional path-remapped harness uses only a fresh
  user-owned temporary root. All blobs are packet-root records completed
  before the bound request/context index and prompt. Domain
  `awa-registration-preprompt-rejection-evidence/v1`; digest excludes
  `digest`.
- `parent_death_evidence` has exactly
  `schema,exact_head,platform_bootstrap_contract_sha256,cases,syscall_trace,
  operator_message_results,digest`. Cases are in this exact order:
  `PARENT_DIES_PRE_WATCHDOG_SIGSTOP,OBSERVATION_ONLY_CONFIRMED_INERT,
  CONFIRMED_NATURAL_EXIT,CONFIRMED_PERSISTENT_REFUSAL,
  AMBIGUOUS_IDENTITY_REFUSAL,PID_REUSE_REFUSAL,FORGED_NONCE_REFUSAL,
  CURRENT_BOOT_RESIDUE_REFUSAL,NEW_BOOT_CLEARANCE,
  NO_PRE_GO_PRODUCT_IMPORT`. Each has exactly
  `case_id,parent_state,child_state,boot_relation,wait_elapsed_ms,decision,
  terminal_reason,process_control_calls,product_import_count,evidence_digest`;
  absent values are JSON null, counts/times are unsigned decimal strings,
  and `process_control_calls` is `"0"` for every later-invocation case.
  `syscall_trace` and `operator_message_results` are evidence-index blob
  records: the first proves no later reconciler kill/signal/process-control
  syscall, and the second proves byte-exact confirmed/ambiguous copy from
  §4.4. The direct supervising parent's separately identified direct-child
  signal case is not a later-reconciler case and proves continuous
  parent-child identity. Domain
  `awa-registration-parent-death-evidence/v1`; digest excludes `digest`.
- `admin_qualification_evidence` has exactly
  `schema,exact_head,packet_root_digest,qualification_context_digest,
  qualification_allowed_signers_digest,qualification_nonce,request_id,
  qualification_root,authorization_result,operation_results,audit_receipts,
  cleanup_result,no_residue,digest`.
  Request ID and nonce are 64 lowercase hex; root is bound to nonce;
  authorization/cleanup results are evidence blob records.
  Operation results are exactly `INSTALL_Q1,UPDATE_Q2,ROLLBACK_Q1,REMOVE,
  CANCEL` and each has exactly
  `operation,request_id,execution_kind,outcome,exit_code,stdout,stderr,
  pre_epoch,post_epoch,pre_current_manifest,post_current_manifest,
  post_previous_manifest,packet_root_digest`. Execution kind is
  `NATIVE|CANCEL_FIXTURE`. Audit receipts are parent QUALIFY plus four child
  root audits in execution order and one client cancellation receipt. All
  fields obey §5.4; cleanup result proves no root, request asset, process, or
  qualified version residue and `no_residue` is true. Domain
  `awa-registration-privileged-qualification/v1`; digest excludes `digest`.
  Before REMOVE deletes the qualification audit directory, the root
  orchestrator writes each receipt, fsyncs it, rereads and verifies it, then
  emits its exact JCS+LF bytes over an already-created bounded capture pipe.
  The unprivileged collector hashes those captured bytes into evidence; root
  cleanup removes the originals. Missing, duplicate, reordered, truncated,
  or post-cleanup-only receipts fail qualification.
- `executed_identities` is path/role sorted; each record has exactly
  `role,path,dev,ino,pid,pidversion,mapped_vnode_dev,mapped_vnode_ino,
  cdhash,sha256,packet_root_digest,digest`. PID/mapped/CDHash fields are
  lowercase hash/decimal or explicit JSON null where not applicable;
  pidversion is the exact §4.4 lowercase hash or null. It covers
  `/usr/bin/osascript`, `/bin/sh`, `/usr/bin/python3`, inline `B`, root admin,
  root entrypoint, bootstrap, child, and private Python actually observed.
  For every project-derived executable, `sha256` must equal its input blob
  built from the exact Git head; no unindexed project byte may execute.
  Platform paths/hashes equal the qualified host/toolchain records. CDHash is
  supplemental. Domain
  `awa-registration-qualified-executable-identity/v1`.
- `securityagent_result` has exactly
  `schema,invocation_id,prompt_count,result,osascript_exit_code,error_number,
  stdout,stderr,started_wall_ns,completed_wall_ns,packet_root_digest,digest`;
  prompt count is `"1"`, result is `ACCEPTED`, exit/error values are exact
  observed decimal strings, stdout/stderr are evidence blobs, and domain is
  `awa-registration-securityagent-result/v1`.
- `private_key_deletion` has exactly
  `schema,qualification_nonce,public_key_openssh,public_key_wire_sha256,
  deleted_wall_ns,private_material_absent,open_fd_matches,
  packet_private_blob_matches,packet_root_digest,digest`. It contains no
  private bytes and no private-key path. Both match counts are `"0"` and
  absence is true after close/unlink plus `ENOENT` and packet-index scans.
  Domain `awa-registration-qualification-private-key-deletion/v1`.

The gate request ID is distinct from but bound to the qualification nonce.
Per-operation request IDs are
`SHA256(ASCII("awa-privileged-qualification-request/v1") || 0x00 ||
ASCII(gate_request_id) || 0x00 || ASCII(operation))`; all request assets are
prepared before the prompt. INSTALL_Q1/UPDATE_Q2/ROLLBACK_Q1/REMOVE are
`NATIVE`.
CANCEL is the deterministic exact AppleScript `-128` fixture and has no root
process or root receipt; its client receipt is required. It does not invoke a
second SecurityAgent prompt. One accepted prompt executes exactly INSTALL Q1
→ UPDATE Q2 → ROLLBACK Q1 → REMOVE and observes:

```text
INSTALL Q1: epoch 1, current Q1, previous null
UPDATE Q2: epoch 2, current Q2, previous Q1
ROLLBACK Q1: epoch 3, current Q1, previous Q2
REMOVE: epoch 4, current null, previous null, root absent
```

The root process receives only the exact bound qualification root and positive
Q1/Q2 lifecycle inputs. Unauthorized-root/namespace/malformed vectors are
never dispatched by the prompt; they are proven only by
`preprompt_rejection_evidence`. After evidence is captured, the synthetic
private key is deleted and proven absent; no private key path or bytes enter
packet authority. The packet retains only the public preimage and deletion
proof.

The packet must show two byte-identical builds, 12 strict-valid Mach-O
records, 837 payload records, two relocations with 350 loaded images each and
zero escape, exact 23-key capability, 264/264 registration evidence, and a
clean full verification result. A differing regenerated count/hash is not
patched to the old feasibility value; it stops for review.

### 7.3 Qualification and readiness gates

The exact sequence is:

1. `V7-C-RUNTIME-IMPLEMENT` authorizes only tests-first code/contracts and
   synthetic/nonprivileged fixtures on the exact branch/scope.
2. `V7-C-RUNTIME-DELIVER` separately authorizes one Draft PR after local
   verification. C-RUNTIME may be delivered before native qualification.
3. Bugbot, Security Review, and exact-head review complete while the PR stays
   Draft and auto-merge remains unarmed.
4. An exact external `V7-C-RUNTIME-QUALIFY` naming repository, Draft PR,
   exact head, source-lock hash, and C-RUNTIME scope hash authorizes exactly
   two local, clean, nonpublishing builds plus collection of every packet
   preimage except native-admin evidence and creation of one qualification-only
   synthetic Ed25519 keypair. It authorizes no owner-key access, owner signing,
   prompt, publication, production install, or head change.
5. The two builds, Q1/Q2 double assemblies, comparisons, relocations, and test
   lanes pass. The pure validator and path-remapped harness reject every
   unauthorized-root/namespace/malformed vector with all privileged/write/
   exec syscalls denied. Exact executed bytes, rendered commands, static contracts,
   attestation preimages, Q1/Q2 envelopes/manifests/signatures, and the dynamic
   qualification-only allowed-signers contract are frozen in the packet-root
   index; then exact root-bound request/context bytes are frozen in the
   bound-input index. Both indexes are final before any prompt.
6. An exact external `PRIVILEGED-QUALIFICATION GO` naming repository, Draft PR
   number, exact head, implementation-scope hash, privileged-qualification-
   context digest, packet-root digest, qualification allowed-signers digest,
   Q1/Q2 envelope/manifest digests, qualification nonce/root, and 64-hex
   request ID authorizes exactly one native
   SecurityAgent prompt against only
   `/Library/Application Support/AWA-qualification-<qualification_nonce>`.
7. The accepted prompt starts one isolated qualification orchestrator. It
   performs the real initial bootstrap for Q1, then invokes the installed
   immutable admin entrypoint as a root child for exact UPDATE Q2, ROLLBACK Q1,
   and REMOVE requests, all under the one bound qualification root; REMOVE
   deletes the admin last. The
   cancellation renderer/result is tested only through the deterministic
   `-128` fixture, never a second prompt. Audit, executed-byte identity, and
   cleanup prove complete removal and produce §7.2 evidence. The gate does not
   authorize testing, reading, writing, or executing privileged code against
   `/Library/Application Support/AWA`, another nonce/root, publication,
   activation, or another prompt. Failure or residue stops; Developer ID is
   not pre-authorized.
8. The synthetic private key is closed, unlinked, and proven absent; only its
   public preimage/deletion proof remains. Admin evidence and the evidence
   index finalize the packet. Generating/reviewing it accesses no owner private
   key and publishes no asset.
9. An exact external `C-RUNTIME-QUALIFICATION GO` names the immutable packet
   digest, packet-root, bound-input-index, and evidence-root digests, exact
   head, PR, source-lock hash, and privileged-evidence digest.
   It accepts evidence only; it authorizes no signing/publication/install.
10. Only then may `V7-C-RUNTIME-READY` name the same exact head, clean reviews,
   packet digest, privilege GO/result, and passing checks. The reviewer App
   alone may approve/arm native auto-merge and merge.
11. C-FINAL starts only after the exact C-RUNTIME merge commit is live on main.

The Q1/Q2 release envelopes are signed only by the one-use synthetic key
created outside production and packet paths, bound to exact head, nonce/root,
packet root, dynamic contract, and fixture digests. The key exercises fixed
`/usr/bin/ssh-keygen` under only the qualification namespace; production
structurally rejects it. No owner signature or owner private key exists at
this stage.

Any C-RUNTIME head change invalidates both qualification records and requires
fresh evidence and exact GOs. Plan acceptance grants none of these gates.

---

## 8. Branched authority DAG

The authority graph is intentionally not a false linear hash chain:

```text
public source lock + verified attestation
        │
        ├── build A: normalizer/recipe/toolchain
        │      └─ normalized tree
        │          ├─ capability + compile options
        │          ├─ per-Mach-O signature inventory
        │          ├─ build manifest + archive
        │          └─ transcript + SBOM/licenses + tests
        │
        └── build B: same branches
                 └─ byte-equality + relocation/load-image evidence
                              │
privileged qualification ─────┴── qualification packet
                                         │
                                         └─ runtime release envelope
                                            + detached owner signature

static v2/bootstrap/privilege contracts
        + root entry/bootstrap/child exact bytes
        └─ bootstrap authority

AWA bundle-entry plain hash
        └─ import-manifest record
             └─ installed_file_hash of receiver payload
                  └─ AWA bundle manifest

bootstrap authority + runtime release envelope + AWA bundle manifest
        └─ expected direct/shadow denial-vector construction
             └─ denial_proof_vector_hash (expected bytes)

receipt body ───────────────────────────────────────────┐
successor enrollment ──────────────────────────────────┤
runtime envelope + expected denial vector + bundle ────┤
                                                       └─ owner gate v3
                                                           └─ owner_gate_digest
receipt body + owner_gate_digest
        └─ final receipt digest
             └─ generation pointer
                  └─ readiness/promotion authority

staged installation after signing
        └─ observed direct/shadow execution evidence
             └─ exact comparison with expected vector
                  └─ readiness evidence only
```

The bundle-entry plain hash and `installed_file_hash` are distinct; the latter
binds the installed receiver payload. Expected denial vectors are constructed
before owner-gate signing. Observed staged execution occurs later and must
equal expected direct/shadow results, but it never feeds back into the signed
expected vector, receipt body, owner gate, or final receipt digest. Final
receipt digest includes `owner_gate_digest`. Pointer/readiness are downstream.
All accepted-v5 Body C A09/A10 and generated vector expectations must be
regenerated from this DAG; no old linear vector or external-interpreter hash
survives.

---

## 9. Exact implementation scope and bodies

### 9.1 Closed 53-path scope

```text
Makefile
build/private-runtime/README.md
build/private-runtime/build.sh
build/private-runtime/manifest.py
build/private-runtime/sources.lock.json
contracts/awa-contract.v1.json
contracts/awa-contract.v2.json
contracts/awa-registration-admin-audit.v1.json
contracts/awa-registration-owner-signers.v1
contracts/awa-registration-owner-signers.v2
contracts/awa-registration-platform-bootstrap.v1.json
contracts/awa-registration-private-runtime.v1.json
contracts/awa-registration-privileged-envelope.v1.json
engine/registration_hook_runtime.py
engine/registration_host.py
engine/registration_installer.py
engine/registration_launcher.py
engine/registration_privileged_installer.py
engine/registration_profile.py
engine/registration_projection.py
engine/registration_receiver.py
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
  ASCII("awa-registration-v7-implementation-scope/v4") || 0x00 ||
  for each path sorted by UTF-8 bytes: UTF8(path) || LF
) =
7466d991a3448ae15f9fcb6032c7a31d87010c1d466ef2d134edf0d60e6c29b2
```

`test_contract_schemas.py` is mandatory because live main asserts that v2
does not exist; `test_install_lib.py` and `test_verify_lane.py` are the
transitive install/freeze owners. Projection is explicitly included. Other
existing cross-body/JCS/schema/predicate tests run but are not editable unless
already listed. Spawn-intent persistence/reconciliation belongs in the listed
bootstrap/launcher/privileged-installer surfaces and
`test_registration_parent_death.py`; no registration launchd product path
exists on live main, host activation remains separately gated, and adding a
daemon/job is not authorized. The closed scope therefore remains 53 paths. A
required 54th path is a stop and successor-plan finding.

### 9.2 Body C-RUNTIME

Branch:

```text
impl/native-entry-durable-registration-v7-runtime-bootstrap
```

It starts from then-live main in a separate clean worktree. Its exact 49-path
ceiling is §9.1 minus:

```text
engine/registration_hook_runtime.py
engine/tests/test_registration_hook_runtime_c.py
live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
live-verify/native-entry-durable-registration-r0.py
```

```text
SHA256(
  ASCII("awa-registration-v7-c-runtime-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) =
704fabc0e15f2a87a9902ea8d6ded4c3b0fe0c29112870fa0ceb0bbb9300ede6
```

Tests first, then implement source lock/build tooling, all successor contracts,
public signature verification, root/private runtime installer and state
machine, dynamic qualification-only trust, Q1/Q2 fixtures, platform
parent/child bootstrap and durable spawn-intent reconciliation, shared
measurement, wrappers, profile/projection/launcher/receiver integration,
synthetic filesystem/admin fixtures, the exact operation/outcome matrix, and
every exact vector. Deliver
`contracts/awa-registration-owner-signers.v1` byte-identically at
`9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e`
so historical gate-v2 verification exists on live main. It is
an intentional unchanged-content addition, not a mutation.

C-RUNTIME is production-forward because it lands the complete protected
runtime/bootstrap/admin boundary, but does not publish assets, invoke native
authorization before §7.3, install production paths, sign, activate, or run
R0. Its exact-head qualification packet must bind the exact executed bytes;
the disposable prompt and packet GOs remain readiness gates, not delivery
authority.

### 9.3 Body C-FINAL

Branch:

```text
impl/native-entry-durable-registration-v7-body-c
```

It starts only from the merged C-RUNTIME live-main commit and reconciles the
preserved working manifest. Its exact 24-path ceiling is §2.2 plus:

```text
live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
```

```text
SHA256(
  ASCII("awa-registration-v7-c-final-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) =
1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8
```

It completes accepted-v5 Body C deployment authority, receiver continuity,
expected/observed denial separation, final receipt/pointer vectors, and
truthful check-only R0 without restoring external-interpreter/config-v1
authority.

### 9.4 Per-body delivery discipline

| Body | Local implementation | Draft delivery | Exact-head readiness |
|---|---|---|---|
| C-RUNTIME | `V7-C-RUNTIME-IMPLEMENT` | `V7-C-RUNTIME-DELIVER` | `V7-C-RUNTIME-READY` after §7.3 |
| C-FINAL | `V7-C-FINAL-IMPLEMENT` | `V7-C-FINAL-DELIVER` | `V7-C-FINAL-READY` |

Each local gate names accepted v7 digest, live base, branch, body scope/hash,
starting preservation manifest, and tests-first authority. Each delivery gate
names the reviewed changed subset and permits exactly one Draft PR. Each
readiness gate binds exact head, full/focused checks, Bugbot, Security Review,
and required qualification. PRs remain Draft and auto-merge unarmed until
readiness. Only the reviewer App may approve, arm native auto-merge, and merge.
Agents never enable, disable, arm, invoke, or bypass auto-merge.

Two serial bodies are sufficient: the runtime/bootstrap dependency must merge
before preserved Body C can safely finish; a third body would add no
independent production boundary.

---

## 10. Acceptance and regression ledger

| ID | Required evidence | Refusal |
|---|---|---|
| V7-A01 | Exact source-lock JCS+LF/hash; install/full-build/SHA256SUMS/PYTHON.json names, paths, URLs, sizes, hashes; exact-one SLSA-v1 selector reproducing bundle JCS+LF hash; release-v0.2 rejected | Unpinned input, ambiguous/multiple attestation, wrong predicate/workflow/subject, guessed field, or source-lock drift |
| V7-A02 | Two clean builds; exact normalizer/signing source preimages; byte-identical trees/archives; 12 strict-valid Mach-O records; 837 manifest records | Placeholder/future hash, nondeterminism, stale signature, or count drift |
| V7-A03 | Two relocations; 350 loaded-image records each; only private root/System/usr/lib; zero escapes; exact rpath/CDHash/inventory agreement | Unexpected image/root/rpath/CDHash or missing raw evidence |
| V7-A04 | Capability object exactly 23 accepted-v5 keys/types/semantics; CPython 3.14.8, SQLite 3.53.1, OpenSSL 3.5.9; compile-options object separately contains THREADSAFE | Shape-only validation, caller capability, or invented capability field |
| V7-A05 | Six static successor artifacts reproduce exact embedded bytes/hashes; v1 signer delivered exact; contract v1 stays exact; dynamic field mutation corpus; external/config-v1 authority refuses before import | Omitted value/array, inferred predecessor semantics, frozen-v1 edit, compatibility fallback, or hash drift |
| V7-A06 | Root:wheel, 0755/0555/0444, regular/nlink-one/no-symlink/no-write ancestry and canonical current/version-lock invariants; same-path replacement plus forged/missing/mismatched current/release/manifest records | User-writable, linked, symlinked, noncanonical, stale, replaced, or unbound object |
| V7-A07 | Public owner verification under exact v1/v2 namespaces, current/successor enrollment predecessor rules, malformed/wrong principal/key/namespace negatives, zero owner-private-key access/signing; synthetic key allowed only under exact QUALIFY nonce/root/namespace and deleted afterward | AWA accesses owner key material, owner-signs, lets synthetic authority cross into production, or crosses namespaces |
| V7-A08 | Initial pathless inline bootstrap; exact AppleScript/shell/argv rendering; only UID/request argv; retained O_NOFOLLOW assets; same-user swap/rebind matrix; dynamic qualification anchor bound to nonce/root/head/packet/Q1/Q2; pure pre-prompt production/cross-binding/owner-namespace/malformed rejection with privileged/write/exec syscalls denied | Caller path/shell/env, credential handling, detached bytes, path race, privileged negative test against an unauthorized root, or qualification trust accepted in production |
| V7-A09 | Production install/update/rollback/remove plus one-prompt Q1 install → Q2 update → Q1 rollback → remove; distinct manifests/epochs; no-replace/fsync/reopen; locks/retention; every crash/recovery boundary; root admin last-in/last-out | Partial success, fixture conflation, production fixture acceptance, active removal, overwrite, implicit rollback, unknown cleanup, or lingering root process |
| V7-A10 | Exact 20-row operation/outcome matrix with JCS null; complete audit fields/formula; cancellation vs refusal/failure/success; receipt failure blocks success; public-only synthetic-key deletion evidence and complete disposable cleanup | Empty/sentinel ambiguity, bare success, unaudited root write, retained private material/path, or residue |
| V7-A11 | Ordinary spawn with only CLOEXEC_DEFAULT; source fds duplicated >=10; exact targets 3–8; collision/EMFILE/partial-spawn/all-close matrix | Suspended-spawn dependency, inherited fd, target close, or leak |
| V7-A12 | Parent verifies all authority and shared lock before spawn; durable PREPARED/SPAWNED intent; child parent-PID/EOF watchdog; original parent alone may signal/reap its continuously identified direct child; mapped vnode/CDHash supplemental; READY/GO/IMPORT_READY | Child-local path proof, unlocked version, missing pre-spawn fsync, transferred signal authority, or mapped evidence treated as sole authority |
| V7-A13 | Parent-first observation-only reconciliation; exact live-pair preservation across PREPARED/SPAWNED/READY/GO/PRODUCT concurrent routes; parent death + pre-watchdog SIGSTOP; later-invocation zero-signal proof; natural exit; persistent/ambiguous/current-boot refusal with exact operator copy; parent/child PID reuse; forged nonce; new-boot clearance; no-next-entry persistence; and zero pre-GO import | Live supervised child touched, any later-process signal/adoption/continuation, same-boot clearance, unconditional no-orphan/bounded-cleanup claim, raced import, or false success |
| V7-A14 | All four wrappers invoke only fixed root entrypoint; platform parent imports zero product modules/opens zero registration SQLite; hostile env/cwd ignored | Overlay authority, platform product execution, or pre-import side effect |
| V7-A15 | Branched DAG vectors distinguish bundle plain hash/receiver installed hash, expected denial before signing, receipt body/gate/final receipt, pointer/readiness, and later observed evidence | Linearized hash, launcher/receiver conflation, observed feedback into signed expected vector, or stale A09/A10 |
| V7-A16 | Qualification packet packet-root/bound-input/evidence indexes plus final digest, exact executed/bootstrap/rendered/request/contract/Q1/Q2 preimages, observed path/dev/inode/PID/pidversion/mapped/CDHash identities, parent-death observation-only syscall/message evidence, SecurityAgent result, exact head, two-build equality, tests | Digest cycle, fabricated value, mutable/missing executed byte, wrong head, missing no-signal evidence, incomplete packet, or packet drift |
| V7-A17 | Current 23-path report; projection/profile/store/deployment/installer/launcher/receiver/host/hook/packaging vectors; every accepted-v5 Body C and A/B independence/fault test | Dirty work lost, blanket-applied, weakened assertion, or omitted transitive lane |
| V7-A18 | 264/264 registration evidence; full `make verify-pre-pr`; py_compile; shell syntax; install/freeze/contracts; exact diff/cached/status/scope audit; no runner | Skipped required lane, unrelated threshold change, scope escape, or paid runner |

Generated vectors/hashes must be regenerated from exact bytes, never copied
from placeholders or the non-authoritative feasibility note. Existing Body C
and cross-body tests remain; additions do not replace them.

---

## 11. Non-goals and later gates

V7 plan acceptance does not:

- implement or deliver either body;
- build or publish a runtime or qualification packet;
- request native authorization or mutate `/Library/Application Support`;
- access owner private-key material or produce an owner signature;
- publish successor enrollment, release assets, tag, or release;
- run install/activation/R0/R1/C1/R2/rollout;
- commit generated 99 MB-class assets;
- add hosted/self-hosted GitHub Actions runners;
- make platform Python the product runtime;
- add Developer ID, daemon, setuid, sudo/password, persistent root, or paid
  dependency;
- alter accepted v5/v6/ADR or unaffected architecture; or
- vendor authority into `~/dev`, Skills, or cpp.

After both bodies merge, owner signing, release/tag/asset publication,
production install, Skills pointer update, `~/dev` host activation, R0, R1,
C1, and R2 remain separately named gates in accepted order. The disposable
privileged qualification is not a production-install precedent.

---

## 12. Exact v7 plan acceptance

### 12.1 Status-only authority

Exact-byte owner acceptance authorizes only:

1. this status line:
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. the v7 index status:
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-03`;
3. the v6 index status:
   `SUPERSEDED BY V7 — 2026-10-03`.

Accepted v5/v6 files remain byte-identical. Acceptance authorizes no code,
build, delivery, prompt, signing, publication, privileged operation, or
rollout.

### 12.2 Anti-replay normalized digest

```text
SHA256(
  ASCII("awa-registration-v7-normalized/v3") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

`normalized_plan_bytes` replaces exactly one complete DRAFT or ACCEPTED status
line with:

```text
- **Status:** __AWA_V7_STATUS__
```

`normalized_index_bytes` replaces exactly one complete v7 DRAFT/ACCEPTED row
with:

```text
| `native-entry-durable-registration-v7.md` | __AWA_V7_INDEX_STATUS__ | Protected private-runtime successor to accepted v6; binds exact SLSA source authority, observation-only pre-import residue refusal, exact executed-byte qualification, qualification-only trust, and a separately gated root-confined disposable native privilege proof. |
```

and exactly one complete v6 ACCEPTED/superseded row with:

```text
| `native-entry-durable-registration-v6.md` | __AWA_V7_PREDECESSOR_INDEX_STATUS__ | Bounded successor to accepted v5 under ADR 0026; restores Body A's typed fresh-basis, same-boot snapshot, and atomic R1-scope providers before Body B resumes. |
```

Each replacement includes one LF. Zero, duplicate, mixed, non-UTF-8, CRLF,
NUL, or non-exact context refuses. Simulated promotion must produce identical
normalized plan/index bytes and digest.

### 12.3 Exact owner acceptance envelope

External acceptance is one JCS object with exactly these keys and values:

```json
{"accepted_v5_file_sha256":"4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b","accepted_v5_normalized_digest":"f4d222435da9c7eb323d0e4c92fe0997f88beb92c56a85dad7cd96704361be94","accepted_v5_receipt_hash":"c27746a232275380bfca5cba110d4533813cdc4e9b4a3710629a9c34742706a6","accepted_v6_file_sha256":"ee8e4fcadd2951fcf3b4260aa5a4672ef98247a2839d7ad53a7ea2d6e02f6a47","accepted_v6_normalized_digest":"1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452","action":"ACCEPT_PLAN_V7","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","allowed_signers_contract_hash":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","attestation_bundle_jcs_lf_sha256":"71ee6bcb100ad2474d01dce968125fa631f2e28616c21ddf67364d2ef7ca94d3","authorized":true,"authorized_actions":["MARK_V6_INDEX_SUPERSEDED","PROMOTE_V7_INDEX_STATUS","PROMOTE_V7_PLAN_STATUS"],"authorized_by":"KleinPerkins","body_c_final_scope_count":24,"body_c_final_scope_hash":"1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8","body_c_runtime_scope_count":49,"body_c_runtime_scope_hash":"704fabc0e15f2a87a9902ea8d6ded4c3b0fe0c29112870fa0ceb0bbb9300ede6","body_c_working_manifest_hash":"9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a","current_receipt_sha256":"a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411","denied_implications":["ACCESS_OWNER_PRIVATE_KEY_OR_OWNER_SIGN","ALTER_PRESERVED_BODY_C_WORK","BUILD_OR_PUBLISH_RUNTIME","COMMIT_PUSH_OR_OPEN_PR","GENERATE_QUALIFICATION_KEY","IMPLEMENT_OR_DELIVER_BODY_C","INVOKE_NATIVE_AUTHORIZATION_PROMPT","MUTATE_EXTERNAL_STATE","PRIVILEGED_PRODUCTION_OPERATION","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","enrollment_hash":"885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4","implementation_scope_count":53,"implementation_scope_hash":"7466d991a3448ae15f9fcb6032c7a31d87010c1d466ef2d134edf0d60e6c29b2","live_base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","normalized_digest":"<reviewed lowercase 64-hex>","repository":"KleinPerkins/awa","schema":"awa-registration-v7-plan-acceptance-go/v4","source_lock_jcs_lf_size":3654,"source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","static_contract_hashes":{"contracts/awa-contract.v2.json":"db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a","contracts/awa-registration-admin-audit.v1.json":"a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a","contracts/awa-registration-owner-signers.v1":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","contracts/awa-registration-owner-signers.v2":"690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3","contracts/awa-registration-platform-bootstrap.v1.json":"4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c","contracts/awa-registration-private-runtime.v1.json":"f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321","contracts/awa-registration-privileged-envelope.v1.json":"7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034"}}
```

The three angle-bracket values are replaced only in the externally submitted
envelope. Its receipt-independent anti-replay digest is:

```text
acceptance_envelope_digest =
  SHA256(ASCII("awa-registration-v7-plan-acceptance-envelope/v1") || 0x00 ||
         JCS(concrete_external_envelope) || LF)
```

Future normalizer/signing/output/packet/admin evidence hashes are
deliberately absent. Before promotion, revalidate every frozen authority,
static contract/source-lock/scope/body-manifest hash, live base, draft
plan/index hashes, exact key/array order, and denied implication. Promotion
changes only three status surfaces. Reread both files and require normalized
equivalence.

---

## 13. Fresh standalone four-pass review and stop conditions

### Pass 1 — facts

Live main and frozen authorities were independently rechecked. The existing
wrappers reach product imports before a verified root bootstrap; current
Body C remains exactly the bound 23-path working set; v1 contract tests
explicitly reject a v2 file and are therefore transitive scope; the qualified
Astral source pin is public and reproducible. Live release metadata reports
the exact three named assets and exactly two attestations for the artifact:
one uniquely matching SLSA provenance v1 record and one non-authoritative
release-v0.2 record. Darwin supplies no atomic parent-death binding before a
child watchdog arms and no pidfd-style identity-bound signalling primitive
that lets a later invocation safely target a discovered PID. No production
private runtime or privileged AWA install exists.

### Pass 2 — gaps closed

This revision removes generated output hashes from plan acceptance; specifies
an exact-head three-index packet with every executed/rendered byte; freezes the
exact SLSA-v1 selector and full-build/PYTHON metadata; replaces suspended
execution with immutable-version locking, durable spawn intent, an immediate
watchdog, and parent-first observation-only reconciliation that leaves every
coherent live supervisor/child pair untouched, never signals from a later
invocation, permits bounded observation for natural exit, and makes reboot the
guaranteed cleanup boundary; freezes FD collisions;
defines pathless initial and immutable-admin privilege protocols plus the
20-row null-exact outcome matrix; binds a one-use qualification-only trust
anchor, explicitly separates prohibited owner-key access/signing from the
bounded synthetic qualification key, and distinct double-built Q1/Q2
releases; adds a root-confined disposable prompt whose unauthorized-root
negatives run only in a syscall-denied pure validator or user-owned remap
harness; delivers v1 signer bytes; embeds every static successor contract;
enumerates all dynamic schemas; breaks packet/evidence digest cycles; and
restores the true branched authority DAG.

### Pass 3 — subtraction

One private runtime, one source pin, one root entrypoint, one stdlib parent,
one child bootstrap, one content-addressed version store, one current record,
one admin path, one qualification packet, one disposable keypair, and two
serial bodies remain. Q1/Q2 share the qualified runtime but differ only where
needed to prove update/rollback. No daemon, suspended-spawn dependency, setuid
helper, alternate runtime,
Developer ID assumption, third body, runner, committed runtime blob, or
ecosystem copy remains. No signal broker, pidfd emulation, daemon, or
later-process cleanup mechanism is introduced; refusal plus reboot is the
smaller honest boundary.

### Pass 4 — demonstrated under-scope

The 53 paths include the five runtime/launcher/installer/projection/receiver
surfaces, all four wrapper routes, privileged installer, build/static
contracts, parent-death/privilege tests, current projection test, and the
demonstrated contract/install/freeze transitive tests. Existing JCS/schema/
predicate/cross-body suites run unchanged. C-RUNTIME is the prerequisite;
C-FINAL preserves accepted Body C. Observation-only reconciliation and its
packet evidence fit the existing bootstrap/launcher/parent-death-test paths;
live main has no registration launchd product path and no daemon/job is
justified. No implementation may begin before exact plan acceptance and its
separate body gate.

Implementation or qualification stops for:

- live base, accepted authority, enrollment, receipt, signer contract, Body C
  manifest, source lock, static contract, or scope drift;
- a needed 54th path, third body, v1 semantic mutation, or unspecified schema;
- upstream attestation/toolchain/source mismatch or nonreproducible build;
- capability not exactly 23 accepted-v5 fields/semantics;
- inability to close a measurement/probe/spawn/import race, guarantee zero
  pre-GO product import, preserve observation-only later reconciliation, or
  refuse ambiguous/current-boot residue without signalling or continuation;
- inability to prove exact AppleScript/shell/argv rendering, retained-asset
  authority, qualification-only trust separation, Q1/Q2 distinctness,
  no-replace publication, exact outcome matrix, audit, synthetic-key deletion,
  or complete disposable cleanup;
- any native qualification failure/residue; Developer ID or another privilege
  mechanism requires a successor decision;
- any owner-private-key dependency/access, owner-signature generation by AWA,
  synthetic key outside exact QUALIFY mode/nonce/root/namespace, runner,
  committed generated runtime, persistent root process, setuid helper, or
  dependency escape; or
- authoritative live config-v1/external-runtime state requiring migration.

Residual uncertainty is deliberately deferred to exact-head evidence: future
normalizer/signing bytes and generated hashes, deterministic two-build and
Q1/Q2 equality, mapped-vnode/CDHash and observation-only pre-watchdog-residue
behavior on the implementation head, and one disposable SecurityAgent
qualification.
The upstream selector and current public attestation/asset preimages are now
frozen; future generated outputs remain deliberately unknown. None may be
inferred from the feasibility run or this plan.
