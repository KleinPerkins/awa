#!/usr/bin/env python3
"""Pathless root-admin bootstrap and immutable subsequent entrypoint.

The module is self-contained because its exact bytes are also inline bootstrap
B for first installation.  Importing it performs no syscall.  Native dispatch
derives all request paths from UID/request ID and never accepts a path.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


PRODUCTION_ROOT = "/Library/Application Support/AWA"
QUALIFICATION_PREFIX = "/Library/Application Support/AWA-qualification-"
REQUEST_PREFIX = "/private/var/tmp/awa-private-runtime-envelope-"
OPERATIONS = ("INSTALL", "UPDATE", "ROLLBACK", "REMOVE", "QUALIFY")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UINT = re.compile(r"^(?:0|[1-9][0-9]*)$")
OWNER_NAMESPACE = "awa-private-runtime-release-envelope-v1"
QUALIFICATION_NAMESPACE = "awa-private-runtime-qualification-release-v1"
OWNER_SIGNERS_V2 = (
    'KleinPerkins namespaces="awa-private-runtime-release-envelope-v1,'
    'awa-registration-owner-gate-v3" ssh-ed25519 '
    "AAAAC3NzaC1lZDI1NTE5AAAAIE+scgn2qp86lkQWcVDpJ+SXT/pVF0DntlxGVnmnFyEp\n"
).encode("ascii")
CONTEXT_FIELDS = frozenset(
    {
        "schema",
        "request",
        "release_envelope",
        "allowed_signers",
        "packet_root_index",
        "installed_closure",
        "context_digest",
    }
)
PACKET_RECORD_FIELDS = frozenset(
    {
        "path",
        "role",
        "domain",
        "size",
        "sha256",
        "mode",
        "media_type",
        "encoding",
    }
)
CLOSURE_ROLES = {
    "ROOT_ADMIN": ("bin/awa-private-runtime-admin", "555"),
    "ROOT_ENTRYPOINT": ("bin/awa-registration", "555"),
    "PLATFORM_BOOTSTRAP": ("bootstrap/v1/bootstrap.py", "555"),
    "CHILD_BOOTSTRAP": ("bootstrap/v1/child.py", "555"),
}
PRODUCTION_RELEASE_FIELDS = frozenset(
    {
        "schema",
        "repository",
        "exact_head",
        "source_lock_sha256",
        "normalizer_source_sha256",
        "signing_recipe_source_sha256",
        "capability_digest",
        "sqlite_compile_options_hash",
        "runtime_manifest_sha256",
        "signature_inventory_sha256",
        "archive_sha256",
        "archive_size",
        "sbom_sha256",
        "license_inventory_sha256",
        "qualification_packet_digest",
        "minimum_epoch",
        "release_envelope_digest",
    }
)
QUALIFICATION_RELEASE_FIELDS = frozenset(
    {
        "schema",
        "repository",
        "mode",
        "exact_head",
        "qualification_nonce",
        "qualification_root",
        "fixture_id",
        "epoch",
        "runtime_archive_sha256",
        "fixture_manifest_digest",
        "marker_sha256",
        "qualification_allowed_signers_digest",
        "release_envelope_digest",
    }
)
RUNTIME_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "source_lock_sha256",
        "normalizer_source_sha256",
        "signing_recipe_source_sha256",
        "record_framing_digest",
        "records",
    }
)
FIXTURE_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "fixture_id",
        "epoch",
        "runtime_archive_sha256",
        "marker",
        "manifest_digest",
    }
)
CURRENT_FIELDS = frozenset(
    {
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
)
REQUEST_FIELDS = frozenset(
    {
        "schema",
        "mode",
        "operation",
        "requested_uid",
        "request_id",
        "target_root",
        "packet_root_digest",
        "qualification_context_digest",
        "qualification_allowed_signers_digest",
        "pre_current_digest",
        "target_release_envelope_digest",
        "target_manifest_sha256",
        "target_epoch",
        "previous_manifest_sha256",
        "current_manifest_sha256",
        "new_manifest_sha256",
        "q1_envelope_digest",
        "q1_manifest_sha256",
        "q2_envelope_digest",
        "q2_manifest_sha256",
        "created_wall_ns",
        "expires_wall_ns",
        "request_digest",
    }
)


class AdminRefusal(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise AdminRefusal("AWA_DUPLICATE_KEY_REFUSED")
        result[key] = value
    return result


def _parse_canonical(raw: bytes) -> object:
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\0" in raw
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        raise AdminRefusal("AWA_AUTHORITY_FRAMING_REFUSED")
    try:
        value = json.loads(
            raw[:-1].decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(
                AdminRefusal("AWA_FLOAT_REFUSED")
            ),
            parse_constant=lambda _: (_ for _ in ()).throw(
                AdminRefusal("AWA_CONSTANT_REFUSED")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdminRefusal("AWA_AUTHORITY_JSON_REFUSED") from exc
    if _canonical(value) + b"\n" != raw:
        raise AdminRefusal("AWA_AUTHORITY_CANONICAL_REFUSED")
    return value


def _digest(domain: str, value: dict) -> str:
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + _canonical(value) + b"\n"
    ).hexdigest()


def _uid(value: str) -> int:
    if UINT.fullmatch(value) is None or len(value) > 10:
        raise AdminRefusal("AWA_UID_REFUSED")
    number = int(value)
    if number > 2**32 - 1:
        raise AdminRefusal("AWA_UID_REFUSED")
    return number


def _request_id(value: str) -> str:
    if HEX64.fullmatch(value) is None:
        raise AdminRefusal("AWA_REQUEST_ID_REFUSED")
    return value


@dataclass(frozen=True)
class RequestAssetPaths:
    envelope: str
    archive: str
    manifest: str
    signature: str


def derive_request_asset_paths(
    requested_uid: str, request_id: str
) -> RequestAssetPaths:
    _uid(requested_uid)
    _request_id(request_id)
    envelope = f"{REQUEST_PREFIX}{requested_uid}-{request_id}.json"
    return RequestAssetPaths(
        envelope=envelope,
        archive=envelope + ".archive",
        manifest=envelope + ".manifest.json",
        signature=envelope + ".sig",
    )


def _read_retained(
    path: str,
    *,
    requested_uid: int,
    minimum: int,
    maximum: int,
) -> tuple[int, bytes]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != requested_uid
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size < minimum
            or before.st_size > maximum
        ):
            raise AdminRefusal("AWA_ASSET_METADATA_REFUSED")
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                raise AdminRefusal("AWA_ASSET_TRUNCATED")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
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
            raise AdminRefusal("AWA_ASSET_CHANGED")
        return descriptor, b"".join(chunks)
    except BaseException:
        os.close(descriptor)
        raise


def parse_privileged_request(raw: bytes) -> dict:
    value = _parse_canonical(raw)
    if (
        not isinstance(value, dict)
        or set(value) != REQUEST_FIELDS
        or value.get("schema") != "awa-registration-privileged-request/v1"
    ):
        raise AdminRefusal("AWA_REQUEST_SCHEMA_REFUSED")
    body = dict(value)
    claimed = body.pop("request_digest")
    if (
        not isinstance(claimed, str)
        or HEX64.fullmatch(claimed) is None
        or claimed != _digest("awa-registration-privileged-request/v1", body)
    ):
        raise AdminRefusal("AWA_REQUEST_DIGEST_REFUSED")
    if (
        HEX64.fullmatch(str(value.get("request_id", ""))) is None
        or HEX64.fullmatch(str(value.get("packet_root_digest", ""))) is None
    ):
        raise AdminRefusal("AWA_REQUEST_HASH_REFUSED")
    for field in (
        "qualification_context_digest",
        "qualification_allowed_signers_digest",
        "pre_current_digest",
        "target_release_envelope_digest",
        "target_manifest_sha256",
        "previous_manifest_sha256",
        "current_manifest_sha256",
        "new_manifest_sha256",
        "q1_envelope_digest",
        "q1_manifest_sha256",
        "q2_envelope_digest",
        "q2_manifest_sha256",
    ):
        item = value.get(field)
        if item is not None and (
            not isinstance(item, str) or HEX64.fullmatch(item) is None
        ):
            raise AdminRefusal("AWA_REQUEST_HASH_REFUSED")
    created = value.get("created_wall_ns")
    expires = value.get("expires_wall_ns")
    if (
        not isinstance(created, str)
        or UINT.fullmatch(created) is None
        or not isinstance(expires, str)
        or UINT.fullmatch(expires) is None
        or int(expires) <= int(created)
        or int(expires) - int(created) > 900_000_000_000
    ):
        raise AdminRefusal("AWA_REQUEST_EXPIRY_REFUSED")
    epoch = value.get("target_epoch")
    if epoch is not None and (
        not isinstance(epoch, str)
        or UINT.fullmatch(epoch) is None
        or int(epoch) < 1
    ):
        raise AdminRefusal("AWA_REQUEST_EPOCH_REFUSED")
    mode = value.get("mode")
    target = value.get("target_root")
    if not isinstance(value.get("requested_uid"), str):
        raise AdminRefusal("AWA_UID_REFUSED")
    _uid(value["requested_uid"])
    if mode == "PRODUCTION":
        if target != PRODUCTION_ROOT:
            raise AdminRefusal("AWA_MODE_ROOT_REFUSED")
        qualification_fields = (
            "qualification_context_digest",
            "qualification_allowed_signers_digest",
            "q1_envelope_digest",
            "q1_manifest_sha256",
            "q2_envelope_digest",
            "q2_manifest_sha256",
        )
        if any(value.get(field) is not None for field in qualification_fields):
            raise AdminRefusal("AWA_PRODUCTION_TRUST_REFUSED")
    elif mode == "QUALIFY":
        suffix = (
            target.removeprefix(QUALIFICATION_PREFIX)
            if isinstance(target, str)
            else ""
        )
        if HEX64.fullmatch(suffix) is None:
            raise AdminRefusal("AWA_MODE_ROOT_REFUSED")
        if any(
            value.get(field) is None
            for field in (
                "qualification_context_digest",
                "qualification_allowed_signers_digest",
                "q1_envelope_digest",
                "q1_manifest_sha256",
                "q2_envelope_digest",
                "q2_manifest_sha256",
            )
        ):
            raise AdminRefusal("AWA_QUALIFICATION_TRUST_REFUSED")
    else:
        raise AdminRefusal("AWA_MODE_REFUSED")
    if value.get("operation") not in OPERATIONS:
        raise AdminRefusal("AWA_OPERATION_REFUSED")
    return value


def parse_privileged_context(
    raw: bytes,
) -> tuple[dict, dict | None, bytes, str, dict[str, bytes]]:
    value = _parse_canonical(raw)
    if (
        not isinstance(value, dict)
        or set(value) != CONTEXT_FIELDS
        or value.get("schema") != "awa-registration-privileged-context/v1"
    ):
        raise AdminRefusal("AWA_CONTEXT_SCHEMA_REFUSED")
    body = dict(value)
    claimed = body.pop("context_digest")
    if claimed != _digest("awa-registration-privileged-context/v1", body):
        raise AdminRefusal("AWA_CONTEXT_DIGEST_REFUSED")
    request_value = value["request"]
    if not isinstance(request_value, dict):
        raise AdminRefusal("AWA_CONTEXT_REQUEST_REFUSED")
    request = parse_privileged_request(_canonical(request_value) + b"\n")
    packet_index = value["packet_root_index"]
    if (
        not isinstance(packet_index, dict)
        or set(packet_index) != {"schema", "records", "index_digest"}
        or packet_index.get("schema")
        != (
            "awa-registration-private-runtime-qualification-"
            "packet-root-index/v2"
        )
        or not isinstance(packet_index.get("records"), list)
    ):
        raise AdminRefusal("AWA_PACKET_INDEX_REFUSED")
    index_body = {
        "schema": packet_index["schema"],
        "records": packet_index["records"],
    }
    if (
        packet_index["records"]
        != sorted(
            packet_index["records"],
            key=lambda row: (
                str(row.get("path", "")).encode("utf-8"),
                str(row.get("role", "")).encode("utf-8"),
            ),
        )
        or any(
            not isinstance(record, dict)
            or set(record) != PACKET_RECORD_FIELDS
            for record in packet_index["records"]
        )
        or packet_index.get("index_digest")
        != _digest(
            "awa-registration-private-runtime-qualification-packet-root/v2",
            index_body,
        )
        or packet_index.get("index_digest") != request["packet_root_digest"]
    ):
        raise AdminRefusal("AWA_PACKET_ROOT_REFUSED")
    packet_by_role = {
        record["role"]: record for record in packet_index["records"]
    }
    closure_value = value["installed_closure"]
    if not isinstance(closure_value, list):
        raise AdminRefusal("AWA_CLOSURE_REFUSED")
    closure: dict[str, bytes] = {}
    for record in closure_value:
        if not isinstance(record, dict) or set(record) != {
            "role",
            "path",
            "mode",
            "size",
            "sha256",
            "content_base64",
        }:
            raise AdminRefusal("AWA_CLOSURE_RECORD_REFUSED")
        role = record["role"]
        expected = CLOSURE_ROLES.get(role)
        try:
            content = base64.b64decode(
                record["content_base64"], validate=True
            )
        except (TypeError, ValueError) as exc:
            raise AdminRefusal("AWA_CLOSURE_ENCODING_REFUSED") from exc
        packet_record = packet_by_role.get(role)
        if (
            expected is None
            or (record["path"], record["mode"]) != expected
            or record["size"] != str(len(content))
            or record["sha256"] != hashlib.sha256(content).hexdigest()
            or packet_record is None
            or packet_record["sha256"] != record["sha256"]
            or packet_record["size"] != record["size"]
            or role in closure
        ):
            raise AdminRefusal("AWA_CLOSURE_RECORD_REFUSED")
        closure[role] = content
    required_roles = (
        set(CLOSURE_ROLES)
        if request["mode"] == "PRODUCTION"
        else {"ROOT_ADMIN"}
    )
    if set(closure) != required_roles:
        raise AdminRefusal("AWA_CLOSURE_INVENTORY_REFUSED")
    release = value["release_envelope"]
    removing = request["operation"] == "REMOVE"
    if release is not None and not isinstance(release, dict):
        raise AdminRefusal("AWA_CONTEXT_RELEASE_REFUSED")
    if removing != (release is None):
        raise AdminRefusal("AWA_CONTEXT_RELEASE_REFUSED")
    release_body = dict(release or {})
    release_digest = release_body.pop("release_envelope_digest", None)
    if request["mode"] == "PRODUCTION":
        if (
            (
                not removing
                and (
                    set(release or {}) != PRODUCTION_RELEASE_FIELDS
                    or release.get("schema")
                    != "awa-private-runtime-release-envelope/v1"
                    or release.get("repository") != "KleinPerkins/awa"
                )
            )
            or value["allowed_signers"] is not None
        ):
            raise AdminRefusal("AWA_PRODUCTION_RELEASE_REFUSED")
        namespace = OWNER_NAMESPACE
        allowed_signers = OWNER_SIGNERS_V2
        if (
            not removing
            and (
                HEX64.fullmatch(
                    str(release.get("qualification_packet_digest", ""))
                )
                is None
                or release.get("qualification_packet_digest")
                == request["packet_root_digest"]
            )
        ):
            raise AdminRefusal("AWA_QUALIFICATION_PACKET_REFUSED")
    else:
        if (
            not removing
            and (
                set(release or {}) != QUALIFICATION_RELEASE_FIELDS
                or release.get("schema")
                != "awa-private-runtime-qualification-release-envelope/v1"
                or release.get("repository") != "KleinPerkins/awa"
                or release.get("mode") != "QUALIFY"
            )
        ):
            raise AdminRefusal("AWA_QUALIFICATION_RELEASE_REFUSED")
        signer = value["allowed_signers"]
        if not isinstance(signer, dict):
            raise AdminRefusal("AWA_QUALIFICATION_SIGNER_REFUSED")
        signer_body = dict(signer)
        signer_digest = signer_body.pop("contract_digest", None)
        line = signer.get("allowed_signers_line")
        if (
            signer.get("schema")
            != "awa-registration-qualification-allowed-signers/v1"
            or signer.get("mode") != "QUALIFY"
            or signer.get("principal") != "AWAQualification"
            or signer.get("namespaces")
            != [QUALIFICATION_NAMESPACE]
            or signer.get("qualification_root") != request["target_root"]
            or signer_digest
            != _digest(
                "awa-registration-qualification-allowed-signers/v1",
                signer_body,
            )
            or signer_digest
            != request["qualification_allowed_signers_digest"]
            or not isinstance(line, str)
            or not line.endswith("\n")
            or hashlib.sha256(line.encode("utf-8")).hexdigest()
            != signer.get("allowed_signers_sha256")
        ):
            raise AdminRefusal("AWA_QUALIFICATION_SIGNER_REFUSED")
        namespace = QUALIFICATION_NAMESPACE
        allowed_signers = line.encode("utf-8")
    if not removing and (
        release_digest
        != _digest(str(release["schema"]), release_body)  # type: ignore[index]
        or release_digest != request["target_release_envelope_digest"]
    ):
        raise AdminRefusal("AWA_RELEASE_DIGEST_REFUSED")
    if removing:
        manifest_digest = None
    elif request["mode"] == "PRODUCTION":
        manifest_digest = release.get("runtime_manifest_sha256")
    else:
        manifest_digest = release.get("fixture_manifest_digest")
    if manifest_digest != request["target_manifest_sha256"]:
        raise AdminRefusal("AWA_RELEASE_MANIFEST_REFUSED")
    return request, release, allowed_signers, namespace, closure


def verify_signature(
    message: bytes,
    signature: bytes,
    *,
    allowed_signers: bytes,
    namespace: str,
) -> str:
    if (
        not message.endswith(b"\n")
        or b"BEGIN SSH SIGNATURE" not in signature
        or not allowed_signers.endswith(b"\n")
    ):
        raise AdminRefusal("AWA_SIGNATURE_SHAPE_REFUSED")
    with tempfile.TemporaryDirectory(prefix="awa-admin-signature.") as raw:
        root = Path(raw)
        signers = root / "allowed-signers"
        detached = root / "release.sig"
        signers.write_bytes(allowed_signers)
        detached.write_bytes(signature)
        signers.chmod(0o600)
        detached.chmod(0o600)
        principal = (
            "KleinPerkins"
            if namespace == OWNER_NAMESPACE
            else "AWAQualification"
        )
        result = subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(signers),
                "-I",
                principal,
                "-n",
                namespace,
                "-s",
                str(detached),
            ],
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=10,
        )
    if result.returncode != 0:
        raise AdminRefusal("AWA_SIGNATURE_INVALID")
    return hashlib.sha256(signature).hexdigest()


def _safe_relative_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\0" in value
        or os.path.normpath(value) != value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise AdminRefusal("AWA_MANIFEST_PATH_REFUSED")
    return value


def validate_manifest_and_archive(
    manifest_raw: bytes,
    archive: bytes,
    *,
    request: dict,
    release: dict,
) -> tuple[dict, tuple[dict, ...]]:
    manifest = _parse_canonical(manifest_raw)
    if not isinstance(manifest, dict):
        raise AdminRefusal("AWA_MANIFEST_SCHEMA_REFUSED")
    archive_digest = hashlib.sha256(archive).hexdigest()
    records: list[dict] = []
    if request["mode"] == "PRODUCTION":
        if (
            set(manifest) != RUNTIME_MANIFEST_FIELDS
            or manifest.get("schema") != "awa-private-runtime-manifest/v1"
            or not isinstance(manifest.get("records"), list)
            or hashlib.sha256(
                b"awa-private-runtime-manifest/v1\0"
                + _canonical(manifest)
            ).hexdigest()
            != request["target_manifest_sha256"]
            or release.get("archive_sha256") != archive_digest
            or release.get("archive_size") != str(len(archive))
        ):
            raise AdminRefusal("AWA_RUNTIME_MANIFEST_REFUSED")
        prior: bytes | None = None
        framing = bytearray()
        for item in manifest["records"]:
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "mode", "size", "sha256", "macho"}
            ):
                raise AdminRefusal("AWA_MANIFEST_RECORD_REFUSED")
            path = _safe_relative_path(item["path"])
            encoded = path.encode("utf-8")
            if prior is not None and encoded <= prior:
                raise AdminRefusal("AWA_MANIFEST_ORDER_REFUSED")
            prior = encoded
            if (
                item["mode"] not in {"444", "555"}
                or not isinstance(item["size"], str)
                or UINT.fullmatch(item["size"]) is None
                or not isinstance(item["sha256"], str)
                or HEX64.fullmatch(item["sha256"]) is None
                or type(item["macho"]) is not bool
            ):
                raise AdminRefusal("AWA_MANIFEST_RECORD_REFUSED")
            records.append(dict(item))
            framing.extend(encoded)
            framing.extend(b"\0" + item["mode"].encode("ascii"))
            framing.extend(b"\0" + item["size"].encode("ascii"))
            framing.extend(b"\0" + item["sha256"].encode("ascii"))
            framing.extend(b"\0" + (b"1" if item["macho"] else b"0") + b"\n")
        if hashlib.sha256(framing).hexdigest() != manifest.get(
            "record_framing_digest"
        ):
            raise AdminRefusal("AWA_MANIFEST_FRAMING_REFUSED")
    else:
        if (
            set(manifest) != FIXTURE_MANIFEST_FIELDS
            or manifest.get("schema")
            != "awa-registration-qualification-fixture-manifest/v1"
            or _digest(
                "awa-registration-qualification-fixture-manifest/v1",
                {
                    key: value
                    for key, value in manifest.items()
                    if key != "manifest_digest"
                },
            )
            != manifest.get("manifest_digest")
            or manifest.get("manifest_digest")
            != request["target_manifest_sha256"]
            or release.get("runtime_archive_sha256") != archive_digest
        ):
            raise AdminRefusal("AWA_FIXTURE_MANIFEST_REFUSED")
        marker = manifest.get("marker")
        if not isinstance(marker, dict) or set(marker) != {
            "path",
            "mode",
            "size",
            "sha256",
        }:
            raise AdminRefusal("AWA_FIXTURE_MARKER_REFUSED")
        records.append(
            {
                **marker,
                "path": _safe_relative_path(marker["path"]),
                "macho": False,
            }
        )
    return manifest, tuple(records)


def extract_validated_archive(
    archive: bytes,
    records: tuple[dict, ...],
    destination: Path,
    *,
    owner_uid: int,
    owner_gid: int,
) -> tuple[str, ...]:
    if destination.exists():
        raise AdminRefusal("AWA_STAGE_EXISTS")
    destination.mkdir(mode=0o755, parents=False)
    expected = {record["path"]: record for record in records}
    observed: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as handle:
            members = handle.getmembers()
            for member in members:
                name = member.name.removesuffix("/")
                if member.isdir():
                    _safe_relative_path(name)
                    continue
                name = _safe_relative_path(name)
                record = expected.get(name)
                if (
                    record is None
                    or name in observed
                    or not member.isfile()
                    or member.issym()
                    or member.islnk()
                    or member.size != int(record["size"])
                ):
                    raise AdminRefusal("AWA_ARCHIVE_MEMBER_REFUSED")
                source = handle.extractfile(member)
                if source is None:
                    raise AdminRefusal("AWA_ARCHIVE_MEMBER_REFUSED")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                with target.open("xb") as output:
                    remaining = member.size
                    digest = hashlib.sha256()
                    while remaining:
                        chunk = source.read(min(remaining, 65_536))
                        if not chunk:
                            raise AdminRefusal("AWA_ARCHIVE_TRUNCATED")
                        output.write(chunk)
                        digest.update(chunk)
                        remaining -= len(chunk)
                    if source.read(1):
                        raise AdminRefusal("AWA_ARCHIVE_OVERFLOW")
                    output.flush()
                    os.fsync(output.fileno())
                if digest.hexdigest() != record["sha256"]:
                    raise AdminRefusal("AWA_ARCHIVE_HASH_REFUSED")
                target.chmod(int(record["mode"], 8))
                os.chown(target, owner_uid, owner_gid)
                observed.add(name)
        if observed != set(expected):
            raise AdminRefusal("AWA_ARCHIVE_INVENTORY_REFUSED")
        for directory, dirnames, filenames in os.walk(
            destination, topdown=False, followlinks=False
        ):
            path = Path(directory)
            for name in (*dirnames, *filenames):
                if (path / name).is_symlink():
                    raise AdminRefusal("AWA_ARCHIVE_LINK_REFUSED")
            path.chmod(0o755)
            os.chown(path, owner_uid, owner_gid)
            descriptor = os.open(
                path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return tuple(
            sorted(observed, key=lambda value: value.encode("utf-8"))
        )
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _sync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_root_directory(path: Path, *, mode: int = 0o755) -> None:
    if path.exists():
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            raise AdminRefusal("AWA_ROOT_DIRECTORY_REFUSED")
        return
    path.mkdir(mode=mode)
    os.chown(path, 0, 0)
    path.chmod(mode)
    _sync_directory(path.parent)


def _root_file(path: Path, *, limit: int = 1_048_576) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != 0
            or before.st_gid != 0
            or stat.S_IMODE(before.st_mode) != 0o444
            or before.st_nlink != 1
            or not 2 <= before.st_size <= limit
        ):
            raise AdminRefusal("AWA_ROOT_FILE_REFUSED")
        raw = bytearray()
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                raise AdminRefusal("AWA_ROOT_FILE_TRUNCATED")
            raw.extend(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_gid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise AdminRefusal("AWA_ROOT_FILE_CHANGED")
        return bytes(raw)
    finally:
        os.close(descriptor)


def parse_current(raw: bytes) -> dict:
    value = _parse_canonical(raw)
    if (
        not isinstance(value, dict)
        or set(value) != CURRENT_FIELDS
        or value.get("schema") != "awa-private-runtime-current/v1"
    ):
        raise AdminRefusal("AWA_CURRENT_SCHEMA_REFUSED")
    body = dict(value)
    claimed = body.pop("current_digest")
    if claimed != _digest("awa-private-runtime-current/v1", body):
        raise AdminRefusal("AWA_CURRENT_DIGEST_REFUSED")
    return value


def _atomic_root_file(path: Path, raw: bytes, *, replace: bool) -> None:
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise AdminRefusal("AWA_ROOT_WRITE_FAILED")
            offset += written
        os.fchmod(descriptor, 0o444)
        os.fchown(descriptor, 0, 0)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if not replace and path.exists():
            raise AdminRefusal("AWA_NO_REPLACE_REFUSED")
        os.replace(temporary, path)
        rebound = _root_file(path, limit=max(1_048_576, len(raw)))
        if rebound != raw:
            raise AdminRefusal("AWA_ROOT_REBIND_REFUSED")
        _sync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _paths_digest(paths: tuple[str, ...]) -> str:
    framed = b"".join(
        path.encode("utf-8") + b"\n"
        for path in sorted(set(paths), key=lambda value: value.encode())
    )
    return hashlib.sha256(
        b"awa-registration-admin-paths/v1\0" + framed
    ).hexdigest()


def _success_receipt(
    *,
    request: dict,
    pre: dict | None,
    post_manifest: str | None,
    signature_sha256: str | None,
    installed: tuple[str, ...],
    removed: tuple[str, ...],
    started_wall_ns: str,
    completed_wall_ns: str,
) -> dict:
    qualification = request["mode"] == "QUALIFY"
    body = {
        "schema": "awa-registration-admin-audit-receipt/v1",
        "mode": request["mode"],
        "receipt_origin": "ROOT_ADMIN",
        "request_id": request["request_id"],
        "operation": request["operation"],
        "requested_uid": request["requested_uid"],
        "target_root": request["target_root"],
        "packet_root_digest": request["packet_root_digest"],
        "qualification_context_digest": request[
            "qualification_context_digest"
        ],
        "qualification_allowed_signers_digest": request[
            "qualification_allowed_signers_digest"
        ],
        "pre_epoch": pre["epoch"] if pre is not None else "0",
        "post_epoch": request["target_epoch"],
        "pre_current_digest": (
            pre["current_digest"] if pre is not None else None
        ),
        "target_release_envelope_digest": request[
            "target_release_envelope_digest"
        ],
        "target_manifest_sha256": request["target_manifest_sha256"],
        "target_epoch": request["target_epoch"],
        "previous_manifest_sha256": (
            pre["active_manifest_sha256"] if pre is not None else None
        ),
        "current_manifest_sha256": post_manifest,
        "new_manifest_sha256": (
            request["target_manifest_sha256"]
            if request["operation"] in {"INSTALL", "UPDATE"}
            else None
        ),
        "q1_envelope_digest": request["q1_envelope_digest"],
        "q1_manifest_sha256": request["q1_manifest_sha256"],
        "q2_envelope_digest": request["q2_envelope_digest"],
        "q2_manifest_sha256": request["q2_manifest_sha256"],
        "envelope_sha256": hashlib.sha256(
            _canonical(request) + b"\n"
        ).hexdigest(),
        "owner_signature_sha256": (
            None if qualification else signature_sha256
        ),
        "synthetic_signature_sha256": (
            signature_sha256 if qualification else None
        ),
        "state_machine_terminal": "SUCCESS_COMMITTED",
        "outcome": "SUCCESS",
        "reason_code": "OK",
        "predecessor_audit_digest": (
            pre["installer_audit_digest"] if pre is not None else None
        ),
        "root_receipt_link_digest": request["request_digest"],
        "partial_stage_state": "NONE",
        "cleanup_digest": _digest(
            "awa-registration-admin-cleanup/v1",
            {"removed": list(removed), "residual": [], "failures": []},
        ),
        "installed_paths_hash": _paths_digest(installed),
        "removed_paths_hash": _paths_digest(removed),
        "started_wall_ns": started_wall_ns,
        "completed_wall_ns": completed_wall_ns,
    }
    value = dict(body)
    value["receipt_digest"] = _digest(
        "awa-registration-admin-audit-receipt/v1", body
    )
    return value


def capture_request_assets(
    requested_uid: str, request_id: str
) -> tuple[dict[str, int], dict[str, bytes], dict]:
    uid = _uid(requested_uid)
    paths = derive_request_asset_paths(requested_uid, request_id)
    limits = {
        "envelope": (2, 1_048_576),
        "archive": (1, 1 << 30),
        "manifest": (2, 64 << 20),
        "signature": (1, 1 << 20),
    }
    descriptors: dict[str, int] = {}
    content: dict[str, bytes] = {}
    try:
        for role in ("envelope", "archive", "manifest", "signature"):
            descriptor, raw = _read_retained(
                getattr(paths, role),
                requested_uid=uid,
                minimum=limits[role][0],
                maximum=limits[role][1],
            )
            descriptors[role] = descriptor
            content[role] = raw
        (
            request,
            _release,
            _signers,
            _namespace,
            _closure,
        ) = parse_privileged_context(content["envelope"])
        if (
            request["requested_uid"] != requested_uid
            or request["request_id"] != request_id
        ):
            raise AdminRefusal("AWA_REQUEST_CONTEXT_REFUSED")
        return descriptors, content, request
    except BaseException:
        for descriptor in descriptors.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _close_all(descriptors: dict[str, int]) -> None:
    primary: OSError | None = None
    for role in sorted(descriptors, reverse=True):
        try:
            os.close(descriptors[role])
        except OSError as exc:
            if primary is None:
                primary = exc
    if primary is not None:
        raise primary


def _install_closure(
    target: Path,
    closure: dict[str, bytes],
    *,
    replace: bool,
    roles: set[str] | None = None,
) -> tuple[str, ...]:
    installed: list[str] = []
    ordered = [
        role for role in CLOSURE_ROLES if role != "ROOT_ADMIN"
    ] + ["ROOT_ADMIN"]
    for role in ordered:
        if roles is not None and role not in roles:
            continue
        content = closure.get(role)
        if content is None:
            continue
        relative, mode = CLOSURE_ROLES[role]
        path = target / relative
        _ensure_root_directory(path.parent)
        if path.exists() and not replace:
            if _root_file(path, limit=8 * 1024 * 1024) != content:
                raise AdminRefusal("AWA_CLOSURE_DRIFT_REFUSED")
            continue
        _atomic_root_file(path, content, replace=path.exists())
        path.chmod(int(mode, 8))
        installed.append(str(path))
    return tuple(installed)


def execute_native_lifecycle(
    *,
    operation: str,
    content: dict[str, bytes],
) -> dict:
    (
        request,
        release,
        allowed_signers,
        namespace,
        closure,
    ) = parse_privileged_context(content["envelope"])
    if request["operation"] != operation or operation == "QUALIFY":
        raise AdminRefusal("AWA_OPERATION_CONTEXT_REFUSED")
    now = time.time_ns()
    if now < int(request["created_wall_ns"]) or now > int(
        request["expires_wall_ns"]
    ):
        raise AdminRefusal("AWA_REQUEST_EXPIRED")
    target = Path(request["target_root"])
    current_path = target / "runtime/current.v1"
    audit_path = target / "runtime/audit" / f"{request['request_id']}.json"
    if audit_path.exists():
        receipt = _parse_canonical(_root_file(audit_path))
        if (
            not isinstance(receipt, dict)
            or receipt.get("request_id") != request["request_id"]
            or receipt.get("root_receipt_link_digest")
            != request["request_digest"]
        ):
            raise AdminRefusal("AWA_NONCE_REPLAY")
        return receipt
    pre: dict | None = None
    if current_path.exists():
        pre = parse_current(_root_file(current_path))
    if operation == "INSTALL":
        if pre is not None or request["target_epoch"] != "1":
            raise AdminRefusal("AWA_STATE_INVALID")
    else:
        if (
            pre is None
            or request["pre_current_digest"] != pre["current_digest"]
            or int(request["target_epoch"]) != int(pre["epoch"]) + 1
        ):
            raise AdminRefusal("AWA_CONTEXT_MISMATCH")
    if operation == "ROLLBACK" and (
        pre["previous_manifest_sha256"] is None
        or request["target_manifest_sha256"]
        != pre["previous_manifest_sha256"]
    ):
        raise AdminRefusal("AWA_ROLLBACK_STATE_REFUSED")
    signature_sha256: str | None = None
    records: tuple[dict, ...] = ()
    if operation != "REMOVE":
        assert release is not None
        signature_sha256 = verify_signature(
            _canonical(release) + b"\n",
            content["signature"],
            allowed_signers=allowed_signers,
            namespace=namespace,
        )
        _manifest, records = validate_manifest_and_archive(
            content["manifest"],
            content["archive"],
            request=request,
            release=release,
        )
    started = str(time.time_ns())
    base_parent = target.parent
    if (
        str(target) == PRODUCTION_ROOT
        and base_parent != Path("/Library/Application Support")
    ):
        raise AdminRefusal("AWA_TARGET_PARENT_REFUSED")
    if not base_parent.exists() or base_parent.is_symlink():
        raise AdminRefusal("AWA_TARGET_PARENT_REFUSED")
    if not target.exists():
        _ensure_root_directory(target)
    for directory in (
        target / "runtime",
        target / "runtime/audit",
        target / "runtime/locks",
        target / "runtime/versions",
        target / "bin",
        target / "bootstrap",
        target / "bootstrap/v1",
    ):
        _ensure_root_directory(directory)
    for path in (target / "runtime/versions").iterdir():
        if (
            path.is_symlink()
            or not path.is_dir()
            or HEX64.fullmatch(path.name) is None
        ):
            raise AdminRefusal("AWA_VERSION_RESIDUE_REFUSED")
    admin_lock_path = target / "runtime/admin.lock"
    lock_fd = os.open(
        admin_lock_path,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
        0o444,
    )
    installed: list[str] = []
    removed: list[str] = []
    version_lock_fds: list[int] = []
    try:
        os.fchmod(lock_fd, 0o444)
        os.fchown(lock_fd, 0, 0)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AdminRefusal("AWA_LOCKED") from exc
        lock_digests = {
            digest
            for digest in (
                pre["active_manifest_sha256"] if pre is not None else None,
                request["target_manifest_sha256"],
            )
            if digest is not None
        }
        if request["operation"] in {"UPDATE", "ROLLBACK", "REMOVE"}:
            lock_digests.update(
                path.name
                for path in (target / "runtime/versions").iterdir()
                if path.is_dir() and HEX64.fullmatch(path.name) is not None
            )
        for digest in sorted(lock_digests):
            path = target / "runtime/locks" / f"{digest}.lock"
            descriptor = os.open(
                path,
                os.O_CREAT
                | os.O_RDWR
                | getattr(os, "O_NOFOLLOW", 0),
                0o444,
            )
            os.fchmod(descriptor, 0o444)
            os.fchown(descriptor, 0, 0)
            try:
                fcntl.flock(
                    descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                )
            except BlockingIOError as exc:
                os.close(descriptor)
                raise AdminRefusal("AWA_LOCKED") from exc
            version_lock_fds.append(descriptor)
        _sync_directory(target / "runtime/locks")
        post_manifest: str | None
        previous_manifest: str | None
        target_manifest = request["target_manifest_sha256"]
        versions = target / "runtime/versions"
        if operation in {"INSTALL", "UPDATE"}:
            stage = target / "runtime" / f".stage-{request['request_id']}"
            extract_validated_archive(
                content["archive"],
                records,
                stage,
                owner_uid=0,
                owner_gid=0,
            )
            if request["mode"] == "PRODUCTION":
                assert release is not None and target_manifest is not None
                prefix = f"awa-private-runtime-{target_manifest}"
                _atomic_root_file(
                    stage / f"{prefix}.manifest.json",
                    content["manifest"],
                    replace=False,
                )
                _atomic_root_file(
                    stage / f"{prefix}.release-envelope.json",
                    _canonical(release) + b"\n",
                    replace=False,
                )
                _atomic_root_file(
                    stage / f"{prefix}.release-envelope.sig",
                    content["signature"],
                    replace=False,
                )
            destination = versions / str(target_manifest)
            if destination.exists():
                raise AdminRefusal("AWA_VERSION_EXISTS")
            os.rename(stage, destination)
            _sync_directory(versions)
            installed.append(str(destination))
            post_manifest = str(target_manifest)
            previous_manifest = (
                pre["active_manifest_sha256"] if pre is not None else None
            )
        elif operation == "ROLLBACK":
            destination = versions / str(target_manifest)
            if (
                not destination.is_dir()
                or destination.is_symlink()
            ):
                raise AdminRefusal("AWA_ROLLBACK_TARGET_REFUSED")
            post_manifest = str(target_manifest)
            previous_manifest = pre["active_manifest_sha256"]
        else:
            post_manifest = None
            previous_manifest = None
        retire: tuple[Path, ...] = ()
        if operation in {"UPDATE", "ROLLBACK"}:
            keep = {post_manifest, previous_manifest}
            retire = tuple(
                path
                for path in sorted(
                    versions.iterdir(),
                    key=lambda item: item.name.encode("utf-8"),
                )
                if path.name not in keep
            )
            removed.extend(str(path) for path in retire)
        if operation != "REMOVE":
            installed.extend(
                _install_closure(
                    target,
                    closure,
                    replace=operation != "INSTALL",
                    roles=set(closure) - {"ROOT_ADMIN"},
                )
            )
            installed.append(
                str(target / CLOSURE_ROLES["ROOT_ADMIN"][0])
            )
        completed = str(time.time_ns())
        receipt = _success_receipt(
            request=request,
            pre=pre,
            post_manifest=post_manifest,
            signature_sha256=signature_sha256,
            installed=tuple(installed),
            removed=tuple(removed),
            started_wall_ns=started,
            completed_wall_ns=completed,
        )
        if operation == "REMOVE":
            for child in sorted(
                versions.iterdir(),
                key=lambda path: path.name.encode("utf-8"),
            ):
                if child.is_symlink() or not child.is_dir():
                    raise AdminRefusal("AWA_VERSION_RESIDUE_REFUSED")
                lock_path = target / "runtime/locks" / f"{child.name}.lock"
                version_lock = os.open(
                    lock_path,
                    os.O_CREAT
                    | os.O_RDWR
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o444,
                )
                try:
                    fcntl.flock(
                        version_lock, fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                    shutil.rmtree(child)
                    removed.append(str(child))
                finally:
                    os.close(version_lock)
            if current_path.exists():
                current_path.unlink()
                _sync_directory(current_path.parent)
            receipt = _success_receipt(
                request=request,
                pre=pre,
                post_manifest=None,
                signature_sha256=None,
                installed=(),
                removed=tuple(removed),
                started_wall_ns=started,
                completed_wall_ns=str(time.time_ns()),
            )
        else:
            assert release is not None and post_manifest is not None
            current_body = {
                "schema": "awa-private-runtime-current/v1",
                "epoch": request["target_epoch"],
                "active_manifest_sha256": post_manifest,
                "previous_manifest_sha256": previous_manifest,
                "active_release_envelope_digest": request[
                    "target_release_envelope_digest"
                ],
                "installed_at_wall_ns": completed,
                "installer_audit_digest": receipt["receipt_digest"],
                "predecessor_current_digest": (
                    pre["current_digest"] if pre is not None else "0" * 64
                ),
            }
            current = dict(current_body)
            current["current_digest"] = _digest(
                "awa-private-runtime-current/v1", current_body
            )
            _atomic_root_file(
                current_path,
                _canonical(current) + b"\n",
                replace=current_path.exists(),
            )
            for path in retire:
                if path.is_symlink() or not path.is_dir():
                    raise AdminRefusal("AWA_VERSION_RESIDUE_REFUSED")
                shutil.rmtree(path)
            if retire:
                _sync_directory(versions)
            _install_closure(
                target,
                closure,
                replace=operation != "INSTALL",
                roles={"ROOT_ADMIN"},
            )
        _atomic_root_file(
            audit_path,
            _canonical(receipt) + b"\n",
            replace=False,
        )
        if operation == "REMOVE":
            for relative in (
                "bin/awa-registration",
                "bootstrap/v1/child.py",
                "bootstrap/v1/bootstrap.py",
                "bin/awa-private-runtime-admin",
            ):
                path = target / relative
                if path.exists():
                    path.unlink()
                    removed.append(str(path))
            shutil.rmtree(target)
            _sync_directory(target.parent)
        return receipt
    finally:
        for descriptor in reversed(version_lock_fds):
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def validate_dispatch_arguments(argv: list[str]) -> tuple[str, str, str]:
    if len(argv) == 2:
        operation = "INSTALL"
        requested_uid, request_id = argv
    elif len(argv) == 3:
        operation, requested_uid, request_id = argv
    else:
        raise AdminRefusal("AWA_ARGV_REFUSED")
    if operation not in OPERATIONS:
        raise AdminRefusal("AWA_OPERATION_REFUSED")
    _uid(requested_uid)
    _request_id(request_id)
    return operation, requested_uid, request_id


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = list(sys.argv[1:] if argv is None else argv)
        initial_transport = len(arguments) == 2
        operation, requested_uid, request_id = validate_dispatch_arguments(
            arguments
        )
        if os.geteuid() != 0:
            raise AdminRefusal("AWA_ROOT_REQUIRED")
        descriptors, _content, request = capture_request_assets(
            requested_uid, request_id
        )
        try:
            if request["operation"] != operation:
                raise AdminRefusal("AWA_OPERATION_CONTEXT_REFUSED")
            # Mutation is delegated only after all retained-byte, signature,
            # manifest, epoch, and packet validators in the installed closure
            # have accepted. A source checkout is never an execution backend.
            installed = os.path.realpath(__file__).startswith(
                PRODUCTION_ROOT + "/"
            ) or os.path.realpath(__file__).startswith(
                request["target_root"] + "/"
            )
            if not installed and not (
                initial_transport and operation == "INSTALL"
            ):
                raise AdminRefusal("AWA_INSTALLED_CLOSURE_REQUIRED")
            receipt = execute_native_lifecycle(
                operation=operation,
                content=_content,
            )
            print((_canonical(receipt) + b"\n").decode("utf-8"), end="")
            return 0
        finally:
            _close_all(descriptors)
    except (AdminRefusal, OSError, ValueError) as exc:
        print(f"awa-private-runtime-admin: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
