"""K0/K1: the engine-OFF + router-OFF invariant harness (kernel safety holds).

The kernel safety guarantee must hold with the Python engine OFF and NO router installed. This
matrix proves it structurally and behaviorally:

  * the kernel libs (awa_roots.py, awa_policy.py) import ONLY the stdlib — zero engine imports,
    zero third-party deps, so the shell kernel can invoke them with the engine package absent;
  * the kernel reads NO router artifact (no router exists — the structural contamination guard
    keeps it that way);
  * with the engine package deliberately UNIMPORTABLE, the kernel clean gate STILL blocks an
    active root and STILL writes a clean_receipt (the safety behavior does not depend on the
    engine being importable);
  * no active OS lock / macOS immutable (uchg) flag is introduced (locked decision for K0/K1).
"""

from __future__ import annotations

import ast
import copy
import fcntl as _fcntl
import hashlib
import json
import math
import os
import re
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .consumer_test_support import scan_tree_for_router_usage
from .helpers import EngineTestCase, commit_all, git

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _REPO_ROOT / "kernel"
_ENGINE = _REPO_ROOT / "engine"
_DEV_WORKTREE = _KERNEL / "bin" / "dev-worktree.sh"
_GUARD = _KERNEL / "hooks" / "worktree-guard.sh"
_ROOTS_PY = _KERNEL / "lib" / "awa_roots.py"

# stdlib roots the kernel libs are ALLOWED to import (union'd with sys.stdlib_module_names when
# present, so the check also works on Python 3.9 where that attribute does not exist).
_KNOWN_STDLIB = {
    "__future__", "argparse", "hashlib", "json", "os", "platform", "subprocess", "sys",
    "time", "calendar", "re", "fnmatch", "shlex", "dataclasses", "pathlib", "typing",
    "functools", "itertools", "collections", "datetime", "tempfile", "importlib", "ast",
    "io", "math", "contextlib", "shutil", "stat", "glob", "textwrap", "enum", "errno", "fcntl",
}
_LOCK_SYMBOLS = frozenset({
    "flock", "lockf", "F_GETLK", "F_SETLK", "F_SETLKW",
    "F_OFD_GETLK", "F_OFD_SETLK", "F_OFD_SETLKW",
})
_IMMUTABLE_SYMBOLS = frozenset({
    "chflags", "lchflags", "fchflags", "uchg", "schg", "uappnd", "sappnd",
    "UF_IMMUTABLE", "SF_IMMUTABLE", "UF_APPEND", "SF_APPEND", "vst_flags",
})
_EXPECTED_BRANCH_DIGESTS = {
    "finish-common-lock-path":
        "d5192ffa36037ff6a886a7d93981e679f0415f2022a832796521ef37f8097c64",
    "roots-common-lock-path":
        "ca69f4663cdb321001b5cba8e53a60e2c9713c8ee85e548a9b186e7934ef2144",
    "handoff-lock-path":
        "2bb7e3efccc48b4d5951df22d453dd2fb9ea7ef0d5521fcabd4642b94469d648",
}
_EXPECTED_RECORD_DIGESTS = {
    "admin-global": "8904823b5efed27c3e92e738650bd078ef582926db689faa7c6f42702856113a",
    "admin-version-remove":
        "602df2f17169aaa3db7ed032ac40d5a878f75ab47a4e5710a14b2a4d02545d34",
    "admin-version-set":
        "f3400e319d27118ccaff9274dcf3883de2b016b83cad4debc1e3bb5e8d6640ed",
    "darwin-fullfsync":
        "7fa14943b5d658d2be086ceb7fea00bc29aa8b6082492f622969fa4fb879cc07",
    "finish-common-dir":
        "f9af31250a4753f87787617d7935cddf6a6e839c05db32cd435d7747d87e141c",
    "finish-inherited-helper":
        "bf7f24b7d212c19161fed7a186628f8a364da5c562ad76ca2a4b5d7bf814891a",
    "finish-shell-bridge":
        "d842cecb0b9b12c1957145aaa1db2104c17ae23364ad26727a3ecadd4630dc96",
    "handoff-cas":
        "4516de4dd2b20b2667f516eb25aae891922b66265c3138eb9a5aec7ed2b66520",
    "remap-posix-spawn":
        "0ee78dbec9bc694c3c306d950e2cc0ab91b6ec74541ad19fc76db250497a8185",
    "remap-preexec":
        "a3f64e5cca87bd2b959b87bcc9427fce3be94f4d57eb4b59e11ca59691ee5c18",
    "roots-current-session-cas":
        "1257617455cdf8d55fd37ca8c418a0c733f361a5f4839191f3c3b67b40ca46a7",
    "runtime-version-retained":
        "b7b33cf09657fd8b57a0410817316ddee41829e2fa7da04d93318cb665b4ab5e",
    "spawn-intent-store":
        "566786a4da4cb4f044f4f3caaa87a63b208c2eee1f4190c4380734ca7942c254",
}
_EXPECTED_INVENTORY_DIGEST = (
    "a3bd2b76246d2ebb48af502da847c42e113292b84be69b955b6adacdadbdd2b0"
)
_SHELL_BRIDGE_SHA256 = (
    "b25f238a929036301443697da871dd8300fdb3708bf61c1e3c2bf5e3da4e6042"
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _jcs(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _preorder(node: ast.AST):
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _preorder(child)


def _parse_python(relative_path: str) -> ast.Module:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 14):
        raise AssertionError("semantic inventory requires the CPython 3.14 AST schema")
    path = _REPO_ROOT / relative_path
    source = path.read_bytes().decode("utf-8", errors="strict")
    if "\x00" in source:
        raise AssertionError(f"{relative_path}: NUL in Python source")
    return ast.parse(
        source,
        filename=relative_path,
        mode="exec",
        type_comments=False,
        feature_version=(3, 14),
        optimize=-1,
    )


def _qualified_scopes(tree: ast.Module) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}

    def visit(body: list[ast.stmt], prefix: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{prefix}.{node.name}" if prefix else node.name
                if qualified in result:
                    raise AssertionError(f"duplicate qualified scope: {qualified}")
                result[qualified] = node
                visit(node.body, qualified)

    visit(tree.body)
    return result


def _scope_selector(
    path: str, qualname: str, trees: dict[str, ast.Module]
) -> dict[str, object]:
    tree = trees.setdefault(path, _parse_python(path))
    try:
        node = _qualified_scopes(tree)[qualname]
    except KeyError as exc:
        raise AssertionError(f"missing scope {path}#{qualname}") from exc
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    digest = _sha256(
        b"awa-kernel-python-scope/v1\0"
        + path.encode()
        + b"\0"
        + qualname.encode()
        + b"\0"
        + dumped.encode()
        + b"\n"
    )
    return {"path": path, "qualname": qualname, "ast_sha256": digest}


def _node_selector(
    path: str,
    qualname: str,
    preorder_index: int,
    trees: dict[str, ast.Module],
) -> dict[str, object]:
    tree = trees.setdefault(path, _parse_python(path))
    scope = _qualified_scopes(tree)[qualname]
    nodes = list(_preorder(scope))
    if preorder_index >= len(nodes):
        raise AssertionError(f"missing node {path}#{qualname}:{preorder_index}")
    node = nodes[preorder_index]
    if not isinstance(node, ast.Call):
        raise AssertionError(
            f"{path}#{qualname}:{preorder_index} is {type(node).__name__}, not Call"
        )
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    digest = _sha256(
        b"awa-kernel-python-node/v1\0"
        + path.encode()
        + b"\0"
        + qualname.encode()
        + b"\0"
        + str(preorder_index).encode()
        + b"\0"
        + dumped.encode()
        + b"\n"
    )
    return {
        "path": path,
        "qualname": qualname,
        "preorder": preorder_index,
        "node_type": "Call",
        "ast_sha256": digest,
    }


def _branch_records(
    scope,
) -> list[dict[str, object]]:
    def const(value: str) -> dict[str, str]:
        return {"const": value}

    def binding(value: str) -> dict[str, str]:
        return {"binding": value}

    def expand(value: dict[str, str]) -> dict[str, object]:
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

    def env_get(key: str) -> dict[str, str]:
        return {
            "api": "os.environ.get",
            "default": "",
            "key": key,
            "postprocess": "str.strip",
        }

    finish = {
        "branches": [
            {
                "predicate": {
                    "binding": "XDG_STATE_HOME_STRIPPED",
                    "op": "STR_TRUTHY",
                },
                "result": expand(binding("XDG_STATE_HOME_STRIPPED")),
            },
            {
                "predicate": {"op": "ELSE"},
                "result": {
                    "arguments": [
                        expand(const("~")),
                        const(".local"),
                        const("state"),
                    ],
                    "op": "OS_PATH_JOIN",
                },
            },
        ],
        "environment_reads": [env_get("XDG_STATE_HOME")],
        "id": "finish-common-lock-path",
        "schema": "awa-kernel-branch-authority/v2",
        "scope_chain": scope(
            "kernel/lib/awa_finish.py",
            [
                "_state_home",
                "awa_state_dir",
                "locks_dir",
                "common_dir_key",
                "lockfile_for",
            ],
        ),
        "suffix_chain": [
            {
                "arguments": [binding("STATE_HOME"), const("awa")],
                "op": "OS_PATH_JOIN",
            },
            {
                "arguments": [binding("AWA_STATE_DIR"), const("locks")],
                "op": "OS_PATH_JOIN",
            },
            {
                "bytes": {
                    "op": "UTF8_ENCODE",
                    "value": {
                        "argument": binding("GIT_COMMON_DIR"),
                        "op": "OS_PATH_ABSPATH",
                    },
                },
                "length": 24,
                "op": "SHA256_HEX_PREFIX",
            },
            {
                "arguments": [
                    binding("LOCKS_DIR"),
                    {
                        "op": "FORMAT",
                        "parts": [
                            const("common-"),
                            binding("COMMON_DIR_KEY"),
                            const(".lock"),
                        ],
                    },
                ],
                "op": "OS_PATH_JOIN",
            },
        ],
    }
    roots = copy.deepcopy(finish)
    roots["id"] = "roots-common-lock-path"
    roots["scope_chain"] = scope(
        "kernel/lib/awa_roots.py",
        ["_state_home", "awa_state_dir", "locks_dir", "_common_dir_key"],
    )
    roots["suffix_chain"][2]["bytes"]["value"]["argument"] = binding("COMMON_DIR")
    handoff = {
        "branches": [
            {
                "predicate": {
                    "binding": "XDG_STATE_HOME_STRIPPED",
                    "op": "STR_TRUTHY",
                },
                "result": {
                    "argument": binding("XDG_STATE_HOME_STRIPPED"),
                    "op": "PATH_EXPANDUSER",
                },
            },
            {
                "predicate": {
                    "binding": "HOME_STRIPPED",
                    "op": "NOT_STR_TRUTHY",
                },
                "result": {
                    "exception": "HandoffUnavailable",
                    "message": "HOME is unavailable",
                    "op": "RAISE",
                },
            },
            {
                "predicate": {"op": "ELSE"},
                "result": {
                    "arguments": [
                        {
                            "argument": binding("HOME_STRIPPED"),
                            "op": "PATH_EXPANDUSER",
                        },
                        const(".local"),
                        const("state"),
                    ],
                    "op": "PATH_DIV_CHAIN",
                },
            },
        ],
        "environment_reads": [env_get("XDG_STATE_HOME"), env_get("HOME")],
        "id": "handoff-lock-path",
        "schema": "awa-kernel-branch-authority/v2",
        "scope_chain": scope(
            "kernel/lib/awa_handoff.py",
            ["_state_home", "handoff_dir", "lock_path"],
        ),
        "suffix_chain": [
            {
                "arguments": [
                    binding("STATE_HOME"),
                    const("awa"),
                    const("handoff"),
                ],
                "op": "PATH_DIV_CHAIN",
            },
            {
                "arguments": [binding("HANDOFF_DIR"), const(".lock")],
                "op": "PATH_DIV_CHAIN",
            },
        ],
    }
    return [finish, roots, handoff]


def _semantic_records() -> tuple[list[dict[str, object]], dict[str, str]]:
    trees: dict[str, ast.Module] = {}

    def scopes(path: str, names: list[str]) -> list[dict[str, object]]:
        return [_scope_selector(path, name, trees) for name in names]

    branches = _branch_records(scopes)
    branch_digests = {
        record["id"]: _sha256(
            b"awa-kernel-branch-authority/v2\0" + _jcs(record) + b"\n"
        )
        for record in branches
    }
    records: list[dict[str, object]] = []

    def nodes(path: str, qualname: str, indexes: list[int]):
        return [_node_selector(path, qualname, index, trees) for index in indexes]

    def add(
        identifier: str,
        kind: str,
        python_scopes: list[dict[str, object]],
        governed_nodes: list[dict[str, object]],
        opener_nodes: list[dict[str, object]] | None = None,
        path_role: str | None = None,
        branch: str | None = None,
        shell_units: list[dict[str, object]] | None = None,
    ) -> None:
        records.append(
            {
                "schema": "awa-kernel-semantic-record/v2",
                "id": identifier,
                "kind": kind,
                "path_role": path_role,
                "branch_authority_digest": branch,
                "python_scopes": python_scopes,
                "shell_units": shell_units or [],
                "opener_nodes": opener_nodes or [],
                "governed_nodes": governed_nodes,
            }
        )

    admin = "kernel/bin/awa-private-runtime-admin.py"
    add("admin-global", "LOCK", scopes(admin, ["execute_native_lifecycle"]),
        nodes(admin, "execute_native_lifecycle", [678, 1883]),
        nodes(admin, "execute_native_lifecycle", [596]), "ADMIN_GLOBAL_LOCK")
    add("admin-version-remove", "LOCK",
        scopes(admin, ["execute_native_lifecycle"]),
        nodes(admin, "execute_native_lifecycle", [1508]),
        nodes(admin, "execute_native_lifecycle", [1479]),
        "ADMIN_REMOVE_VERSION_LOCK")
    add("admin-version-set", "LOCK", scopes(admin, ["execute_native_lifecycle"]),
        nodes(admin, "execute_native_lifecycle", [865, 1862]),
        nodes(admin, "execute_native_lifecycle", [817]),
        "ADMIN_VERSION_DIGEST_LOCK")

    finish = "kernel/lib/awa_finish.py"
    finish_path = ["_state_home", "awa_state_dir", "locks_dir",
                   "common_dir_key", "lockfile_for"]
    shell = [{
        "path": "kernel/bin/dev-worktree.sh",
        "encoding": "EXACT_UTF8_LF_FILE",
        "sha256": _sha256((_REPO_ROOT / "kernel/bin/dev-worktree.sh").read_bytes()),
    }]
    add("finish-common-dir", "LOCK",
        scopes(finish, finish_path + ["common_dir_lock"]),
        nodes(finish, "common_dir_lock", [91, 162, 258]),
        nodes(finish, "common_dir_lock", [33]), "COMMON_DIR_LOCK",
        branch_digests["finish-common-lock-path"])
    add("finish-inherited-helper", "LOCK",
        scopes(finish, finish_path + ["_flock_inherited_fd"]),
        nodes(finish, "_flock_inherited_fd", [30]), [],
        "COMMON_DIR_LOCK", branch_digests["finish-common-lock-path"], shell)
    add("finish-shell-bridge", "LOCK_BRIDGE",
        scopes(finish, finish_path + ["main"]), [],
        nodes(finish, "main", [2066]), "COMMON_DIR_LOCK",
        branch_digests["finish-common-lock-path"], shell)

    handoff = "kernel/lib/awa_handoff.py"
    add("handoff-cas", "LOCK",
        scopes(handoff, ["_state_home", "handoff_dir", "lock_path", "_lock"]),
        nodes(handoff, "_lock", [130, 185]), nodes(handoff, "_lock", [59]),
        "HANDOFF_CAS_LOCK", branch_digests["handoff-lock-path"])
    roots = "kernel/lib/awa_roots.py"
    add("roots-current-session-cas", "LOCK",
        scopes(roots, ["_state_home", "awa_state_dir", "locks_dir",
                       "_common_dir_key", "_common_dir_lock"]),
        nodes(roots, "_common_dir_lock", [93, 140]),
        nodes(roots, "_common_dir_lock", [43]), "COMMON_DIR_LOCK",
        branch_digests["roots-common-lock-path"])

    bootstrap = "kernel/bin/awa-registration-bootstrap.py"
    add("runtime-version-retained", "LOCK",
        scopes(bootstrap, ["load_installed_launch_authority"]),
        nodes(bootstrap, "load_installed_launch_authority", [341, 364]),
        nodes(bootstrap, "load_installed_launch_authority", [307]),
        "RUNTIME_VERSION_LOCK")
    add("spawn-intent-store", "LOCK",
        scopes(bootstrap, ["FilesystemIntentStore.__init__",
                           "FilesystemIntentStore.for_uid",
                           "FilesystemIntentStore._lock",
                           "FilesystemIntentStore._unlock"]),
        nodes(bootstrap, "FilesystemIntentStore._lock", [102])
        + nodes(bootstrap, "FilesystemIntentStore._unlock", [7]),
        nodes(bootstrap, "FilesystemIntentStore._lock", [6]),
        "SPAWN_INTENT_LOCK")
    add("remap-preexec", "DESCRIPTOR_CONTROL",
        scopes(bootstrap, ["apply_fd_remap"]),
        nodes(bootstrap, "apply_fd_remap", [66]))
    add("remap-posix-spawn", "DESCRIPTOR_CONTROL",
        scopes(bootstrap, ["DarwinPosixSpawnBackend._spawn_pid"]),
        nodes(bootstrap, "DarwinPosixSpawnBackend._spawn_pid", [157]))
    durability = "kernel/lib/awa_durability.py"
    add("darwin-fullfsync", "DESCRIPTOR_CONTROL",
        scopes(durability, ["_sync_fd"]), nodes(durability, "_sync_fd", [51]))
    return sorted(records, key=lambda value: value["id"].encode()), branch_digests


def _record_digest(record: dict[str, object]) -> str:
    return _sha256(b"awa-kernel-semantic-record/v2\0" + _jcs(record) + b"\n")


def _semantic_inventory_digest(records: list[dict[str, object]]) -> str:
    return _sha256(
        b"awa-kernel-semantic-inventory/v2\0"
        + b"".join(_jcs(record) + b"\n" for record in records)
    )


def _is_docstring(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> bool:
    owner = parent.get(node)
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and isinstance(owner, ast.Expr)
        and bool(parent.get(owner))
        and isinstance(parent.get(owner), (ast.Module, ast.ClassDef, ast.FunctionDef,
                                           ast.AsyncFunctionDef))
        and parent.get(owner).body[0] is owner
    )


def _exact_vinfo_declaration(tree: ast.Module) -> tuple[ast.Tuple, set[ast.AST]]:
    matches: list[ast.Tuple] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "_VinfoStat":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "_fields_"
                       for target in statement.targets):
                continue
            if not isinstance(statement.value, (ast.List, ast.Tuple)):
                continue
            for index, item in enumerate(statement.value.elts):
                if (
                    index == 17
                    and isinstance(item, ast.Tuple)
                    and len(item.elts) == 2
                    and isinstance(item.elts[0], ast.Constant)
                    and item.elts[0].value == "vst_flags"
                    and ast.dump(item.elts[1], include_attributes=False)
                    == "Attribute(value=Name(id='ctypes', ctx=Load()), "
                       "attr='c_uint32', ctx=Load())"
                ):
                    matches.append(item)
    if len(matches) != 1:
        raise AssertionError(f"expected one exact _VinfoStat.vst_flags declaration: {matches}")
    allowed = set(ast.walk(matches[0]))
    return matches[0], allowed


@dataclass
class _ScanResult:
    findings: list[str] = field(default_factory=list)
    accepted_lock_nodes: list[str] = field(default_factory=list)
    accepted_descriptor_nodes: list[str] = field(default_factory=list)
    vinfo_declarations: int = 0

    @property
    def refused(self) -> bool:
        return bool(self.findings)

    def merge(self, other: "_ScanResult") -> None:
        self.findings.extend(other.findings)
        self.accepted_lock_nodes.extend(other.accepted_lock_nodes)
        self.accepted_descriptor_nodes.extend(other.accepted_descriptor_nodes)
        self.vinfo_declarations += other.vinfo_declarations


