#!/usr/bin/env python3
"""Private-runtime child bootstrap; no AWA product import occurs before GO."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.abc
import importlib.machinery
import io
import json
import os
import select
import socket
import stat
import sys
import threading
import time
from dataclasses import dataclass
from importlib.resources.abc import Traversable, TraversableResources


CONTROL_FD = 3
AUTHORITY_FDS = (4, 5, 6, 7, 8)
ROUTES = ("admission", "receiver", "startup", "tick")
GO_TIMEOUT_SECONDS = 5.0
HEX64 = frozenset("0123456789abcdef")
RUNTIME_MANIFEST_FIELDS = {
    "schema",
    "source_lock_sha256",
    "normalizer_source_sha256",
    "signing_recipe_source_sha256",
    "record_framing_digest",
    "records",
}
IMPORT_MANIFEST_FIELDS = {"schema", "entry_modules", "records"}
CURRENT_FIELDS = {
    "schema",
    "epoch",
    "active_manifest_sha256",
    "previous_manifest_sha256",
    "active_release_envelope_digest",
    "installed_at_wall_ns",
    "installer_audit_digest",
    "predecessor_current_digest",
    "current_digest",
}
OWNER_GATE_FIELDS = {
    "schema",
    "repository",
    "authorized_by",
    "deployment_scope",
    "direct_receipt_body_hash",
    "candidate_digest",
    "bundle_digest",
    "bundle_projection_hash",
    "import_manifest_hash",
    "source_lock_sha256",
    "runtime_release_envelope_digest",
    "runtime_manifest_sha256",
    "signature_inventory_sha256",
    "capability_digest",
    "qualification_packet_digest",
    "denial_proof_vector_hash",
    "installed_file_hash",
    "wrapper_runtime_hash",
    "bootstrap_contract_hash",
    "private_runtime_contract_hash",
    "privileged_envelope_contract_hash",
    "admin_audit_contract_hash",
    "installer_identity_hash",
    "installer_capability_hash",
    "allowed_signers_contract_path_hash",
    "allowed_signers_contract_hash",
    "signer_public_key_sha256",
    "signer_fingerprint",
    "key_enrollment_digest",
    "key_current_enrollment_hash",
    "accepted_v6_normalized_digest",
    "implementation_exact_head",
    "canonical_root_hash",
    "member_id",
    "harness_root_hash",
    "authorized",
}
LAUNCH_FIELDS = {
    "schema",
    "nonce",
    "route",
    "current_digest",
    "runtime_manifest_sha256",
    "runtime_release_envelope_digest",
    "owner_gate_digest",
    "import_manifest_hash",
    "private_executable_sha256",
    "version_lock_identity",
    "launch_digest",
}


class ChildRefusal(RuntimeError):
    pass


@dataclass(frozen=True)
class RetainedImportRecord:
    kind: str
    logical_name: str
    relative_path: str
    owner_module: str | None
    mode: str
    sha256: str
    content: bytes

    def __post_init__(self) -> None:
        if self.kind not in {"PACKAGE_INITIALIZER", "MODULE", "RESOURCE"}:
            raise ValueError("retained import kind is invalid")
        if (
            self.mode != "0444"
            or hashlib.sha256(self.content).hexdigest() != self.sha256
        ):
            raise ValueError("retained import content mismatch")


class _MemoryTraversable(Traversable):
    def __init__(self, name: str, content: bytes | None = None):
        self._name = name
        self._content = content
        self._children: dict[str, _MemoryTraversable] = {}

    @property
    def name(self) -> str:
        return self._name

    def iterdir(self):
        return iter(self._children.values())

    def is_dir(self) -> bool:
        return self._content is None

    def is_file(self) -> bool:
        return self._content is not None

    def joinpath(self, *descendants: str):
        node = self
        for name in descendants:
            node = node._children.get(name, _MemoryTraversable(name))
        return node

    def open(self, mode: str = "r", *args, **kwargs):
        if self._content is None:
            raise FileNotFoundError(self._name)
        if "b" in mode:
            return io.BytesIO(self._content)
        return io.StringIO(self._content.decode(kwargs.get("encoding") or "utf-8"))


class _RetainedResourceReader(TraversableResources):
    def __init__(self, resources: dict[str, bytes]):
        self._root = _MemoryTraversable("")
        self._root._children.update(
            {
                name: _MemoryTraversable(name, content)
                for name, content in resources.items()
            }
        )

    def files(self):
        return self._root


class RetainedProductImporter(
    importlib.abc.MetaPathFinder,
    importlib.abc.Loader,
):
    def __init__(self, records: tuple[RetainedImportRecord, ...]):
        modules: dict[str, RetainedImportRecord] = {}
        resources: dict[str, dict[str, bytes]] = {}
        for record in records:
            if record.kind in {"PACKAGE_INITIALIZER", "MODULE"}:
                if record.logical_name in modules:
                    raise ValueError("duplicate retained module")
                record.content.decode("utf-8", "strict")
                modules[record.logical_name] = record
            else:
                if record.owner_module is None:
                    raise ValueError("retained resource owner absent")
                name = record.logical_name.rsplit(":", 1)[-1]
                if name in resources.setdefault(record.owner_module, {}):
                    raise ValueError("duplicate retained resource")
                resources[record.owner_module][name] = record.content
        self._modules = modules
        self._resources = resources

    def find_spec(self, fullname, path=None, target=None):
        record = self._modules.get(fullname)
        if record is None:
            return None
        package = record.kind == "PACKAGE_INITIALIZER"
        spec = importlib.machinery.ModuleSpec(
            fullname, self, is_package=package
        )
        spec.origin = self.get_filename(fullname)
        spec.has_location = True
        if package:
            spec.submodule_search_locations = ()
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        record = self._modules[module.__name__]
        code = compile(
            record.content.decode("utf-8", "strict"),
            self.get_filename(module.__name__),
            "exec",
            dont_inherit=True,
            optimize=0,
        )
        exec(code, module.__dict__)

    def get_filename(self, fullname: str) -> str:
        record = self._modules[fullname]
        return f"awa-retained://{record.sha256}/{fullname}"

    def get_resource_reader(self, fullname: str):
        return _RetainedResourceReader(self._resources.get(fullname, {}))


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ChildRefusal(f"duplicate authority key: {key}")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in HEX64 for character in value)
    )


def _authority_digest(domain: str, value: dict, *, lf: bool) -> str:
    framed = _canonical(value) + (b"\n" if lf else b"")
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + framed
    ).hexdigest()


def _canonical_authority(
    fd: int, limit: int = 4 * 1024 * 1024
) -> tuple[bytes, dict]:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ChildRefusal(f"authority fd {fd} metadata refused")
    if before.st_size <= 1 or before.st_size > limit:
        raise ChildRefusal(f"authority fd {fd} size refused")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = before.st_size
    while remaining:
        chunk = os.read(fd, min(remaining, 65_536))
        if not chunk:
            raise ChildRefusal(f"authority fd {fd} truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\x00" in raw
    ):
        raise ChildRefusal(f"authority fd {fd} framing refused")
    try:
        value = json.loads(
            raw[:-1].decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(
                ChildRefusal("floating-point authority refused")
            ),
            parse_constant=lambda _: (_ for _ in ()).throw(
                ChildRefusal("non-finite authority refused")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChildRefusal(f"authority fd {fd} JSON refused") from exc
    encoded = _canonical(value) + b"\n"
    if not isinstance(value, dict) or encoded != raw:
        raise ChildRefusal(f"authority fd {fd} is not JCS+LF")
    after = os.fstat(fd)
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_gid,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    )
    if identity != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
        after.st_gid,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ChildRefusal(f"authority fd {fd} changed while reading")
    return raw, value


def _verify_authority_fds(
    *, route: str, nonce: str
) -> tuple[bytes, ...]:
    rows = tuple(_canonical_authority(fd) for fd in AUTHORITY_FDS)
    raw = tuple(item[0] for item in rows)
    runtime, imports, gate, current, launch = (
        item[1] for item in rows
    )
    if (
        set(runtime) != RUNTIME_MANIFEST_FIELDS
        or runtime.get("schema") != "awa-private-runtime-manifest/v1"
    ):
        raise ChildRefusal("runtime manifest authority refused")
    runtime_digest = _authority_digest(
        "awa-private-runtime-manifest/v1", runtime, lf=False
    )
    if (
        set(imports) != IMPORT_MANIFEST_FIELDS
        or imports.get("schema") != "awa-registration-import-manifest/v1"
    ):
        raise ChildRefusal("AWA import manifest authority refused")
    import_digest = hashlib.sha256(
        b"awa-registration-import-manifest/v1\0" + raw[1][:-1]
    ).hexdigest()
    if (
        set(gate) != OWNER_GATE_FIELDS
        or gate.get("schema") != "awa-registration-owner-gate/v3"
        or gate.get("authorized") is not True
    ):
        raise ChildRefusal("owner gate authority refused")
    gate_digest = _authority_digest(
        "awa-registration-owner-gate/v3", gate, lf=False
    )
    if (
        set(current) != CURRENT_FIELDS
        or current.get("schema") != "awa-private-runtime-current/v1"
    ):
        raise ChildRefusal("current authority refused")
    current_body = dict(current)
    current_claim = current_body.pop("current_digest", None)
    if current_claim != _authority_digest(
        "awa-private-runtime-current/v1", current_body, lf=True
    ):
        raise ChildRefusal("current digest refused")
    if (
        set(launch) != LAUNCH_FIELDS
        or launch.get("schema") != "awa-registration-launch/v1"
    ):
        raise ChildRefusal("launch authority refused")
    launch_body = dict(launch)
    launch_claim = launch_body.pop("launch_digest", None)
    if launch_claim != _authority_digest(
        "awa-registration-launch/v1", launch_body, lf=True
    ):
        raise ChildRefusal("launch digest refused")
    expected = {
        "nonce": nonce,
        "route": route,
        "current_digest": current_claim,
        "runtime_manifest_sha256": runtime_digest,
        "runtime_release_envelope_digest": gate.get(
            "runtime_release_envelope_digest"
        ),
        "owner_gate_digest": gate_digest,
        "import_manifest_hash": import_digest,
    }
    if any(launch.get(key) != value for key, value in expected.items()):
        raise ChildRefusal("launch authority cross-binding refused")
    if (
        current.get("active_manifest_sha256") != runtime_digest
        or current.get("active_release_envelope_digest")
        != gate.get("runtime_release_envelope_digest")
        or gate.get("runtime_manifest_sha256") != runtime_digest
        or gate.get("import_manifest_hash") != import_digest
        or not _hex64(launch.get("private_executable_sha256"))
        or not _hex64(launch.get("version_lock_identity"))
    ):
        raise ChildRefusal("retained authority disagreement")
    return raw


class _Watchdog:
    def __init__(self, control: socket.socket, expected_parent_pid: int):
        self._control = control
        self._expected_parent_pid = expected_parent_pid
        self._complete = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="awa-registration-parent-watchdog",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def complete(self) -> None:
        self._complete.set()

    def _run(self) -> None:
        while not self._complete.wait(0.05):
            if os.getppid() != self._expected_parent_pid:
                os._exit(70)
            try:
                readable, _, _ = select.select([self._control], [], [], 0)
                if readable:
                    data = self._control.recv(1, socket.MSG_PEEK)
                    if data == b"":
                        os._exit(71)
            except OSError:
                os._exit(72)


def await_parent_go(
    control: socket.socket,
    *,
    expected_parent_pid: int,
    route: str,
    nonce: str,
) -> tuple[_Watchdog, tuple[bytes, ...]]:
    if os.getppid() != expected_parent_pid:
        raise ChildRefusal("expected parent PID mismatch before watchdog")
    watchdog = _Watchdog(control, expected_parent_pid)
    watchdog.start()
    if os.getppid() != expected_parent_pid:
        raise ChildRefusal("expected parent PID mismatch after watchdog")
    authorities = _verify_authority_fds(route=route, nonce=nonce)
    control.sendall(f"READY {nonce}\n".encode("ascii"))
    control.settimeout(GO_TIMEOUT_SECONDS)
    expected = f"GO {nonce}\n".encode("ascii")
    received = bytearray()
    while len(received) <= len(expected):
        chunk = control.recv(len(expected) - len(received))
        if not chunk:
            raise ChildRefusal("control EOF before GO")
        received.extend(chunk)
        if received.endswith(b"\n"):
            break
    if bytes(received) != expected:
        raise ChildRefusal("GO token/order/nonce refused")
    if os.getppid() != expected_parent_pid:
        raise ChildRefusal("expected parent PID mismatch at GO")
    if _verify_authority_fds(route=route, nonce=nonce) != authorities:
        raise ChildRefusal("authority descriptors drifted before import")
    if os.environ.get("AWA_REGISTRATION_SPAWN_NONCE") != nonce:
        raise ChildRefusal("spawn nonce environment mismatch")
    control.sendall(f"IMPORT_READY {nonce}\n".encode("ascii"))
    return watchdog, authorities


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", choices=ROUTES, required=True)
    parser.add_argument("--expected-parent-pid", type=int, required=True)
    parser.add_argument("--nonce", required=True)
    args = parser.parse_args(argv)
    if (
        args.expected_parent_pid <= 0
        or len(args.nonce) != 64
        or any(char not in "0123456789abcdef" for char in args.nonce)
    ):
        raise ChildRefusal("child arguments refused")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    control = socket.socket(fileno=CONTROL_FD)
    watchdog: _Watchdog | None = None
    try:
        watchdog, authorities = await_parent_go(
            control,
            expected_parent_pid=args.expected_parent_pid,
            route=args.route,
            nonce=args.nonce,
        )
        # This is the first AWA product import in the process. Every authority
        # and barrier above has completed before this exact statement.
        receiver = importlib.import_module("engine.registration_receiver")
        result = int(
            receiver.private_runtime_main(
                [args.route], authority_bytes=authorities
            )
        )
        control.sendall(f"TERMINAL {args.nonce} {result}\n".encode("ascii"))
        watchdog.complete()
        return result
    except BaseException:
        if watchdog is not None:
            watchdog.complete()
        return 1
    finally:
        try:
            control.close()
        except OSError:
            pass
        for fd in AUTHORITY_FDS:
            try:
                os.close(fd)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
