# Native Entry Durable Registration

- **Version:** v10
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-10-04
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v9.md`](native-entry-durable-registration-v9.md),
  preserved byte-identically at SHA-256
  `69110832b1acb00e7250dd4b5b0420354b023e46f204d9ee521f48f3eb33f525`
  and normalized digest
  `c8ed54298a5d0e074744be79670158feaec27d870c66dd4fd365d7dd67899703`.
- **Inherited authority:** accepted v9 index SHA-256
  `1c021a1cfdd4e0f085f67e08e23fdcade0539b0cbe17fd507f47f67938e51ca6`;
  accepted v8 plan SHA-256
  `1009c3f2e950fcf88adc1f2a862e7127c9d8bb36001389e6ed22bed347a3e770`;
  immutable [ADR 0026](../adr/0026-durable-registration-authority-hardening.md)
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
  implemented v9 C-RUNTIME 59-path manifest
  `e7576bba802cfb06822f0bd54f436e1e7a7596a7db8c3cde445cb5d94ac3c0f7`;
  exact 20-path changed-subset digest
  `5b20759388fac04217583a8208d30615204bd4c641227731316ff72ee923a8d6`.

> **Governance stop:** this draft authorizes only this new file and its DRAFT
> README row. It authorizes no test or implementation edit, staging, commit,
> push, PR, build, packet, key access/generation/signing, native prompt,
> privileged operation, installation, publication, release, activation,
> R0/R1/C1/R2, external mutation, or rollout.

---

## 1. Valid stop and smallest successor

Independent adjudication returned `VALID_STOP` for v9 C-RUNTIME. The complete
local gate exposed exactly one stale test authority:
`engine/tests/test_kernel_off_matrix.py`. Its raw whole-file token scans
conflate accepted registration-product synchronization and descriptor
transport with forbidden worktree protection:

1. accepted v8 requires exclusive admin/current/version locks, retained shared
   version locks, spawn-intent serialization and collision-free
   `F_DUPFD_CLOEXEC` descriptor remapping;
2. the old scan rejects every `flock` and `fcntl` token anywhere under
   `kernel/`, regardless of target or operation;
3. Darwin process identity requires the exact `_VinfoStat.vst_flags` ABI field
   declaration, while the old scan rejects the declaration as if it were an
   immutable-flag operation.

The production behavior is accepted authority and is not renamed or weakened
to evade a scanner. V10 adds exactly the existing test path and replaces only
those two lexical assertions with closed semantic inventories. Every other
v9/v8/v7/v6/v5/ADR requirement, current implementation byte, contract,
schema, test and gate remains normative and byte-identical.

There is no new production path, static contract, schema, digest domain,
runtime byte, receipt, gate, packet field, executable, body, or rollout
action.

---

## 2. Complete deterministic scanner

### 2.1 Closed file universe

The later implementation changes only
`engine/tests/test_kernel_off_matrix.py`. It walks every descendant of
`kernel/` in UTF-8 byte-path order. A symlink, unreadable object or non-regular
leaf refuses. Exact handling is:

- `*.py`: strict UTF-8, no NUL, parsed by `ast.parse`;
- `*.sh`: strict UTF-8, no NUL/CR, tokenized by the shell grammar below;
- `*.yml`: strict UTF-8 declarative data; any advisory-lock, descriptor-control
  or immutable-flag primitive token refuses;
- `__pycache__/**` and `*.pyc`: generated outputs excluded before traversal;
- any other suffix: refuses until this plan is superseded.

Comments are omitted by `ast.parse`; Python docstring `Expr(Constant(...))`
nodes remain in the frozen scope AST and therefore affect its digest.
No file is clean by filename. There is no `_LOCK_EXEMPT`,
`_FSYNC_ONLY_FCNTL`, early return, basename exemption or token-renaming path.

### 2.2 Canonical Python and shell bytes

The implementation uses no semantic prose or variable-name allowlist.
It requires CPython with `sys.version_info[:2] == (3,14)` and parses strict
UTF-8 source with exactly
`ast.parse(source, filename=path, mode="exec", type_comments=False,
feature_version=(3,14), optimize=-1)`. Any other AST schema refuses. It
assigns each nested class/function/async-function its dot-qualified lexical
name and visits a selected scope with this exact preorder:

```python
def preorder(node):
    yield node
    for child in ast.iter_child_nodes(node):
        yield from preorder(child)
```

`D(node)` is exactly
`ast.dump(node, annotate_fields=True, include_attributes=False)`. Scope and
node authorities are:

```text
scope_digest = SHA256(
  ASCII("awa-kernel-python-scope/v1") || 0x00 ||
  UTF8(path) || 0x00 || UTF8(qualname) || 0x00 || UTF8(D(scope)) || LF
)
node_digest = SHA256(
  ASCII("awa-kernel-python-node/v1") || 0x00 ||
  UTF8(path) || 0x00 || UTF8(qualname) || 0x00 ||
  ASCII(preorder_index) || 0x00 || UTF8(D(node)) || LF
)
```

Each node selector is exactly
`{path,qualname,preorder,node_type,ast_sha256}`. Each scope selector is
exactly `{path,qualname,ast_sha256}`. Duplicate qualified names, missing
selectors, wrong node types or digest mismatch refuse. Freezing the complete
scope AST, rather than a reconstructed data-flow summary, binds every
cross-statement assignment, branch, helper call, opener flag/mode, metadata
check, callback, release and close in that scope. No graph encoding is
needed or permitted.

The one approved shell bridge has the stricter canonical encoding
`{path:"kernel/bin/dev-worktree.sh",encoding:"EXACT_UTF8_LF_FILE",sha256:
"b25f238a929036301443697da871dd8300fdb3708bf61c1e3c2bf5e3da4e6042"}`.
It hashes the complete exact regular-file bytes; CR, invalid UTF-8, NUL,
symlink or any byte drift refuses. Synthetic shell fixtures still use the
§2.5 grammar to prove indirect forbidden forms bite.

### 2.3 Exact branch and path authority

Generic branch-dependent, loop-carried, closure, reflective or unresolved
provenance refuses. The only branch-dependent lock roots are the following
three canonical records. A record contains exactly
`schema,id,environment_reads,branches,suffix_chain,scope_chain`; objects use
JCS, arrays preserve displayed order, and no extra key is allowed.

Expression objects have exactly one `op` from
`STR_TRUTHY`, `NOT_STR_TRUTHY`, `ELSE`, `PY_OS_PATH_EXPANDUSER`,
`PATH_EXPANDUSER`, `OS_PATH_JOIN`, `PATH_DIV_CHAIN`, `OS_PATH_ABSPATH`,
`UTF8_ENCODE`, `SHA256_HEX_PREFIX`, `FORMAT`, or `RAISE`, plus only the
arguments displayed for that operation. A value reference is exactly one of
`{"binding":string}` or `{"const":string}`. `PY_OS_PATH_EXPANDUSER` freezes
the source call and its POSIX resolution branches: non-tilde identity,
`HOME` exact value when present, `pwd.getpwuid(os.getuid()).pw_dir` for bare
tilde when `HOME` is absent, and `pwd.getpwnam(name).pw_dir` for named tilde.
No other environment key, expansion API, normalization or fallback passes.

This normative pseudocode constructs the exact records; `S(path,names)`
returns the ordered §2.2 scope-selector objects and `JCS` sorts object keys:

```python
import copy

def C(value): return {"const": value}
def V(value): return {"binding": value}
def EXPAND(value):
    return {
        "argument": value,
        "non_tilde": "IDENTITY",
        "op": "PY_OS_PATH_EXPANDUSER",
        "tilde_resolution": [
            "HOME_IF_PRESENT_EXACT_VALUE",
            "PWD_GETPWUID_FOR_BARE_TILDE_WHEN_HOME_ABSENT",
            "PWD_GETPWNAM_FOR_NAMED_TILDE",
        ],
    }
def GET(key):
    return {"api": "os.environ.get", "default": "", "key": key,
            "postprocess": "str.strip"}

finish_branch = {
    "branches": [
        {"predicate": {"binding": "XDG_STATE_HOME_STRIPPED",
                       "op": "STR_TRUTHY"},
         "result": EXPAND(V("XDG_STATE_HOME_STRIPPED"))},
        {"predicate": {"op": "ELSE"},
         "result": {"arguments": [EXPAND(C("~")), C(".local"), C("state")],
                    "op": "OS_PATH_JOIN"}},
    ],
    "environment_reads": [GET("XDG_STATE_HOME")],
    "id": "finish-common-lock-path",
    "schema": "awa-kernel-branch-authority/v2",
    "scope_chain": S("kernel/lib/awa_finish.py",
                     ["_state_home", "awa_state_dir", "locks_dir",
                      "common_dir_key", "lockfile_for"]),
    "suffix_chain": [
        {"arguments": [V("STATE_HOME"), C("awa")], "op": "OS_PATH_JOIN"},
        {"arguments": [V("AWA_STATE_DIR"), C("locks")], "op": "OS_PATH_JOIN"},
        {"bytes": {"op": "UTF8_ENCODE",
                   "value": {"argument": V("GIT_COMMON_DIR"),
                             "op": "OS_PATH_ABSPATH"}},
         "length": 24, "op": "SHA256_HEX_PREFIX"},
        {"arguments": [V("LOCKS_DIR"),
                       {"op": "FORMAT",
                        "parts": [C("common-"), V("COMMON_DIR_KEY"),
                                  C(".lock")]}],
         "op": "OS_PATH_JOIN"},
    ],
}
roots_branch = copy.deepcopy(finish_branch)
roots_branch["id"] = "roots-common-lock-path"
roots_branch["scope_chain"] = S(
    "kernel/lib/awa_roots.py",
    ["_state_home", "awa_state_dir", "locks_dir", "_common_dir_key"])
roots_branch["suffix_chain"][2]["bytes"]["value"]["argument"] = V("COMMON_DIR")

handoff_branch = {
    "branches": [
        {"predicate": {"binding": "XDG_STATE_HOME_STRIPPED",
                       "op": "STR_TRUTHY"},
         "result": {"argument": V("XDG_STATE_HOME_STRIPPED"),
                    "op": "PATH_EXPANDUSER"}},
        {"predicate": {"binding": "HOME_STRIPPED",
                       "op": "NOT_STR_TRUTHY"},
         "result": {"exception": "HandoffUnavailable",
                    "message": "HOME is unavailable", "op": "RAISE"}},
        {"predicate": {"op": "ELSE"},
         "result": {"arguments": [
             {"argument": V("HOME_STRIPPED"), "op": "PATH_EXPANDUSER"},
             C(".local"), C("state")], "op": "PATH_DIV_CHAIN"}},
    ],
    "environment_reads": [GET("XDG_STATE_HOME"), GET("HOME")],
    "id": "handoff-lock-path",
    "schema": "awa-kernel-branch-authority/v2",
    "scope_chain": S("kernel/lib/awa_handoff.py",
                     ["_state_home", "handoff_dir", "lock_path"]),
    "suffix_chain": [
        {"arguments": [V("STATE_HOME"), C("awa"), C("handoff")],
         "op": "PATH_DIV_CHAIN"},
        {"arguments": [V("HANDOFF_DIR"), C(".lock")],
         "op": "PATH_DIV_CHAIN"},
    ],
}
```

| ID | Exact source outcome set | Exact ordered scope selectors | Branch-authority digest |
|---|---|---|---|
| `finish-common-lock-path` | `XDG_STATE_HOME = os.environ.get("XDG_STATE_HOME","").strip()`; truthy → `os.path.expanduser(XDG_STATE_HOME)`; falsey → `os.path.join(os.path.expanduser("~"),".local","state")`; then `os.path.join(STATE_HOME,"awa")`, `os.path.join(AWA_STATE_DIR,"locks")`, `sha256(os.path.abspath(git_common_dir).encode("utf-8")).hexdigest()[:24]`, and `os.path.join(LOCKS_DIR,f"common-{COMMON_DIR_KEY}.lock")` | `kernel/lib/awa_finish.py#_state_home,awa_state_dir,locks_dir,common_dir_key,lockfile_for` | `d5192ffa36037ff6a886a7d93981e679f0415f2022a832796521ef37f8097c64` |
| `roots-common-lock-path` | `XDG_STATE_HOME = os.environ.get("XDG_STATE_HOME","").strip()`; truthy → `os.path.expanduser(XDG_STATE_HOME)`; falsey → `os.path.join(os.path.expanduser("~"),".local","state")`; then `os.path.join(STATE_HOME,"awa")`, `os.path.join(AWA_STATE_DIR,"locks")`, `sha256(os.path.abspath(common_dir).encode("utf-8")).hexdigest()[:24]`, and `os.path.join(LOCKS_DIR,f"common-{COMMON_DIR_KEY}.lock")` | `kernel/lib/awa_roots.py#_state_home,awa_state_dir,locks_dir,_common_dir_key` | `ca69f4663cdb321001b5cba8e53a60e2c9713c8ee85e548a9b186e7934ef2144` |
| `handoff-lock-path` | `XDG_STATE_HOME = os.environ.get("XDG_STATE_HOME","").strip()`; truthy → `Path(XDG_STATE_HOME).expanduser()`; falsey reads `HOME = os.environ.get("HOME","").strip()`; falsey `HOME` raises `HandoffUnavailable("HOME is unavailable")`; truthy `HOME` → `Path(HOME).expanduser()/".local"/"state"`; then `/ "awa" / "handoff" / ".lock"` | `kernel/lib/awa_handoff.py#_state_home,handoff_dir,lock_path` | `2bb7e3efccc48b4d5951df22d453dd2fb9ea7ef0d5521fcabd4642b94469d648` |

For a comma after `#`, the path remains the preceding exact path and the
next token is another qualified name in that file. The extractor computes
every complete scope digest under §2.2 and inserts it into `scope_chain`.
Its digest is:

```text
SHA256(
  ASCII("awa-kernel-branch-authority/v2") || 0x00 ||
  JCS(branch_record) || LF
)
```

Every affected record repeats the applicable branch-authority digest:
`finish-common-dir`, `finish-shell-bridge` and
`finish-inherited-helper` bind `finish-common-lock-path`;
`roots-current-session-cas` binds `roots-common-lock-path`; and
`handoff-cas` binds `handoff-lock-path`. Their exact opener node is also
selected in §2.4. An extra branch, environment source, empty-value behavior,
fallback, suffix, normalization, opener target or shell target changes an
AST/file/branch digest and refuses.

### 2.4 Exact source-derived semantic records

Each record has exactly
`schema,id,kind,path_role,branch_authority_digest,python_scopes,shell_units,
opener_nodes,governed_nodes`. `schema` is
`awa-kernel-semantic-record/v2`; `kind` is `LOCK`, `LOCK_BRIDGE`, or
`DESCRIPTOR_CONTROL`; `path_role` is null or one of the exact uppercase
tokens below. Arrays preserve selector-manifest order.

The extractor applies §2.2 to this exact manifest. `scope` entries are
`path#qualname`; node entries are `qualname:preorder`. There is no line-number
authority and no source-text shorthand:

| ID | Kind / path role | Scope selectors | Opener nodes | Governed nodes | Branch / shell |
|---|---|---|---|---|---|
| `admin-global` | `LOCK` / `ADMIN_GLOBAL_LOCK` | `kernel/bin/awa-private-runtime-admin.py#execute_native_lifecycle` | `execute_native_lifecycle:596` | `execute_native_lifecycle:678,1883` | null |
| `admin-version-remove` | `LOCK` / `ADMIN_REMOVE_VERSION_LOCK` | `kernel/bin/awa-private-runtime-admin.py#execute_native_lifecycle` | `execute_native_lifecycle:1479` | `execute_native_lifecycle:1508` | null |
| `admin-version-set` | `LOCK` / `ADMIN_VERSION_DIGEST_LOCK` | `kernel/bin/awa-private-runtime-admin.py#execute_native_lifecycle` | `execute_native_lifecycle:817` | `execute_native_lifecycle:865,1862` | null |
| `finish-common-dir` | `LOCK` / `COMMON_DIR_LOCK` | `kernel/lib/awa_finish.py#_state_home,awa_state_dir,locks_dir,common_dir_key,lockfile_for,common_dir_lock` | `common_dir_lock:33` | `common_dir_lock:91,162,258` | `d5192ffa36037ff6a886a7d93981e679f0415f2022a832796521ef37f8097c64` |
| `finish-inherited-helper` | `LOCK` / `COMMON_DIR_LOCK` | `kernel/lib/awa_finish.py#_state_home,awa_state_dir,locks_dir,common_dir_key,lockfile_for,_flock_inherited_fd` | none | `_flock_inherited_fd:30` | `d5192ffa36037ff6a886a7d93981e679f0415f2022a832796521ef37f8097c64`; exact shell file |
| `finish-shell-bridge` | `LOCK_BRIDGE` / `COMMON_DIR_LOCK` | `kernel/lib/awa_finish.py#_state_home,awa_state_dir,locks_dir,common_dir_key,lockfile_for,main` | `main:2066` | none | `d5192ffa36037ff6a886a7d93981e679f0415f2022a832796521ef37f8097c64`; exact shell file |
| `handoff-cas` | `LOCK` / `HANDOFF_CAS_LOCK` | `kernel/lib/awa_handoff.py#_state_home,handoff_dir,lock_path,_lock` | `_lock:59` | `_lock:130,185` | `2bb7e3efccc48b4d5951df22d453dd2fb9ea7ef0d5521fcabd4642b94469d648` |
| `roots-current-session-cas` | `LOCK` / `COMMON_DIR_LOCK` | `kernel/lib/awa_roots.py#_state_home,awa_state_dir,locks_dir,_common_dir_key,_common_dir_lock` | `_common_dir_lock:43` | `_common_dir_lock:93,140` | `ca69f4663cdb321001b5cba8e53a60e2c9713c8ee85e548a9b186e7934ef2144` |
| `runtime-version-retained` | `LOCK` / `RUNTIME_VERSION_LOCK` | `kernel/bin/awa-registration-bootstrap.py#load_installed_launch_authority` | `load_installed_launch_authority:307` | `load_installed_launch_authority:341,364` | null |
| `spawn-intent-store` | `LOCK` / `SPAWN_INTENT_LOCK` | `kernel/bin/awa-registration-bootstrap.py#FilesystemIntentStore.__init__,FilesystemIntentStore.for_uid,FilesystemIntentStore._lock,FilesystemIntentStore._unlock` | `FilesystemIntentStore._lock:6` | `FilesystemIntentStore._lock:102;FilesystemIntentStore._unlock:7` | null |
| `darwin-fullfsync` | `DESCRIPTOR_CONTROL` / null | `kernel/lib/awa_durability.py#_sync_fd` | none | `_sync_fd:51` | null |
| `remap-posix-spawn` | `DESCRIPTOR_CONTROL` / null | `kernel/bin/awa-registration-bootstrap.py#DarwinPosixSpawnBackend._spawn_pid` | none | `DarwinPosixSpawnBackend._spawn_pid:157` | null |
| `remap-preexec` | `DESCRIPTOR_CONTROL` / null | `kernel/bin/awa-registration-bootstrap.py#apply_fd_remap` | none | `apply_fd_remap:66` | null |

The extractor recomputes the complete scope/node digests, emits canonical
JCS, and compares these per-record digests:

```text
admin-global                 8904823b5efed27c3e92e738650bd078ef582926db689faa7c6f42702856113a
admin-version-remove         602df2f17169aaa3db7ed032ac40d5a878f75ab47a4e5710a14b2a4d02545d34
admin-version-set            f3400e319d27118ccaff9274dcf3883de2b016b83cad4debc1e3bb5e8d6640ed
darwin-fullfsync             7fa14943b5d658d2be086ceb7fea00bc29aa8b6082492f622969fa4fb879cc07
finish-common-dir            f9af31250a4753f87787617d7935cddf6a6e839c05db32cd435d7747d87e141c
finish-inherited-helper      bf7f24b7d212c19161fed7a186628f8a364da5c562ad76ca2a4b5d7bf814891a
finish-shell-bridge          d842cecb0b9b12c1957145aaa1db2104c17ae23364ad26727a3ecadd4630dc96
handoff-cas                  4516de4dd2b20b2667f516eb25aae891922b66265c3138eb9a5aec7ed2b66520
remap-posix-spawn            0ee78dbec9bc694c3c306d950e2cc0ab91b6ec74541ad19fc76db250497a8185
remap-preexec                a3f64e5cca87bd2b959b87bcc9427fce3be94f4d57eb4b59e11ca59691ee5c18
roots-current-session-cas    1257617455cdf8d55fd37ca8c418a0c733f361a5f4839191f3c3b67b40ca46a7
runtime-version-retained     b7b33cf09657fd8b57a0410817316ddee41829e2fa7da04d93318cb665b4ab5e
spawn-intent-store           566786a4da4cb4f044f4f3caaa87a63b208c2eee1f4190c4380734ca7942c254
```

Each per-record digest is
`SHA256("awa-kernel-semantic-record/v2" || NUL || JCS(record) || LF)`.
Records sorted by `id` UTF-8 bytes produce:

```text
SHA256(
  ASCII("awa-kernel-semantic-inventory/v2") || 0x00 ||
  each JCS(record) || LF
) = a3bd2b76246d2ebb48af502da847c42e113292b84be69b955b6adacdadbdd2b0
```

The scanner discovers every governed call/callback independently and requires
one-to-one equality with the selected governed nodes. Scope digests make
descriptor origins, assignments, open flags/modes, metadata checks, path
construction and releases bite even when they are not governed-call nodes.
The ten lock/bridge records and three descriptor-control records are exact;
addition, deletion, relocation or any scope/node/file drift refuses.

### 2.5 Detection grammar and refusal

Python import aliases, attribute/subscript/mapping access, tuple/list
unpacking, assignments, callbacks and wrappers are resolved. Star import,
dynamic import, dynamic `getattr`/`setattr`/`delattr`, unresolved callable,
generated source, branch provenance outside §2.3, or governed string
construction refuses. Literal source reaching `compile`, `exec`, `eval`,
`runpy`, import loaders, `subprocess.*`, `os.system`, `os.popen` or
spawn/exec APIs is recursively parsed.

Shell fixtures use `shlex.shlex(posix=True,
punctuation_chars=";&|<>()\n")`, `whitespace=" \t"`, comments enabled,
longest exact punctuation matching, and LF/`;`/`&&`/`||`/`|`/`&`/parenthesis
command separation. Only one dominating literal assignment may resolve a
variable. `${!name}`, `eval`, dynamic `source`, generated commands,
unresolved expansion, wrapper/function/variable aliases and command
substitution involving a governed primitive refuse.

Only the two exact `F_DUPFD_CLOEXEC` records and one exact Darwin
`F_FULLFSYNC` record pass. `F_GETLK`, `F_SETLK`, `F_SETLKW`, all
`F_OFD_*LK*`, numeric equivalents, `lockf` and every other descriptor
command refuse.

### 2.6 Exact positive references

Two non-operation references are exact:

```text
kernel/bin/awa-registration-bootstrap.py|REQUIRED_PYTHON_APIS|"fcntl.flock"
kernel/bin/awa-registration-bootstrap.py|CAPABILITY_PROBE_SOURCE|hasattr(fcntl,"flock")
```

They may only test/report API availability. Any call, callback, assignment to
a callable, command construction or flow to executable source refuses.

---

## 3. Immutable-field scanner and biting matrix

### 3.1 Sole Darwin declaration

The only permitted immutable-family lexical/AST node is the exact `_fields_`
list element in class `_VinfoStat`, at zero-based index 17:

```python
("vst_flags", ctypes.c_uint32)
```

The scanner emits
`awa-darwin-abi-field/v1|kernel/bin/awa-registration-bootstrap.py|_VinfoStat|_fields_|17|vst_flags|ctypes.c_uint32`
and requires singleton equality. Reads, writes and deletes escape nothing:
`Attribute`, `Subscript`, mapping key, `getattr`, `setattr`, `delattr`,
reflection, serialization, comparison, bit operation, assignment, callback,
wrapper, command argument and string-driven access all refuse.

Across every scanned Python, shell and YAML source, direct, imported, aliased,
attribute, subscript, mapping, dynamic, subprocess and shell forms of
`chflags`, `lchflags`, `fchflags`, `uchg`, `schg`, `uappnd`, `sappnd`,
`UF_IMMUTABLE`, `SF_IMMUTABLE`, `UF_APPEND`, `SF_APPEND` and numeric/platform
equivalents refuse. The scanner resolves aliases and assignment chains under
§2.2–§2.3; unresolved forms fail closed.

### 3.2 Parameterized negative matrix

One parameterized fixture table has exactly these families, each with direct,
module-alias, imported-symbol alias, assignment alias, callback/wrapper,
dynamic `getattr`/import, subprocess/list, subprocess/string, shell function,
shell variable, command substitution and unresolved-indirection variants
where the language permits:

```text
PY_FLOCK
PY_LOCKF
PY_FCNTL_F_GETLK
PY_FCNTL_F_SETLK
PY_FCNTL_F_SETLKW
PY_FCNTL_F_OFD_GETLK
PY_FCNTL_F_OFD_SETLK
PY_FCNTL_F_OFD_SETLKW
PY_FCNTL_NUMERIC_OR_UNKNOWN_COMMAND
PY_CTYPES_OR_SYSCALL_FCNTL_OR_FLOCK
PY_EXTRA_APPROVED_FILE_CALL
PY_MOVED_APPROVED_CALL
PY_CHANGED_DESCRIPTOR_ORIGIN
PY_CHANGED_PATH_PROVENANCE
PY_CHANGED_XDG_ENVIRONMENT_KEY
PY_CHANGED_XDG_EMPTY_OR_STRIP_SEMANTICS
PY_CHANGED_HOME_FALLBACK
PY_CHANGED_PASSWD_TILDE_FALLBACK
PY_CHANGED_PATH_SUFFIX
PY_EXTRA_PATH_BRANCH_OR_TARGET
PY_CHANGED_ASSIGNMENT_CHAIN
PY_CHANGED_OPEN_FLAGS
PY_CHANGED_OPEN_MODE
PY_CHANGED_METADATA_CHECK
PY_CHANGED_LOCK_FLAGS
PY_CHANGED_RELEASE
PY_F_DUPFD_WITHOUT_CLOEXEC
PY_F_DUPFD_CLOEXEC_USED_AS_LOCK_OR_UNKNOWN
PY_VST_FLAGS_ATTRIBUTE_LOAD
PY_VST_FLAGS_ATTRIBUTE_STORE
PY_VST_FLAGS_ATTRIBUTE_DELETE
PY_VST_FLAGS_GETATTR
PY_VST_FLAGS_SETATTR
PY_VST_FLAGS_DELATTR
PY_VST_FLAGS_SUBSCRIPT
PY_VST_FLAGS_MAPPING
PY_VST_FLAGS_REFLECTION
PY_DUPLICATE_VST_FLAGS_DECLARATION
PY_CHANGED_VST_FLAGS_TYPE
PY_CHANGED_VST_FLAGS_INDEX
PY_CHFLAGS
PY_LCHFLAGS
PY_FCHFLAGS
PY_UCHG
PY_SCHG
PY_UAPPND
PY_SAPPND
PY_UF_IMMUTABLE
PY_SF_IMMUTABLE
PY_UF_APPEND
PY_SF_APPEND
PY_IMMUTABLE_NUMERIC_OR_UNKNOWN
SHELL_FLOCK
SHELL_LOCKF
SHELL_FCNTL_SETLK_FAMILY
SHELL_CHFLAGS
SHELL_UCHG
SHELL_SCHG
SHELL_UAPPND
SHELL_SAPPND
SHELL_IMMUTABLE_CONSTANT
SHELL_FUNCTION_WRAPPER
SHELL_VARIABLE_ALIAS
SHELL_COMMAND_SUBSTITUTION
SHELL_CHANGED_BRIDGE_BYTES
SHELL_EVAL
SHELL_DYNAMIC_SOURCE
SHELL_UNRESOLVED_INDIRECTION
SUBPROCESS_LOCK_LIST
SUBPROCESS_LOCK_STRING
SUBPROCESS_IMMUTABLE_LIST
SUBPROCESS_IMMUTABLE_STRING
YAML_LOCK_PRIMITIVE
YAML_IMMUTABLE_PRIMITIVE
UNKNOWN_SUFFIX
SYMLINK_OR_NONREGULAR
```

Each row supplies minimal synthetic source, expected normalized offender
family and `REFUSE`; the fixture asserts every row ran and every declared
family is present exactly once. Positive fixtures cover all ten lock records,
three descriptor-control records, two capability references, the one Darwin
ABI node, current shell bridge and current YAML. Mutation tests delete and
alter every field of every positive record. No existing kernel-first,
engine-off, router-off, active-root refusal or refusal-receipt assertion is
removed, loosened, skipped, renamed or reparameterized.

---

## 4. Closed scope and stopped-work manifest

### 4.1 Exact full 64-path ceiling

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
engine/tests/test_kernel_off_matrix.py
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
  ASCII("awa-registration-v10-implementation-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) = 2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334
```

This is exactly accepted v9's 63 paths plus
`engine/tests/test_kernel_off_matrix.py`.

### 4.2 Exact C-RUNTIME 60-path ceiling

C-RUNTIME is the full list minus exactly:

```text
engine/registration_hook_runtime.py
engine/tests/test_registration_hook_runtime_c.py
live-verify/native-entry-durable-registration-body-c-desktop-uat.sh
live-verify/native-entry-durable-registration-r0.py
```

Its exact sorted list is:

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
```

```text
SHA256(
  ASCII("awa-registration-v10-c-runtime-scope/v1") || 0x00 ||
  sorted UTF8(path) || LF records
) = 7a1c9ef2fdddad6f2cddb81c49c6a41f9b1cf28841759e60ac4bd24eaecbe5d0
```

C-FINAL remains exactly 24 paths with accepted hash
`1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8`.

### 4.3 Exact 60-record stopped-work manifest

```text
SHA256(
  ASCII("awa-registration-v10-c-runtime-working-manifest/v1") || 0x00 ||
  for each C-RUNTIME path sorted by UTF-8 bytes:
    UTF8(path) || 0x00 || ASCII(kind) || 0x00 ||
    ASCII(mode) || 0x00 || ASCII(sha256) || LF
) = d08a51aa577536022466982314bab8f2483ab0bbf48f68bb176e819b9d6380f6
```

All records are regular files measured descriptor-safely from current bytes:

```text
Makefile|REGULAR|644|b7fc90e778adaaa1e3bf5ba2f276ace726d0e73aa29dbe13ee39e9e04386a9f0
build/private-runtime/README.md|REGULAR|644|eb110cd893e7f0d0e7e44a6aa0a79e0e588ce2596fb997fa688e0427c9fc29b7
build/private-runtime/build.sh|REGULAR|644|01398c80fe32a81656c21805e84b7880594619bd047c633639e4a29871a78f3f
build/private-runtime/manifest.py|REGULAR|644|a0c8173497ed9af647b77e1016254cb16d7fd170a73326f4b12f1639c56f8711
build/private-runtime/sources.lock.json|REGULAR|644|a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72
contracts/awa-contract.v1.json|REGULAR|644|408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9
contracts/awa-contract.v2.json|REGULAR|644|db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a
contracts/awa-contract.v3.json|REGULAR|644|fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9
contracts/awa-contract.v4.json|REGULAR|644|f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3
contracts/awa-registration-admin-audit.v1.json|REGULAR|644|a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a
contracts/awa-registration-admin-audit.v2.json|REGULAR|644|b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2
contracts/awa-registration-admin-audit.v3.json|REGULAR|644|f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa
contracts/awa-registration-owner-signers.v1|REGULAR|644|9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e
contracts/awa-registration-owner-signers.v2|REGULAR|644|690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3
contracts/awa-registration-platform-bootstrap.v1.json|REGULAR|644|4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c
contracts/awa-registration-platform-bootstrap.v2.json|REGULAR|644|404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9
contracts/awa-registration-platform-bootstrap.v3.json|REGULAR|644|ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0
contracts/awa-registration-private-runtime.v1.json|REGULAR|644|f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321
contracts/awa-registration-private-runtime.v2.json|REGULAR|644|91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8
contracts/awa-registration-private-runtime.v3.json|REGULAR|644|29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84
contracts/awa-registration-privileged-envelope.v1.json|REGULAR|644|7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034
engine/registration_host.py|REGULAR|644|57d1c0d956ff76a8a129d1563663161dd3e22c1e835c703a3d767516faf4aaf5
engine/registration_installer.py|REGULAR|644|e6fc894f0ddf1900acdcaff196238c32ec914c045756274ea29b4521f1d057e4
engine/registration_launcher.py|REGULAR|644|807e0d50922c47bde638ed9bab70e784f9787a526e2cf45828982dfae346979f
engine/registration_privileged_installer.py|REGULAR|644|8b9f10ee8f07be1c47a683b5f96481d44d0b7b7b6e1d332738ba79890fb6a231
engine/registration_profile.py|REGULAR|644|889ff613c38567e862e16a84be56a0a35e16be2369371d0ce1ba31c8a458bf4a
engine/registration_projection.py|REGULAR|644|3d08bbc7cc6c2d2598df212db9c563d186852de2403207c55b256e5ea6e73f42
engine/registration_receiver.py|REGULAR|644|49925ba2687f01b88bbf26c0fc15ee9c1db48aa1ea63ca50f332952ff3111831
engine/registration_schema.py|REGULAR|644|944f734e6cd62134448720e4cfa47734c2eb300301cb4885ac36aaac808681e0
engine/tests/registration_body_c_fixtures.py|REGULAR|644|e07736b0ecde2e268fd9256c56705874719e8a335d8ef698d9d943f9c160f978
engine/tests/test_contract_schemas.py|REGULAR|644|4a7945c586eb791f073562a63c305eda7532a0cf1cb45c239f0617c7ce248c69
engine/tests/test_install_lib.py|REGULAR|644|901cb72233426c993a5986ede683798ce5c386732bd0148f5ee2aaba28aae1e3
engine/tests/test_kernel_off_matrix.py|REGULAR|644|76ffd65a549f105557b91a0c03502f7ecc219d9abf11f89ba8186f9e003120dc
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
install.sh|REGULAR|755|fb4c72787ea93e1059a60fabe710f4730b8471e9f9fbad1edf20bf65ab0ef42f
kernel/bin/awa-private-runtime-admin.py|REGULAR|644|b25db3fa68685a6639ee2de056110f3b8ef0f600deb95c7966fd6d887fa5711b
kernel/bin/awa-registration-bootstrap.py|REGULAR|644|88d3793b8f66ef8868e68d499f3beaa4af0d60b78cf14dde996590703b473c5d
kernel/bin/awa-registration-child.py|REGULAR|644|884ae7d618dd5907829c1750e98fb7c3f38b52e35a5bcf6ce7b5fa59e3d65dc1
kernel/bin/awa-registration-entrypoint.sh|REGULAR|644|2db540bd53e931d864b2fe3f1ccd56634b288e96703f83e2a1a19046f3b84ddc
kernel/bin/awa-registration-receiver.sh|REGULAR|755|01b642005ae8109aedbcae899ef1a0039620e598b26e56db617bb0417cc94da0
kernel/bin/awa-registration-tick.sh|REGULAR|755|8e7f889e1aa2c84cec304ee69f63f9c5c2108bc07c13bbfca53da265abce0ef6
kernel/checks/awa-contract-freeze.sh|REGULAR|755|f28aa75bb1628adfcfed485391703b0b355f10e133da04a9a7694f6aeea5c062
kernel/hooks/awa-registration-admission.sh|REGULAR|755|2ee4728b7f00590fa68f0ba8c5edff5cffff156aac2639be2720990be42ca3d5
kernel/hooks/awa-registration-startup.sh|REGULAR|755|3efb923c2fad00c5b57263c98554c05498beb047f57583ed9baf30d42535a1fa
```

The manifest is exactly the implemented v9 59-path state plus the unchanged
kernel-off test:

```text
engine/tests/test_kernel_off_matrix.py|76ffd65a549f105557b91a0c03502f7ecc219d9abf11f89ba8186f9e003120dc
```

The inherited changed subset is exactly this canonical JCS map:

```json
{"contracts/awa-contract.v3.json":"fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9","contracts/awa-contract.v4.json":"f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3","contracts/awa-registration-admin-audit.v2.json":"b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2","contracts/awa-registration-admin-audit.v3.json":"f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa","contracts/awa-registration-platform-bootstrap.v2.json":"404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9","contracts/awa-registration-platform-bootstrap.v3.json":"ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0","contracts/awa-registration-private-runtime.v2.json":"91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8","contracts/awa-registration-private-runtime.v3.json":"29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84","engine/registration_privileged_installer.py":"8b9f10ee8f07be1c47a683b5f96481d44d0b7b7b6e1d332738ba79890fb6a231","engine/registration_projection.py":"3d08bbc7cc6c2d2598df212db9c563d186852de2403207c55b256e5ea6e73f42","engine/registration_schema.py":"944f734e6cd62134448720e4cfa47734c2eb300301cb4885ac36aaac808681e0","install.sh":"fb4c72787ea93e1059a60fabe710f4730b8471e9f9fbad1edf20bf65ab0ef42f","kernel/bin/awa-registration-bootstrap.py":"88d3793b8f66ef8868e68d499f3beaa4af0d60b78cf14dde996590703b473c5d","kernel/bin/awa-registration-child.py":"884ae7d618dd5907829c1750e98fb7c3f38b52e35a5bcf6ce7b5fa59e3d65dc1","kernel/bin/awa-registration-entrypoint.sh":"2db540bd53e931d864b2fe3f1ccd56634b288e96703f83e2a1a19046f3b84ddc","kernel/bin/awa-registration-receiver.sh":"01b642005ae8109aedbcae899ef1a0039620e598b26e56db617bb0417cc94da0","kernel/bin/awa-registration-tick.sh":"8e7f889e1aa2c84cec304ee69f63f9c5c2108bc07c13bbfca53da265abce0ef6","kernel/checks/awa-contract-freeze.sh":"f28aa75bb1628adfcfed485391703b0b355f10e133da04a9a7694f6aeea5c062","kernel/hooks/awa-registration-admission.sh":"2ee4728b7f00590fa68f0ba8c5edff5cffff156aac2639be2720990be42ca3d5","kernel/hooks/awa-registration-startup.sh":"3efb923c2fad00c5b57263c98554c05498beb047f57583ed9baf30d42535a1fa"}
```

```text
SHA256(
  ASCII("awa-registration-v9-c-runtime-changed-subset/v1") || 0x00 ||
  JCS(map) || LF
) = 5b20759388fac04217583a8208d30615204bd4c641227731316ff72ee923a8d6
```

The later implementation GO must preserve all 59 inherited records and the
20-path changed subset byte-identically. Only the kernel-off test may change,
and completion must report its final hash plus the recomputed 60-record
manifest. Any second changed path is a stop.

---

## 5. Acceptance ledger, sequencing and stops

Carry every V9-A01..V9-A06 and inherited V8-A01..V8-A15 row forward
unchanged. Add:

| ID | Required evidence | Refusal |
|---|---|---|
| V10-A01 | Reproduce 64/60/24 scopes, current 59-path manifest, 20-path subset, test hash and 60-record manifest | Missing record, drift or second changed path |
| V10-A02 | Exact scanner inventory accepts only ten lock, three descriptor-control, two capability-reference and one Darwin ABI records and rejects add/remove/move/alias/provenance/opener/usage drift | Filename exemption, token rename, partial inventory or stale authority |
| V10-A03 | Worktree lock fixtures bite for direct/aliased/callback/wrapper/shell and every prohibited lock family | Any forbidden worktree lock accepted |
| V10-A04 | Only exact `_VinfoStat.vst_flags` ABI declaration passes; every operational access and immutable setter fixture refuses | Declaration-wide exemption or immutable operation accepted |
| V10-A05 | All untouched kernel-first, engine-off, router-off, active-root and refusal-receipt tests remain byte/semantically unchanged | Assertion weakening, deletion, skip or behavior drift |
| V10-A06 | Previously failing two tests pass; complete focused/registration/full verification passes without production change | Production edit, remaining failure or omitted gate |

Exact sequencing:

1. v10 acceptance promotes only plan/index statuses and marks v9 superseded in
   the index.
2. A separate exact `V10-C-RUNTIME-IMPLEMENT` GO must bind the promoted v10
   plan/index/normalized hashes, branch/base, 60-path scope, stopped manifest,
   kernel-off test hash and preserved 20-path subset.
3. Implementation is tests-only in the one added path.
4. Run the two formerly failing tests, all kernel-off tests, focused
   registration tests, complete registration suite, `make verify-pre-pr`,
   `make verify`, diff/cached/scope/manifest checks, Bugbot and Security
   Review.
5. A separate `V10-C-RUNTIME-DELIVER` GO binds the one-path changed subset and
   final 60-record manifest before one Draft PR.
6. Packet, qualification key, native prompt, acceptance, readiness, merge and
   C-FINAL remain separately gated exactly as inherited.

Stop for any production edit, second test path, scope escape, inability to
express exact semantic inventory, AST ambiguity, need to rename production
tokens, loss of an inherited assertion, changed static contract/schema,
working-manifest drift, private/key/prompt/install boundary, or any inherited
v9/v8 stop.

---

## 6. Exact v10 plan acceptance

### 6.1 Status-only authority

Exact-byte owner acceptance authorizes only:

1. this plan status:
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO`;
2. v10 index status:
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-10-04`;
3. v9 index status:
   `SUPERSEDED BY V10 — 2026-10-04`.

It authorizes no test/implementation edit, delivery, build, key, signing,
prompt, privileged operation, installation, publication, release, activation,
R0/R1/C1/R2, external mutation or rollout.

### 6.2 Anti-replay normalization

```text
SHA256(
  ASCII("awa-registration-v10-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

Replace exactly one DRAFT/ACCEPTED plan status line with:

```text
- **Status:** __AWA_V10_STATUS__
```

Replace exactly one v10 DRAFT/ACCEPTED index row with:

```text
| `native-entry-durable-registration-v10.md` | __AWA_V10_INDEX_STATUS__ | Minimal semantic-inventory successor to accepted v9; adds only the kernel-off matrix test to distinguish accepted registration locks/ABI layout from forbidden worktree locks and immutable-flag operations. |
```

Replace exactly one v9 accepted/superseded index row with:

```text
| `native-entry-durable-registration-v9.md` | __AWA_V10_PREDECESSOR_INDEX_STATUS__ | Minimal fixed-point successor to accepted v8; replaces only circular bundle-manifest v2 with acyclic v3 derivation and expands the exact static set to 16. |
```

Each replacement includes one LF. Zero, duplicate, mixed, non-UTF-8, CRLF,
NUL or non-exact context refuses. Simulated draft and promoted bytes must
normalize identically.

### 6.3 Exact owner envelope shape

External acceptance is one canonical JCS object with exactly:

```json
{"accepted_v9_index_sha256":"1c021a1cfdd4e0f085f67e08e23fdcade0539b0cbe17fd507f47f67938e51ca6","accepted_v9_normalized_digest":"c8ed54298a5d0e074744be79670158feaec27d870c66dd4fd365d7dd67899703","accepted_v9_plan_sha256":"69110832b1acb00e7250dd4b5b0420354b023e46f204d9ee521f48f3eb33f525","action":"ACCEPT_PLAN_V10","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","authorized":true,"authorized_actions":["MARK_V9_INDEX_SUPERSEDED","PROMOTE_V10_INDEX_STATUS","PROMOTE_V10_PLAN_STATUS"],"authorized_by":"KleinPerkins","branch":"impl/native-entry-durable-registration-v7-runtime-bootstrap","c_final_scope_count":24,"c_final_scope_hash":"1ea0c1e1699e82650d34e330de6ab34c353fa76478ee166cdc81b6be587908a8","denied_implications":["ACCESS_OR_GENERATE_KEY_OR_SIGN","ALTER_PRESERVED_WORK","BUILD_OR_PUBLISH","COMMIT_PUSH_OR_OPEN_PR","IMPLEMENT_OR_DELIVER","INVOKE_NATIVE_AUTHORIZATION_PROMPT","MUTATE_EXTERNAL_STATE","PRIVILEGED_OPERATION","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT","RUN_R0_R1_C1_OR_R2"],"draft_index_sha256":"<reviewed lowercase 64-hex>","draft_plan_sha256":"<reviewed lowercase 64-hex>","kernel_off_test_sha256":"76ffd65a549f105557b91a0c03502f7ecc219d9abf11f89ba8186f9e003120dc","live_base_commit":"03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d","new_c_runtime_scope_count":60,"new_c_runtime_scope_hash":"7a1c9ef2fdddad6f2cddb81c49c6a41f9b1cf28841759e60ac4bd24eaecbe5d0","new_full_scope_count":64,"new_full_scope_hash":"2b558712d38215788993dbcd33c9ab389c1281399375aba00aa63c8a3e889334","normalized_digest":"<reviewed lowercase 64-hex>","old_c_runtime_scope_count":59,"old_c_runtime_scope_hash":"31c0b9e23865ccf2b372b39c75432ce837490f9407e46398f013d89694b0ec59","old_full_scope_count":63,"old_full_scope_hash":"885a2a5561dcc285ed2372171f9593dcbde706c3da7c6dc8d9a16d79e17d1830","pre_v7_body_c_manifest_hash":"9210111d256068804ac0b169ac8dcc7323299f11e997d6403f1f2428eba0202a","preserved_changed_subset_count":20,"preserved_changed_subset_digest":"5b20759388fac04217583a8208d30615204bd4c641227731316ff72ee923a8d6","promoted_index_sha256":"<reviewed lowercase 64-hex>","promoted_plan_sha256":"<reviewed lowercase 64-hex>","repository":"KleinPerkins/awa","schema":"awa-registration-v10-plan-acceptance-go/v1","source_lock_sha256":"a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72","v10_working_manifest_count":60,"v10_working_manifest_hash":"d08a51aa577536022466982314bab8f2483ab0bbf48f68bb176e819b9d6380f6","v9_implemented_manifest_count":59,"v9_implemented_manifest_hash":"e7576bba802cfb06822f0bd54f436e1e7a7596a7db8c3cde445cb5d94ac3c0f7"}
```

Placeholders are replaced only in the external submitted envelope. Its digest
is:

```text
SHA256(
  ASCII("awa-registration-v10-plan-acceptance-envelope/v1") || 0x00 ||
  JCS(concrete_external_envelope) || LF
)
```

Immediately before promotion, recompute every accepted authority, draft and
promoted hash, normalized equivalence, 64/60/24 scopes, both working
manifests, changed subset, exact test hash, branch/base/staging and every
denied implication. Mismatch refuses without mutation.

---

## 7. Standalone four-pass review

### Pass 1 — facts

Accepted v9 plan/index/normalization, accepted v8, ADR, source lock,
HEAD/origin-main, branch, prior Body C, current 59-path manifest, 20-path
subset and kernel-off test bytes were independently measured from current
state. The full gate's two failures follow from raw token scans, not from
registration behavior failure.

### Pass 2 — closure

Closed Python/shell/YAML scanners inventory every inherited finish, handoff,
roots and clean bridge plus registration admin/version/spawn-intent locks,
descriptor remapping and durability. Descriptor/path origins, assignment
chains, openers, metadata checks, uses and releases are exact. The one ABI
field declaration is distinguished from every operational immutable-flag
action. Exact set equality and the full negative family matrix make additions,
deletions, aliases, indirection and semantic drift bite.

### Pass 3 — subtraction

One existing test path is added. No production, contract, schema, vector,
fixture file, runtime, receipt, gate, packet, body or rollout surface changes.
The implementation is confined to replacing two stale assertions and adding
their biting synthetic fixtures in that same file.

### Pass 4 — under-scope proof

The 64/60 scopes are exactly v9's 63/59 lists plus the kernel-off test.
The 60-record manifest is exactly the current implemented 59 records plus the
unchanged test. C-FINAL remains 24. Acceptance remains documentation-only;
implementation requires a separate exact GO. Independent review clearance is
not asserted.