_LOCK_COMMAND_NAMES = frozenset({
    "F_GETLK", "F_SETLK", "F_SETLKW",
    "F_OFD_GETLK", "F_OFD_SETLK", "F_OFD_SETLKW",
})
_LOCK_NUMERIC_VALUES = frozenset(
    value
    for name in _LOCK_COMMAND_NAMES
    if isinstance((value := getattr(_fcntl, name, None)), int)
)
_DESCRIPTOR_COMMAND_NAMES = frozenset({
    "F_DUPFD", "F_DUPFD_CLOEXEC", "F_FULLFSYNC",
}) | _LOCK_COMMAND_NAMES
_COMMAND_SINKS = frozenset({
    "subprocess.call", "subprocess.check_call", "subprocess.check_output",
    "subprocess.Popen", "subprocess.run", "os.system", "os.popen",
    "os.execl", "os.execle", "os.execlp", "os.execlpe", "os.execv",
    "os.execve", "os.execvp", "os.execvpe", "os.posix_spawn",
    "os.posix_spawnp",
})
_DYNAMIC_SOURCE_SINKS = frozenset({
    "builtins.compile", "builtins.eval", "builtins.exec", "runpy.run_module",
    "runpy.run_path",
})
_RETAINED_IMPORTER_SHA256 = (
    "e02fa2d8ba3696e5373a92c8daf23f5d9ade16581e5956c46a5607c99d85d7c6"
)
_BOOTSTRAP_SHA256 = (
    "25e4979c48a221a578669ba7ccc7dcc626fff611522aab04abfa1ee2bfd5b3d3"
)
_CAPABILITY_PROBE_SHA256 = (
    "b6fc9f44f4d10941ba8cedf02b74821760dcf7e9ac7717fcace15bbaef0ed288"
)


def _module(value: str):
    return ("module", value)


def _symbol(value: str):
    return ("symbol", value)


def _string(value: str):
    return ("string", value)


def _integer(value: int):
    return ("integer", value)


def _abstract_number(value: object) -> int | float | complex | None:
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    if value[0] == "boolean":
        return int(value[1])
    if value[0] == "integer":
        return int(value[1])
    if value[0] == "constant" and isinstance(
        value[1], (float, complex),
    ):
        return value[1]
    return None


def _number_value(value: int | float | complex):
    return _integer(value) if isinstance(value, int) else ("constant", value)


_UNKNOWN = ("unknown", None)
_HEAP_KEY = "\0abstract_heap"
_ALLOCATIONS_KEY = "\0allocation_sites"
_CLASS_KEY = "\0class_allocation"
_POTENTIAL_KEY = "\0potential_evaluation"
_WEAK_WRITES_KEY = "\0weak_heap_writes"
_WILDCARD_SUBSCRIPT = ("wildcard", "subscript")
_WILDCARD_MAPPING = ("wildcard", "mapping")
_WILDCARD_SEQUENCE = ("wildcard", "sequence")
_WILDCARD_ATTRIBUTE = ("wildcard", "attribute")


def _heap_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, tuple) or len(value) != 2:
        return []
    kind, payload = value
    if kind == "heapref":
        return [payload]
    if kind == "heaprefs":
        return list(payload[0])
    return []


def _heap_value(
    records: list[dict[str, object]],
    unresolved: bool = False,
):
    unique = {
        str(record["id"]): record
        for record in records
    }
    ordered = tuple(unique[key] for key in sorted(unique))
    if len(ordered) == 1 and not unresolved:
        return ("heapref", ordered[0])
    return ("heaprefs", (ordered, unresolved))


def _allocate(
    node: ast.AST,
    kind: str,
    env: dict[str, object],
) -> dict[str, object]:
    allocations = env.get(_ALLOCATIONS_KEY, {})
    heap = env.get(_HEAP_KEY, {})
    allocation_id = allocations.get(node)
    if allocation_id is None:
        raise AssertionError("missing deterministic allocation-site identity")
    record = heap.get(allocation_id)
    if record is None:
        record = {
            "id": allocation_id,
            "kind": kind,
            "members": {},
            "opaque": False,
        }
        heap[allocation_id] = record
    return record


def _heap_member_values(
    record: dict[str, object],
) -> list[object]:
    members = record["members"]
    assert isinstance(members, dict)
    return list(members.values())


def _heap_store(
    record: dict[str, object],
    key: object,
    value: object,
    *,
    strong: bool = False,
) -> None:
    members = record["members"]
    assert isinstance(members, dict)
    members[key] = (
        value
        if strong and _exact_mapping_key(key)
        else _merge_values([members[key], value])
        if key in members
        else value
    )


def _heap_update_mapping(
    destination: dict[str, object],
    source: dict[str, object],
    *,
    strong: bool,
) -> None:
    members = source["members"]
    assert isinstance(members, dict)
    if source["kind"] == "dict":
        for key, value in members.items():
            _heap_store(destination, key, value, strong=strong)
        return
    if source["kind"] in {"list", "tuple"}:
        for value in _ordered_heap_members(_heap_value([source])):
            if (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] == "tuple"
                and len(value[1]) == 2
            ):
                _heap_store(
                    destination,
                    _mapping_key(value[1][0]),
                    _containerized(value[1][1]),
                    strong=strong,
                )
            else:
                destination["opaque"] = True
        return
    for value in members.values():
        _heap_store(destination, _WILDCARD_MAPPING, value)
    if bool(source["opaque"]):
        destination["opaque"] = True


def _normalized_ratio(value: float) -> tuple[int, int] | None:
    if not math.isfinite(value):
        return None
    numerator, denominator = value.as_integer_ratio()
    if numerator == 0:
        return (0, 1)
    divisor = math.gcd(numerator, denominator)
    return (numerator // divisor, denominator // divisor)


def _numeric_mapping_key(value: object) -> object | None:
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    kind, payload = value
    if kind == "boolean":
        return ("mapping-key", "number", (int(payload), 1), (0, 1))
    if kind == "integer":
        return ("mapping-key", "number", (int(payload), 1), (0, 1))
    if kind != "constant":
        return None
    if isinstance(payload, float):
        real = _normalized_ratio(payload)
        return (
            ("mapping-key", "number", real, (0, 1))
            if real is not None else None
        )
    if isinstance(payload, complex):
        real = _normalized_ratio(payload.real)
        imaginary = _normalized_ratio(payload.imag)
        return (
            ("mapping-key", "number", real, imaginary)
            if real is not None and imaginary is not None
            else None
        )
    return None


def _mapping_key(value: object) -> object:
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "string"
    ):
        return ("mapping-key", "string", value[1])
    numeric = _numeric_mapping_key(value)
    if numeric is not None:
        return numeric
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "constant"
        and isinstance(value[1], bytes)
    ):
        return ("mapping-key", "bytes", value[1].hex())
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "constant"
        and value[1] is None
    ):
        return ("mapping-key", "none")
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "tuple"
    ):
        items = tuple(_mapping_key(item) for item in value[1])
        if all(_exact_mapping_key(item) for item in items):
            return ("mapping-key", "tuple", items)
    return _WILDCARD_MAPPING


def _exact_mapping_key(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) >= 2
        and value[0] == "mapping-key"
    )


def _subscript_key(
    record: dict[str, object],
    node: ast.AST,
    value: object,
) -> object:
    kind = record["kind"]
    if kind == "dict":
        return _mapping_key(value)
    if kind in {"list", "tuple", "bytearray", "bytes"}:
        if any(isinstance(item, ast.Slice) for item in ast.walk(node)):
            return _WILDCARD_SEQUENCE
        if (
            isinstance(value, tuple)
            and len(value) == 2
            and value[0] in {"integer", "boolean"}
        ):
            return ("index", int(value[1]))
        return _WILDCARD_SEQUENCE
    return _WILDCARD_SUBSCRIPT


def _heap_read_subscript(
    record: dict[str, object],
    key_token: object,
) -> list[object]:
    members = record["members"]
    assert isinstance(members, dict)
    if key_token == _WILDCARD_SUBSCRIPT:
        return [
            value
            for key, value in members.items()
            if (
                key in {
                    _WILDCARD_SUBSCRIPT,
                    _WILDCARD_MAPPING,
                    _WILDCARD_SEQUENCE,
                }
                or isinstance(key, tuple)
                and len(key) == 2
                and key[0] == "index"
                or _exact_mapping_key(key)
            )
        ]
    if key_token == _WILDCARD_MAPPING:
        return [
            value
            for key, value in members.items()
            if key in {
                _WILDCARD_SUBSCRIPT,
                _WILDCARD_MAPPING,
            } or _exact_mapping_key(key)
        ]
    if key_token == _WILDCARD_SEQUENCE:
        return [
            value
            for key, value in members.items()
            if key in {_WILDCARD_SUBSCRIPT, _WILDCARD_SEQUENCE}
            or isinstance(key, tuple)
            and len(key) == 2
            and key[0] == "index"
        ]
    values = []
    if key_token in members:
        values.append(members[key_token])
    if _exact_mapping_key(key_token):
        if _WILDCARD_MAPPING in members:
            values.append(members[_WILDCARD_MAPPING])
    elif isinstance(key_token, tuple) and key_token[0] == "index":
        if _WILDCARD_SEQUENCE in members:
            values.append(members[_WILDCARD_SEQUENCE])
    if _WILDCARD_SUBSCRIPT in members:
        values.append(members[_WILDCARD_SUBSCRIPT])
    return values


def _ordered_heap_members(value: object) -> list[object]:
    members: list[tuple[object, object]] = []
    for record in _heap_records(value):
        record_members = record["members"]
        assert isinstance(record_members, dict)
        members.extend(record_members.items())
    return [
        item
        for _, item in sorted(members, key=lambda pair: repr(pair[0]))
    ]


def _expanded_positional_values(
    node: ast.Call,
    env: dict[str, object],
) -> list[object]:
    result: list[object] = []
    for argument in node.args:
        if isinstance(argument, ast.Starred):
            value = _static_value(argument.value, env)
            if (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] == "tuple"
            ):
                result.extend(value[1])
            elif _heap_records(value):
                result.extend(_ordered_heap_members(value))
                if _is_unresolved(value):
                    result.append(_opaque_callable())
            else:
                targets = _value_callable_targets(value)
                tags = _value_tags(value)
                result.append(
                    _tainted(tags, targets, True)
                    if tags or targets else _opaque_callable()
                )
        else:
            result.append(_static_value(argument, env))
    return result


def _expanded_keyword_values(
    node: ast.Call,
    env: dict[str, object],
) -> list[tuple[object, object]]:
    result: list[tuple[object, object]] = []
    for keyword in node.keywords:
        value = _static_value(keyword.value, env)
        if keyword.arg is not None:
            result.append((_string(keyword.arg), value))
            continue
        records = _heap_records(value)
        if not records:
            targets = _value_callable_targets(value)
            tags = _value_tags(value)
            result.append((
                _UNKNOWN,
                _tainted(tags, targets, True)
                if tags or targets else _opaque_callable(),
            ))
            continue
        for record in records:
            members = record["members"]
            assert isinstance(members, dict)
            for key, item in members.items():
                if (
                    _exact_mapping_key(key)
                    and key[1] == "string"
                ):
                    result.append((_string(str(key[2])), item))
                elif key in {
                    _WILDCARD_SUBSCRIPT,
                    _WILDCARD_MAPPING,
                }:
                    result.append((_UNKNOWN, item))
        if any(bool(record["opaque"]) for record in records):
            result.append((_UNKNOWN, _opaque_callable()))
    return result


def _all_call_values(
    node: ast.Call,
    env: dict[str, object],
) -> tuple[list[object], list[tuple[object, object]], list[object]]:
    positional = _expanded_positional_values(node, env)
    keywords = _expanded_keyword_values(node, env)
    return positional, keywords, positional + [
        value for _, value in keywords
    ]


def _heap_summary(
    value: object,
    *,
    targets: bool,
    seen: set[str] | None = None,
) -> set[str]:
    if seen is None:
        seen = set()
    result: set[str] = set()
    for record in _heap_records(value):
        identity = str(record["id"])
        if identity in seen:
            continue
        seen.add(identity)
        for member in _heap_member_values(record):
            result.update(
                _value_callable_targets(member)
                if targets else _value_tags(member)
            )
    return result


def _tainted(
    tags: set[str],
    targets: set[str],
    unresolved: bool,
):
    return (
        "tainted",
        (tuple(sorted(tags)), tuple(sorted(targets)), unresolved),
    )


def _opaque_callable():
    return ("opaque_callable", None)


def _safe_callable(name: str):
    return ("safe_callable", name)


def _opaque_member(targets: set[str] | None = None):
    return ("opaque_member", tuple(sorted(targets or set())))


def _value_tags(
    value: object,
    seen: set[str] | None = None,
) -> set[str]:
    if seen is None:
        seen = set()
    if not isinstance(value, tuple) or len(value) != 2:
        return set()
    kind, payload = value
    if kind == "tainted":
        return set(payload[0])
    if kind == "opaque":
        return _value_tags(payload, seen)
    if kind == "opaque_member":
        return set()
    if kind == "opaque_callable":
        return {"opaque_callable"}
    if kind in {"heapref", "heaprefs"}:
        result: set[str] = set()
        for record in _heap_records(value):
            identity = str(record["id"])
            if identity in seen:
                continue
            next_seen = seen | {identity}
            for member in _heap_member_values(record):
                result.update(_value_tags(member, next_seen))
        return result
    if kind == "symbol":
        symbol = str(payload)
        if symbol in _COMMAND_SINKS:
            return {"command_callable"}
        if symbol in _DYNAMIC_SOURCE_SINKS:
            return {"generated_callable"}
        module_name, _, name = symbol.rpartition(".")
        if module_name == "fcntl" and name in {
            "flock", "lockf", "fcntl",
        }:
            return {"lock_callable"}
        if name in _IMMUTABLE_SYMBOLS:
            return {"immutable_callable"}
        return set()
    if kind == "string":
        text = str(payload)
        tags: set[str] = set()
        if any(
            re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])",
                text,
            )
            for word in (_LOCK_SYMBOLS | _DESCRIPTOR_COMMAND_NAMES | {"fcntl"})
        ):
            tags.add("lock_command")
        if any(
            re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])",
                text,
            )
            for word in _IMMUTABLE_SYMBOLS
        ):
            tags.add("immutable_command")
        return tags
    if kind in {"list", "tuple"}:
        return set().union(
            *(_value_tags(item, seen) for item in payload), set()
        )
    if kind == "dict":
        return set().union(
            *(
                _value_tags(key, seen) | _value_tags(item, seen)
                for key, item in payload
            ),
            set(),
        )
    if kind == "object":
        return set().union(
            *(_value_tags(item, seen) for _, item in payload),
            set(),
        )
    return set()


def _value_callable_targets(
    value: object,
    seen: set[str] | None = None,
) -> set[str]:
    if seen is None:
        seen = set()
    if not isinstance(value, tuple) or len(value) != 2:
        return set()
    kind, payload = value
    if kind == "tainted":
        return set(payload[1])
    if kind == "opaque":
        return _value_callable_targets(payload, seen)
    if kind == "opaque_member":
        return set(payload)
    if kind == "opaque_callable":
        return set()
    if kind in {"heapref", "heaprefs"}:
        result: set[str] = set()
        for record in _heap_records(value):
            identity = str(record["id"])
            if identity in seen:
                continue
            next_seen = seen | {identity}
            for member in _heap_member_values(record):
                result.update(_value_callable_targets(member, next_seen))
        return result
    if kind == "symbol" and _value_tags(value):
        return {str(payload)}
    if kind in {"list", "tuple"}:
        return set().union(
            *(_value_callable_targets(item, seen) for item in payload),
            set(),
        )
    if kind == "dict":
        return set().union(
            *(
                _value_callable_targets(key, seen)
                | _value_callable_targets(item, seen)
                for key, item in payload
            ),
            set(),
        )
    if kind == "object":
        return set().union(
            *(_value_callable_targets(item, seen) for _, item in payload),
            set(),
        )
    return set()


def _merge_values(values: list[object]):
    if values and all(value == values[0] for value in values[1:]):
        return values[0]
    if any(
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "opaque"
        for value in values
    ):
        return _opaque(_UNKNOWN)
    if any(
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "opaque_member"
        for value in values
    ):
        return _opaque_member(set().union(
            *(_value_callable_targets(value) for value in values),
            set(),
        ))
    if any(
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "opaque_callable"
        for value in values
    ):
        return _opaque_callable()
    records = [
        record
        for value in values
        for record in _heap_records(value)
    ]
    if records and all(
        value == _UNKNOWN or _heap_records(value)
        for value in values
    ):
        return _heap_value(
            records,
            unresolved=any(
                value == _UNKNOWN
                or (
                    isinstance(value, tuple)
                    and len(value) == 2
                    and value[0] == "heaprefs"
                    and bool(value[1][1])
                )
                for value in values
            ),
        )
    tags = set().union(*(_value_tags(value) for value in values), set())
    targets = set().union(
        *(_value_callable_targets(value) for value in values),
        set(),
    )
    if tags or targets:
        return _tainted(tags, targets, True)
    return _UNKNOWN


def _value_has_callable_authority(value: object) -> bool:
    return bool(
        _value_callable_targets(value)
        or _value_tags(value)
        & {
            "command_callable",
            "generated_callable",
            "lock_callable",
            "immutable_callable",
            "opaque_callable",
        }
    )


def _callback_argument_refuses(
    value: object,
    target: object,
) -> bool:
    tags = _value_tags(value)
    direct_tags = tags - {"opaque_callable"}
    return bool(
        _value_callable_targets(value)
        or direct_tags
        & {
            "command_callable",
            "generated_callable",
            "lock_callable",
            "immutable_callable",
        }
        or ("opaque_callable" in tags and _is_unresolved(target))
    )


def _containerized(value: object):
    if _heap_records(value):
        return value
    if _value_has_callable_authority(value):
        return _merge_values([value, _UNKNOWN])
    return value


def _protocol_value(value: object):
    return (
        _opaque_callable()
        if value == _UNKNOWN else _containerized(value)
    )


def _opaque(value: object):
    return ("opaque", value)


def _replace_nested(value: object, old: object, new: object):
    if value == old:
        return new
    if not isinstance(value, tuple) or len(value) != 2:
        return value
    kind, payload = value
    if kind in {"list", "tuple"}:
        return (
            kind,
            tuple(_replace_nested(item, old, new) for item in payload),
        )
    if kind == "dict":
        return (
            "dict",
            tuple(
                (
                    _replace_nested(key, old, new),
                    _replace_nested(item, old, new),
                )
                for key, item in payload
            ),
        )
    if kind == "object":
        return (
            "object",
            tuple(
                (name, _replace_nested(item, old, new))
                for name, item in payload
            ),
        )
    if kind == "opaque":
        return _opaque(_replace_nested(payload, old, new))
    return value


def _mutable_values(value: object) -> list[object]:
    records = _heap_records(value)
    if records:
        result: list[object] = []
        seen: set[str] = set()

        def visit(record: dict[str, object]) -> None:
            identity = str(record["id"])
            if identity in seen:
                return
            seen.add(identity)
            result.append(record)
            for member in _heap_member_values(record):
                for child in _heap_records(member):
                    visit(child)

        for record in records:
            visit(record)
        return result
    if not isinstance(value, tuple) or len(value) != 2:
        return []
    kind, payload = value
    if kind not in {"list", "dict", "object", "opaque"}:
        return []
    result = [value]
    if kind == "list":
        children = payload
    elif kind == "dict":
        children = tuple(
            child for pair in payload for child in pair
        )
    elif kind == "object":
        children = tuple(child for _, child in payload)
    else:
        children = (payload,)
    for child in children:
        result.extend(_mutable_values(child))
    return result


def _is_unresolved(value: object) -> bool:
    return (
        not isinstance(value, tuple)
        or len(value) != 2
        or value[0] in {"unknown", "call_result"}
        or value[0] == "opaque"
        or value[0] == "opaque_member"
        or value[0] == "opaque_callable"
        or (
            value[0] == "heaprefs"
            and bool(value[1][1])
        )
        or (value[0] == "tainted" and bool(value[1][2]))
    )


def _value_contains_governed(
    value: object,
    seen: set[str] | None = None,
) -> bool:
    if seen is None:
        seen = set()
    if not isinstance(value, tuple) or len(value) != 2:
        return False
    kind, payload = value
    if kind == "tainted":
        return bool(payload[0] or payload[1])
    if kind in {"heapref", "heaprefs"}:
        for record in _heap_records(value):
            identity = str(record["id"])
            if identity in seen:
                continue
            next_seen = seen | {identity}
            if any(
                _value_contains_governed(member, next_seen)
                for member in _heap_member_values(record)
            ):
                return True
        return False
    if kind == "module":
        return payload in {"fcntl"}
    if kind == "symbol":
        module_name, _, name = str(payload).rpartition(".")
        return (
            (module_name == "fcntl" and (
                name in _LOCK_SYMBOLS
                or name in _DESCRIPTOR_COMMAND_NAMES
                or name == "fcntl"
            ))
            or (module_name in {"os", "stat"} and name in _IMMUTABLE_SYMBOLS)
            or name in _IMMUTABLE_SYMBOLS
        )
    if kind == "string":
        text = str(payload)
        governed_words = (
            _LOCK_SYMBOLS
            | _DESCRIPTOR_COMMAND_NAMES
            | _IMMUTABLE_SYMBOLS
            | {"fcntl"}
        )
        return any(
            re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", text)
            for word in governed_words
        )
    if kind == "integer":
        return False
    if kind in {"list", "tuple"}:
        return any(_value_contains_governed(item, seen) for item in payload)
    if kind == "dict":
        return any(
            _value_contains_governed(key, seen)
            or _value_contains_governed(item, seen)
            for key, item in payload
        )
    if kind == "object":
        return any(
            _value_contains_governed(item, seen) for _, item in payload
        )
    return False


def _value_is_governed_reference(
    value: object,
    seen: set[str] | None = None,
) -> bool:
    if seen is None:
        seen = set()
    if not isinstance(value, tuple) or len(value) != 2:
        return False
    kind, payload = value
    if kind == "tainted":
        return bool(
            set(payload[0])
            & {
                "lock_command", "immutable_command",
                "lock_callable", "immutable_callable",
            }
        )
    if kind in {"heapref", "heaprefs"}:
        for record in _heap_records(value):
            identity = str(record["id"])
            if identity in seen:
                continue
            next_seen = seen | {identity}
            if any(
                _value_is_governed_reference(member, next_seen)
                for member in _heap_member_values(record)
            ):
                return True
        return False
    if kind == "module":
        return payload == "fcntl"
    if kind == "symbol":
        return _value_contains_governed(value)
    if kind == "integer":
        return False
    if kind in {"list", "tuple"}:
        return any(
            _value_is_governed_reference(item, seen) for item in payload
        )
    if kind == "dict":
        return any(
            _value_is_governed_reference(key, seen)
            or _value_is_governed_reference(item, seen)
            for key, item in payload
        )
    if kind == "object":
        return any(
            _value_is_governed_reference(item, seen) for _, item in payload
        )
    return False


def _is_exact_capability_probe(value: object) -> bool:
    if not isinstance(value, tuple) or value[0] != "string":
        return False
    if _sha256(value[1].encode("utf-8")) != _CAPABILITY_PROBE_SHA256:
        return False
    try:
        tree = ast.parse(value[1], mode="exec", feature_version=(3, 14))
    except (SyntaxError, ValueError):
        return False
    governed = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Name) and node.id == "fcntl"
        ) or (
            isinstance(node, ast.Attribute)
            and (
                node.attr in _LOCK_SYMBOLS
                or node.attr in _DESCRIPTOR_COMMAND_NAMES
            )
        ) or (
            isinstance(node, ast.Constant)
            and node.value in (_LOCK_SYMBOLS | _DESCRIPTOR_COMMAND_NAMES)
        )
    ]
    expected = [
        "Name(id='fcntl', ctx=Load())",
        "Constant(value='flock')",
    ]
    return sorted(
        ast.dump(node, annotate_fields=True, include_attributes=False)
        for node in governed
    ) == sorted(expected)


def _is_exact_capability_probe_call(
    relative_path: str,
    source: str,
    node: ast.Call,
    environments: dict[ast.AST, dict[str, object]],
) -> bool:
    if (
        relative_path != "kernel/bin/awa-registration-bootstrap.py"
        or _sha256(source.encode("utf-8")) != _BOOTSTRAP_SHA256
    ):
        return False
    target = _static_value(node.func, environments.get(node, {}))
    if target == _symbol("builtins.compile") and node.args:
        return _is_exact_capability_probe(
            _static_value(node.args[0], environments.get(node.args[0], {}))
        )
    if target == _symbol("builtins.exec") and node.args \
            and isinstance(node.args[0], ast.Call):
        return _is_exact_capability_probe_call(
            relative_path, source, node.args[0], environments
        )
    return False


def _retained_importer_generated_nodes(
    relative_path: str,
    source: str,
    tree: ast.Module,
) -> set[ast.Call]:
    if (
        relative_path != "kernel/bin/awa-registration-child.py"
        or _sha256(source.encode("utf-8")) != _RETAINED_IMPORTER_SHA256
    ):
        return set()
    scope = _qualified_scopes(tree).get("RetainedProductImporter.exec_module")
    if scope is None:
        return set()
    calls = {
        node
        for node in ast.walk(scope)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id in {"compile", "exec"}
        )
    }
    if len(calls) != 2:
        raise AssertionError("retained importer generated-source closure drift")
    return calls


def _static_value(node: ast.AST, env: dict[str, object], depth: int = 0):
    if depth > 24:
        return _UNKNOWN
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return _string(node.value)
        if isinstance(node.value, bool):
            return ("boolean", node.value)
        if isinstance(node.value, int):
            return _integer(node.value)
        return ("constant", node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id.startswith("safe_"):
            return _safe_callable(node.id)
        if node.id in {
            "getattr", "setattr", "delattr", "__import__",
            "compile", "eval", "exec", "list", "tuple", "set", "dict",
            "str", "bytes", "bytearray", "bool", "int", "len",
            "enumerate", "range", "min",
            "max", "reversed", "sorted", "all", "any", "isinstance",
            "zip", "print", "object", "type", "super",
        }:
            return _symbol(f"builtins.{node.id}")
        return _UNKNOWN
    if isinstance(node, ast.Starred):
        return _static_value(node.value, env, depth + 1)
    if isinstance(node, ast.UnaryOp) and isinstance(
        node.op, (ast.UAdd, ast.USub),
    ):
        operand = _abstract_number(
            _static_value(node.operand, env, depth + 1)
        )
        if operand is not None:
            return _number_value(
                +operand if isinstance(node.op, ast.UAdd) else -operand
            )
        return _UNKNOWN
    if isinstance(node, ast.Attribute):
        base = _static_value(node.value, env, depth + 1)
        if base[0] == "opaque_member":
            return base
        if base[0] in {"module", "symbol"}:
            return _symbol(f"{base[1]}.{node.attr}")
        records = _heap_records(base)
        if records:
            values: list[object] = []
            opaque = False
            heap_methods = {
                "append", "extend", "insert", "add", "update",
                "setdefault", "pop", "popitem", "remove", "clear",
                "sort", "reverse", "items", "keys", "values", "copy",
                "get", "index", "count", "discard", "__setitem__",
                "__delitem__", "__setattr__", "__delattr__",
            }
            if all(
                record["kind"] in {"bytearray", "bytes"}
                for record in records
            ):
                heap_methods.update({
                    "find", "endswith", "startswith", "decode",
                })
            if node.attr in heap_methods:
                identities = ",".join(
                    sorted(str(record["id"]) for record in records)
                )
                return _symbol(f"heapmethod.{identities}.{node.attr}")
            for record in records:
                opaque = opaque or bool(record["opaque"])
                members = record["members"]
                assert isinstance(members, dict)
                key = ("attribute", node.attr)
                if key in members:
                    values.append(members[key])
                if _WILDCARD_ATTRIBUTE in members:
                    values.append(members[_WILDCARD_ATTRIBUTE])
            if values:
                if base[0] == "heaprefs" and base[1][1]:
                    values.append(_UNKNOWN)
                if opaque:
                    values.append(_opaque_member())
                return _merge_values(values)
            if opaque:
                return _opaque_member(_value_callable_targets(base))
            return _UNKNOWN
        if base[0] == "object":
            matches = [
                value for name, value in base[1] if name == node.attr
            ]
            return matches[0] if len(matches) == 1 else _UNKNOWN
        if (
            base[0] == "call_result"
            and base[1] == _symbol("re.compile")
            and node.attr in {"fullmatch", "match", "search"}
        ):
            return _symbol(f"re.Pattern.{node.attr}")
        if (
            base[0] == "call_result"
            and base[1] == _symbol("builtins.super")
            and node.attr == "__init__"
        ):
            return _symbol("builtins.super.__init__")
        if base[0] == "tainted":
            return base
        if base[0] == "opaque":
            return _opaque_member(_value_callable_targets(base))
        return _UNKNOWN
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_value(node.left, env, depth + 1)
        right = _static_value(node.right, env, depth + 1)
        if left[0] == right[0] == "string":
            return _string(left[1] + right[1])
        if left[0] == right[0] == "integer":
            return _integer(left[1] + right[1])
        left_number = _abstract_number(left)
        right_number = _abstract_number(right)
        if left_number is not None and right_number is not None:
            return _number_value(left_number + right_number)
        return _UNKNOWN
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _static_value(node.left, env, depth + 1)
        right = _static_value(node.right, env, depth + 1)
        if left[0] == right[0] == "integer":
            return _integer(left[1] | right[1])
        records = _heap_records(left) + _heap_records(right)
        if records:
            result = _allocate(node, "dict", env)
            for source in records:
                _heap_update_mapping(result, source, strong=True)
            if not _heap_records(left) or not _heap_records(right):
                result["opaque"] = True
            return _heap_value([result])
        return ("tuple", (left, right))
    if isinstance(node, ast.BoolOp):
        return _merge_values([
            _static_value(value, env, depth + 1)
            for value in node.values
        ])
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        kind = (
            "list" if isinstance(node, ast.List)
            else "set" if isinstance(node, ast.Set)
            else "tuple"
        )
        if kind != "tuple" and env.get(_POTENTIAL_KEY) is True:
            return _heap_value([_allocate(node, kind, env)])
        items: list[object] = []
        for item in node.elts:
            value = _static_value(
                item.value if isinstance(item, ast.Starred) else item,
                env,
                depth + 1,
            )
            if (
                isinstance(item, ast.Starred)
                and isinstance(value, tuple)
                and len(value) == 2
                and value[0] in {"list", "tuple"}
            ):
                items.extend(value[1])
            elif isinstance(item, ast.Starred):
                items.append(_containerized(value))
            else:
                items.append(_containerized(value))
        if kind == "tuple":
            return (kind, tuple(items))
        record = _allocate(node, kind, env)
        members = record["members"]
        assert isinstance(members, dict)
        if not members:
            members.update({
                ("index", index): value
                for index, value in enumerate(items)
            })
        return _heap_value([record])
    if isinstance(node, ast.Dict):
        if env.get(_POTENTIAL_KEY) is True:
            return _heap_value([_allocate(node, "dict", env)])
        entries: list[tuple[object, object]] = []
        mapping_operations: list[tuple[object, object]] = []
        unresolved_unpack = False
        for key, value_node in zip(node.keys, node.values):
            value = _static_value(value_node, env, depth + 1)
            if key is None:
                records = _heap_records(value)
                if records and all(
                    record["kind"] == "dict"
                    and not bool(record["opaque"])
                    for record in records
                ):
                    for source in records:
                        source_members = source["members"]
                        assert isinstance(source_members, dict)
                        mapping_operations.extend(source_members.items())
                elif value[0] == "dict":
                    entries.extend(value[1])
                else:
                    unresolved_unpack = True
                    entries.append((_UNKNOWN, _containerized(value)))
                continue
            entries.append((
                _static_value(key, env, depth + 1),
                _containerized(value),
            ))
        record = _allocate(node, "dict", env)
        members = record["members"]
        assert isinstance(members, dict)
        if not members:
            mapping_operations.extend(
                (_mapping_key(key), value) for key, value in entries
            )
            for key_token, value in mapping_operations:
                _heap_store(
                    record, key_token, value, strong=True,
                )
        if unresolved_unpack:
            record["opaque"] = True
        return _heap_value([record])
    if isinstance(
        node,
        (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp),
    ):
        if env.get(_POTENTIAL_KEY) is True:
            return _heap_value([_allocate(node, "comprehension", env)])
        record = _allocate(node, "comprehension", env)
        return _heap_value([record])
    if isinstance(node, ast.Subscript):
        container = _static_value(node.value, env, depth + 1)
        key = _static_value(node.slice, env, depth + 1)
        if container[0] == "opaque_member":
            return container
        if container[0] == "tainted":
            return container
        if container[0] == "opaque":
            return _opaque_member(_value_callable_targets(container))
        records = _heap_records(container)
        if records:
            values: list[object] = []
            opaque = False
            for record in records:
                opaque = opaque or bool(record["opaque"])
                key_token = _subscript_key(record, node.slice, key)
                values.extend(_heap_read_subscript(record, key_token))
            if container[0] == "heaprefs" and container[1][1]:
                values.append(_UNKNOWN)
            if opaque:
                values.append(_opaque_member())
            return _merge_values(values) if values else _UNKNOWN
        if container[0] == "dict" and key != _UNKNOWN:
            matches = [value for candidate, value in container[1] if candidate == key]
            return matches[0] if len(matches) == 1 else _UNKNOWN
        if container[0] in {"list", "tuple"} and key[0] == "integer":
            try:
                return container[1][key[1]]
            except IndexError:
                return _UNKNOWN
        return _UNKNOWN
    if isinstance(node, ast.IfExp):
        return _merge_values([
            _static_value(node.body, env, depth + 1),
            _static_value(node.orelse, env, depth + 1),
        ])
    if isinstance(node, ast.JoinedStr):
        values: list[str] = []
        for item in node.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
            elif isinstance(item, ast.FormattedValue):
                value = _static_value(item.value, env, depth + 1)
                if value[0] not in {"string", "integer"}:
                    return _UNKNOWN
                values.append(str(value[1]))
            else:
                return _UNKNOWN
        return _string("".join(values))
    if isinstance(node, ast.Call):
        callee = _static_value(node.func, env, depth + 1)
        positional_values, keyword_values, _ = _all_call_values(node, env)
        keyword_map = {
            key[1]: value
            for key, value in keyword_values
            if (
                isinstance(key, tuple)
                and len(key) == 2
                and key[0] == "string"
            )
        }
        if callee == _symbol("builtins.object"):
            if env.get(_POTENTIAL_KEY) is True:
                return _heap_value([_allocate(node, "object", env)])
            record = _allocate(node, "object", env)
            positional, keywords, _ = _all_call_values(node, env)
            if positional or keywords:
                record["opaque"] = True
            return _heap_value([record])
        if any(callee == item for item in (
            _symbol("builtins.dict"),
            _symbol("builtins.list"),
            _symbol("builtins.set"),
            _symbol("builtins.tuple"),
            _symbol("builtins.bytearray"),
        )):
            kind = str(callee[1]).rpartition(".")[2]
            if env.get(_POTENTIAL_KEY) is True:
                return _heap_value([_allocate(node, kind, env)])
            record = _allocate(node, kind, env)
            members = record["members"]
            assert isinstance(members, dict)
            positional, keywords, _ = _all_call_values(node, env)
            if kind == "dict":
                for source in positional:
                    source_records = _heap_records(source)
                    if source_records:
                        for source_record in source_records:
                            _heap_update_mapping(
                                record, source_record, strong=True,
                            )
                    elif (
                        isinstance(source, tuple)
                        and len(source) == 2
                        and source[0] == "tuple"
                    ):
                        for pair in source[1]:
                            if (
                                isinstance(pair, tuple)
                                and len(pair) == 2
                                and pair[0] == "tuple"
                                and len(pair[1]) == 2
                            ):
                                _heap_store(
                                    record,
                                    _mapping_key(pair[1][0]),
                                    _containerized(pair[1][1]),
                                    strong=True,
                                )
                            else:
                                record["opaque"] = True
                    else:
                        record["opaque"] = True
                for key, item in keywords:
                    if key == _UNKNOWN:
                        _heap_store(
                            record, _WILDCARD_MAPPING,
                            _containerized(item),
                        )
                    else:
                        _heap_store(
                            record,
                            _mapping_key(key),
                            _containerized(item),
                            strong=True,
                        )
            else:
                values: list[object] = []
                for source in positional:
                    source_records = _heap_records(source)
                    if source_records:
                        values.extend(_ordered_heap_members(source))
                    elif (
                        isinstance(source, tuple)
                        and len(source) == 2
                        and source[0] == "tuple"
                    ):
                        values.extend(source[1])
                    elif source == _UNKNOWN:
                        record["opaque"] = True
                    else:
                        values.append(source)
                for _, item in keywords:
                    values.append(item)
                    record["opaque"] = True
                for index, item in enumerate(values):
                    _heap_store(
                        record,
                        ("index", index),
                        _containerized(item),
                    )
            return _heap_value([record])
        if callee == _symbol("builtins.__import__") or callee == _symbol(
            "importlib.import_module"
        ):
            if not positional_values:
                return _UNKNOWN
            name = positional_values[0]
            return _module(name[1]) if name[0] == "string" else _UNKNOWN
        if callee == _symbol("builtins.getattr") and len(positional_values) >= 2:
            base = positional_values[0]
            name = positional_values[1]
            if base[0] in {"module", "symbol"} and name[0] == "string":
                return _symbol(f"{base[1]}.{name[1]}")
            return _UNKNOWN
        if (
            callee[0] == "symbol"
            and str(callee[1]).startswith("heapmethod.")
        ):
            _, identities, method = str(callee[1]).split(".", 2)
            heap = env.get(_HEAP_KEY, {})
            records = [
                heap[identity]
                for identity in identities.split(",")
                if isinstance(heap, dict) and identity in heap
            ]
            if method in {"get", "pop", "setdefault"} and (
                positional_values or "key" in keyword_map
            ):
                key = (
                    positional_values[0]
                    if positional_values else keyword_map["key"]
                )
                values: list[object] = []
                for record in records:
                    key_token = _subscript_key(
                        record,
                        node.args[0] if node.args else node,
                        key,
                    )
                    values.extend(_heap_read_subscript(record, key_token))
                    if bool(record["opaque"]):
                        values.append(_opaque_member())
                if not values and (
                    len(positional_values) > 1 or "default" in keyword_map
                ):
                    values.append(
                        positional_values[1]
                        if len(positional_values) > 1
                        else keyword_map["default"]
                    )
                return _merge_values(values) if values else _UNKNOWN
            return ("call_result", callee)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "join":
            separator = _static_value(node.func.value, env, depth + 1)
            values = (
                positional_values[0] if positional_values else _UNKNOWN
            )
            if separator[0] == "string" and values[0] in {"list", "tuple"} \
                    and all(value[0] == "string" for value in values[1]):
                return _string(separator[1].join(value[1] for value in values[1]))
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "strip", "lstrip", "rstrip",
        }:
            base = _static_value(node.func.value, env, depth + 1)
            if base[0] == "string":
                characters = (
                    positional_values[0]
                    if positional_values else _string(None)
                )
                if characters[0] == "string":
                    return _string(
                        getattr(base[1], node.func.attr)(characters[1])
                    )
        return ("call_result", callee)
    return _UNKNOWN


def _node_references_governed(node: ast.AST, env: dict[str, object]) -> bool:
    return any(
        isinstance(child, (ast.Name, ast.Attribute, ast.Constant))
        and (
            _value_is_governed_reference(_static_value(child, env))
            or (
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and _value_contains_governed(_string(child.value))
            )
        )
        for child in ast.walk(node)
    )


def _assignment_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    result: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            result.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            result.extend(item.id for item in target.elts if isinstance(item, ast.Name))
    return result


def _merge_environments(
    environments: list[dict[str, object]],
) -> dict[str, object]:
    keys = set().union(*(environment.keys() for environment in environments))
    merged = {
        key: _merge_values(values)
        for key in keys - {
            _HEAP_KEY, _ALLOCATIONS_KEY, _CLASS_KEY, _POTENTIAL_KEY,
            _WEAK_WRITES_KEY,
        }
        if (values := [environment.get(key, _UNKNOWN) for environment in environments])
    }
    for special in (_HEAP_KEY, _ALLOCATIONS_KEY, _CLASS_KEY):
        for environment in environments:
            if special in environment:
                merged[special] = environment[special]
                break
    return merged


def _scope_local_names(scope: ast.AST) -> set[str]:
    names: set[str] = set()
    global_names: set[str] = set()
    nonlocal_names: set[str] = set()

    def visit(node: ast.AST) -> None:
        if node is not scope and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            names.add(node.name) if hasattr(node, "name") else None
            return
        if isinstance(node, ast.Global):
            global_names.update(node.names)
            return
        if isinstance(node, ast.Nonlocal):
            nonlocal_names.update(node.names)
            return
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names.update(_assignment_targets(node))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            names.update(_target_names(node.target))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    names.update(_target_names(item.optional_vars))
        elif isinstance(node, ast.NamedExpr):
            names.update(_target_names(node.target))
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(scope)
    return names - global_names - nonlocal_names


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(item) for item in target.elts))
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    if isinstance(target, ast.MatchAs):
        return ({target.name} if target.name else set()) | (
            _target_names(target.pattern) if target.pattern is not None else set()
        )
    if isinstance(target, ast.MatchStar):
        return {target.name} if target.name else set()
    if isinstance(target, ast.MatchMapping):
        return ({target.rest} if target.rest else set()) | set().union(
            *(_target_names(pattern) for pattern in target.patterns),
            set(),
        )
    if isinstance(target, ast.MatchClass):
        return set().union(
            *(
                _target_names(pattern)
                for pattern in list(target.patterns) + list(target.kwd_patterns)
            ),
            set(),
        )
    if isinstance(target, (ast.MatchSequence, ast.MatchOr)):
        return set().union(
            *(_target_names(pattern) for pattern in target.patterns),
            set(),
        )
    return set()


def _parameter_names(arguments: ast.arguments) -> set[str]:
    return {
        argument.arg
        for argument in (
            list(arguments.posonlyargs)
            + list(arguments.args)
            + list(arguments.kwonlyargs)
        )
    } | ({arguments.vararg.arg} if arguments.vararg else set()) | (
        {arguments.kwarg.arg} if arguments.kwarg else set()
    )


def _annotation_container_kind(annotation: ast.AST | None) -> str:
    cursor = annotation
    while isinstance(cursor, ast.Subscript):
        cursor = cursor.value
    name = (
        cursor.id
        if isinstance(cursor, ast.Name)
        else cursor.attr
        if isinstance(cursor, ast.Attribute)
        else ""
    )
    if name in {"dict", "Dict", "Mapping", "MutableMapping"}:
        return "dict"
    if name in {"list", "List", "Sequence", "MutableSequence"}:
        return "list"
    if name in {"tuple", "Tuple"}:
        return "tuple"
    if name in {"bytes", "bytearray"}:
        return name
    return "mutable"


class _EnvironmentBuilder:
    def __init__(
        self,
        tree: ast.Module,
        initial: dict[str, object],
        source_id: str = "<synthetic>",
    ) -> None:
        self.tree = tree
        self.source_id = source_id
        self.by_node: dict[ast.AST, dict[str, object]] = {}
        self.parent = {
            child: node
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }
        scope_names = {
            node: name
            for name, node in _qualified_scopes(tree).items()
        }
        scope_names[tree] = "<module>"
        preorder: list[ast.AST] = []

        def visit(node: ast.AST) -> None:
            preorder.append(node)
            for child in ast.iter_child_nodes(node):
                visit(child)

        visit(tree)
        allocations: dict[ast.AST, str] = {}
        for index, node in enumerate(preorder):
            scope: ast.AST | None = node
            while scope not in scope_names:
                scope = self.parent.get(scope)
                if scope is None:
                    break
            qualname = scope_names.get(scope, "<module>")
            allocations[node] = _sha256(
                b"awa-kernel-abstract-allocation/v1\0"
                + source_id.encode("utf-8")
                + b"\0"
                + qualname.encode("utf-8")
                + b"\0"
                + str(index).encode("ascii")
                + b"\0"
                + ast.dump(
                    node,
                    annotate_fields=True,
                    include_attributes=False,
                ).encode("utf-8")
                + b"\n"
            )
        self.heap: dict[str, dict[str, object]] = {}
        self.initial = dict(initial)
        self.initial[_HEAP_KEY] = self.heap
        self.initial[_ALLOCATIONS_KEY] = allocations
        self.volatile_names = {
            name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Global, ast.Nonlocal))
            for name in node.names
        }
        mutation_methods = {
            "append", "extend", "insert", "add", "update", "setdefault",
            "__setitem__", "__delitem__", "__setattr__", "__delattr__",
        }

        def owner(node: ast.AST) -> ast.AST:
            cursor: ast.AST | None = node
            while cursor is not None and not isinstance(
                cursor,
                (
                    ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                    ast.ClassDef, ast.Lambda,
                ),
            ):
                cursor = self.parent.get(cursor)
            return cursor if cursor is not None else tree

        self.mutable_names: dict[ast.AST, set[str]] = {
            scope: set()
            for scope in scope_names
        }
        for node in ast.walk(tree):
            scope = owner(node)
            if isinstance(node, ast.Subscript) and isinstance(
                node.ctx, (ast.Store, ast.Del),
            ) and isinstance(node.value, ast.Name):
                self.mutable_names.setdefault(scope, set()).add(node.value.id)
            elif isinstance(node, ast.Attribute) and isinstance(
                node.ctx, (ast.Store, ast.Del),
            ) and isinstance(node.value, ast.Name):
                self.mutable_names.setdefault(scope, set()).add(node.value.id)
            elif isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in mutation_methods
                    and isinstance(node.func.value, ast.Name)
                ):
                    self.mutable_names.setdefault(scope, set()).add(
                        node.func.value.id
                    )
                direct_name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else None
                )
                if direct_name in mutation_methods | {"setattr", "delattr"} \
                        and node.args and isinstance(node.args[0], ast.Name):
                    self.mutable_names.setdefault(scope, set()).add(
                        node.args[0].id
                    )
        aliases = [
            (owner(node), node.targets[0].id, node.value.id)
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Name)
        ]
        for _ in range(max(1, len(aliases) + 1)):
            changed = False
            for scope, left, right in aliases:
                names = self.mutable_names.setdefault(scope, set())
                if left in names or right in names:
                    before = len(names)
                    names.update({left, right})
                    changed = changed or len(names) != before
            if not changed:
                break
        alias_environment: dict[str, object] = {
            _HEAP_KEY: self.heap,
            _ALLOCATIONS_KEY: allocations,
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    alias_environment[
                        alias.asname or alias.name.split(".")[0]
                    ] = _module(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    alias_environment[alias.asname or alias.name] = _symbol(
                        f"{node.module}.{alias.name}"
                    )
        self.volatile_values = {
            name: _UNKNOWN for name in self.volatile_names
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) \
                    and getattr(node, "value", None) is not None:
                volatile_targets = (
                    set(_assignment_targets(node)) & self.volatile_names
                )
                if not volatile_targets:
                    continue
                evaluation = dict(alias_environment)
                evaluation[_POTENTIAL_KEY] = True
                value = _static_value(node.value, evaluation)
                for name in volatile_targets:
                    self.volatile_values[name] = _merge_values([
                        self.volatile_values[name], value, _UNKNOWN,
                    ])
        scopes = [
            node for node in ast.walk(tree)
            if isinstance(
                node,
                (
                    ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                    ast.ClassDef, ast.Lambda,
                ),
            )
        ]
        self.scope_potentials: dict[ast.AST, dict[str, object]] = {
            scope: {} for scope in scopes
        }
        direct_writes: list[tuple[ast.AST, str, ast.AST | object]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = self._enclosing_scope(node)
                if owner is not None:
                    direct_writes.append(
                        (owner, node.name, _symbol(f"local.{node.name}"))
                    )
                continue
            if isinstance(node, ast.Import):
                owner = self._enclosing_scope(node)
                if owner is not None:
                    direct_writes.extend(
                        (
                            owner,
                            alias.asname or alias.name.split(".")[0],
                            _module(alias.name),
                        )
                        for alias in node.names
                    )
                continue
            if isinstance(node, ast.ImportFrom) and node.module:
                owner = self._enclosing_scope(node)
                if owner is not None:
                    direct_writes.extend(
                        (
                            owner,
                            alias.asname or alias.name,
                            _symbol(f"{node.module}.{alias.name}"),
                        )
                        for alias in node.names
                    )
                continue
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            value_node = getattr(node, "value", None)
            if value_node is None:
                continue
            owner = self._enclosing_scope(node)
            if owner is None:
                continue
            targets = (
                _assignment_targets(node)
                if isinstance(node, (ast.Assign, ast.AnnAssign))
                else _target_names(node.target)
            )
            direct_writes.extend(
                (owner, name, value_node) for name in targets
            )
        for _ in range(max(1, len(direct_writes) + 1)):
            changed = False
            for owner, name, value_source in direct_writes:
                evaluation = dict(alias_environment)
                evaluation.update(self.scope_potentials[owner])
                evaluation[_POTENTIAL_KEY] = True
                value = (
                    _static_value(value_source, evaluation)
                    if isinstance(value_source, ast.AST)
                    else value_source
                )
                if _value_has_callable_authority(value):
                    value = _containerized(value)
                previous = self.scope_potentials[owner].get(name)
                updated = (
                    value if previous is None
                    else _merge_values([previous, value])
                )
                if previous != updated:
                    self.scope_potentials[owner][name] = updated
                    changed = True
            if not changed:
                break

    def build(self) -> dict[ast.AST, dict[str, object]]:
        self._statements(self.tree.body, dict(self.initial))
        return self.by_node

    def _enclosing_scope(self, node: ast.AST) -> ast.AST | None:
        cursor = self.parent.get(node)
        while cursor is not None:
            if isinstance(
                cursor,
                (
                    ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                    ast.ClassDef, ast.Lambda,
                ),
            ):
                return cursor
            cursor = self.parent.get(cursor)
        return None

    def _mark(self, node: ast.AST, environment: dict[str, object]) -> None:
        self.by_node[node] = dict(environment)

    def _mutation_records(
        self,
        expression: ast.AST,
        environment: dict[str, object],
        kind: str,
    ) -> list[dict[str, object]]:
        value = _static_value(expression, environment)
        records = _heap_records(value)
        if records:
            if kind != "mutable":
                for record in records:
                    if record["kind"] == "mutable":
                        record["kind"] = kind
            return records
        if not isinstance(expression, ast.Name) or not _is_unresolved(value):
            return records
        record = _allocate(expression, kind, environment)
        heap_value = _heap_value([record])
        environment[expression.id] = heap_value
        if expression in self.by_node:
            self.by_node[expression][expression.id] = heap_value
        return [record]

    def _replace_aliases(
        self,
        old: object,
        new: object,
        environment: dict[str, object],
    ) -> None:
        for name, binding in list(environment.items()):
            environment[name] = _replace_nested(binding, old, new)

    def _bind(
        self,
        target: ast.AST,
        value: object,
        environment: dict[str, object],
    ) -> None:
        self._mark(target, environment)
        if isinstance(target, ast.Name):
            environment[target.id] = (
                _merge_values([
                    environment.get(target.id, _UNKNOWN),
                    value,
                    self.volatile_values.get(target.id, _UNKNOWN),
                    _UNKNOWN,
                ])
                if target.id in self.volatile_names
                else _containerized(value)
            )
        elif isinstance(target, (ast.Tuple, ast.List)):
            values = (
                value[1]
                if isinstance(value, tuple)
                and len(value) == 2
                and value[0] in {"tuple", "list"}
                and len(value[1]) == len(target.elts)
                else (_UNKNOWN,) * len(target.elts)
            )
            records = _heap_records(value)
            if records and len(records) == 1:
                members = records[0]["members"]
                assert isinstance(members, dict)
                values = tuple(
                    members.get(("index", index), _UNKNOWN)
                    for index in range(len(target.elts))
                )
            for item, item_value in zip(target.elts, values):
                self._bind(item, item_value, environment)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, _UNKNOWN, environment)
        elif isinstance(target, ast.Subscript):
            self._mark_expression(target.value, environment)
            self._mark_expression(target.slice, environment)
            container = _static_value(target.value, environment)
            key = _static_value(target.slice, environment)
            stored = _protocol_value(value)
            records = self._mutation_records(
                target.value, environment, "mutable",
            )
            if records:
                for record in records:
                    key_token = _subscript_key(record, target.slice, key)
                    _heap_store(
                        record,
                        key_token,
                        stored,
                        strong=not (
                            environment.get(_POTENTIAL_KEY)
                            or environment.get(_WEAK_WRITES_KEY)
                        ),
                    )
                return
            if container[0] == "dict" and not _is_unresolved(key):
                entries = [
                    (candidate, item)
                    for candidate, item in container[1]
                    if candidate != key
                ]
                entries.append((key, stored))
                updated = (
                    "dict",
                    tuple(sorted(entries, key=lambda item: repr(item[0]))),
                )
            elif (
                container[0] in {"list", "tuple"}
                and key[0] == "integer"
                and 0 <= key[1] < len(container[1])
            ):
                entries = list(container[1])
                entries[key[1]] = stored
                updated = (container[0], tuple(entries))
            else:
                updated = _merge_values([container, stored, _UNKNOWN])
            if container == _UNKNOWN and isinstance(target.value, ast.Name):
                environment[target.value.id] = updated
            else:
                self._replace_aliases(container, updated, environment)
        elif isinstance(target, ast.Attribute):
            self._mark_expression(target.value, environment)
            container = _static_value(target.value, environment)
            records = self._mutation_records(
                target.value, environment, "object",
            )
            if records:
                for record in records:
                    _heap_store(
                        record,
                        ("attribute", target.attr),
                        _containerized(value),
                    )
                return
            attributes = (
                dict(container[1]) if container[0] == "object" else {}
            )
            attributes[target.attr] = _containerized(value)
            updated = (
                "object",
                tuple(sorted(attributes.items(), key=lambda item: item[0])),
            )
            if container == _UNKNOWN and isinstance(target.value, ast.Name):
                environment[target.value.id] = updated
            else:
                self._replace_aliases(container, updated, environment)
        else:
            for child in ast.iter_child_nodes(target):
                self._mark_expression(child, environment)

    def _mark_expression(
        self,
        node: ast.AST,
        environment: dict[str, object],
        walrus_environment: dict[str, object] | None = None,
        conditional_walrus: bool = False,
    ) -> None:
        if walrus_environment is None:
            walrus_environment = environment
        self._mark(node, environment)
        if isinstance(node, ast.Lambda):
            child = dict(environment)
            for name in _scope_local_names(node) | _parameter_names(node.args):
                child[name] = _UNKNOWN
            for argument in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
                + ([node.args.vararg] if node.args.vararg else [])
                + ([node.args.kwarg] if node.args.kwarg else [])
            ):
                if argument.arg in self.mutable_names.get(node, set()):
                    child[argument.arg] = _heap_value([
                        _allocate(
                            argument,
                            _annotation_container_kind(argument.annotation),
                            child,
                        )
                    ])
            for default in list(node.args.defaults) + [
                value for value in node.args.kw_defaults if value is not None
            ]:
                self._mark_expression(default, environment)
            self._mark_expression(node.body, child, child)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            child = dict(environment)
            for generator in node.generators:
                self._mark_expression(
                    generator.iter, child, walrus_environment, True
                )
                self._bind(generator.target, _UNKNOWN, child)
                for condition in generator.ifs:
                    self._mark_expression(
                        condition, child, walrus_environment, True
                    )
            if isinstance(node, ast.DictComp):
                self._mark_expression(
                    node.key, child, walrus_environment, True
                )
                self._mark_expression(
                    node.value, child, walrus_environment, True
                )
            else:
                self._mark_expression(
                    node.elt, child, walrus_environment, True
                )
            return
        if isinstance(node, ast.NamedExpr):
            self._mark_expression(
                node.value, environment, walrus_environment, conditional_walrus
            )
            value = _static_value(node.value, self.by_node[node.value])
            if conditional_walrus:
                before = dict(walrus_environment)
                executed = dict(walrus_environment)
                executed[_WEAK_WRITES_KEY] = True
                self._bind(node.target, value, executed)
                walrus_environment.clear()
                walrus_environment.update(
                    _merge_environments([before, executed])
                )
                for name in _target_names(node.target):
                    environment[name] = walrus_environment.get(name, _UNKNOWN)
            else:
                self._bind(node.target, value, walrus_environment)
            return
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr in {
                "append", "extend", "insert", "add", "update",
                "setdefault", "__setitem__", "__delitem__",
                "__setattr__", "__delattr__",
            }
        ):
            self._mutation_records(node.value, environment, "mutable")
            self._mark(node, environment)
        for child in ast.iter_child_nodes(node):
            self._mark_expression(
                child,
                environment,
                walrus_environment,
                conditional_walrus,
            )
        if isinstance(node, ast.Call):
            direct_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if direct_name in {
                "setattr", "delattr", "__setitem__", "__delitem__",
                "__setattr__", "__delattr__",
            } and node.args:
                mutation_kind = (
                    "dict"
                    if isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "dict"
                    else "list"
                    if isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in {"list", "tuple", "bytearray"}
                    else "object"
                    if direct_name in {"setattr", "delattr", "__setattr__",
                                       "__delattr__"}
                    else "mutable"
                )
                self._mutation_records(
                    node.args[0], environment, mutation_kind,
                )
                self._mark(node, environment)
            target = _static_value(node.func, self.by_node[node.func])
            value = _static_value(node, self.by_node[node])
            call_environment = self.by_node[node]
            positional, keywords, all_values = _all_call_values(
                node, call_environment
            )
            keyword_map = {
                key[1]: item
                for key, item in keywords
                if (
                    isinstance(key, tuple)
                    and len(key) == 2
                    and key[0] == "string"
                )
            }
            records: list[dict[str, object]] = []
            method: str | None = None
            if (
                isinstance(target, tuple)
                and len(target) == 2
                and target[0] == "symbol"
                and str(target[1]).startswith("heapmethod.")
            ):
                _, identities, method = str(target[1]).split(".", 2)
                records = [
                    self.heap[identity]
                    for identity in identities.split(",")
                    if identity in self.heap
                ]
            elif (
                isinstance(target, tuple)
                and len(target) == 2
                and target[0] == "symbol"
                and str(target[1]).rpartition(".")[2] in {
                    "append", "extend", "insert", "add", "update",
                    "setdefault", "__setitem__", "__delitem__",
                    "__setattr__", "__delattr__",
                }
                and positional
            ):
                method = str(target[1]).rpartition(".")[2]
                records = _heap_records(positional.pop(0))
            elif target == _symbol("builtins.setattr") and len(positional) >= 3:
                attribute_name = positional[1]
                if attribute_name[0] == "string":
                    for record in _heap_records(positional[0]):
                        _heap_store(
                            record,
                            ("attribute", attribute_name[1]),
                            _protocol_value(positional[2]),
                        )
                else:
                    for record in _heap_records(positional[0]):
                        _heap_store(
                            record,
                            _WILDCARD_ATTRIBUTE,
                            _protocol_value(positional[2]),
                        )
            elif target == _symbol("builtins.setattr") and positional:
                for record in _heap_records(positional[0]):
                    _heap_store(
                        record, _WILDCARD_ATTRIBUTE, _opaque_callable()
                    )
            elif target == _symbol("builtins.delattr") and len(positional) >= 2:
                attribute_name = positional[1]
                if attribute_name[0] == "string":
                    for record in _heap_records(positional[0]):
                        _heap_store(
                            record,
                            ("attribute", attribute_name[1]),
                            _UNKNOWN,
                        )
                else:
                    for record in _heap_records(positional[0]):
                        _heap_store(
                            record, _WILDCARD_ATTRIBUTE, _opaque_callable()
                        )
            elif target == _symbol("builtins.delattr") and positional:
                for record in _heap_records(positional[0]):
                    _heap_store(
                        record, _WILDCARD_ATTRIBUTE, _opaque_callable()
                    )
            elif (
                any(target == item for item in (
                    _symbol("operator.setitem"),
                    _symbol("builtins.setitem"),
                ))
                and len(positional) >= 3
            ):
                method = "__setitem__"
                records = _heap_records(positional.pop(0))
            elif (
                target == _symbol("operator.delitem")
                and len(positional) >= 2
            ):
                method = "__delitem__"
                records = _heap_records(positional.pop(0))
            if records and method is not None:
                for record in records:
                    members = record["members"]
                    assert isinstance(members, dict)
                    if method in {"append", "add"} and positional:
                        indexes = [
                            key[1]
                            for key in members
                            if isinstance(key, tuple)
                            and len(key) == 2
                            and key[0] == "index"
                            and isinstance(key[1], int)
                        ]
                        _heap_store(
                            record,
                            ("index", max(indexes, default=-1) + 1),
                            _containerized(positional[0]),
                        )
                    elif method in {"append", "add"}:
                        record["opaque"] = True
                        for _, item in keywords:
                            _heap_store(
                                record,
                                ("index", f"keyword-{len(members)}"),
                                _containerized(item),
                            )
                    elif method == "extend" and positional:
                        source_values: list[object] = []
                        source_records = _heap_records(positional[0])
                        if source_records:
                            source_values.extend(
                                value
                                for source in source_records
                                for value in _heap_member_values(source)
                            )
                        elif (
                            isinstance(positional[0], tuple)
                            and len(positional[0]) == 2
                            and positional[0][0] == "tuple"
                        ):
                            source_values.extend(positional[0][1])
                        else:
                            record["opaque"] = True
                        indexes = [
                            key[1]
                            for key in members
                            if isinstance(key, tuple)
                            and len(key) == 2
                            and key[0] == "index"
                            and isinstance(key[1], int)
                        ]
                        next_index = max(indexes, default=-1) + 1
                        for item in source_values:
                            _heap_store(
                                record,
                                ("index", next_index),
                                _containerized(item),
                            )
                            next_index += 1
                    elif method == "extend":
                        record["opaque"] = True
                        for _, item in keywords:
                            _heap_store(
                                record,
                                ("index", f"keyword-{len(members)}"),
                                _containerized(item),
                            )
                    elif method == "update":
                        for source_value in positional:
                            source_records = _heap_records(source_value)
                            if source_records:
                                for source in source_records:
                                    _heap_update_mapping(
                                        record,
                                        source,
                                        strong=not (
                                            environment.get(_POTENTIAL_KEY)
                                            or environment.get(_WEAK_WRITES_KEY)
                                        ),
                                    )
                            else:
                                record["opaque"] = True
                        for key, item in keywords:
                            if key == _UNKNOWN:
                                _heap_store(
                                    record,
                                    _WILDCARD_MAPPING,
                                    _containerized(item),
                                )
                            else:
                                _heap_store(
                                    record,
                                    _mapping_key(key),
                                    _containerized(item),
                                    strong=not (
                                        environment.get(_POTENTIAL_KEY)
                                        or environment.get(_WEAK_WRITES_KEY)
                                    ),
                                )
                    elif method == "setdefault" and (
                        positional or "key" in keyword_map
                    ):
                        key = (
                            positional[0]
                            if positional else keyword_map["key"]
                        )
                        key_token = _subscript_key(
                            record,
                            node.args[0] if node.args else node,
                            key,
                        )
                        if key_token not in members:
                            _heap_store(
                                record,
                                key_token,
                                _containerized(
                                    positional[1]
                                    if len(positional) > 1
                                    else keyword_map.get(
                                        "default", _UNKNOWN
                                    )
                                ),
                            )
                    elif method == "setdefault":
                        record["opaque"] = True
                    elif method == "__setitem__":
                        key = (
                            positional[0]
                            if positional else keyword_map.get(
                                "key", _UNKNOWN
                            )
                        )
                        item = (
                            positional[1]
                            if len(positional) > 1 else keyword_map.get(
                                "value", _UNKNOWN
                            )
                        )
                        key_token = _subscript_key(
                            record,
                            node.args[0] if node.args else node,
                            key,
                        )
                        _heap_store(
                            record,
                            key_token,
                            _protocol_value(item),
                            strong=not (
                                environment.get(_POTENTIAL_KEY)
                                or environment.get(_WEAK_WRITES_KEY)
                            ),
                        )
                    elif method == "__delitem__":
                        key = (
                            positional[0]
                            if positional else keyword_map.get(
                                "key", _UNKNOWN
                            )
                        )
                        key_token = _subscript_key(
                            record,
                            node.args[0] if node.args else node,
                            key,
                        )
                        _heap_store(
                            record, key_token, _opaque_callable()
                        )
                    elif method == "__setattr__":
                        key = (
                            positional[0]
                            if positional else keyword_map.get(
                                "name", _UNKNOWN
                            )
                        )
                        item = (
                            positional[1]
                            if len(positional) > 1 else keyword_map.get(
                                "value", _UNKNOWN
                            )
                        )
                        _heap_store(
                            record,
                            (
                                ("attribute", key[1])
                                if key[0] == "string"
                                else _WILDCARD_ATTRIBUTE
                            ),
                            _protocol_value(item),
                        )
                    elif method == "__delattr__":
                        key = (
                            positional[0]
                            if positional else keyword_map.get(
                                "name", _UNKNOWN
                            )
                        )
                        _heap_store(
                            record,
                            (
                                ("attribute", key[1])
                                if key[0] == "string"
                                else _WILDCARD_ATTRIBUTE
                            ),
                            _opaque_callable(),
                        )
                    elif method == "insert":
                        if len(positional) >= 2:
                            record["opaque"] = True
                            _heap_store(
                                record,
                                ("index", positional[0][1])
                                if positional[0][0] == "integer"
                                else ("index", "unknown"),
                                _containerized(positional[1]),
                            )
                        else:
                            record["opaque"] = True
                    elif method == "clear":
                        for key in list(members):
                            _heap_store(record, key, _UNKNOWN)
                    elif method in {"pop", "remove", "discard"}:
                        if positional:
                            key = positional[0]
                            key_token = _subscript_key(record, node, key)
                            _heap_store(record, key_token, _UNKNOWN)
            if _is_unresolved(target) and _is_unresolved(value):
                for binding in all_values:
                    for record in _mutable_values(binding):
                        assert isinstance(record, dict)
                        record["opaque"] = True
            self._mark(node, environment)

    def _function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        environment: dict[str, object],
    ) -> None:
        for expression in (
            list(node.decorator_list)
            + list(node.args.defaults)
            + [value for value in node.args.kw_defaults if value is not None]
            + ([node.returns] if node.returns is not None else [])
        ):
            self._mark_expression(expression, environment)
        positional = list(node.args.posonlyargs) + list(node.args.args)
        default_bindings = {
            argument.arg: _static_value(default, self.by_node[default])
            for argument, default in zip(
                positional[-len(node.args.defaults):],
                node.args.defaults,
            )
        } if node.args.defaults else {}
        default_bindings.update({
            argument.arg: _static_value(default, self.by_node[default])
            for argument, default in zip(
                node.args.kwonlyargs, node.args.kw_defaults,
            )
            if default is not None
        })
        environment[node.name] = _symbol(f"local.{node.name}")
        child = dict(environment)
        owner = self._enclosing_scope(node)
        local_names = _scope_local_names(node) | _parameter_names(node.args)
        if owner is not None:
            for name, potential in self.scope_potentials.get(owner, {}).items():
                if name in local_names:
                    continue
                current = child.get(name, _UNKNOWN)
                child[name] = (
                    potential
                    if (
                        isinstance(potential, tuple)
                        and len(potential) == 2
                        and potential[0] == "symbol"
                        and str(potential[1]).startswith("local.")
                    )
                    else _merge_values([current, potential])
                )
        cursor: ast.AST | None = self.parent.get(node)
        nested = False
        while cursor is not None and not isinstance(cursor, ast.Module):
            if isinstance(
                cursor,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                nested = True
                break
            cursor = self.parent.get(cursor)
        if nested:
            for name, value in list(child.items()):
                if (
                    isinstance(value, tuple)
                    and len(value) == 2
                    and value[0] not in {"module", "symbol"}
                ):
                    child[name] = _merge_values([value, _UNKNOWN])
        for name in local_names:
            child[name] = _UNKNOWN
        for argument in (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        ):
            if argument.arg in self.mutable_names.get(node, set()):
                child[argument.arg] = _heap_value([
                    _allocate(
                        argument,
                        _annotation_container_kind(argument.annotation),
                        child,
                    )
                ])
        if (
            isinstance(owner, ast.ClassDef)
            and _CLASS_KEY in environment
            and positional
        ):
            child[positional[0].arg] = environment[_CLASS_KEY]
        for name, value in default_bindings.items():
            child[name] = _merge_values([value, _UNKNOWN])
        self._statements(node.body, child)

    def _statements(
        self,
        statements: list[ast.stmt],
        environment: dict[str, object],
    ) -> dict[str, object]:
        for statement in statements:
            self._mark(statement, environment)
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function(statement, environment)
            elif isinstance(statement, ast.ClassDef):
                for expression in list(statement.decorator_list) + list(statement.bases):
                    self._mark_expression(expression, environment)
                for keyword in statement.keywords:
                    self._mark_expression(keyword.value, environment)
                child = dict(environment)
                class_record = _allocate(statement, "class", environment)
                class_value = _heap_value([class_record])
                child[_CLASS_KEY] = class_value
                for name in _scope_local_names(statement):
                    child[name] = _UNKNOWN
                self._statements(statement.body, child)
                members = class_record["members"]
                assert isinstance(members, dict)
                for name in _scope_local_names(statement):
                    _heap_store(
                        class_record,
                        ("attribute", name),
                        child.get(name, _UNKNOWN),
                    )
                environment[statement.name] = class_value
            elif isinstance(statement, ast.Import):
                for alias in statement.names:
                    environment[alias.asname or alias.name.split(".")[0]] = _module(
                        alias.name
                    )
            elif isinstance(statement, ast.ImportFrom):
                if statement.module is None or any(
                    alias.name == "*" for alias in statement.names
                ):
                    special = {
                        key: environment[key]
                        for key in (
                            _HEAP_KEY, _ALLOCATIONS_KEY, _CLASS_KEY,
                        )
                        if key in environment
                    }
                    environment.clear()
                    environment.update(special)
                else:
                    for alias in statement.names:
                        environment[alias.asname or alias.name] = _symbol(
                            f"{statement.module}.{alias.name}"
                        )
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                value_node = statement.value
                if value_node is None:
                    value = _UNKNOWN
                else:
                    self._mark_expression(value_node, environment)
                    value = _static_value(value_node, self.by_node[value_node])
                targets = (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
                for target in targets:
                    self._bind(target, value, environment)
            elif isinstance(statement, ast.AugAssign):
                self._mark_expression(statement.value, environment)
                self._mark_expression(statement.target, environment)
                left = _static_value(statement.target, environment)
                right = _static_value(
                    statement.value, self.by_node[statement.value]
                )
                target_records = _heap_records(left)
                if isinstance(statement.op, ast.BitOr) and target_records:
                    source_records = _heap_records(right)
                    for record in target_records:
                        if not source_records:
                            record["opaque"] = True
                            continue
                        for source in source_records:
                            if record["kind"] == "dict":
                                _heap_update_mapping(
                                    record,
                                    source,
                                    strong=not (
                                        environment.get(_POTENTIAL_KEY)
                                        or environment.get(_WEAK_WRITES_KEY)
                                    ),
                                )
                            else:
                                record["opaque"] = True
                elif target_records:
                    for record in target_records:
                        record["opaque"] = True
                else:
                    containers = (
                        self._mutation_records(
                            statement.target.value, environment, "mutable",
                        )
                        if isinstance(
                            statement.target,
                            (ast.Attribute, ast.Subscript),
                        )
                        else []
                    )
                    if containers:
                        for record in containers:
                            record["opaque"] = True
                    elif isinstance(statement.target, ast.Name):
                        environment[statement.target.id] = _merge_values([
                            left, right, _UNKNOWN,
                        ])
            elif isinstance(statement, ast.Delete):
                for target in statement.targets:
                    for name in _target_names(target):
                        environment[name] = _UNKNOWN
                    self._mark_expression(target, environment)
                    if isinstance(target, ast.Subscript):
                        container = _static_value(
                            target.value, self.by_node[target.value]
                        )
                        key = _static_value(
                            target.slice, self.by_node[target.slice]
                        )
                        records = self._mutation_records(
                            target.value, environment, "mutable",
                        )
                        for record in records:
                            key_token = _subscript_key(
                                record, target.slice, key,
                            )
                            _heap_store(
                                record, key_token, _opaque_callable()
                            )
                    elif isinstance(target, ast.Attribute):
                        container = _static_value(
                            target.value, self.by_node[target.value]
                        )
                        records = self._mutation_records(
                            target.value, environment, "object",
                        )
                        for record in records:
                            _heap_store(
                                record,
                                ("attribute", target.attr),
                                _UNKNOWN,
                            )
            elif isinstance(statement, ast.Expr):
                self._mark_expression(statement.value, environment)
            elif isinstance(statement, (ast.Return, ast.Raise)):
                for value in (
                    [statement.value] if isinstance(statement, ast.Return)
                    and statement.value is not None
                    else [item for item in (statement.exc, statement.cause)
                          if item is not None]
                    if isinstance(statement, ast.Raise)
                    else []
                ):
                    self._mark_expression(value, environment)
            elif isinstance(statement, ast.Assert):
                self._mark_expression(statement.test, environment)
                if statement.msg is not None:
                    self._mark_expression(statement.msg, environment)
            elif isinstance(statement, ast.If):
                self._mark_expression(statement.test, environment)
                before = dict(environment)
                body_environment = dict(before)
                body_environment[_WEAK_WRITES_KEY] = True
                alternate_environment = dict(before)
                alternate_environment[_WEAK_WRITES_KEY] = True
                body = self._statements(statement.body, body_environment)
                alternate = self._statements(
                    statement.orelse, alternate_environment,
                )
                environment.clear()
                environment.update(_merge_environments([body, alternate]))
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                self._mark_expression(statement.iter, environment)
                before = dict(environment)
                body = dict(before)
                body[_WEAK_WRITES_KEY] = True
                self._bind(statement.target, _UNKNOWN, body)
                body = self._statements(statement.body, body)
                alternate_environment = dict(before)
                alternate_environment[_WEAK_WRITES_KEY] = True
                alternate = self._statements(
                    statement.orelse, alternate_environment,
                )
                environment.clear()
                environment.update(_merge_environments([before, body, alternate]))
            elif isinstance(statement, ast.While):
                self._mark_expression(statement.test, environment)
                before = dict(environment)
                body_environment = dict(before)
                body_environment[_WEAK_WRITES_KEY] = True
                alternate_environment = dict(before)
                alternate_environment[_WEAK_WRITES_KEY] = True
                body = self._statements(statement.body, body_environment)
                alternate = self._statements(
                    statement.orelse, alternate_environment,
                )
                environment.clear()
                environment.update(_merge_environments([before, body, alternate]))
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                child = dict(environment)
                for item in statement.items:
                    self._mark_expression(item.context_expr, child)
                    if item.optional_vars is not None:
                        self._bind(item.optional_vars, _UNKNOWN, child)
                environment.clear()
                environment.update(self._statements(statement.body, child))
            elif isinstance(statement, (ast.Try, ast.TryStar)):
                before = dict(environment)
                body_environment = dict(before)
                body_environment[_WEAK_WRITES_KEY] = True
                body = self._statements(statement.body, body_environment)
                successful = self._statements(statement.orelse, dict(body))
                paths = [successful]
                for handler in statement.handlers:
                    handler_environment = dict(before)
                    handler_environment[_WEAK_WRITES_KEY] = True
                    if handler.type is not None:
                        self._mark_expression(handler.type, handler_environment)
                    if handler.name:
                        handler_environment[handler.name] = _UNKNOWN
                    paths.append(
                        self._statements(handler.body, handler_environment)
                    )
                merged = _merge_environments(paths + [before])
                environment.clear()
                environment.update(
                    self._statements(statement.finalbody, merged)
                )
            elif isinstance(statement, ast.Match):
                self._mark_expression(statement.subject, environment)
                before = dict(environment)
                paths = [before]
                for case in statement.cases:
                    case_environment = dict(before)
                    case_environment[_WEAK_WRITES_KEY] = True
                    for name in _target_names(case.pattern):
                        case_environment[name] = _UNKNOWN
                    self._mark_expression(case.pattern, case_environment)
                    if case.guard is not None:
                        self._mark_expression(case.guard, case_environment)
                    paths.append(
                        self._statements(case.body, case_environment)
                    )
                environment.clear()
                environment.update(_merge_environments(paths))
            elif isinstance(statement, (ast.Global, ast.Nonlocal)):
                for name in statement.names:
                    environment[name] = _merge_values([
                        environment.get(name, _UNKNOWN),
                        self.volatile_values.get(name, _UNKNOWN),
                        _UNKNOWN,
                    ])
            elif isinstance(statement, (ast.Pass, ast.Break, ast.Continue)):
                continue
            else:
                for child in ast.iter_child_nodes(statement):
                    if isinstance(child, ast.expr):
                        self._mark_expression(child, environment)
        return environment


def _capability_assignment(node: ast.AST) -> bool:
    names = _assignment_targets(node)
    if names == ["REQUIRED_PYTHON_APIS"]:
        return any(
            isinstance(item, ast.Constant) and item.value == "fcntl.flock"
            for item in ast.walk(node)
        )
    if names == ["CAPABILITY_PROBE_SOURCE"]:
        return any(
            isinstance(item, ast.Constant)
            and isinstance(item.value, str)
            and 'hasattr(fcntl, "flock")' in item.value
            for item in ast.walk(node)
        )
    return False


def _allowed_python_nodes(
    relative_path: str,
    tree: ast.Module,
    records: list[dict[str, object]],
) -> tuple[set[ast.AST], set[ast.Call]]:
    scopes = _qualified_scopes(tree)
    allowed_scope_nodes: set[ast.AST] = set()
    allowed_governed: set[ast.Call] = set()
    for record in records:
        for selector in record["python_scopes"]:
            if selector["path"] != relative_path:
                continue
            scope = scopes[selector["qualname"]]
            allowed_scope_nodes.update(ast.walk(scope))
        for selector in record["governed_nodes"]:
            if selector["path"] != relative_path:
                continue
            scope = scopes[selector["qualname"]]
            node = list(_preorder(scope))[selector["preorder"]]
            if not isinstance(node, ast.Call):
                raise AssertionError(f"accepted governed selector is not Call: {selector}")
            allowed_governed.add(node)
    return allowed_scope_nodes, allowed_governed


def _scan_python(
    relative_path: str,
    source: str,
    records: list[dict[str, object]],
) -> _ScanResult:
    result = _ScanResult()
    try:
        tree = ast.parse(
            source,
            filename=relative_path,
            mode="exec",
            type_comments=False,
            feature_version=(3, 14),
            optimize=-1,
        )
    except (SyntaxError, ValueError) as exc:
        result.findings.append(f"{relative_path}: parse:{type(exc).__name__}")
        return result
    allowed_scopes, allowed_governed = _allowed_python_nodes(
        relative_path, tree, records
    )
    retained_generated = _retained_importer_generated_nodes(
        relative_path, source, tree
    )
    parent = {
        child: node
        for node in ast.walk(tree)
        for child in ast.iter_child_nodes(node)
    }
    allowed_vinfo: set[ast.AST] = set()
    if relative_path == "kernel/bin/awa-registration-bootstrap.py":
        try:
            _, allowed_vinfo = _exact_vinfo_declaration(tree)
        except AssertionError:
            pass
        else:
            result.vinfo_declarations = 1

    environments = _EnvironmentBuilder(
        tree, {}, source_id=relative_path,
    ).build()

    def environment(node: ast.AST) -> dict[str, object]:
        return environments.get(node, {})

    function_definitions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    class_names: set[str] = set()
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_definitions.setdefault(candidate.name, []).append(candidate)
        elif isinstance(candidate, ast.ClassDef):
            class_names.add(candidate.name)

    def closed_local_constructor(call_node: ast.Call) -> bool:
        return (
            isinstance(call_node.func, ast.Name)
            and call_node.func.id in class_names
        )

    def closed_parameter_call(call_node: ast.Call) -> bool:
        if not isinstance(call_node.func, ast.Name):
            return False
        scope: ast.AST | None = parent.get(call_node)
        while scope is not None and not isinstance(
            scope, (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            scope = parent.get(scope)
        if scope is None or call_node.func.id not in _parameter_names(scope.args):
            return False
        uses = [
            candidate
            for candidate in ast.walk(tree)
            if isinstance(candidate, ast.Call)
            and isinstance(candidate.func, ast.Name)
            and candidate.func.id == scope.name
        ]
        references = [
            candidate
            for candidate in ast.walk(tree)
            if isinstance(candidate, ast.Name)
            and isinstance(candidate.ctx, ast.Load)
            and candidate.id == scope.name
        ]
        return bool(uses) and len(uses) == len(references) and all(
            candidate in allowed_scopes for candidate in uses
        )

    def parameter_is_data_only(
        definition: ast.FunctionDef | ast.AsyncFunctionDef,
        name: str,
        visiting: set[tuple[ast.AST, str]],
    ) -> bool:
        key = (definition, name)
        if key in visiting:
            return True
        next_visiting = visiting | {key}
        for reference in ast.walk(definition):
            if not (
                isinstance(reference, ast.Name)
                and isinstance(reference.ctx, ast.Load)
                and reference.id == name
            ):
                continue
            cursor: ast.AST = reference
            while parent.get(cursor) is not definition:
                owner = parent.get(cursor)
                if owner is None:
                    return False
                if isinstance(owner, ast.Call):
                    if (
                        isinstance(owner.func, ast.Attribute)
                        and owner.func.value is reference
                        and owner.func.attr in {
                            "get", "items", "keys", "values", "copy",
                        }
                    ):
                        break
                    expansion = (
                        isinstance(cursor, ast.Starred)
                        or isinstance(cursor, ast.keyword)
                        and cursor.arg is None
                    )
                    if not expansion:
                        return False
                    called_name = (
                        owner.func.id
                        if isinstance(owner.func, ast.Name)
                        else owner.func.attr
                        if isinstance(owner.func, ast.Attribute)
                        else None
                    )
                    candidates = function_definitions.get(called_name or "", [])
                    if not candidates:
                        return False
                    for candidate in candidates:
                        parameter = (
                            candidate.args.vararg
                            if isinstance(cursor, ast.Starred)
                            else candidate.args.kwarg
                        )
                        if parameter is None or not parameter_is_data_only(
                            candidate, parameter.arg, next_visiting,
                        ):
                            return False
                    break
                cursor = owner
        return True

    def closed_local_method_expansion(call_node: ast.Call) -> bool:
        if not isinstance(call_node.func, ast.Attribute):
            return False
        definitions = function_definitions.get(call_node.func.attr, [])
        if not definitions:
            return False
        has_star = any(isinstance(argument, ast.Starred) for argument in call_node.args)
        has_starstar = any(keyword.arg is None for keyword in call_node.keywords)
        if not (has_star or has_starstar):
            return False
        for definition in definitions:
            parameters = []
            if has_star:
                parameters.append(definition.args.vararg)
            if has_starstar:
                parameters.append(definition.args.kwarg)
            if any(parameter is None for parameter in parameters):
                return False
            if any(
                not parameter_is_data_only(definition, parameter.arg, set())
                for parameter in parameters
                if parameter is not None
            ):
                return False
        return True

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                target = _symbol(f"{node.module}.{alias.name}")
                if (
                    _value_contains_governed(target)
                    and node not in allowed_scopes
                ):
                    result.findings.append(
                        f"{relative_path}: governed import {node.module}.{alias.name}"
                    )

    all_assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and getattr(node, "value", None) is not None
    ]
    for node in all_assignments:
        value = _static_value(node.value, environment(node.value))
        if (
            _value_is_governed_reference(value)
            and node not in allowed_scopes
            and not _capability_assignment(node)
        ):
            result.findings.append(
                f"{relative_path}: governed assignment {','.join(_assignment_targets(node))}"
            )

    for node in ast.walk(tree):
        if node in allowed_vinfo or _is_docstring(node, parent):
            continue
        immutable_name = (
            node.id if isinstance(node, ast.Name)
            else node.attr if isinstance(node, ast.Attribute)
            else node.value if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            else None
        )
        if immutable_name in _IMMUTABLE_SYMBOLS:
            result.findings.append(
                f"{relative_path}: immutable reference {immutable_name}"
            )
            continue
        governed_name = (
            node.id if isinstance(node, ast.Name)
            else node.attr if isinstance(node, ast.Attribute)
            else None
        )
        if (
            governed_name in (_LOCK_SYMBOLS | _DESCRIPTOR_COMMAND_NAMES)
            and node not in allowed_scopes
        ):
            result.findings.append(
                f"{relative_path}: governed lexical reference {governed_name}"
            )
            continue
        if isinstance(node, (ast.Name, ast.Attribute)):
            value = _static_value(node, environment(node))
            if _value_is_governed_reference(value) and node not in allowed_scopes:
                result.findings.append(
                    f"{relative_path}: governed reference {ast.dump(node, include_attributes=False)}"
                )
        if not isinstance(node, ast.Call):
            continue
        node_environment = environment(node)
        target = _static_value(node.func, node_environment)
        positional_values, keyword_values, argument_values = _all_call_values(
            node, node_environment
        )
        keyword_map = {
            key[1]: value
            for key, value in keyword_values
            if (
                isinstance(key, tuple)
                and len(key) == 2
                and key[0] == "string"
            )
        }
        tainted_callable = (
            (
                isinstance(target, tuple)
                and len(target) == 2
                and target[0] in {"heapref", "heaprefs"}
                and _value_has_callable_authority(target)
                and any(
                    record["kind"] != "class"
                    for record in _heap_records(target)
                )
            )
            or (
                isinstance(target, tuple)
                and len(target) == 2
                and (
                    target[0] in {"opaque_member", "opaque_callable"}
                    or (
                        target[0] == "tainted"
                        and _value_has_callable_authority(target)
                    )
                )
            )
        )
        if tainted_callable:
            result.findings.append(
                f"{relative_path}:{node.lineno}: tainted callable authority"
            )
        lock_targets = (
            _symbol("fcntl.flock"), _symbol("fcntl.lockf"),
        )
        is_lock = any(target == item for item in lock_targets) or any(
            any(value == item for item in lock_targets)
            for value in argument_values
        )
        is_descriptor = target == _symbol("fcntl.fcntl") or any(
            value == _symbol("fcntl.fcntl") for value in argument_values
        )
        immutable = (
            target[0] == "symbol"
            and str(target[1]).rpartition(".")[2] in _IMMUTABLE_SYMBOLS
        )
        dynamic_governed = (
            any(target == item for item in (
                _symbol("builtins.getattr"), _symbol("builtins.setattr"),
                _symbol("builtins.delattr"),
            ))
            and (
                any(_value_contains_governed(value) for value in argument_values)
                or (
                    positional_values
                    and any(
                        positional_values[0] == item
                        for item in (
                            _module("fcntl"), _module("os"), _module("stat"),
                        )
                    )
                    and (
                        len(positional_values) < 2
                        or _is_unresolved(positional_values[1])
                    )
                )
            )
        )
        dynamic_import = any(target == item for item in (
            _symbol("builtins.__import__"), _symbol("importlib.import_module"),
        ))
        imported = (
            _static_value(node, node_environment)
            if dynamic_import else _UNKNOWN
        )
        if dynamic_import and (
            imported == _module("fcntl") or _is_unresolved(imported)
        ):
            result.findings.append(f"{relative_path}: governed dynamic import")
        if target[0] == "symbol" and target[1] in _COMMAND_SINKS:
            command = (
                positional_values[0]
                if positional_values else keyword_map.get(
                    "args", keyword_map.get("command", _UNKNOWN)
                )
            )
            if _value_contains_governed(command):
                result.findings.append(f"{relative_path}: governed command")
            elif (
                _is_unresolved(command)
                and node not in allowed_scopes
            ):
                result.findings.append(f"{relative_path}: unresolved governed command")
        if target[0] == "symbol" and target[1] in _DYNAMIC_SOURCE_SINKS:
            if (
                node not in retained_generated
                and not _is_exact_capability_probe_call(
                    relative_path, source, node, environments
                )
            ):
                result.findings.append(f"{relative_path}: unresolved generated source")
        if is_lock:
            if node in allowed_governed:
                result.accepted_lock_nodes.append(relative_path)
            else:
                result.findings.append(f"{relative_path}: unlisted advisory lock")
        elif is_descriptor:
            command = (
                positional_values[1]
                if len(positional_values) > 1
                else keyword_map.get("cmd", _UNKNOWN)
            )
            if node in allowed_governed:
                result.accepted_descriptor_nodes.append(relative_path)
            elif (
                command == _UNKNOWN
                or _value_contains_governed(command)
                or command[0] in {"integer", "symbol"}
            ):
                result.findings.append(f"{relative_path}: unlisted descriptor command")
        elif immutable or dynamic_governed:
            static_descriptor_lookup = (
                node in allowed_scopes
                and _static_value(node, node_environment)
                == _symbol("fcntl.F_FULLFSYNC")
            )
            if not static_descriptor_lookup:
                result.findings.append(f"{relative_path}: immutable/dynamic operation")
        elif any(
            _callback_argument_refuses(value, target)
            or (
                _value_contains_governed(value)
                and _is_unresolved(target)
            )
            or (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] == "opaque_member"
                and _is_unresolved(target)
            )
            for value in argument_values
        ):
            exact_reporting = (
                target == _symbol("builtins.list")
                and len(positional_values) == 1
                and positional_values[0]
                == node_environment.get("REQUIRED_PYTHON_APIS")
            )
            exact_probe_flow = (
                target == _symbol("builtins.compile")
                and positional_values
                and _is_exact_capability_probe(positional_values[0])
            )
            if (
                node not in allowed_scopes
                and not exact_reporting
                and not exact_probe_flow
                and not closed_parameter_call(node)
                and not closed_local_method_expansion(node)
                and not closed_local_constructor(node)
            ):
                result.findings.append(
                    f"{relative_path}:{node.lineno}: governed callback/wrapper"
                )
    return result


def _scan_shell(
    relative_path: str,
    source: str,
    exact_record_authorized: bool,
) -> _ScanResult:
    result = _ScanResult()
    governed = _LOCK_SYMBOLS | _IMMUTABLE_SYMBOLS | _DESCRIPTOR_COMMAND_NAMES
    has_governed_text = any(token in source for token in governed)
    try:
        lexer = shlex.shlex(source, posix=True, punctuation_chars=";&|<>()\n")
        lexer.whitespace = " \t"
        lexer.commenters = "#"
        tokens = list(lexer)
    except ValueError as exc:
        if has_governed_text:
            result.findings.append(f"{relative_path}: shell parse:{exc}")
        return result
    assignment_values: dict[str, list[str]] = {}
    for token in tokens:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            name, value = token.split("=", 1)
            assignment_values.setdefault(name, []).append(value)
    raw_assignment_values: dict[str, list[str]] = {}
    for match in re.finditer(
        r"(?:^|[;\n])[\t ]*([A-Za-z_][A-Za-z0-9_]*)=([^;\n]*)",
        source,
    ):
        name, value = match.group(1), match.group(2).strip()
        raw_assignment_values.setdefault(name, []).append(value)
    assignment_values.update(raw_assignment_values)
    assignments = {
        name: values[0]
        for name, values in assignment_values.items()
        if len(values) == 1
    }
    variable = re.compile(
        r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))"
    )
    resolved: dict[str, str] = {}

    def resolve_name(name: str, active: frozenset[str]) -> str:
        if name in resolved:
            return resolved[name]
        if name not in assignments or name in active:
            return f"${{{name}}}"
        value = variable.sub(
            lambda match: resolve_name(
                match.group(1) or match.group(2),
                active | {name},
            ),
            assignments[name],
        )
        resolved[name] = value
        return value

    for name in assignments:
        resolve_name(name, frozenset())

    def expand(token: str) -> str:
        return variable.sub(
            lambda match: resolved.get(
                match.group(1) or match.group(2),
                match.group(0),
            ),
            token,
        )

    expanded = [expand(token) for token in tokens]
    joined = " ".join(expanded) + "\n" + expand(source)
    if any(token in joined for token in governed):
        result.findings.append(f"{relative_path}: governed shell command")
    if (has_governed_text or any(token in joined for token in governed)) and any(
        token in source for token in ("${!", "eval ", "source $", "$(")
    ):
        result.findings.append(f"{relative_path}: unresolved shell indirection")
    if exact_record_authorized:
        result.findings.clear()
    return result


def _scan_unit(
    relative_path: str,
    source: str,
    records: list[dict[str, object]],
) -> _ScanResult:
    suffix = Path(relative_path).suffix
    if suffix == ".py":
        return _scan_python(relative_path, source, records)
    if suffix == ".sh":
        exact_record_authorized = any(
            unit["path"] == relative_path
            and unit["encoding"] == "EXACT_UTF8_LF_FILE"
            and unit["sha256"] == _sha256(source.encode("utf-8"))
            for record in records
            for unit in record["shell_units"]
        )
        return _scan_shell(relative_path, source, exact_record_authorized)
    result = _ScanResult()
    if suffix in {".yml", ".yaml"}:
        governed = _LOCK_SYMBOLS | _IMMUTABLE_SYMBOLS | _DESCRIPTOR_COMMAND_NAMES
        if any(token in source for token in governed):
            result.findings.append(f"{relative_path}: governed YAML primitive")
        return result
    result.findings.append(f"{relative_path}: unsupported source kind")
    return result


def _scan_path(
    path: Path,
    root: Path,
    records: list[dict[str, object]],
) -> _ScanResult:
    relative = path.relative_to(root).as_posix()
    result = _ScanResult()
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        result.findings.append(f"{relative}: symlink")
        return result
    if not stat.S_ISREG(metadata.st_mode):
        result.findings.append(f"{relative}: nonregular")
        return result
    raw = path.read_bytes()
    try:
        source = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        result.findings.append(f"{relative}: invalid UTF-8")
        return result
    if "\x00" in source or (path.suffix == ".sh" and "\r" in source):
        result.findings.append(f"{relative}: forbidden byte")
        return result
    return _scan_unit(relative, source, records)


def _scan_kernel(records: list[dict[str, object]]) -> _ScanResult:
    result = _ScanResult()
    for path in sorted(_KERNEL.rglob("*"), key=lambda value: os.fsencode(value)):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if stat.S_ISDIR(path.lstat().st_mode):
            continue
        result.merge(
            _scan_path(path, _REPO_ROOT, records)
        )
    return result


_NEGATIVE_FAMILIES = (
    "PY_FLOCK", "PY_LOCKF", "PY_FCNTL_F_GETLK", "PY_FCNTL_F_SETLK",
    "PY_FCNTL_F_SETLKW", "PY_FCNTL_F_OFD_GETLK", "PY_FCNTL_F_OFD_SETLK",
    "PY_FCNTL_F_OFD_SETLKW", "PY_FCNTL_NUMERIC_OR_UNKNOWN_COMMAND",
    "PY_CTYPES_OR_SYSCALL_FCNTL_OR_FLOCK", "PY_EXTRA_APPROVED_FILE_CALL",
    "PY_MOVED_APPROVED_CALL", "PY_CHANGED_DESCRIPTOR_ORIGIN",
    "PY_CHANGED_PATH_PROVENANCE", "PY_CHANGED_XDG_ENVIRONMENT_KEY",
    "PY_CHANGED_XDG_EMPTY_OR_STRIP_SEMANTICS", "PY_CHANGED_HOME_FALLBACK",
    "PY_CHANGED_PASSWD_TILDE_FALLBACK", "PY_CHANGED_PATH_SUFFIX",
    "PY_EXTRA_PATH_BRANCH_OR_TARGET", "PY_CHANGED_ASSIGNMENT_CHAIN",
    "PY_CHANGED_OPEN_FLAGS", "PY_CHANGED_OPEN_MODE", "PY_CHANGED_METADATA_CHECK",
    "PY_CHANGED_LOCK_FLAGS", "PY_CHANGED_RELEASE", "PY_F_DUPFD_WITHOUT_CLOEXEC",
    "PY_F_DUPFD_CLOEXEC_USED_AS_LOCK_OR_UNKNOWN", "PY_VST_FLAGS_ATTRIBUTE_LOAD",
    "PY_VST_FLAGS_ATTRIBUTE_STORE", "PY_VST_FLAGS_ATTRIBUTE_DELETE",
    "PY_VST_FLAGS_GETATTR", "PY_VST_FLAGS_SETATTR", "PY_VST_FLAGS_DELATTR",
    "PY_VST_FLAGS_SUBSCRIPT", "PY_VST_FLAGS_MAPPING", "PY_VST_FLAGS_REFLECTION",
    "PY_DUPLICATE_VST_FLAGS_DECLARATION", "PY_CHANGED_VST_FLAGS_TYPE",
    "PY_CHANGED_VST_FLAGS_INDEX", "PY_CHFLAGS", "PY_LCHFLAGS", "PY_FCHFLAGS",
    "PY_UCHG", "PY_SCHG", "PY_UAPPND", "PY_SAPPND", "PY_UF_IMMUTABLE",
    "PY_SF_IMMUTABLE", "PY_UF_APPEND", "PY_SF_APPEND",
    "PY_IMMUTABLE_NUMERIC_OR_UNKNOWN", "SHELL_FLOCK", "SHELL_LOCKF",
    "SHELL_FCNTL_SETLK_FAMILY", "SHELL_CHFLAGS", "SHELL_UCHG", "SHELL_SCHG",
    "SHELL_UAPPND", "SHELL_SAPPND", "SHELL_IMMUTABLE_CONSTANT",
    "SHELL_FUNCTION_WRAPPER", "SHELL_VARIABLE_ALIAS", "SHELL_COMMAND_SUBSTITUTION",
    "SHELL_CHANGED_BRIDGE_BYTES", "SHELL_EVAL", "SHELL_DYNAMIC_SOURCE",
    "SHELL_UNRESOLVED_INDIRECTION", "SUBPROCESS_LOCK_LIST",
    "SUBPROCESS_LOCK_STRING", "SUBPROCESS_IMMUTABLE_LIST",
    "SUBPROCESS_IMMUTABLE_STRING", "YAML_LOCK_PRIMITIVE",
    "YAML_IMMUTABLE_PRIMITIVE", "UNKNOWN_SUFFIX", "SYMLINK_OR_NONREGULAR",
)


def _negative_fixture(family: str) -> tuple[str, str]:
    if family == "UNKNOWN_SUFFIX":
        return "UNKNOWN", "governed.data"
    if family == "SYMLINK_OR_NONREGULAR":
        return "SYMLINK", "link"
    if family.startswith("SHELL_"):
        token = {
            "SHELL_FLOCK": "flock",
            "SHELL_LOCKF": "lockf",
            "SHELL_CHFLAGS": "chflags",
            "SHELL_UCHG": "uchg",
            "SHELL_SCHG": "schg",
            "SHELL_UAPPND": "uappnd",
            "SHELL_SAPPND": "sappnd",
        }.get(family, "F_SETLK")
        return "SHELL", f'f() {{ {token} \"$1\"; }}; cmd={token}; $cmd target'
    if family.startswith("YAML_"):
        return "YAML", "operation: flock" if "LOCK" in family else "flag: UF_IMMUTABLE"
    if family.startswith("SUBPROCESS_"):
        token = "flock" if "LOCK" in family else "chflags"
        return "PYTHON", f"import subprocess\nsubprocess.run([{token!r}, 'target'])"
    immutable = {
        "PY_CHFLAGS": "chflags", "PY_LCHFLAGS": "lchflags",
        "PY_FCHFLAGS": "fchflags", "PY_UCHG": "uchg", "PY_SCHG": "schg",
        "PY_UAPPND": "uappnd", "PY_SAPPND": "sappnd",
        "PY_UF_IMMUTABLE": "UF_IMMUTABLE", "PY_SF_IMMUTABLE": "SF_IMMUTABLE",
        "PY_UF_APPEND": "UF_APPEND", "PY_SF_APPEND": "SF_APPEND",
    }
    if family in immutable:
        return "PYTHON", f"x = {immutable[family]!r}\ngetattr(os, x)"
    if family.startswith("PY_VST_FLAGS") or family.startswith("PY_CHANGED_VST") \
            or family == "PY_DUPLICATE_VST_FLAGS_DECLARATION":
        return "PYTHON", "value = object.vst_flags"
    if family in {"PY_FLOCK", "PY_LOCKF"}:
        api = family.removeprefix("PY_").lower()
        return "PYTHON", f"import fcntl\nfcntl.{api}(fd, 1)"
    command = next(
        (name for name in _LOCK_SYMBOLS if name in family),
        "F_SETLK",
    )
    return "PYTHON", (
        "import fcntl\n"
        f"alias = getattr(fcntl, {command!r})\n"
        "alias(fd, 1)\n"
    )


def _negative_variants(family: str) -> list[tuple[str, str, str]]:
    kind, source = _negative_fixture(family)
    variants = [("declared", kind, source)]
    if family.startswith("PY_") and not family.startswith("PY_VST_FLAGS"):
        variants.extend([
            ("module_alias", "PYTHON",
             "import fcntl as f\nf.flock(fd, f.LOCK_EX)\n"),
            ("imported_alias", "PYTHON",
             "from fcntl import flock as acquire\nacquire(fd, 1)\n"),
            ("assignment_alias", "PYTHON",
             "import fcntl\nacquire = fcntl.flock\nacquire(fd, 1)\n"),
            ("callback_wrapper", "PYTHON",
             "import fcntl\nregister(fcntl.flock, fd, 1)\n"),
            ("dynamic_getattr_import", "PYTHON",
             "acquire = getattr(__import__('fcntl'), 'flock')\nacquire(fd, 1)\n"),
            ("subprocess_list", "PYTHON",
             "import subprocess\nsubprocess.run(['flock', 'target'])\n"),
            ("subprocess_string", "PYTHON",
             "import subprocess\nsubprocess.run('flock target', shell=True)\n"),
        ])
    if family.startswith("SHELL_"):
        variants.extend([
            ("function_wrapper", "SHELL", "f() { flock \"$1\"; }; f target"),
            ("variable_alias", "SHELL", "cmd=flock; \"$cmd\" target"),
            ("command_substitution", "SHELL", "cmd=$(printf flock); \"$cmd\" target"),
            ("eval", "SHELL", "cmd='flock target'; eval \"$cmd\""),
            ("dynamic_source", "SHELL", "source \"$dynamic\"; flock target"),
            ("unresolved_indirection", "SHELL", "${!name} target # flock"),
        ])
    return variants


class KernelOffMatrixTest(EngineTestCase):
    # ---- stdlib-only: no engine / third-party imports in the kernel libs ----
    def test_kernel_libs_are_stdlib_only(self) -> None:
        stdlib = _KNOWN_STDLIB | set(getattr(sys, "stdlib_module_names", set()))
        for py in sorted(_KERNEL.rglob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        roots.add(node.module.split(".")[0])
            offenders = {r for r in roots if r != "__future__" and r not in stdlib}
            self.assertEqual(offenders, set(),
                             f"{py.relative_to(_REPO_ROOT)} imports non-stdlib: {offenders} "
                             "(kernel must run engine-OFF, stdlib-only)")
            self.assertNotIn("engine", roots, f"{py.name} must not import the engine package")

    # ---- router-off: the kernel imports/reads no router artifact ------------
    def test_kernel_has_no_router_import_or_read(self) -> None:
        """SHOULD-FIX 7 — delegate to the ONE comprehensive kernel rglob scan
        (consumer_test_support.scan_tree_for_router_usage) instead of a narrow hardcoded 3-file list,
        so the WHOLE kernel surface (every kernel/*.py and *.sh) is covered — not just three files."""
        offenders = scan_tree_for_router_usage(_KERNEL)
        self.assertEqual(offenders, [],
                         "the kernel must import/read ZERO router artifacts (KI2):\n"
                         + "\n".join(offenders))

    # ---- behavioral: engine unimportable, kernel still blocks an active root -
    def _engine_off_env(self) -> dict[str, str]:
        env = {}
        for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"):
            if k in os.environ:
                env[k] = os.environ[k]
        env["AWA_HOME"] = str(_REPO_ROOT)
        env["XDG_STATE_HOME"] = str(self.state_home)
        # deliberately point PYTHONPATH at an EMPTY dir so the engine package is NOT importable
        empty = self.data_home / "empty-pp"
        empty.mkdir(parents=True, exist_ok=True)
        env["PYTHONPATH"] = str(empty)
        return env

    def test_engine_is_actually_off_under_matrix_env(self) -> None:
        env = self._engine_off_env()
        r = subprocess.run(["python3", "-c", "import engine"], env=env,
                           capture_output=True, text=True, cwd=str(self.data_home))
        self.assertNotEqual(r.returncode, 0,
                            "matrix env must make the engine package UNIMPORTABLE (engine-off)")

    def test_maintenance_context_stays_live_with_engine_off(self) -> None:
        repo = self.make_repo("engoff-maintenance")
        remote = self.add_bare_remote(repo, "engoff-maintenance-origin.git")
        git(repo, "push", "-q", "-u", "origin", "main")
        policy = self.data_home / "engoff-maintenance-policy.yml"
        policy.write_text(
            "version: 1\n"
            "governed_roots:\n"
            "  - {0}\n"
            "default: include\n"
            "include:\n"
            "  - '*'\n"
            "exclude:\n"
            "  - .\n"
            "detectors:\n"
            "  governed_markers:\n"
            "    - _ops/POLICY.md\n"
            "  foreign_hook_frameworks:\n"
            "    - husky\n".format(self.data_home),
            encoding="utf-8",
        )
        env = self._engine_off_env()
        env.update(
            {
                "AWA_GOVERNED_ROOT": str(self.data_home),
                "AWA_POLICY": str(policy),
            }
        )

        def guard(command: str) -> dict:
            result = subprocess.run(
                ["bash", str(_GUARD)],
                input=json.dumps({"cwd": repo, "command": command}),
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)

        self.assertEqual(guard("git fetch"), {"permission": "allow"})
        Path(repo, "dirty").write_text("dirty\n", encoding="utf-8")
        denied = guard("git fetch")
        self.assertEqual(denied.get("permission"), "deny", denied)

    def test_maintenance_context_has_no_persistent_cache_surface(self) -> None:
        source = _GUARD.read_text(encoding="utf-8")
        for forbidden in (
            "functools.lru_cache",
            "functools.cache",
            "PRIMARY_MAINTENANCE_CONTEXT=",
            "AWA_PRIMARY_MAINTENANCE_CONTEXT",
        ):
            self.assertNotIn(forbidden, source)

    def test_active_root_blocks_with_engine_off(self) -> None:
        repo = self.make_repo("engoff")
        wt = self.add_worktree(repo, "feat/off")
        Path(wt, "feature.txt").write_text("f\n", encoding="utf-8")
        commit_all(wt, "feature")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", "feat/off")
        commit_all(repo, "squash")
        env = self._engine_off_env()
        # mark ACTIVE via the kernel lib subprocess (also engine-off)
        subprocess.run(["python3", str(_ROOTS_PY), "heartbeat", "--root", wt],
                       env=env, capture_output=True, text=True, check=True)
        r = subprocess.run(["bash", str(_DEV_WORKTREE), "clean", "--path", wt],
                           env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "an active root must block even engine-off")
        self.assertTrue(Path(wt).exists())
        # a receipt was still written (engine-off)
        disp = subprocess.run(["python3", str(_ROOTS_PY), "list-receipts", "--limit", "1"],
                              env=env, capture_output=True, text=True)
        self.assertIn("active_root", disp.stdout)

    def test_refusal_writes_receipt_with_engine_off(self) -> None:
        env = self._engine_off_env()
        subprocess.run(["bash", str(_DEV_WORKTREE), "clean",
                        "--path", str(self.data_home / "nope")],
                       env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True)
        r = subprocess.run(["python3", str(_ROOTS_PY), "list-receipts", "--limit", "1"],
                           env=env, capture_output=True, text=True)
        self.assertIn("not_a_directory", r.stdout)
        self.assertIn("clean_receipt/v1", r.stdout)

    def test_semantic_lock_and_descriptor_inventory_is_exact(self) -> None:
        records, branch_digests = _semantic_records()
        self.assertEqual(branch_digests, _EXPECTED_BRANCH_DIGESTS)
        observed = {record["id"]: _record_digest(record) for record in records}
        self.assertEqual(observed, _EXPECTED_RECORD_DIGESTS)
        self.assertEqual(_semantic_inventory_digest(records), _EXPECTED_INVENTORY_DIGEST)
        self.assertEqual(_sha256(_DEV_WORKTREE.read_bytes()), _SHELL_BRIDGE_SHA256)
        scan = _scan_kernel(records)
        self.assertEqual(
            (len(scan.accepted_lock_nodes), len(scan.accepted_descriptor_nodes)),
            (17, 3),
            "exactly 17 flock/callback nodes and three descriptor-control nodes are authorized",
        )
        self.assertEqual(scan.vinfo_declarations, 1)
        self.assertEqual(scan.findings, [], "\n".join(scan.findings))
        self.assertEqual(
            sum(record["kind"] in {"LOCK", "LOCK_BRIDGE"} for record in records),
            10,
        )
        self.assertEqual(
            sum(record["kind"] == "DESCRIPTOR_CONTROL" for record in records),
            3,
        )

    def test_semantic_record_and_branch_field_mutations_bite(self) -> None:
        records, _ = _semantic_records()

        def assert_every_field_bites(
            record: dict[str, object], domain: bytes, expected: str
        ) -> None:
            for key in record:
                with self.subTest(identifier=record["id"], field=key):
                    changed = copy.deepcopy(record)
                    changed[key] = "__DRIFT__" if changed[key] is not None else {}
                    digest = _sha256(domain + _jcs(changed) + b"\n")
                    self.assertNotEqual(digest, expected)
                    removed = copy.deepcopy(record)
                    removed.pop(key)
                    self.assertNotEqual(
                        _sha256(domain + _jcs(removed) + b"\n"),
                        expected,
                    )

        for record in records:
            assert_every_field_bites(
                record,
                b"awa-kernel-semantic-record/v2\0",
                _EXPECTED_RECORD_DIGESTS[record["id"]],
            )
        trees: dict[str, ast.Module] = {}

        def scopes(path: str, names: list[str]):
            return [_scope_selector(path, name, trees) for name in names]

        for record in _branch_records(scopes):
            assert_every_field_bites(
                record,
                b"awa-kernel-branch-authority/v2\0",
                _EXPECTED_BRANCH_DIGESTS[record["id"]],
            )

    def test_closed_kernel_source_universe_and_immutable_declaration(self) -> None:
        scan = _scan_kernel(_semantic_records()[0])
        self.assertEqual(scan.vinfo_declarations, 1)
        self.assertEqual(scan.findings, [], "\n".join(scan.findings))

    def test_positive_capability_references_are_exact(self) -> None:
        source = (
            _KERNEL / "bin" / "awa-registration-bootstrap.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(source.count('"fcntl.flock"'), 1)
        self.assertEqual(source.count('hasattr(fcntl, "flock")'), 1)
        self.assertNotIn("getattr(fcntl, \"flock\")", source)

    def test_no_unlisted_governed_python_reference(self) -> None:
        scan = _scan_kernel(_semantic_records()[0])
        self.assertEqual(scan.findings, [], "\n".join(scan.findings))

    def test_complete_negative_family_matrix_bites(self) -> None:
        self.assertEqual(len(_NEGATIVE_FAMILIES), len(set(_NEGATIVE_FAMILIES)))
        executed: set[str] = set()
        for family in _NEGATIVE_FAMILIES:
            for variant, kind, source in _negative_variants(family):
                with self.subTest(family=family, variant=variant):
                    if kind == "SYMLINK":
                        target = self.data_home / "scanner-target.py"
                        link = self.data_home / "scanner-link.py"
                        target.write_text("pass\n", encoding="utf-8")
                        link.symlink_to(target)
                        scan = _scan_path(
                            link,
                            self.data_home,
                            [],
                        )
                        link.unlink()
                        target.unlink()
                    else:
                        suffix = {
                            "PYTHON": ".py",
                            "SHELL": ".sh",
                            "YAML": ".yml",
                        }.get(kind, ".data")
                        scan = _scan_unit(
                            f"kernel/lib/synthetic{suffix}",
                            source,
                            [],
                        )
                    self.assertTrue(scan.findings, f"{family}/{variant} did not refuse")
            executed.add(family)
        self.assertEqual(executed, set(_NEGATIVE_FAMILIES))

    def test_real_scanner_rejects_independent_audit_bypasses(self) -> None:
        python_bypasses = {
            "imported_flock_alias":
                "from fcntl import flock as acquire\nacquire(fd, 1)\n",
            "aliased_fcntl_setlk":
                "import fcntl as f\nf.fcntl(fd, f.F_SETLK)\n",
            "imported_setlk_alias":
                "from fcntl import fcntl as control, F_SETLK as command\n"
                "control(fd, command)\n",
            "numeric_setlk":
                "import fcntl\nfcntl.fcntl(fd, 8)\n",
            "constructed_dynamic_import":
                "from importlib import import_module\nimport_module('fc' + 'ntl')\n",
            "constructed_getattr":
                "import fcntl\ngetattr(fcntl, 'fl' + 'ock')(fd, 1)\n",
            "imported_chflags_alias":
                "from os import chflags as mutate\nmutate(path, flags)\n",
            "constructed_immutable_constant":
                "import stat\ngetattr(stat, 'UF_' + 'IMMUTABLE')\n",
            "constructed_immutable_setter":
                "import os\ngetattr(os, 'ch' + 'flags')(path, flags)\n",
            "callback_wrapper":
                "import fcntl\nregister(fcntl.flock, fd, 1)\n",
            "ctypes_flock":
                "import ctypes\nctypes.CDLL(None).flock(fd, 1)\n",
            "mapping_indirection":
                "import fcntl\ncalls = {'acquire': fcntl.flock}\n"
                "calls['acquire'](fd, 1)\n",
            "subprocess_callable_alias":
                "import subprocess\nrunner = subprocess.run\n"
                "runner('flock target', shell=True)\n",
            "subprocess_list":
                "import subprocess\nsubprocess.run(['flock', 'target'])\n",
            "subprocess_string":
                "import subprocess\nsubprocess.run('chflags uchg target', shell=True)\n",
            "unresolved_dynamic_getattr":
                "import fcntl\nname = input()\ngetattr(fcntl, name)(fd, 1)\n",
            "nested_local_command_chain":
                "import subprocess\n"
                "def f():\n"
                "    left = 'fl'\n"
                "    cmd = left + 'ock'\n"
                "    subprocess.run(cmd, shell=True)\n",
            "nested_local_immutable_setter":
                "import os\n"
                "def f(path, flags):\n"
                "    left = 'ch'\n"
                "    name = left + 'flags'\n"
                "    getattr(os, name)(path, flags)\n",
            "unresolved_generated_source":
                "def f(payload):\n"
                "    exec(payload)\n",
            "unresolved_compile":
                "def f(payload):\n"
                "    compile(payload, '<dynamic>', 'exec')\n",
            "unresolved_eval_alias":
                "def f(payload):\n"
                "    evaluate = eval\n"
                "    evaluate(payload)\n",
            "unresolved_runpy":
                "import runpy\n"
                "def f(path):\n"
                "    runpy.run_path(path)\n",
            "branch_command_invalidation":
                "import subprocess\n"
                "def f(condition):\n"
                "    if condition:\n"
                "        cmd = 'fl' + 'ock'\n"
                "    else:\n"
                "        cmd = input()\n"
                "    subprocess.run(cmd, shell=True)\n",
            "rebound_command_invalidation":
                "import subprocess\n"
                "def f():\n"
                "    cmd = 'fl' + 'ock'\n"
                "    cmd = input()\n"
                "    subprocess.run(cmd, shell=True)\n",
            "branch_immutable_invalidation":
                "import os\n"
                "def f(path, flags, condition):\n"
                "    name = 'ch' + 'flags'\n"
                "    if condition:\n"
                "        name = input()\n"
                "    getattr(os, name)(path, flags)\n",
            "loop_command_invalidation":
                "import subprocess\n"
                "def f(items):\n"
                "    cmd = 'echo safe'\n"
                "    for item in items:\n"
                "        cmd = 'fl' + 'ock'\n"
                "    subprocess.run(cmd, shell=True)\n",
            "try_immutable_invalidation":
                "import os\n"
                "def f(path, flags):\n"
                "    name = 'safe'\n"
                "    try:\n"
                "        name = 'ch' + 'flags'\n"
                "    except Exception:\n"
                "        name = input()\n"
                "    getattr(os, name)(path, flags)\n",
            "closure_command_chain":
                "import subprocess\n"
                "def outer():\n"
                "    cmd = 'fl' + 'ock'\n"
                "    def inner():\n"
                "        subprocess.run(cmd, shell=True)\n",
            "closure_late_rebinding":
                "import subprocess\n"
                "def outer():\n"
                "    cmd = 'echo safe'\n"
                "    def inner():\n"
                "        subprocess.run(cmd, shell=True)\n"
                "    cmd = input()\n",
            "global_rebinding":
                "import subprocess\n"
                "cmd = 'echo safe'\n"
                "def mutate():\n"
                "    global cmd\n"
                "    cmd = input()\n"
                "def invoke():\n"
                "    subprocess.run(cmd, shell=True)\n",
            "nonlocal_rebinding":
                "import subprocess\n"
                "def outer():\n"
                "    cmd = 'echo safe'\n"
                "    def inner():\n"
                "        nonlocal cmd\n"
                "        cmd = input()\n"
                "        subprocess.run(cmd, shell=True)\n",
            "unknown_call_mutable_invalidation":
                "import subprocess\n"
                "def f():\n"
                "    commands = ['echo safe']\n"
                "    mutate(commands)\n"
                "    subprocess.run(commands[0], shell=True)\n",
            "lambda_command_scope":
                "import subprocess\n"
                "invoke = lambda cmd: subprocess.run(cmd, shell=True)\n",
            "comprehension_command_scope":
                "import subprocess\n"
                "def f(commands):\n"
                "    return [subprocess.run(cmd, shell=True) for cmd in commands]\n",
            "branch_generated_source":
                "def f(condition, payload):\n"
                "    source = 'pass' if condition else payload\n"
                "    exec(source)\n",
        }
        for name, source in python_bypasses.items():
            with self.subTest(name=name):
                scan = _scan_unit(
                    "kernel/lib/synthetic.py",
                    source,
                    [],
                )
                self.assertTrue(scan.findings, name)
        shell_bypasses = {
            "shell_function": "acquire() { flock \"$1\"; }; acquire target\n",
            "shell_variable": "command=chflags; \"$command\" uchg target\n",
            "shell_constructed_variable":
                "left=fl; right=ock; command=${left}${right}; $command target\n",
            "shell_command_substitution": "result=$(flock target)\n",
            "shell_unresolved": "name=flock; \"${!name}\" target\n",
        }
        for name, source in shell_bypasses.items():
            with self.subTest(name=name):
                scan = _scan_unit(
                    "kernel/lib/synthetic.sh",
                    source,
                    [],
                )
                self.assertTrue(scan.findings, name)

    def test_real_scanner_tracks_callable_and_container_taint(self) -> None:
        adversarial = {
            "conditional_runner_rebinding":
                "import subprocess\n"
                "def f(condition):\n"
                "    runner = subprocess.run if condition else safe_runner\n"
                "    runner('echo safe')\n",
            "nonlocal_runner_rebinding":
                "import subprocess\n"
                "def outer(condition):\n"
                "    runner = safe_runner\n"
                "    def mutate():\n"
                "        nonlocal runner\n"
                "        if condition:\n"
                "            runner = subprocess.run\n"
                "    runner('echo safe')\n",
            "global_runner_rebinding":
                "import subprocess\n"
                "runner = safe_runner\n"
                "def mutate(condition):\n"
                "    global runner\n"
                "    if condition:\n"
                "        runner = subprocess.run\n"
                "def invoke():\n"
                "    runner('echo safe')\n",
            "mapping_callable_roundtrip":
                "import subprocess\n"
                "calls = {}\n"
                "calls['run'] = subprocess.run\n"
                "calls['run']('echo safe')\n",
            "attribute_callable_roundtrip":
                "import subprocess\n"
                "holder = object()\n"
                "holder.run = subprocess.run\n"
                "holder.run('echo safe')\n",
            "container_alias_mutation":
                "import subprocess\n"
                "calls = {}\n"
                "alias = calls\n"
                "alias['run'] = subprocess.run\n"
                "calls['run']('echo safe')\n",
            "deletion_branch_rebinding":
                "import subprocess\n"
                "def f(condition):\n"
                "    runner = subprocess.run\n"
                "    if condition:\n"
                "        del runner\n"
                "        runner = safe_runner\n"
                "    runner('echo safe')\n",
            "comprehension_walrus_write_through":
                "import subprocess\n"
                "cmd = 'echo safe'\n"
                "[(cmd := 'fl' + 'ock') for _ in [1]]\n"
                "subprocess.run(cmd, shell=True)\n",
            "callback_callable_taint":
                "import subprocess\n"
                "callback = subprocess.run\n"
                "register(callback)\n",
            "wrapper_callable_taint":
                "import subprocess\n"
                "def f(condition):\n"
                "    callback = subprocess.run if condition else safe_runner\n"
                "    invoke(callback, 'echo safe')\n",
            "default_callable_capture":
                "import subprocess\n"
                "def f(runner=subprocess.run):\n"
                "    runner('echo safe')\n",
            "loop_callable_rebinding":
                "import subprocess\n"
                "def f(items):\n"
                "    runner = safe_runner\n"
                "    for item in items:\n"
                "        runner = subprocess.run\n"
                "    runner('echo safe')\n",
            "try_finally_callable_rebinding":
                "import subprocess\n"
                "def f():\n"
                "    runner = safe_runner\n"
                "    try:\n"
                "        runner = subprocess.run\n"
                "    finally:\n"
                "        marker = True\n"
                "    runner('echo safe')\n",
            "match_callable_rebinding":
                "import subprocess\n"
                "def f(value):\n"
                "    runner = safe_runner\n"
                "    match value:\n"
                "        case 1:\n"
                "            runner = subprocess.run\n"
                "    runner('echo safe')\n",
            "generated_callable_taint":
                "def f(condition):\n"
                "    evaluate = exec if condition else safe_runner\n"
                "    evaluate('pass')\n",
            "immutable_callable_taint":
                "import os\n"
                "def f(condition, path, flags):\n"
                "    mutate = os.chflags if condition else safe_runner\n"
                "    mutate(path, flags)\n",
            "lock_callable_taint":
                "import fcntl\n"
                "def f(condition, fd):\n"
                "    acquire = fcntl.flock if condition else safe_runner\n"
                "    acquire(fd, 0)\n",
        }
        for name, source in adversarial.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertTrue(scan.findings, name)

        clean = {
            "clean_conditional_runner":
                "def f(condition):\n"
                "    runner = safe_one if condition else safe_two\n"
                "    runner('echo safe')\n",
            "clean_mapping":
                "calls = {'run': safe_runner}\n"
                "calls['run']('echo safe')\n",
            "clean_attribute":
                "holder = object()\n"
                "holder.run = safe_runner\n"
                "holder.run('echo safe')\n",
            "clean_comprehension_walrus":
                "import subprocess\n"
                "cmd = 'echo safe'\n"
                "[(cmd := 'echo safe') for _ in [1]]\n"
                "subprocess.run(cmd, shell=True)\n",
            "clean_delete_rebind":
                "import subprocess\n"
                "runner = subprocess.run\n"
                "del runner\n"
                "runner = safe_runner\n"
                "runner('echo safe')\n",
            "clean_default_capture":
                "def f(runner=safe_runner):\n"
                "    runner('echo safe')\n",
        }
        for name, source in clean.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertEqual(scan.findings, [], name)

    def test_real_scanner_tracks_late_binding_and_nested_aggregates(self) -> None:
        adversarial = {
            "module_late_binding":
                "import subprocess\n"
                "runner = safe_runner\n"
                "def invoke(cmd):\n"
                "    runner(cmd)\n"
                "runner = subprocess.run\n",
            "closure_late_binding":
                "import subprocess\n"
                "def outer():\n"
                "    runner = safe_runner\n"
                "    def invoke(cmd):\n"
                "        runner(cmd)\n"
                "    runner = subprocess.run\n",
            "nonlocal_late_binding":
                "import subprocess\n"
                "def outer():\n"
                "    runner = safe_runner\n"
                "    def invoke(cmd):\n"
                "        runner(cmd)\n"
                "    def mutate():\n"
                "        nonlocal runner\n"
                "        runner = subprocess.run\n",
            "boolop_runner_merge":
                "import subprocess\n"
                "def f(condition):\n"
                "    runner = (condition and subprocess.run) or safe_runner\n"
                "    runner('echo safe')\n",
            "nested_container_callable":
                "import subprocess\n"
                "calls = {'nested': {'run': subprocess.run}}\n"
                "calls['nested']['run']('echo safe')\n",
            "mapping_unpack_callable":
                "import subprocess\n"
                "calls = {**{'run': subprocess.run}}\n"
                "calls['run']('echo safe')\n",
            "nested_alias_mutation":
                "import subprocess\n"
                "inner = {}\n"
                "calls = {'nested': inner}\n"
                "alias = calls['nested']\n"
                "alias['run'] = subprocess.run\n"
                "calls['nested']['run']('echo safe')\n",
            "unresolved_mapping_mutator":
                "calls = {'run': safe_runner}\n"
                "mutate(calls)\n"
                "calls['run']('echo safe')\n",
            "unresolved_object_mutator":
                "holder = object()\n"
                "holder.run = safe_runner\n"
                "mutate(holder)\n"
                "holder.run('echo safe')\n",
            "unresolved_nested_mutator":
                "inner = {'run': safe_runner}\n"
                "calls = {'nested': inner}\n"
                "mutate(calls)\n"
                "calls['nested']['run']('echo safe')\n",
        }
        for name, source in adversarial.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertTrue(scan.findings, name)

        clean = {
            "clean_module_late_binding":
                "runner = safe_one\n"
                "def invoke(cmd):\n"
                "    runner(cmd)\n"
                "runner = safe_two\n",
            "clean_boolop":
                "def f(condition):\n"
                "    runner = (condition and safe_one) or safe_two\n"
                "    runner('echo safe')\n",
            "clean_mapping_unpack":
                "calls = {**{'run': safe_runner}}\n"
                "calls['run']('echo safe')\n",
            "clean_nested_alias":
                "inner = {'run': safe_runner}\n"
                "calls = {'nested': inner}\n"
                "alias = calls['nested']\n"
                "alias['run']('echo safe')\n",
            "clean_mutated_data_not_invoked":
                "calls = {'value': 'safe'}\n"
                "mutate(calls)\n"
                "value = calls['value']\n",
        }
        for name, source in clean.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertEqual(scan.findings, [], name)

    def test_real_scanner_tracks_late_mutable_writes_by_allocation(self) -> None:
        adversarial = {
            "late_mapping_member":
                "import subprocess\n"
                "calls = {}\n"
                "def invoke():\n"
                "    calls['run']('echo safe')\n"
                "calls['run'] = subprocess.run\n",
            "late_object_member":
                "import subprocess\n"
                "holder = object()\n"
                "def invoke():\n"
                "    holder.run('echo safe')\n"
                "holder.run = subprocess.run\n",
            "opaque_mapping_mutator":
                "calls = {'run': safe_runner}\n"
                "def invoke():\n"
                "    calls['run']('echo safe')\n"
                "mutate(calls)\n",
            "late_imported_callable":
                "runner = safe_runner\n"
                "def invoke():\n"
                "    runner('echo safe')\n"
                "from subprocess import run as runner\n",
            "closure_late_mapping_member":
                "import subprocess\n"
                "def outer():\n"
                "    calls = {}\n"
                "    def invoke():\n"
                "        calls['run']('echo safe')\n"
                "    calls['run'] = subprocess.run\n",
            "branch_late_mapping_member":
                "import subprocess\n"
                "calls = {}\n"
                "def invoke():\n"
                "    calls['run']('echo safe')\n"
                "if condition:\n"
                "    calls['run'] = subprocess.run\n"
                "else:\n"
                "    calls['run'] = safe_runner\n",
            "container_method_late_member":
                "import subprocess\n"
                "calls = {}\n"
                "def invoke():\n"
                "    calls['run']('echo safe')\n"
                "calls.update({'run': subprocess.run})\n",
            "global_late_mapping_member":
                "import subprocess\n"
                "calls = {}\n"
                "def invoke():\n"
                "    calls['run']('echo safe')\n"
                "def mutate():\n"
                "    global calls\n"
                "    calls['run'] = subprocess.run\n",
            "nonlocal_late_mapping_member":
                "import subprocess\n"
                "def outer():\n"
                "    calls = {}\n"
                "    def invoke():\n"
                "        calls['run']('echo safe')\n"
                "    def mutate():\n"
                "        nonlocal calls\n"
                "        calls['run'] = subprocess.run\n",
            "deleted_member_remains_potential":
                "import subprocess\n"
                "calls = {'run': subprocess.run}\n"
                "del calls['run']\n"
                "calls['run']('echo safe')\n",
            "class_late_member":
                "import subprocess\n"
                "class Holder:\n"
                "    run = safe_runner\n"
                "def invoke():\n"
                "    Holder.run('echo safe')\n"
                "Holder.run = subprocess.run\n",
            "class_method_late_member":
                "import subprocess\n"
                "class Holder:\n"
                "    run = safe_runner\n"
                "    def invoke(self):\n"
                "        self.run('echo safe')\n"
                "Holder.run = subprocess.run\n",
        }
        for name, source in adversarial.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertTrue(scan.findings, name)

        clean = {
            "equal_allocations_do_not_alias":
                "left = {}\n"
                "right = {}\n"
                "right['run'] = safe_runner\n"
                "mutate(left)\n"
                "right['run']('echo safe')\n",
            "late_safe_mapping_member":
                "calls = {}\n"
                "def invoke():\n"
                "    calls['run']('echo safe')\n"
                "calls['run'] = safe_runner\n",
            "late_safe_object_member":
                "holder = object()\n"
                "def invoke():\n"
                "    holder.run('echo safe')\n"
                "holder.run = safe_runner\n",
        }
        for name, source in clean.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertEqual(scan.findings, [], name)

    def test_real_scanner_covers_keyword_and_inplace_heap_forms(self) -> None:
        adversarial = {
            "keyword_callback":
                "import subprocess\n"
                "register(callback=subprocess.run)\n",
            "kwargs_callback":
                "import subprocess\n"
                "kwargs = {'callback': subprocess.run}\n"
                "register(**kwargs)\n",
            "starred_callback":
                "import subprocess\n"
                "args = (subprocess.run,)\n"
                "register(*args)\n",
            "unknown_starred_callback":
                "def invoke(args):\n"
                "    register(*args)\n",
            "unknown_kwargs_callback":
                "def invoke(kwargs):\n"
                "    register(**kwargs)\n",
            "dict_keyword_callable":
                "import subprocess\n"
                "calls = dict(run=subprocess.run)\n"
                "calls['run']('echo safe')\n",
            "dict_kwargs_callable":
                "import subprocess\n"
                "source = {'run': subprocess.run}\n"
                "calls = dict(**source)\n"
                "calls['run']('echo safe')\n",
            "update_keyword_callable":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "calls.update(run=subprocess.run)\n"
                "calls['run']('echo safe')\n",
            "update_kwargs_callable":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "source = {'run': subprocess.run}\n"
                "calls.update(**source)\n"
                "calls['run']('echo safe')\n",
            "inplace_mapping_union":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "calls |= {'run': subprocess.run}\n"
                "calls['run']('echo safe')\n",
            "aliased_update_keyword":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "apply = calls.update\n"
                "apply(run=subprocess.run)\n"
                "calls['run']('echo safe')\n",
            "aliased_setitem":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "store = calls.__setitem__\n"
                "store('run', subprocess.run)\n"
                "calls['run']('echo safe')\n",
            "direct_protocol_setitem":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "dict.__setitem__(calls, 'run', subprocess.run)\n"
                "calls['run']('echo safe')\n",
            "direct_protocol_unknown_setitem":
                "calls = {'run': safe_runner}\n"
                "def mutate(source):\n"
                "    dict.__setitem__(calls, 'run', source)\n"
                "calls['run']('echo safe')\n",
            "bound_protocol_setitem":
                "import subprocess\n"
                "calls = {'run': safe_runner}\n"
                "store = calls.__setitem__\n"
                "store('run', subprocess.run)\n"
                "calls['run']('echo safe')\n",
            "attribute_setter":
                "import subprocess\n"
                "holder = object()\n"
                "setattr(holder, 'run', subprocess.run)\n"
                "holder.run('echo safe')\n",
            "attribute_unknown_setter":
                "holder = object()\n"
                "def mutate(source):\n"
                "    setattr(holder, 'run', source)\n"
                "holder.run('echo safe')\n",
            "object_protocol_setter":
                "import subprocess\n"
                "holder = object()\n"
                "object.__setattr__(holder, 'run', subprocess.run)\n"
                "holder.run('echo safe')\n",
            "bound_object_protocol_setter":
                "import subprocess\n"
                "holder = object()\n"
                "store = holder.__setattr__\n"
                "store('run', subprocess.run)\n"
                "holder.run('echo safe')\n",
        }
        for name, source in adversarial.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertTrue(scan.findings, name)

        clean = {
            "clean_keyword_callback":
                "register(callback=safe_runner)\n",
            "clean_kwargs_callback":
                "kwargs = {'callback': safe_runner}\n"
                "register(**kwargs)\n",
            "clean_starred_callback":
                "args = (safe_runner,)\n"
                "register(*args)\n",
            "clean_dict_keyword":
                "calls = dict(run=safe_runner)\n"
                "calls['run']('echo safe')\n",
            "clean_update_keyword":
                "calls = {'run': safe_runner}\n"
                "calls.update(run=safe_runner)\n"
                "calls['run']('echo safe')\n",
            "clean_inplace_union":
                "calls = {'run': safe_runner}\n"
                "calls |= {'run': safe_runner}\n"
                "calls['run']('echo safe')\n",
            "clean_direct_protocol_setitem":
                "calls = {'run': safe_runner}\n"
                "dict.__setitem__(calls, 'run', safe_runner)\n"
                "calls['run']('echo safe')\n",
            "clean_attribute_setter":
                "holder = object()\n"
                "setattr(holder, 'run', safe_runner)\n"
                "holder.run('echo safe')\n",
            "clean_object_protocol_setter":
                "holder = object()\n"
                "object.__setattr__(holder, 'run', safe_runner)\n"
                "holder.run('echo safe')\n",
        }
        for name, source in clean.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertEqual(scan.findings, [], name)

    def test_real_scanner_covers_dynamic_subscript_and_protocol_regions(self) -> None:
        adversarial = {
            "unresolved_named_subscript":
                "import subprocess\n"
                "def mutate(calls):\n"
                "    calls['run'] = subprocess.run\n"
                "    calls['run']('echo safe')\n",
            "dynamic_mapping_key":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    calls[key] = subprocess.run\n"
                "    calls['run']('echo safe')\n",
            "dynamic_mapping_alias":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    alias = calls\n"
                "    alias[key] = subprocess.run\n"
                "    calls['run']('echo safe')\n",
            "dynamic_mapping_unknown_value":
                "def mutate(calls, key, source):\n"
                "    calls[key] = source\n"
                "    calls['run']('echo safe')\n",
            "unresolved_local_alias":
                "import subprocess\n"
                "def mutate(source, key):\n"
                "    calls = source\n"
                "    calls[key] = subprocess.run\n"
                "    source['run']('echo safe')\n",
            "slice_assignment":
                "import subprocess\n"
                "def mutate(calls):\n"
                "    calls[1:3] = [subprocess.run]\n"
                "    calls[1]('echo safe')\n",
            "extended_slice_assignment":
                "import subprocess\n"
                "def mutate(calls):\n"
                "    calls[::2] = [subprocess.run]\n"
                "    calls[4]('echo safe')\n",
            "dynamic_delete_preserves_possible_sink":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    calls['run'] = subprocess.run\n"
                "    del calls[key]\n"
                "    calls['run']('echo safe')\n",
            "slice_delete_taints_region":
                "def mutate(calls):\n"
                "    del calls[1:]\n"
                "    calls[1]('echo safe')\n",
            "unresolved_direct_protocol":
                "import subprocess\n"
                "def mutate(calls):\n"
                "    dict.__setitem__(calls, 'run', subprocess.run)\n"
                "    calls['run']('echo safe')\n",
            "unresolved_dynamic_protocol":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    dict.__setitem__(calls, key, subprocess.run)\n"
                "    calls['run']('echo safe')\n",
            "unresolved_list_slice_protocol":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    list.__setitem__(calls, key, subprocess.run)\n"
                "    calls[2]('echo safe')\n",
            "unresolved_bound_protocol":
                "import subprocess\n"
                "def mutate(calls):\n"
                "    store = calls.__setitem__\n"
                "    store('run', subprocess.run)\n"
                "    calls['run']('echo safe')\n",
            "unresolved_protocol_delete":
                "def mutate(calls, key):\n"
                "    dict.__delitem__(calls, key)\n"
                "    calls['run']('echo safe')\n",
            "unresolved_attribute_protocol":
                "import subprocess\n"
                "def mutate(holder):\n"
                "    setattr(holder, 'run', subprocess.run)\n"
                "    holder.run('echo safe')\n",
            "unresolved_dynamic_attribute":
                "import subprocess\n"
                "def mutate(holder, name):\n"
                "    object.__setattr__(holder, name, subprocess.run)\n"
                "    holder.run('echo safe')\n",
        }
        for name, source in adversarial.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertTrue(scan.findings, name)

        clean = {
            "clean_unresolved_named_subscript":
                "def mutate(calls):\n"
                "    calls['run'] = safe_runner\n"
                "    calls['run']('echo safe')\n",
            "clean_dynamic_mapping_key":
                "def mutate(calls, key):\n"
                "    calls[key] = safe_runner\n"
                "    calls['run']('echo safe')\n",
            "clean_dynamic_mapping_alias":
                "def mutate(calls, key):\n"
                "    alias = calls\n"
                "    alias[key] = safe_runner\n"
                "    calls['run']('echo safe')\n",
            "clean_slice_assignment":
                "def mutate(calls):\n"
                "    calls[1:3] = [safe_runner]\n"
                "    calls[1]('echo safe')\n",
            "clean_direct_protocol":
                "def mutate(calls):\n"
                "    dict.__setitem__(calls, 'run', safe_runner)\n"
                "    calls['run']('echo safe')\n",
            "clean_dynamic_protocol":
                "def mutate(calls, key):\n"
                "    dict.__setitem__(calls, key, safe_runner)\n"
                "    calls['run']('echo safe')\n",
            "clean_attribute_protocol":
                "def mutate(holder):\n"
                "    setattr(holder, 'run', safe_runner)\n"
                "    holder.run('echo safe')\n",
            "clean_dynamic_attribute":
                "def mutate(holder, name):\n"
                "    object.__setattr__(holder, name, safe_runner)\n"
                "    holder.run('echo safe')\n",
        }
        for name, source in clean.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertEqual(scan.findings, [], name)

    def test_real_scanner_uses_equality_sound_mapping_key_regions(self) -> None:
        adversarial = {
            "integer_literal_key":
                "import subprocess\n"
                "calls = {1: subprocess.run}\n"
                "calls[1]('echo safe')\n",
            "dangerous_first_unequal_integer":
                "import subprocess\n"
                "calls = {1: subprocess.run, 2: safe_runner}\n"
                "calls[1]('echo safe')\n",
            "float_overwrites_integer_region":
                "import subprocess\n"
                "calls = {1: safe_runner}\n"
                "calls[1.0] = subprocess.run\n"
                "calls[1]('echo safe')\n",
            "bool_matches_integer":
                "import subprocess\n"
                "calls = {True: subprocess.run}\n"
                "calls[1]('echo safe')\n",
            "integer_matches_bool":
                "import subprocess\n"
                "calls = {True: safe_runner}\n"
                "calls[1] = subprocess.run\n"
                "calls[True]('echo safe')\n",
            "complex_matches_float":
                "import subprocess\n"
                "calls = {1.0: safe_runner}\n"
                "calls[1+0j] = subprocess.run\n"
                "calls[1.0]('echo safe')\n",
            "dangerous_complex_key":
                "import subprocess\n"
                "calls = {2+3j: subprocess.run, 2+4j: safe_runner}\n"
                "calls[2+3j]('echo safe')\n",
            "dangerous_bytes_key":
                "import subprocess\n"
                "calls = {b'run': subprocess.run, b'safe': safe_runner}\n"
                "calls[b'run']('echo safe')\n",
            "constructor_pair_numeric":
                "import subprocess\n"
                "calls = dict([(1, subprocess.run)])\n"
                "calls[1.0]('echo safe')\n",
            "update_numeric":
                "import subprocess\n"
                "calls = {1: safe_runner}\n"
                "calls.update({1.0: subprocess.run})\n"
                "calls[True]('echo safe')\n",
            "union_numeric":
                "import subprocess\n"
                "calls = {1: safe_runner} | {1.0: subprocess.run}\n"
                "calls[1]('echo safe')\n",
            "dynamic_numeric_key":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    calls[key] = subprocess.run\n"
                "    calls[1]('echo safe')\n",
            "protocol_numeric_key":
                "import subprocess\n"
                "calls = {1: safe_runner}\n"
                "dict.__setitem__(calls, 1.0, subprocess.run)\n"
                "calls[True]('echo safe')\n",
            "protocol_dynamic_key":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    dict.__setitem__(calls, key, subprocess.run)\n"
                "    calls[1]('echo safe')\n",
            "wildcard_then_exact_safe_remains_tainted":
                "import subprocess\n"
                "def mutate(calls, key):\n"
                "    calls[key] = subprocess.run\n"
                "    calls[1] = safe_runner\n"
                "    calls[1]('echo safe')\n",
            "infinite_key_is_wildcard":
                "import subprocess\n"
                "calls = {1e309: subprocess.run, 1: safe_runner}\n"
                "calls[1]('echo safe')\n",
            "nan_key_is_wildcard":
                "import subprocess\n"
                "key = float('nan')\n"
                "calls = {key: subprocess.run, 1: safe_runner}\n"
                "calls[1]('echo safe')\n",
        }
        for name, source in adversarial.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertTrue(scan.findings, name)

        clean = {
            "clean_integer_literal":
                "calls = {1: safe_runner}\n"
                "calls[1]('echo safe')\n",
            "clean_numeric_join":
                "calls = {1: safe_runner}\n"
                "calls[1.0] = safe_runner\n"
                "calls[True]('echo safe')\n",
            "clean_bool_overwrites_integer":
                "import subprocess\n"
                "calls = {1: subprocess.run, True: safe_runner}\n"
                "calls[1.0]('echo safe')\n",
            "clean_float_overwrites_bool":
                "import subprocess\n"
                "calls = {True: subprocess.run}\n"
                "calls[1.0] = safe_runner\n"
                "calls[1]('echo safe')\n",
            "clean_complex_overwrites_float":
                "import subprocess\n"
                "calls = {1.0: subprocess.run}\n"
                "calls[1+0j] = safe_runner\n"
                "calls[True]('echo safe')\n",
            "clean_negative_zero_overwrite":
                "import subprocess\n"
                "calls = {-0.0: subprocess.run, 0: safe_runner}\n"
                "calls[0+0j]('echo safe')\n",
            "clean_unequal_numeric_keys":
                "import subprocess\n"
                "calls = {1: subprocess.run, 2: safe_runner}\n"
                "calls[2.0]('echo safe')\n",
            "clean_equal_bytes_overwrite":
                "import subprocess\n"
                "calls = {b'run': subprocess.run, b'run': safe_runner}\n"
                "calls[b'run']('echo safe')\n",
            "clean_distinct_bytes_keys":
                "import subprocess\n"
                "calls = {b'bad': subprocess.run, b'run': safe_runner}\n"
                "calls[b'run']('echo safe')\n",
            "clean_constructor_pair":
                "calls = dict([(1, safe_runner)])\n"
                "calls[1.0]('echo safe')\n",
            "clean_protocol_numeric":
                "calls = {1: safe_runner}\n"
                "dict.__setitem__(calls, 1.0, safe_runner)\n"
                "calls[True]('echo safe')\n",
            "clean_protocol_overwrite":
                "import subprocess\n"
                "calls = {1: subprocess.run}\n"
                "dict.__setitem__(calls, True, safe_runner)\n"
                "calls[1.0]('echo safe')\n",
            "clean_update_overwrite":
                "import subprocess\n"
                "calls = {1: subprocess.run}\n"
                "calls.update({1.0: safe_runner})\n"
                "calls[True]('echo safe')\n",
            "clean_wildcard_collision":
                "def mutate(calls, key):\n"
                "    calls[key] = safe_runner\n"
                "    calls[1] = safe_runner\n"
                "    calls[1]('echo safe')\n",
            "clean_list_integer_precision":
                "calls = [safe_runner, safe_runner]\n"
                "calls[1]('echo safe')\n",
            "clean_list_distinct_indexes":
                "calls = [safe_runner, safe_runner]\n"
                "calls[0] = safe_runner\n"
                "calls[1]('echo safe')\n",
            "clean_tuple_integer_precision":
                "calls = (safe_runner, safe_runner)\n"
                "calls[1]('echo safe')\n",
        }
        for name, source in clean.items():
            with self.subTest(name=name):
                scan = _scan_unit("kernel/lib/synthetic.py", source, [])
                self.assertEqual(scan.findings, [], name)

    def test_exact_vinfo_declaration_is_the_only_positive_immutable_fixture(self) -> None:
        padding = ",\n".join(f"('field_{index}', ctypes.c_uint32)"
                            for index in range(17))
        exact = (
            "import ctypes\nclass _VinfoStat(ctypes.Structure):\n"
            f"    _fields_ = [{padding}, ('vst_flags', ctypes.c_uint32)]\n"
        )
        positive = _scan_unit(
            "kernel/bin/awa-registration-bootstrap.py",
            exact,
            [],
        )
        self.assertEqual(positive.findings, [])
        self.assertEqual(positive.vinfo_declarations, 1)
        wrong_file = _scan_unit(
            "kernel/lib/synthetic.py",
            exact,
            [],
        )
        self.assertTrue(wrong_file.findings)
        for drift in (
            exact.replace("ctypes.c_uint32)]", "ctypes.c_uint64)]"),
            exact.replace("field_16", "vst_flags"),
            exact + "value = _VinfoStat().vst_flags\n",
            exact + "setattr(_VinfoStat(), 'vst_flags', 1)\n",
        ):
            with self.subTest(drift=drift[-80:]):
                scan = _scan_unit(
                    "kernel/bin/awa-registration-bootstrap.py",
                    drift,
                    [],
                )
                self.assertTrue(scan.findings)


if __name__ == "__main__":
    import unittest
    unittest.main()
