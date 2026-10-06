"""Body C closed inventory, hook projection, and DIRECT receipt authority."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import unicodedata
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable, Iterable, Mapping

from . import registration_jcs
from .registration_admission import DeploymentReceipt


DIRECT_RECEIPT_FIELDS = (
    "schema",
    "owner_mode",
    "deployment_scope",
    "candidate_digest",
    "schema_hash",
    "profile_hash",
    "runtime_capability_hash",
    "writer_binary_hash",
    "writer_capability_hash",
    "tool_inventory_hash",
    "hook_projection_hash",
    "hook_matcher_mode",
    "hook_matcher_hash",
    "installed_file_hash",
    "projection_file_generation",
    "protocol_generation",
    "wrapper_runtime_hash",
    "installer_identity_hash",
    "installer_capability_hash",
    "owner_gate_digest",
    "canonical_root_hash",
    "member_id",
)
_HISTORICAL_DIRECT_RECEIPT_FIELDS = DIRECT_RECEIPT_FIELDS
CANDIDATE_FIELDS = (
    "schema_hash",
    "profile_hash",
    "runtime_capability_hash",
    "writer_binary_hash",
    "writer_capability_hash",
    "tool_inventory_hash",
    "hook_projection_hash",
    "hook_matcher_mode",
    "hook_matcher_hash",
    "projection_file_generation",
    "protocol_generation",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_SCHEMA_IDENTIFIER = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"
)
_REGEX_META = frozenset("*+?[](){}|\\^$")


class HookUnsupported(ValueError):
    """The installed matcher cannot prove all required discriminator receipt."""


@dataclass(frozen=True)
class InterpreterSelection:
    schema: str
    scope: str
    repository: str
    authorized_by: str
    source_revision: str
    candidate_digest: str
    harness_root_hash: str | None
    installation_root_hash: str | None
    interpreter_path: str
    authorization_nonce: str
    authorized: bool

    FIELDS = (
        "schema",
        "scope",
        "repository",
        "authorized_by",
        "source_revision",
        "candidate_digest",
        "harness_root_hash",
        "installation_root_hash",
        "interpreter_path",
        "authorization_nonce",
        "authorized",
    )

    def __post_init__(self) -> None:
        if (
            self.schema
            != "awa-registration-interpreter-selection/v1"
            or self.repository != "KleinPerkins/awa"
            or self.authorized_by != "KleinPerkins"
            or self.authorized is not True
            or not isinstance(self.source_revision, str)
            or re.fullmatch(r"[0-9a-f]{40}", self.source_revision) is None
        ):
            raise ValueError("interpreter selection identity is invalid")
        _require_hash(self.candidate_digest, "candidate_digest")
        _require_hash(self.authorization_nonce, "authorization_nonce")
        if self.scope == "R0":
            _require_hash(self.harness_root_hash, "harness_root_hash")
            if self.installation_root_hash is not None:
                raise ValueError("R0 selection has installation root")
        elif self.scope == "INSTALL":
            _require_hash(
                self.installation_root_hash,
                "installation_root_hash",
            )
            if self.harness_root_hash is not None:
                raise ValueError("INSTALL selection has harness root")
        elif self.scope == "RELEASE":
            if (
                self.harness_root_hash is not None
                or self.installation_root_hash is not None
            ):
                raise ValueError("RELEASE selection roots must be null")
        else:
            raise ValueError("interpreter selection scope is invalid")
        validate_interpreter_path(self.interpreter_path)

    def to_mapping(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.FIELDS}

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-interpreter-selection/v1",
            self.to_mapping(),
        )

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, object]
    ) -> "InterpreterSelection":
        if not isinstance(value, Mapping) or set(value) != set(cls.FIELDS):
            raise ValueError("interpreter selection fields are not exact")
        return cls(**{field: value[field] for field in cls.FIELDS})


def validate_interpreter_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != unicodedata.normalize("NFC", value)
        or not 1 <= len(value.encode("utf-8", "strict")) <= 4096
        or not value.startswith("/")
        or "\\" in value
        or "\0" in value
        or any(ord(character) < 0x20 for character in value)
        or os.path.normpath(value) != value
        or any(part in {"", ".", ".."} for part in value.split("/")[1:])
    ):
        raise ValueError("interpreter path is invalid")
    return value


def interpreter_path_hash(value: object) -> str:
    path = validate_interpreter_path(value)
    return hashlib.sha256(
        b"awa-registration-interpreter-path/v1\0"
        + path.encode("utf-8")
    ).hexdigest()


_ANCESTRY_FIELDS = (
    "ordinal",
    "component_hash",
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_gid",
    "st_nlink",
    "object_type",
)


def interpreter_ancestry_hash(
    records: Iterable[Mapping[str, object]],
) -> str:
    values = tuple(dict(record) for record in records)
    if not values:
        raise ValueError("interpreter ancestry cannot be empty")
    for ordinal, record in enumerate(values):
        if (
            set(record) != set(_ANCESTRY_FIELDS)
            or record["ordinal"] != str(ordinal)
            or record["object_type"] != "DIRECTORY"
        ):
            raise ValueError("interpreter ancestry record is invalid")
        _require_hash(record["component_hash"], "component_hash")
        for field in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
        ):
            _require_decimal(record[field], field)
        mode = int(record["st_mode"])
        if (
            not stat.S_ISDIR(mode)
            or mode & 0o022
            or int(record["st_nlink"]) < 1
        ):
            raise ValueError("interpreter ancestor is unsafe")
    return _domain_hash(
        "awa-registration-interpreter-ancestry/v1",
        {
            "schema": "awa-registration-interpreter-ancestry/v1",
            "records": values,
        },
    )


def _domain_hash(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii")
        + b"\0"
        + registration_jcs.canonical_bytes(value)
    ).hexdigest()


def _regular_bytes(path: Path, *, limit: int = 8 * 1024 * 1024) -> bytes:
    path = Path(path)
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_size < 0
        or metadata.st_size > limit
    ):
        raise ValueError("installed artifact identity is unsupported")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        rebound = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (
            rebound.st_dev,
            rebound.st_ino,
        ):
            raise ValueError("installed artifact changed while opening")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(value) > limit:
        raise ValueError("installed artifact exceeds bound")
    return value


def installed_file_hash(path: Path) -> str:
    return hashlib.sha256(
        b"awa-registration-installed-file/v1\0"
        + _regular_bytes(Path(path))
    ).hexdigest()


def wrapper_runtime_hash(
    wrapper: Path, runtime_files: Iterable[Path]
) -> str:
    paths = (Path(wrapper),) + tuple(Path(path) for path in runtime_files)
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate wrapper/runtime artifact")
    records = [
        {
            "ordinal": str(ordinal),
            "role": "wrapper" if ordinal == 0 else "runtime",
            "sha256": installed_file_hash(path),
        }
        for ordinal, path in enumerate(paths)
    ]
    return _domain_hash(
        "awa-registration-wrapper-runtime/v1", records
    )


def _require_hash(value: object, field: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase 64-hex")


def _require_decimal(value: object, field: str) -> None:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise ValueError(f"{field} must be an unsigned decimal string")


def candidate_digest(value: Mapping[str, object]) -> str:
    if set(value) != set(CANDIDATE_FIELDS):
        raise ValueError("candidate digest fields are not exact")
    candidate = {field: value[field] for field in CANDIDATE_FIELDS}
    for field in (
        "schema_hash",
        "profile_hash",
        "runtime_capability_hash",
        "writer_binary_hash",
        "writer_capability_hash",
        "tool_inventory_hash",
        "hook_projection_hash",
        "hook_matcher_hash",
    ):
        _require_hash(candidate[field], field)
    if candidate["hook_matcher_mode"] not in {
        "CATCH_ALL",
        "ENUMERATED",
    }:
        raise ValueError("unknown hook matcher mode")
    _require_decimal(
        candidate["projection_file_generation"],
        "projection_file_generation",
    )
    _require_decimal(
        candidate["protocol_generation"], "protocol_generation"
    )
    return _domain_hash("awa-registration-candidate/v1", candidate)


@dataclass(frozen=True)
class DirectReceipt:
    schema: str
    owner_mode: str
    deployment_scope: str
    candidate_digest: str
    schema_hash: str
    profile_hash: str
    runtime_capability_hash: str
    writer_binary_hash: str
    writer_capability_hash: str
    tool_inventory_hash: str
    hook_projection_hash: str
    hook_matcher_mode: str
    hook_matcher_hash: str
    installed_file_hash: str
    projection_file_generation: str
    protocol_generation: str
    wrapper_runtime_hash: str
    installer_identity_hash: str
    installer_capability_hash: str
    owner_gate_digest: str
    canonical_root_hash: str | None
    member_id: str | None

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-direct-receipt/v2":
            raise ValueError("unknown DIRECT receipt schema")
        if self.owner_mode != "DIRECT":
            raise ValueError("external projection ownership is unsupported")
        if self.hook_matcher_mode not in {"CATCH_ALL", "ENUMERATED"}:
            raise ValueError("unknown hook matcher mode")
        for field in (
            "candidate_digest",
            "schema_hash",
            "profile_hash",
            "runtime_capability_hash",
            "writer_binary_hash",
            "writer_capability_hash",
            "tool_inventory_hash",
            "hook_projection_hash",
            "hook_matcher_hash",
            "installed_file_hash",
            "wrapper_runtime_hash",
            "installer_identity_hash",
            "installer_capability_hash",
            "owner_gate_digest",
        ):
            _require_hash(getattr(self, field), field)
        for field in (
            "projection_file_generation",
            "protocol_generation",
        ):
            _require_decimal(getattr(self, field), field)
        if self.deployment_scope == "R1_CANARY":
            _require_hash(
                self.canonical_root_hash, "canonical_root_hash"
            )
            _require_hash(self.member_id, "member_id")
        elif self.deployment_scope in {"R0_THROWAWAY", "R2_DIRECT"}:
            if (
                self.canonical_root_hash is not None
                or self.member_id is not None
            ):
                raise ValueError(
                    f"{self.deployment_scope} requires null root/member"
                )
        else:
            raise ValueError("unknown deployment scope")
        expected = candidate_digest(
            {field: getattr(self, field) for field in CANDIDATE_FIELDS}
        )
        if self.candidate_digest != expected:
            raise ValueError("candidate digest mismatch")

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-direct-receipt/v2", self.to_mapping()
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in _HISTORICAL_DIRECT_RECEIPT_FIELDS
        }

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "DirectReceipt":
        if not isinstance(value, Mapping) or set(value) != set(
            _HISTORICAL_DIRECT_RECEIPT_FIELDS
        ):
            raise ValueError("DIRECT receipt fields are not exact")
        return cls(
            **{
                field: value[field]
                for field in _HISTORICAL_DIRECT_RECEIPT_FIELDS
            }
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "DirectReceipt":
        if (
            not isinstance(raw, bytes)
            or not 1 <= len(raw) <= 65_536
            or not raw.endswith(b"\n")
            or raw.endswith(b"\n\n")
        ):
            raise ValueError("DIRECT receipt bytes are malformed")

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate DIRECT receipt field")
                result[key] = value
            return result

        try:
            value = json.loads(
                raw[:-1].decode("utf-8", "strict"),
                object_pairs_hook=pairs,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(value)
                ),
            )
        except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("DIRECT receipt is not strict JSON") from exc
        receipt = cls.from_mapping(value)
        if receipt.to_bytes() != raw:
            raise ValueError("DIRECT receipt is not canonical")
        return receipt

    def deployment_receipt(self) -> DeploymentReceipt:
        return DeploymentReceipt(
            owner_mode=self.owner_mode,
            deployment_scope=self.deployment_scope,
            candidate_digest=self.candidate_digest,
            canonical_root_hash=self.canonical_root_hash,
            member_id=self.member_id,
            owner_gate_digest=self.owner_gate_digest,
        )

    @classmethod
    def vector_r1(cls) -> "DirectReceipt":
        values = {
            field: "aa" * 32
            for field in CANDIDATE_FIELDS
            if field
            not in {
                "hook_matcher_mode",
                "projection_file_generation",
                "protocol_generation",
            }
        }
        values.update(
            {
                "hook_matcher_mode": "ENUMERATED",
                "projection_file_generation": "1",
                "protocol_generation": "1",
            }
        )
        digest = candidate_digest(values)
        return cls(
            schema="awa-registration-direct-receipt/v2",
            owner_mode="DIRECT",
            deployment_scope="R1_CANARY",
            candidate_digest=digest,
            **values,
            installed_file_hash="bb" * 32,
            wrapper_runtime_hash="bb" * 32,
            installer_identity_hash="aa" * 32,
            installer_capability_hash="aa" * 32,
            owner_gate_digest="cc" * 32,
            canonical_root_hash="dd" * 32,
            member_id="ee" * 32,
        )


@dataclass(frozen=True)
class OwnerGate:
    schema: str
    repository: str
    authorized_by: str
    deployment_scope: str
    candidate_digest: str
    canonical_root_hash: str | None
    member_id: str | None
    authorized: bool

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-owner-gate/v1"
            or self.repository != "KleinPerkins/awa"
            or self.authorized_by != "KleinPerkins"
            or self.authorized is not True
        ):
            raise ValueError("owner gate authority is invalid")
        _require_hash(self.candidate_digest, "candidate_digest")
        if self.deployment_scope == "R1_CANARY":
            _require_hash(
                self.canonical_root_hash, "canonical_root_hash"
            )
            _require_hash(self.member_id, "member_id")
        elif self.deployment_scope in {"R0_THROWAWAY", "R2_DIRECT"}:
            if (
                self.canonical_root_hash is not None
                or self.member_id is not None
            ):
                raise ValueError("broad owner gate scope must be null")
        else:
            raise ValueError("owner gate scope is unknown")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "repository": self.repository,
            "authorized_by": self.authorized_by,
            "deployment_scope": self.deployment_scope,
            "candidate_digest": self.candidate_digest,
            "canonical_root_hash": self.canonical_root_hash,
            "member_id": self.member_id,
            "authorized": self.authorized,
        }

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> "OwnerGate":
        if (
            not isinstance(raw, bytes)
            or not raw.endswith(b"\n")
            or raw.endswith(b"\n\n")
        ):
            raise ValueError("owner gate bytes are malformed")
        expected = {
            "schema",
            "repository",
            "authorized_by",
            "deployment_scope",
            "candidate_digest",
            "canonical_root_hash",
            "member_id",
            "authorized",
        }
        try:
            value = registration_jcs.parse_canonical(raw[:-1])
        except (ValueError, registration_jcs.JcsError) as exc:
            raise ValueError("owner gate is not canonical JCS") from exc
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("owner gate fields are not exact")
        gate = cls(**value)
        if gate.to_bytes() != raw:
            raise ValueError("owner gate bytes are not canonical")
        return gate


def verified_owner_gate_digest(
    gate_bytes: bytes,
    detached_signature: bytes,
    *,
    verifier: Callable[[bytes, bytes], bool],
) -> str:
    OwnerGate.from_bytes(gate_bytes)
    if (
        not isinstance(detached_signature, bytes)
        or not detached_signature
        or not callable(verifier)
        or verifier(gate_bytes, detached_signature) is not True
    ):
        raise ValueError("detached owner signature did not verify")
    # The detached signature is deliberately outside the JCS receipt and
    # runtime secret surface. Valid signatures over identical gate bytes
    # therefore produce one stable gate digest.
    return hashlib.sha256(
        b"awa-registration-owner-gate/v1\0" + gate_bytes[:-1]
    ).hexdigest()


def verify_receipt_owner_gate(
    receipt: DirectReceipt,
    gate_bytes: bytes,
    detached_signature: bytes,
    *,
    verifier: Callable[[bytes, bytes], bool],
) -> None:
    gate = OwnerGate.from_bytes(gate_bytes)
    digest = verified_owner_gate_digest(
        gate_bytes, detached_signature, verifier=verifier
    )
    if (
        receipt.owner_gate_digest != digest
        or receipt.deployment_scope != gate.deployment_scope
        or receipt.candidate_digest != gate.candidate_digest
        or receipt.canonical_root_hash != gate.canonical_root_hash
        or receipt.member_id != gate.member_id
    ):
        raise ValueError("DIRECT receipt is not bound to owner gate")


@dataclass(frozen=True)
class InventoryEntry:
    event: str
    server_or_empty: str
    discriminator: str
    role: str
    serializer_schema: str

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, str):
                raise ValueError(f"{field.name} must be a string")
        if (
            _IDENTIFIER.fullmatch(self.event) is None
            or (
                self.server_or_empty
                and _IDENTIFIER.fullmatch(self.server_or_empty) is None
            )
            or _IDENTIFIER.fullmatch(self.discriminator) is None
            or _SCHEMA_IDENTIFIER.fullmatch(self.serializer_schema) is None
            or self.role not in {"ordinary", "task_launch"}
            or any(char in _REGEX_META for char in self.discriminator)
        ):
            raise ValueError("invalid inventory tuple")

    def mapping(self) -> dict[str, str]:
        return {
            "event": self.event,
            "server_or_empty": self.server_or_empty,
            "discriminator": self.discriminator,
            "role": self.role,
            "serializer_schema": self.serializer_schema,
        }


def _sorted_unique_mappings(
    values: Iterable[object], mapper
) -> list[dict[str, object]]:
    mappings = [mapper(value) for value in values]
    encoded = [
        (registration_jcs.canonical_bytes(value), value)
        for value in mappings
    ]
    encoded.sort(key=lambda item: item[0])
    if any(
        encoded[index - 1][0] == encoded[index][0]
        for index in range(1, len(encoded))
    ):
        raise ValueError("duplicate closed tuple")
    return [value for _, value in encoded]


def tool_inventory_hash(entries: Iterable[InventoryEntry]) -> str:
    ordered = _sorted_unique_mappings(entries, lambda entry: entry.mapping())
    if not ordered:
        raise ValueError("tool inventory cannot be empty")
    roles = {entry["role"] for entry in ordered}
    if roles != {"ordinary", "task_launch"}:
        raise ValueError("inventory must include ordinary and Task roles")
    return _domain_hash("awa-registration-tool-inventory/v1", ordered)


@dataclass(frozen=True)
class HookRow:
    event: str
    matcher: str
    command_argv: tuple[str, ...]
    timeout_ms: int
    fail_closed: bool

    def __post_init__(self) -> None:
        if _IDENTIFIER.fullmatch(self.event) is None:
            raise ValueError("invalid hook event")
        if not isinstance(self.matcher, str):
            raise ValueError("hook matcher must be a string")
        if (
            not isinstance(self.command_argv, tuple)
            or not self.command_argv
            or any(
                not isinstance(value, str)
                or not value
                or "\0" in value
                for value in self.command_argv
            )
            or not os.path.isabs(self.command_argv[0])
        ):
            raise ValueError("invalid command argv")
        if type(self.timeout_ms) is not int or self.timeout_ms <= 0:
            raise ValueError("invalid timeout")
        if type(self.fail_closed) is not bool:
            raise ValueError("fail_closed must be boolean")

    def mapping(self) -> dict[str, object]:
        return {
            "event": self.event,
            "matcher": self.matcher,
            "command_argv": list(self.command_argv),
            "timeout_ms": str(self.timeout_ms),
            "fail_closed": self.fail_closed,
        }


def hook_projection_hash(
    rows: Iterable[HookRow],
    *,
    matcher_mode: str,
    matcher_hash: str,
    inventory_hash: str,
    file_generation: str,
    protocol_generation: str,
    wrapper_runtime_hash: str,
) -> str:
    if matcher_mode not in {"CATCH_ALL", "ENUMERATED"}:
        raise ValueError("unknown matcher mode")
    for field, value in (
        ("matcher_hash", matcher_hash),
        ("inventory_hash", inventory_hash),
        ("wrapper_runtime_hash", wrapper_runtime_hash),
    ):
        _require_hash(value, field)
    _require_decimal(file_generation, "file_generation")
    _require_decimal(protocol_generation, "protocol_generation")
    ordered = _sorted_unique_mappings(rows, lambda row: row.mapping())
    if not ordered:
        raise ValueError("hook projection cannot be empty")
    if matcher_mode == "ENUMERATED" and any(
        any(char in _REGEX_META for char in str(row["matcher"]))
        for row in ordered
    ):
        raise ValueError("enumerated matcher contains regex syntax")
    return _domain_hash(
        "awa-registration-hook-projection/v1",
        {
            "rows": ordered,
            "matcher_mode": matcher_mode,
            "matcher_hash": matcher_hash,
            "inventory_hash": inventory_hash,
            "file_generation": file_generation,
            "protocol_generation": protocol_generation,
            "wrapper_runtime_hash": wrapper_runtime_hash,
        },
    )


@dataclass(frozen=True)
class MatcherProof:
    mode: str
    official_contract_hash: str | None
    observed_discriminators: frozenset[str]
    task_launch_receivable: bool


def matcher_proof_hash(proof: MatcherProof) -> str:
    if proof.mode not in {"CATCH_ALL", "ENUMERATED"}:
        raise HookUnsupported("unknown matcher mode")
    if proof.official_contract_hash is not None:
        _require_hash(
            proof.official_contract_hash, "official_contract_hash"
        )
    if (
        not isinstance(proof.observed_discriminators, frozenset)
        or any(
            not isinstance(value, str) or not value
            for value in proof.observed_discriminators
        )
        or type(proof.task_launch_receivable) is not bool
    ):
        raise HookUnsupported("matcher proof is malformed")
    return _domain_hash(
        "awa-registration-hook-matcher/v1",
        {
            "mode": proof.mode,
            "official_contract_hash": proof.official_contract_hash,
            "observed_discriminators": sorted(
                proof.observed_discriminators,
                key=lambda value: value.encode("utf-8"),
            ),
            "task_launch_receivable": proof.task_launch_receivable,
        },
    )


def validate_matcher_proof(
    proof: MatcherProof, inventory: Iterable[InventoryEntry]
) -> None:
    entries = tuple(inventory)
    expected = frozenset(entry.discriminator for entry in entries)
    if not proof.task_launch_receivable or "Task" not in expected:
        raise HookUnsupported("Task launch is not receivable")
    if proof.mode == "ENUMERATED":
        if proof.observed_discriminators != expected:
            raise HookUnsupported("enumerated inventory is not exact")
        return
    if proof.mode != "CATCH_ALL":
        raise HookUnsupported("unknown matcher mode")
    if proof.official_contract_hash is None:
        raise HookUnsupported("catch-all official contract is absent")
    _require_hash(
        proof.official_contract_hash, "official_contract_hash"
    )
    required = {
        "Shell",
        "Read",
        "Write",
        "Grep",
        "Delete",
        "Task",
    }
    observed = proof.observed_discriminators
    if not required <= observed or not any(
        value.startswith("MCP:") for value in observed
    ):
        raise HookUnsupported(
            "catch-all live discriminator UAT is incomplete"
        )


def validate_candidate_evidence(
    receipt: DirectReceipt,
    *,
    inventory: Iterable[InventoryEntry],
    matcher_proof: MatcherProof,
    rows: Iterable[HookRow],
) -> None:
    entries = tuple(inventory)
    hook_rows = tuple(rows)
    validate_matcher_proof(matcher_proof, entries)
    inventory_digest = tool_inventory_hash(entries)
    matcher_digest = matcher_proof_hash(matcher_proof)
    projection_digest = hook_projection_hash(
        hook_rows,
        matcher_mode=matcher_proof.mode,
        matcher_hash=matcher_digest,
        inventory_hash=inventory_digest,
        file_generation=receipt.projection_file_generation,
        protocol_generation=receipt.protocol_generation,
        wrapper_runtime_hash=receipt.wrapper_runtime_hash,
    )
    if (
        receipt.hook_matcher_mode != matcher_proof.mode
        or receipt.tool_inventory_hash != inventory_digest
        or receipt.hook_matcher_hash != matcher_digest
        or receipt.hook_projection_hash != projection_digest
    ):
        raise HookUnsupported(
            "inventory/matcher/projection receipt mismatch"
        )


# Accepted ADR 0026/v5 deployment authority. The v1 gate and v2 receipt
# definitions above remain readable historical evidence, but these aliases
# ensure they cannot be confused with current deployment authority.
HistoricalDirectReceiptV2 = DirectReceipt
HistoricalOwnerGateV1 = OwnerGate
_DIRECT_RECEIPT_V2_FIELDS = _HISTORICAL_DIRECT_RECEIPT_FIELDS
DIRECT_RECEIPT_FIELDS = _DIRECT_RECEIPT_V2_FIELDS + (
    "bundle_generation",
    "bundle_digest",
    "bundle_projection_hash",
    "import_manifest_hash",
    "external_interpreter_hash",
    "interpreter_capability_hash",
    "denial_proof_vector_hash",
    "allowed_signers_contract_path_hash",
    "allowed_signers_contract_hash",
    "signer_public_key_sha256",
    "signer_fingerprint",
    "key_enrollment_digest",
    "harness_root_hash",
)
DIRECT_RECEIPT_BODY_FIELDS = tuple(
    field for field in DIRECT_RECEIPT_FIELDS if field != "owner_gate_digest"
)
OWNER_GATE_FIELDS = (
    "schema",
    "repository",
    "authorized_by",
    "deployment_scope",
    "direct_receipt_body_hash",
    "candidate_digest",
    "bundle_digest",
    "bundle_projection_hash",
    "import_manifest_hash",
    "external_interpreter_hash",
    "interpreter_capability_hash",
    "denial_proof_vector_hash",
    "installed_file_hash",
    "wrapper_runtime_hash",
    "installer_identity_hash",
    "installer_capability_hash",
    "allowed_signers_contract_path_hash",
    "allowed_signers_contract_hash",
    "signer_public_key_sha256",
    "signer_fingerprint",
    "key_enrollment_digest",
    "canonical_root_hash",
    "member_id",
    "harness_root_hash",
    "authorized",
)


def _require_scope(
    scope: object,
    canonical_root_hash: object,
    member_id: object,
    harness_root_hash: object,
) -> None:
    if scope == "R0_THROWAWAY":
        if canonical_root_hash is not None or member_id is not None:
            raise ValueError("R0 requires null root/member")
        _require_hash(harness_root_hash, "harness_root_hash")
    elif scope == "R1_CANARY":
        _require_hash(canonical_root_hash, "canonical_root_hash")
        _require_hash(member_id, "member_id")
        if harness_root_hash is not None:
            raise ValueError("R1 requires null harness root")
    elif scope == "R2_DIRECT":
        if any(
            value is not None
            for value in (
                canonical_root_hash,
                member_id,
                harness_root_hash,
            )
        ):
            raise ValueError("R2 requires null root/member/harness")
    else:
        raise ValueError("unknown deployment scope")


def _parse_canonical_object(
    raw: bytes, *, fields_expected: tuple[str, ...], label: str
) -> dict[str, object]:
    if (
        not isinstance(raw, bytes)
        or not 1 <= len(raw) <= 131_072
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\0" in raw
    ):
        raise ValueError(f"{label} bytes are malformed")
    try:
        value = registration_jcs.parse_canonical(raw[:-1])
    except (ValueError, registration_jcs.JcsError) as exc:
        raise ValueError(f"{label} is not canonical JCS") from exc
    if (
        not isinstance(value, dict)
        or set(value) != set(fields_expected)
        or registration_jcs.canonical_bytes(value) + b"\n" != raw
    ):
        raise ValueError(f"{label} fields are not exact")
    return value


@dataclass(frozen=True)
class DirectReceipt:
    schema: str
    owner_mode: str
    deployment_scope: str
    candidate_digest: str
    schema_hash: str
    profile_hash: str
    runtime_capability_hash: str
    writer_binary_hash: str
    writer_capability_hash: str
    tool_inventory_hash: str
    hook_projection_hash: str
    hook_matcher_mode: str
    hook_matcher_hash: str
    installed_file_hash: str
    projection_file_generation: str
    protocol_generation: str
    wrapper_runtime_hash: str
    installer_identity_hash: str
    installer_capability_hash: str
    owner_gate_digest: str
    canonical_root_hash: str | None
    member_id: str | None
    bundle_generation: str
    bundle_digest: str
    bundle_projection_hash: str
    import_manifest_hash: str
    external_interpreter_hash: str
    interpreter_capability_hash: str
    denial_proof_vector_hash: str
    allowed_signers_contract_path_hash: str
    allowed_signers_contract_hash: str
    signer_public_key_sha256: str
    signer_fingerprint: str
    key_enrollment_digest: str
    harness_root_hash: str | None

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-direct-receipt/v3":
            raise ValueError("current DIRECT receipt must be v3")
        if self.owner_mode != "DIRECT":
            raise ValueError("external projection ownership is unsupported")
        if self.hook_matcher_mode not in {"CATCH_ALL", "ENUMERATED"}:
            raise ValueError("unknown hook matcher mode")
        for field in (
            "candidate_digest",
            "schema_hash",
            "profile_hash",
            "runtime_capability_hash",
            "writer_binary_hash",
            "writer_capability_hash",
            "tool_inventory_hash",
            "hook_projection_hash",
            "hook_matcher_hash",
            "installed_file_hash",
            "wrapper_runtime_hash",
            "installer_identity_hash",
            "installer_capability_hash",
            "owner_gate_digest",
            "bundle_digest",
            "bundle_projection_hash",
            "import_manifest_hash",
            "external_interpreter_hash",
            "interpreter_capability_hash",
            "denial_proof_vector_hash",
            "allowed_signers_contract_path_hash",
            "allowed_signers_contract_hash",
            "signer_public_key_sha256",
            "key_enrollment_digest",
        ):
            _require_hash(getattr(self, field), field)
        for field in (
            "projection_file_generation",
            "protocol_generation",
            "bundle_generation",
        ):
            _require_decimal(getattr(self, field), field)
            if getattr(self, field) == "0":
                raise ValueError(f"{field} must be positive")
        if (
            not isinstance(self.signer_fingerprint, str)
            or not self.signer_fingerprint.startswith("SHA256:")
            or len(self.signer_fingerprint) < 16
        ):
            raise ValueError("signer_fingerprint is malformed")
        _require_scope(
            self.deployment_scope,
            self.canonical_root_hash,
            self.member_id,
            self.harness_root_hash,
        )
        expected = candidate_digest(
            {field: getattr(self, field) for field in CANDIDATE_FIELDS}
        )
        if self.candidate_digest != expected:
            raise ValueError("candidate digest mismatch")

    @property
    def direct_receipt_body_hash(self) -> str:
        return _domain_hash(
            "awa-registration-direct-receipt-authority/v2",
            {
                field: getattr(self, field)
                for field in DIRECT_RECEIPT_BODY_FIELDS
            },
        )

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-direct-receipt/v3", self.to_mapping()
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            field: getattr(self, field) for field in DIRECT_RECEIPT_FIELDS
        }

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "DirectReceipt":
        if not isinstance(value, Mapping) or set(value) != set(
            DIRECT_RECEIPT_FIELDS
        ):
            raise ValueError("DIRECT receipt fields are not exact")
        return cls(
            **{field: value[field] for field in DIRECT_RECEIPT_FIELDS}
        )

    @classmethod
    def from_bytes(cls, raw: bytes) -> "DirectReceipt":
        value = _parse_canonical_object(
            raw,
            fields_expected=DIRECT_RECEIPT_FIELDS,
            label="DIRECT receipt",
        )
        return cls.from_mapping(value)

    def deployment_receipt(self) -> DeploymentReceipt:
        return DeploymentReceipt(
            owner_mode=self.owner_mode,
            deployment_scope=self.deployment_scope,
            candidate_digest=self.candidate_digest,
            canonical_root_hash=self.canonical_root_hash,
            member_id=self.member_id,
            owner_gate_digest=self.owner_gate_digest,
        )

    @classmethod
    def vector_r1(cls) -> "DirectReceipt":
        return fixed_authority_vector("R1_CANARY")[0]


@dataclass(frozen=True)
class OwnerGate:
    schema: str
    repository: str
    authorized_by: str
    deployment_scope: str
    direct_receipt_body_hash: str
    candidate_digest: str
    bundle_digest: str
    bundle_projection_hash: str
    import_manifest_hash: str
    external_interpreter_hash: str
    interpreter_capability_hash: str
    denial_proof_vector_hash: str
    installed_file_hash: str
    wrapper_runtime_hash: str
    installer_identity_hash: str
    installer_capability_hash: str
    allowed_signers_contract_path_hash: str
    allowed_signers_contract_hash: str
    signer_public_key_sha256: str
    signer_fingerprint: str
    key_enrollment_digest: str
    canonical_root_hash: str | None
    member_id: str | None
    harness_root_hash: str | None
    authorized: bool

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-owner-gate/v2"
            or self.repository != "KleinPerkins/awa"
            or self.authorized_by != "KleinPerkins"
            or self.authorized is not True
        ):
            raise ValueError("owner gate authority is invalid")
        for field in (
            "direct_receipt_body_hash",
            "candidate_digest",
            "bundle_digest",
            "bundle_projection_hash",
            "import_manifest_hash",
            "external_interpreter_hash",
            "interpreter_capability_hash",
            "denial_proof_vector_hash",
            "installed_file_hash",
            "wrapper_runtime_hash",
            "installer_identity_hash",
            "installer_capability_hash",
            "allowed_signers_contract_path_hash",
            "allowed_signers_contract_hash",
            "signer_public_key_sha256",
            "key_enrollment_digest",
        ):
            _require_hash(getattr(self, field), field)
        if (
            not isinstance(self.signer_fingerprint, str)
            or not self.signer_fingerprint.startswith("SHA256:")
        ):
            raise ValueError("signer_fingerprint is malformed")
        _require_scope(
            self.deployment_scope,
            self.canonical_root_hash,
            self.member_id,
            self.harness_root_hash,
        )

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-owner-gate/v2", self.to_mapping()
        )

    def to_mapping(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in OWNER_GATE_FIELDS}

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "OwnerGate":
        if not isinstance(value, Mapping) or set(value) != set(
            OWNER_GATE_FIELDS
        ):
            raise ValueError("owner gate fields are not exact")
        return cls(**{field: value[field] for field in OWNER_GATE_FIELDS})

    @classmethod
    def from_bytes(cls, raw: bytes) -> "OwnerGate":
        return cls.from_mapping(
            _parse_canonical_object(
                raw,
                fields_expected=OWNER_GATE_FIELDS,
                label="owner gate",
            )
        )


def validate_receipt_against_gate(
    receipt: DirectReceipt, gate: OwnerGate
) -> None:
    if not isinstance(receipt, DirectReceipt) or not isinstance(
        gate, OwnerGate
    ):
        raise ValueError("current receipt and gate types are required")
    repeated = (
        "deployment_scope",
        "candidate_digest",
        "bundle_digest",
        "bundle_projection_hash",
        "import_manifest_hash",
        "external_interpreter_hash",
        "interpreter_capability_hash",
        "denial_proof_vector_hash",
        "installed_file_hash",
        "wrapper_runtime_hash",
        "installer_identity_hash",
        "installer_capability_hash",
        "allowed_signers_contract_path_hash",
        "allowed_signers_contract_hash",
        "signer_public_key_sha256",
        "signer_fingerprint",
        "key_enrollment_digest",
        "canonical_root_hash",
        "member_id",
        "harness_root_hash",
    )
    if (
        receipt.direct_receipt_body_hash != gate.direct_receipt_body_hash
        or receipt.owner_gate_digest != gate.digest
        or any(
            getattr(receipt, field) != getattr(gate, field)
            for field in repeated
        )
    ):
        raise ValueError("DIRECT receipt is not bound to owner gate")


@dataclass(frozen=True)
class CurrentOwnerKey:
    schema: str
    sequence: str
    status: str
    principal: str
    namespace: str
    key_algorithm: str
    public_key_sha256: str
    openssh_fingerprint: str
    allowed_signers_relative_path: str
    allowed_signers_path_hash: str
    allowed_signers_contract_hash: str
    key_enrollment_digest: str
    owner_authorization_digest: str
    previous_enrollment_hash: str | None
    created_wall_ns: str
    enrollment_hash: str

    FIELDS = (
        "schema",
        "sequence",
        "status",
        "principal",
        "namespace",
        "key_algorithm",
        "public_key_sha256",
        "openssh_fingerprint",
        "allowed_signers_relative_path",
        "allowed_signers_path_hash",
        "allowed_signers_contract_hash",
        "key_enrollment_digest",
        "owner_authorization_digest",
        "previous_enrollment_hash",
        "created_wall_ns",
        "enrollment_hash",
    )

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-owner-key-current/v1"
            or self.principal != "KleinPerkins"
            or self.namespace != "awa-registration-owner-gate-v2"
            or self.key_algorithm != "ssh-ed25519"
            or self.allowed_signers_relative_path
            != "contracts/awa-registration-owner-signers.v1"
        ):
            raise ValueError("owner-key receipt identity is invalid")
        if self.status not in {"ACTIVE", "REVOKED"}:
            raise ValueError("owner-key receipt status is invalid")
        if (
            not isinstance(self.openssh_fingerprint, str)
            or re.fullmatch(
                r"SHA256:[A-Za-z0-9+/]{43}",
                self.openssh_fingerprint,
            )
            is None
        ):
            raise ValueError("owner-key fingerprint is invalid")
        for field in ("sequence", "created_wall_ns"):
            _require_decimal(getattr(self, field), field)
        for field in (
            "public_key_sha256",
            "allowed_signers_path_hash",
            "allowed_signers_contract_hash",
            "key_enrollment_digest",
            "owner_authorization_digest",
            "enrollment_hash",
        ):
            _require_hash(getattr(self, field), field)
        enrollment = {
            "schema": "awa-registration-owner-key-enrollment/v1",
            "principal": self.principal,
            "namespace": self.namespace,
            "key_algorithm": self.key_algorithm,
            "public_key_sha256": self.public_key_sha256,
            "openssh_fingerprint": self.openssh_fingerprint,
            "allowed_signers_relative_path": (
                self.allowed_signers_relative_path
            ),
            "allowed_signers_path_hash": self.allowed_signers_path_hash,
            "allowed_signers_contract_hash": (
                self.allowed_signers_contract_hash
            ),
            "authorized": True,
        }
        if self.key_enrollment_digest != _domain_hash(
            "awa-registration-owner-key-enrollment/v1",
            enrollment,
        ):
            raise ValueError("owner-key enrollment digest mismatch")
        _require_hash(
            self.previous_enrollment_hash,
            "previous_enrollment_hash",
            nullable=True,
        )
        body = {
            field: getattr(self, field)
            for field in self.FIELDS
            if field != "enrollment_hash"
        }
        if self.enrollment_hash != _domain_hash(
            "awa-registration-owner-key-current/v1", body
        ):
            raise ValueError("owner-key enrollment hash mismatch")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CurrentOwnerKey":
        value = _parse_canonical_object(
            raw,
            fields_expected=cls.FIELDS,
            label="current owner-key receipt",
        )
        return cls(**value)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, object]
    ) -> "CurrentOwnerKey":
        if not isinstance(value, Mapping) or set(value) != set(cls.FIELDS):
            raise ValueError("current owner-key fields are not exact")
        return cls(**{field: value[field] for field in cls.FIELDS})


@dataclass(frozen=True)
class ImportRecord:
    path: str
    role: str
    mode: str
    size: str
    sha256: str

    def __post_init__(self) -> None:
        _require_relative_path(self.path)
        if self.role not in {"PACKAGE_INITIALIZER", "MODULE"}:
            raise ValueError("unknown import-manifest role")
        _require_decimal(self.mode, "mode")
        _require_decimal(self.size, "size")
        _require_hash(self.sha256, "sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "path": self.path,
            "role": self.role,
            "mode": self.mode,
            "size": self.size,
            "sha256": self.sha256,
        }


def _require_relative_path(path: object) -> None:
    if (
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or "\\" in path
        or "\0" in path
        or path != Path(path).as_posix()
        or any(
            component in {"", ".", ".."}
            for component in path.split("/")
        )
        or any(ord(character) < 32 for character in path)
    ):
        raise ValueError("bundle-relative path is invalid")


@dataclass(frozen=True)
class ImportManifest:
    schema: str
    entry_modules: tuple[str, ...]
    records: tuple[ImportRecord, ...]

    FIELDS = ("schema", "entry_modules", "records")

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-import-manifest/v1":
            raise ValueError("unknown import-manifest schema")
        if (
            not self.entry_modules
            or tuple(
                sorted(
                    set(self.entry_modules),
                    key=lambda value: value.encode("utf-8"),
                )
            )
            != self.entry_modules
        ):
            raise ValueError("entry modules are not unique bytewise sorted")
        if any(
            not isinstance(value, str)
            or not value
            or value.startswith(".")
            for value in self.entry_modules
        ):
            raise ValueError("entry module is invalid")
        paths = tuple(record.path for record in self.records)
        if (
            not paths
            or tuple(
                sorted(set(paths), key=lambda value: value.encode("utf-8"))
            )
            != paths
        ):
            raise ValueError("manifest records are not unique path sorted")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "entry_modules": list(self.entry_modules),
            "records": [record.to_mapping() for record in self.records],
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-import-manifest/v1", self.to_mapping()
        )

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ImportManifest":
        value = _parse_canonical_object(
            raw, fields_expected=cls.FIELDS, label="import manifest"
        )
        if not isinstance(value["entry_modules"], list) or not isinstance(
            value["records"], list
        ):
            raise ValueError("import-manifest arrays are invalid")
        return cls(
            schema=str(value["schema"]),
            entry_modules=tuple(value["entry_modules"]),
            records=tuple(
                ImportRecord(**record) for record in value["records"]
            ),
        )


@dataclass(frozen=True)
class BundleEntry:
    path: str
    role: str
    mode: str
    size: str
    sha256: str

    ROLES = frozenset(
        {
            "RECEIVER",
            "LAUNCHER",
            "RUNTIME",
            "PACKAGE_INITIALIZER",
            "IMPORT_MANIFEST",
            "SIGNER_CONTRACT",
            "CONFIG",
        }
    )

    def __post_init__(self) -> None:
        _require_relative_path(self.path)
        if self.role not in self.ROLES:
            raise ValueError("unknown bundle-entry role")
        _require_decimal(self.mode, "mode")
        _require_decimal(self.size, "size")
        _require_hash(self.sha256, "sha256")

    def to_mapping(self) -> dict[str, str]:
        return {
            "path": self.path,
            "role": self.role,
            "mode": self.mode,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class BundleManifest:
    schema: str
    generation: str
    entries: tuple[BundleEntry, ...]
    import_manifest_hash: str
    external_interpreter_hash: str
    interpreter_capability_hash: str
    allowed_signers_contract_hash: str

    FIELDS = (
        "schema",
        "generation",
        "entries",
        "import_manifest_hash",
        "external_interpreter_hash",
        "interpreter_capability_hash",
        "allowed_signers_contract_hash",
    )

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-bundle-manifest/v1":
            raise ValueError("unknown bundle-manifest schema")
        _require_decimal(self.generation, "generation")
        if self.generation == "0":
            raise ValueError("bundle generation must be positive")
        paths = tuple(entry.path for entry in self.entries)
        if (
            not paths
            or tuple(
                sorted(set(paths), key=lambda value: value.encode("utf-8"))
            )
            != paths
        ):
            raise ValueError("bundle entries are not unique path sorted")
        for required in (
            "RECEIVER",
            "LAUNCHER",
            "IMPORT_MANIFEST",
            "SIGNER_CONTRACT",
            "CONFIG",
        ):
            if sum(entry.role == required for entry in self.entries) != 1:
                raise ValueError(f"bundle requires one {required} entry")
        for field in (
            "import_manifest_hash",
            "external_interpreter_hash",
            "interpreter_capability_hash",
            "allowed_signers_contract_hash",
        ):
            _require_hash(getattr(self, field), field)
        manifest_entry = next(
            entry
            for entry in self.entries
            if entry.role == "IMPORT_MANIFEST"
        )
        contract_entry = next(
            entry
            for entry in self.entries
            if entry.role == "SIGNER_CONTRACT"
        )
        if contract_entry.sha256 != self.allowed_signers_contract_hash:
            raise ValueError("signer contract entry hash mismatch")
        if manifest_entry.path != "import-manifest.json":
            raise ValueError("import-manifest bundle path is not exact")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "generation": self.generation,
            "entries": [entry.to_mapping() for entry in self.entries],
            "import_manifest_hash": self.import_manifest_hash,
            "external_interpreter_hash": self.external_interpreter_hash,
            "interpreter_capability_hash": (
                self.interpreter_capability_hash
            ),
            "allowed_signers_contract_hash": (
                self.allowed_signers_contract_hash
            ),
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-bundle-manifest/v1", self.to_mapping()
        )

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> "BundleManifest":
        value = _parse_canonical_object(
            raw,
            fields_expected=cls.FIELDS,
            label="bundle manifest",
        )
        if not isinstance(value["entries"], list):
            raise ValueError("bundle entries must be an array")
        return cls(
            schema=value["schema"],
            generation=value["generation"],
            entries=tuple(
                BundleEntry(**entry) for entry in value["entries"]
            ),
            import_manifest_hash=value["import_manifest_hash"],
            external_interpreter_hash=value[
                "external_interpreter_hash"
            ],
            interpreter_capability_hash=value[
                "interpreter_capability_hash"
            ],
            allowed_signers_contract_hash=value[
                "allowed_signers_contract_hash"
            ],
        )


@dataclass(frozen=True)
class LauncherConfig:
    schema: str
    bundle_generation: str
    interpreter_path: str
    external_interpreter_hash: str
    interpreter_capability_hash: str
    import_manifest_hash: str
    entry_module: str
    isolated_flags: tuple[str, ...]

    FIELDS = (
        "schema",
        "bundle_generation",
        "interpreter_path",
        "external_interpreter_hash",
        "interpreter_capability_hash",
        "import_manifest_hash",
        "entry_module",
        "isolated_flags",
    )

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-launcher-config/v1":
            raise ValueError("unknown launcher-config schema")
        _require_decimal(self.bundle_generation, "bundle_generation")
        if (
            not isinstance(self.interpreter_path, str)
            or not self.interpreter_path.startswith("/")
            or os.path.normpath(self.interpreter_path)
            != self.interpreter_path
            or os.path.realpath(self.interpreter_path)
            != self.interpreter_path
        ):
            raise ValueError("launcher interpreter path is not canonical")
        for field in (
            "external_interpreter_hash",
            "interpreter_capability_hash",
            "import_manifest_hash",
        ):
            _require_hash(getattr(self, field), field)
        if (
            not isinstance(self.entry_module, str)
            or not self.entry_module
            or self.entry_module.startswith(".")
            or self.isolated_flags != ("-I", "-S", "-B")
        ):
            raise ValueError("launcher entry contract is invalid")

    def to_mapping(self) -> dict[str, object]:
        return {
            **{
                field: getattr(self, field)
                for field in self.FIELDS
                if field != "isolated_flags"
            },
            "isolated_flags": list(self.isolated_flags),
        }

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @property
    def file_hash(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, raw: bytes) -> "LauncherConfig":
        value = _parse_canonical_object(
            raw,
            fields_expected=cls.FIELDS,
            label="launcher config",
        )
        if not isinstance(value["isolated_flags"], list):
            raise ValueError("launcher flags must be an array")
        return cls(
            **{
                **value,
                "isolated_flags": tuple(value["isolated_flags"]),
            }
        )


@dataclass(frozen=True)
class BundleProjection:
    schema: str
    generation: str
    bundle_digest: str
    receiver_relative_path: str
    launcher_relative_path: str
    import_manifest_hash: str
    external_interpreter_hash: str
    interpreter_capability_hash: str
    runtime_config_hash: str
    allowed_signers_contract_hash: str

    FIELDS = (
        "schema",
        "generation",
        "bundle_digest",
        "receiver_relative_path",
        "launcher_relative_path",
        "import_manifest_hash",
        "external_interpreter_hash",
        "interpreter_capability_hash",
        "runtime_config_hash",
        "allowed_signers_contract_hash",
    )

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-bundle-projection/v1":
            raise ValueError("unknown bundle projection schema")
        _require_decimal(self.generation, "generation")
        if self.receiver_relative_path != "bin/awa-registration-receiver":
            raise ValueError("receiver relative path is not exact")
        if self.launcher_relative_path != "bin/awa-registration-launcher":
            raise ValueError("launcher relative path is not exact")
        for field in (
            "bundle_digest",
            "import_manifest_hash",
            "external_interpreter_hash",
            "interpreter_capability_hash",
            "runtime_config_hash",
            "allowed_signers_contract_hash",
        ):
            _require_hash(getattr(self, field), field)

    def to_mapping(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in self.FIELDS}

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-bundle-projection/v1", self.to_mapping()
        )

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> "BundleProjection":
        return cls(
            **_parse_canonical_object(
                raw,
                fields_expected=cls.FIELDS,
                label="bundle projection",
            )
        )


@dataclass(frozen=True)
class DenialProofRecord:
    event: str
    server_or_empty: str
    discriminator: str
    serializer_schema: str
    role: str
    seam: str
    bundle_digest: str
    request_hash: str
    output_hash: str
    exit_code: str

    def __post_init__(self) -> None:
        InventoryEntry(
            self.event,
            self.server_or_empty,
            self.discriminator,
            self.role,
            self.serializer_schema,
        )
        if self.seam not in {"DIRECT_RECEIVER", "SHADOW_INSTALLED"}:
            raise ValueError("unknown denial-proof seam")
        for field in ("bundle_digest", "request_hash", "output_hash"):
            _require_hash(getattr(self, field), field)
        _require_decimal(self.exit_code, "exit_code")
        if self.exit_code == "0":
            raise ValueError("denial proof cannot have an allow exit")

    def to_mapping(self) -> dict[str, str]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }


@dataclass(frozen=True)
class StagedDenialProof:
    schema: str
    records: tuple[DenialProofRecord, ...]

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-staged-denial-proof/v2":
            raise ValueError("unknown staged denial proof schema")
        encoded = tuple(
            registration_jcs.canonical_bytes(record.to_mapping())
            for record in self.records
        )
        if (
            not encoded
            or tuple(sorted(set(encoded))) != encoded
        ):
            raise ValueError("denial records are not unique JCS sorted")
        grouped: dict[tuple[str, str, str, str], set[str]] = {}
        roles: dict[tuple[str, str, str, str], str] = {}
        for record in self.records:
            key = (
                record.event,
                record.server_or_empty,
                record.discriminator,
                record.serializer_schema,
            )
            grouped.setdefault(key, set()).add(record.seam)
            prior = roles.setdefault(key, record.role)
            if prior != record.role:
                raise ValueError("denial proof has conflicting roles")
        if any(
            seams != {"DIRECT_RECEIVER", "SHADOW_INSTALLED"}
            for seams in grouped.values()
        ):
            raise ValueError("denial proof does not cover both seams")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "records": [record.to_mapping() for record in self.records],
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-staged-denial-proof/v2",
            self.to_mapping(),
        )


def wrapper_runtime_v2_hash(
    *,
    bundle_digest: str,
    launcher_hash: str,
    import_manifest_hash: str,
    external_interpreter_hash: str,
    interpreter_capability_hash: str,
    launcher_config_hash: str,
    runtime_records: Iterable[BundleEntry],
) -> str:
    for field, value in (
        ("bundle_digest", bundle_digest),
        ("launcher_hash", launcher_hash),
        ("import_manifest_hash", import_manifest_hash),
        ("external_interpreter_hash", external_interpreter_hash),
        ("interpreter_capability_hash", interpreter_capability_hash),
        ("launcher_config_hash", launcher_config_hash),
    ):
        _require_hash(value, field)
    records = tuple(runtime_records)
    if not records or any(
        record.role not in {"PACKAGE_INITIALIZER", "RUNTIME"}
        for record in records
    ):
        raise ValueError("wrapper runtime records are not exact")
    paths = tuple(record.path for record in records)
    if tuple(
        sorted(set(paths), key=lambda value: value.encode("utf-8"))
    ) != paths:
        raise ValueError("wrapper runtime records are not path sorted")
    return _domain_hash(
        "awa-registration-wrapper-runtime/v2",
        {
            "schema": "awa-registration-wrapper-runtime/v2",
            "bundle_digest": bundle_digest,
            "launcher_hash": launcher_hash,
            "import_manifest_hash": import_manifest_hash,
            "external_interpreter_hash": external_interpreter_hash,
            "interpreter_capability_hash": (
                interpreter_capability_hash
            ),
            "launcher_config_hash": launcher_config_hash,
            "runtime_records": [
                record.to_mapping() for record in records
            ],
        },
    )


@dataclass(frozen=True)
class StagedReadiness:
    schema: str
    mode: str
    current_protocol_hash: str
    staged_epoch_hash: str
    bundle_digest: str
    direct_receipt_hash: str
    import_manifest_hash: str
    external_interpreter_hash: str
    interpreter_capability_hash: str
    measured_profile_hash: str
    storage_dev: str
    denial_proof_vector_hash: str

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-staged-readiness/v2"
            or self.mode != "DENY_ONLY"
        ):
            raise ValueError("staged readiness must be deny-only v2")
        for field in (
            "current_protocol_hash",
            "staged_epoch_hash",
            "bundle_digest",
            "direct_receipt_hash",
            "import_manifest_hash",
            "external_interpreter_hash",
            "interpreter_capability_hash",
            "measured_profile_hash",
            "denial_proof_vector_hash",
        ):
            _require_hash(getattr(self, field), field)
        _require_decimal(self.storage_dev, "storage_dev")

    def to_mapping(self) -> dict[str, str]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-staged-readiness/v2",
            self.to_mapping(),
        )


@dataclass(frozen=True)
class ActiveBundlePointer:
    schema: str
    generation: str
    bundle_relative_dir: str
    bundle_digest: str
    bundle_projection_hash: str
    direct_receipt_hash: str
    external_interpreter_hash: str
    interpreter_capability_hash: str

    FIELDS = (
        "schema",
        "generation",
        "bundle_relative_dir",
        "bundle_digest",
        "bundle_projection_hash",
        "direct_receipt_hash",
        "external_interpreter_hash",
        "interpreter_capability_hash",
    )

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-active-bundle/v1":
            raise ValueError("unknown active-bundle schema")
        _require_decimal(self.generation, "generation")
        if self.generation == "0":
            raise ValueError("generation must be positive")
        _require_relative_path(self.bundle_relative_dir)
        if self.bundle_relative_dir != (
            f"bundles/{self.generation}-{self.bundle_digest}"
        ):
            raise ValueError("active bundle directory is not canonical")
        for field in (
            "bundle_digest",
            "bundle_projection_hash",
            "direct_receipt_hash",
            "external_interpreter_hash",
            "interpreter_capability_hash",
        ):
            _require_hash(getattr(self, field), field)

    def to_mapping(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in self.FIELDS}

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-active-bundle/v1", self.to_mapping()
        )

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ActiveBundlePointer":
        return cls(
            **_parse_canonical_object(
                raw,
                fields_expected=cls.FIELDS,
                label="active-bundle pointer",
            )
        )


def lookup_inventory_entry(
    entries: Iterable[InventoryEntry],
    *,
    event: str,
    server_or_empty: str,
    discriminator: str,
    serializer_schema: str,
) -> InventoryEntry:
    key = (event, server_or_empty, discriminator, serializer_schema)
    selected = [
        entry
        for entry in entries
        if (
            entry.event,
            entry.server_or_empty,
            entry.discriminator,
            entry.serializer_schema,
        )
        == key
    ]
    if len(selected) != 1:
        raise HookUnsupported("observable inventory lookup is not unique")
    return selected[0]


def tool_inventory_hash(entries: Iterable[InventoryEntry]) -> str:
    values = tuple(entries)
    keys = [
        (
            entry.event,
            entry.server_or_empty,
            entry.discriminator,
            entry.serializer_schema,
        )
        for entry in values
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate observable inventory key")
    ordered = _sorted_unique_mappings(
        values, lambda entry: entry.mapping()
    )
    if not ordered:
        raise ValueError("tool inventory cannot be empty")
    roles = {entry["role"] for entry in ordered}
    if roles != {"ordinary", "task_launch"}:
        raise ValueError("inventory must include ordinary and Task roles")
    return _domain_hash("awa-registration-tool-inventory/v1", ordered)


_FIXED = {
    "bundle_digest": "2ceab2235e3c1c107c26fcdaa213cf191450b395e51d8e1d08f34e52e0b9ca3d",
    "bundle_projection_hash": "28793a6f63a8a045df41a7590f4002897c3d860b65f96ded1bc04a1e46fa9b71",
    "import_manifest_hash": "dddb3b7741e48de647da4d6950364e7330a56bb94617097a79b2b7207676e170",
    "external_interpreter_hash": "7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2",
    "interpreter_capability_hash": "ca675a27a71e6ff366a59c943ab17e47d02e8f560cd3c2cc00f213424747c9f6",
    "denial_proof_vector_hash": "c72a4fc31d3037732bf55305511f58dbf0b7f5f58377e98bd80a61461d53b4cd",
    "allowed_signers_contract_path_hash": "ff4fbbc153649c484ee3d8f5203efa64db0c2a4dcae0a1a692514f5347d66faa",
    "allowed_signers_contract_hash": "bbd1f1bc972dc5ab20635021d8486f15de24011f61b59c1c6861379acc8b8c5f",
    "signer_public_key_sha256": "8b5a6781cafa6fd206a9681ddc4f09148311c8a14a571c784d30e5c53777e429",
    "signer_fingerprint": "SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA",
    "key_enrollment_digest": "ff7b0f05ac7d34958401277fef51ecf054b8328bf9c4571e2fa794c19fe15428",
    "wrapper_runtime_hash": "9b2d07ca937ea451028f5b0d5a755383320f5b0f3c8224eea3c090a9fdad28e0",
}


def bind_owner_gate(
    receipt: DirectReceipt,
) -> tuple[DirectReceipt, OwnerGate]:
    """Bind a current receipt body to its exact unsigned v2 owner gate."""
    gate = OwnerGate(
        schema="awa-registration-owner-gate/v2",
        repository="KleinPerkins/awa",
        authorized_by="KleinPerkins",
        deployment_scope=receipt.deployment_scope,
        direct_receipt_body_hash=receipt.direct_receipt_body_hash,
        candidate_digest=receipt.candidate_digest,
        bundle_digest=receipt.bundle_digest,
        bundle_projection_hash=receipt.bundle_projection_hash,
        import_manifest_hash=receipt.import_manifest_hash,
        external_interpreter_hash=receipt.external_interpreter_hash,
        interpreter_capability_hash=receipt.interpreter_capability_hash,
        denial_proof_vector_hash=receipt.denial_proof_vector_hash,
        installed_file_hash=receipt.installed_file_hash,
        wrapper_runtime_hash=receipt.wrapper_runtime_hash,
        installer_identity_hash=receipt.installer_identity_hash,
        installer_capability_hash=receipt.installer_capability_hash,
        allowed_signers_contract_path_hash=(
            receipt.allowed_signers_contract_path_hash
        ),
        allowed_signers_contract_hash=(
            receipt.allowed_signers_contract_hash
        ),
        signer_public_key_sha256=receipt.signer_public_key_sha256,
        signer_fingerprint=receipt.signer_fingerprint,
        key_enrollment_digest=receipt.key_enrollment_digest,
        canonical_root_hash=receipt.canonical_root_hash,
        member_id=receipt.member_id,
        harness_root_hash=receipt.harness_root_hash,
        authorized=True,
    )
    bound = DirectReceipt.from_mapping(
        {**receipt.to_mapping(), "owner_gate_digest": gate.digest}
    )
    validate_receipt_against_gate(bound, gate)
    return bound, gate


def fixed_authority_vector(
    scope: str,
) -> tuple[DirectReceipt, OwnerGate]:
    hash_value = lambda character: character * 64
    candidate = {
        field: hash_value("a")
        for field in CANDIDATE_FIELDS
        if field
        not in {
            "hook_matcher_mode",
            "projection_file_generation",
            "protocol_generation",
        }
    }
    candidate.update(
        {
            "hook_matcher_mode": "ENUMERATED",
            "projection_file_generation": "2",
            "protocol_generation": "2",
        }
    )
    if scope == "R0_THROWAWAY":
        root, member, harness = None, None, hash_value("7")
    elif scope == "R1_CANARY":
        root, member, harness = hash_value("8"), hash_value("9"), None
    elif scope == "R2_DIRECT":
        root, member, harness = None, None, None
    else:
        raise ValueError("unknown fixed-vector scope")
    mapping: dict[str, object] = {
        "schema": "awa-registration-direct-receipt/v3",
        "owner_mode": "DIRECT",
        "deployment_scope": scope,
        "candidate_digest": candidate_digest(candidate),
        **candidate,
        "installed_file_hash": hash_value("b"),
        "wrapper_runtime_hash": _FIXED["wrapper_runtime_hash"],
        "installer_identity_hash": hash_value("1"),
        "installer_capability_hash": hash_value("2"),
        "owner_gate_digest": hash_value("0"),
        "canonical_root_hash": root,
        "member_id": member,
        "bundle_generation": "2",
        **{
            field: _FIXED[field]
            for field in (
                "bundle_digest",
                "bundle_projection_hash",
                "import_manifest_hash",
                "external_interpreter_hash",
                "interpreter_capability_hash",
                "denial_proof_vector_hash",
                "allowed_signers_contract_path_hash",
                "allowed_signers_contract_hash",
                "signer_public_key_sha256",
                "signer_fingerprint",
                "key_enrollment_digest",
            )
        },
        "harness_root_hash": harness,
    }
    provisional = DirectReceipt.from_mapping(mapping)
    return bind_owner_gate(provisional)


def mutated_authority_value(field: str, value: object) -> object:
    """Return a deterministic one-field mutation for closed-vector tests."""
    if value is None:
        return "f" * 64
    if type(value) is bool:
        return not value
    if isinstance(value, str) and _HEX64.fullmatch(value):
        return ("0" if value[0] != "0" else "1") + value[1:]
    if isinstance(value, str) and _DECIMAL.fullmatch(value):
        return str(int(value) + 1)
    if field == "signer_fingerprint":
        return value + "x"
    if field == "deployment_scope":
        return "R2_DIRECT" if value != "R2_DIRECT" else "R1_CANARY"
    return f"{value}-mutated"


def _authority_descriptor(
    path: Path, *, modes: frozenset[int], limit: int
) -> tuple[int, bytes]:
    path = Path(path)
    descriptor = -1
    try:
        before = path.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) not in modes
            or before.st_nlink != 1
            or not 0 <= before.st_size <= limit
        ):
            raise ValueError("authority file identity is unsafe")
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        opened = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise ValueError("authority file changed while opening")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > limit:
            raise ValueError("authority file exceeds bound")
        after = os.fstat(descriptor)
        visible = path.lstat()
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
        )
        if identity != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        ) or identity != (
            visible.st_dev,
            visible.st_ino,
            visible.st_mode,
            visible.st_uid,
            visible.st_nlink,
            visible.st_size,
            visible.st_mtime_ns,
        ):
            raise ValueError("authority file changed while reading")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, raw
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _parse_allowed_signers(
    raw: bytes,
) -> tuple[str, str, str]:
    pattern = re.compile(
        rb'^KleinPerkins namespaces="awa-registration-owner-gate-v2" '
        rb"ssh-ed25519 ([A-Za-z0-9+/]+={0,2})\n$"
    )
    match = pattern.fullmatch(raw)
    if match is None:
        raise ValueError("allowed-signers contract is not exact")
    encoded = match.group(1)
    try:
        blob = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("allowed-signers key is not canonical base64") from exc
    if base64.b64encode(blob) != encoded:
        raise ValueError("allowed-signers key is not canonical base64")

    def take(offset: int) -> tuple[bytes, int]:
        if offset + 4 > len(blob):
            raise ValueError("allowed-signers wire key is truncated")
        size = int.from_bytes(blob[offset : offset + 4], "big")
        start = offset + 4
        end = start + size
        if end > len(blob):
            raise ValueError("allowed-signers wire key is truncated")
        return blob[start:end], end

    algorithm, offset = take(0)
    public_key, offset = take(offset)
    if (
        algorithm != b"ssh-ed25519"
        or len(public_key) != 32
        or offset != len(blob)
    ):
        raise ValueError("allowed-signers key is not ssh-ed25519")
    identity = b"ssh-ed25519 " + encoded + b"\n"
    public_hash = hashlib.sha256(identity).hexdigest()
    fingerprint = (
        "SHA256:"
        + base64.b64encode(hashlib.sha256(blob).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return public_hash, fingerprint, hashlib.sha256(raw).hexdigest()


def verify_owner_gate_signature(
    gate_bytes: bytes,
    *,
    signature_path: Path,
    bundle_root: Path,
    current_receipt_path: Path,
    expected_enrollment_hash: str,
) -> OwnerGate:
    """Verify one current gate with stock OpenSSH and enrolled public authority."""
    gate = OwnerGate.from_bytes(gate_bytes)
    _require_hash(expected_enrollment_hash, "expected_enrollment_hash")
    bundle_root = Path(bundle_root)
    if (
        not bundle_root.is_absolute()
        or os.path.normpath(str(bundle_root)) != str(bundle_root)
    ):
        raise ValueError("installed bundle root must be canonical absolute")
    root_metadata = bundle_root.lstat()
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise ValueError("installed bundle root is unsafe")
    allowed_signers_path = (
        bundle_root / "contracts/awa-registration-owner-signers.v1"
    )
    current_fd = contract_fd = signature_fd = -1
    try:
        current_fd, current_raw = _authority_descriptor(
            current_receipt_path,
            modes=frozenset({0o600}),
            limit=65_536,
        )
        current = CurrentOwnerKey.from_bytes(current_raw)
        if current.status != "ACTIVE":
            raise ValueError("owner-key enrollment is not ACTIVE")
        if current.enrollment_hash != expected_enrollment_hash:
            raise ValueError("owner-key enrollment is not delivery authority")
        contract_fd, contract_raw = _authority_descriptor(
            allowed_signers_path,
            modes=frozenset({0o644}),
            limit=512,
        )
        public_hash, fingerprint, contract_hash = _parse_allowed_signers(
            contract_raw
        )
        path_hash = hashlib.sha256(
            b"awa-registration-owner-signers-path/v1\0"
            b"contracts/awa-registration-owner-signers.v1"
        ).hexdigest()
        expected = {
            "principal": "KleinPerkins",
            "namespace": "awa-registration-owner-gate-v2",
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256": public_hash,
            "openssh_fingerprint": fingerprint,
            "allowed_signers_path_hash": path_hash,
            "allowed_signers_contract_hash": contract_hash,
        }
        if any(getattr(current, field) != value for field, value in expected.items()):
            raise ValueError("allowed-signers contract is not currently enrolled")
        if (
            gate.signer_public_key_sha256 != current.public_key_sha256
            or gate.signer_fingerprint != current.openssh_fingerprint
            or gate.allowed_signers_contract_path_hash
            != current.allowed_signers_path_hash
            or gate.allowed_signers_contract_hash
            != current.allowed_signers_contract_hash
            or gate.key_enrollment_digest
            != current.key_enrollment_digest
        ):
            raise ValueError("owner gate is not bound to current enrollment")
        signature_fd, _signature_raw = _authority_descriptor(
            signature_path,
            modes=frozenset({0o600, 0o644}),
            limit=65_536,
        )
        result = subprocess.run(
            [
                "/usr/bin/ssh-keygen",
                "-Y",
                "verify",
                "-f",
                f"/dev/fd/{contract_fd}",
                "-I",
                "KleinPerkins",
                "-n",
                "awa-registration-owner-gate-v2",
                "-s",
                f"/dev/fd/{signature_fd}",
            ],
            input=gate_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            pass_fds=(contract_fd, signature_fd),
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
        if result.returncode != 0:
            raise ValueError("detached owner signature did not verify")
        return gate
    finally:
        for descriptor in (signature_fd, contract_fd, current_fd):
            if descriptor >= 0:
                os.close(descriptor)


def verified_owner_gate_digest(
    gate_bytes: bytes,
    detached_signature: bytes | None = None,
    *,
    verifier: Callable[[bytes, bytes], bool] | None = None,
    signature_path: Path | None = None,
    bundle_root: Path | None = None,
    current_receipt_path: Path | None = None,
    expected_enrollment_hash: str | None = None,
) -> str:
    if detached_signature is not None or verifier is not None:
        raise ValueError("callback owner verification is historical only")
    if (
        signature_path is None
        or bundle_root is None
        or current_receipt_path is None
        or expected_enrollment_hash is None
    ):
        raise ValueError("stock OpenSSH verification inputs are required")
    gate = verify_owner_gate_signature(
        gate_bytes,
        signature_path=signature_path,
        bundle_root=bundle_root,
        current_receipt_path=current_receipt_path,
        expected_enrollment_hash=expected_enrollment_hash,
    )
    return gate.digest


def verify_receipt_owner_gate(
    receipt: DirectReceipt,
    gate_bytes: bytes,
    detached_signature: bytes | None = None,
    *,
    verifier: Callable[[bytes, bytes], bool] | None = None,
    signature_path: Path | None = None,
    bundle_root: Path | None = None,
    current_receipt_path: Path | None = None,
    expected_enrollment_hash: str | None = None,
) -> None:
    digest = verified_owner_gate_digest(
        gate_bytes,
        detached_signature,
        verifier=verifier,
        signature_path=signature_path,
        bundle_root=bundle_root,
        current_receipt_path=current_receipt_path,
        expected_enrollment_hash=expected_enrollment_hash,
    )
    gate = OwnerGate.from_bytes(gate_bytes)
    if digest != gate.digest:
        raise ValueError("verified owner gate digest changed")
    validate_receipt_against_gate(receipt, gate)


R0_BARRIERS = (
    "C0.PREFLIGHT",
    "C1.BUNDLE_PUBLISHED",
    "C2.DRAIN_COMMITTED",
    "C2.STAGE_COMMITTED",
    "C2.DIRECT_PROOF",
    "C2.SHADOW_PROOF",
    "C3.POINTER_SWITCHED",
    "C3.POST_SWITCH_PROOF",
    "C3.OLD_ENTRY_DISABLED",
    "C4.ADOPT_COMMITTED",
    "C4.TRANSFER_RECEIVED",
    "C4.TRANSFER_ACTIVATED",
    "C4.MARK_COMMITTED",
    "C4.REACQUIRE_COMMITTED",
    "C5.RECONCILIATION_BATCH",
    "C5.CUSTODY_EMPTY",
    "C6.ADVANCE_COMMITTED",
    "C7.OLD_BUNDLE_REMOVED",
    "C7.RESIDUE_RECONCILED",
)
R0_SURFACE_CLASSES = frozenset(
    {
        "PROTOCOL_STATE",
        "RUNTIME",
        "HOOKS",
        "JOBS",
        "SKILLS",
        "DEV_OVERLAY",
        "INSTALLED_BYTES",
        "EXTERNAL_INTERPRETER",
    }
)


@dataclass(frozen=True)
class R0ManifestRecord:
    path_hash: str
    surface_class: str
    presence: str
    object_type: str | None
    st_dev: str | None
    st_ino: str | None
    st_mode: str | None
    st_uid: str | None
    st_gid: str | None
    st_nlink: str | None
    st_size: str | None
    content_sha256: str | None
    authority_hash: str | None

    def __post_init__(self) -> None:
        _require_hash(self.path_hash, "path_hash")
        if self.surface_class not in R0_SURFACE_CLASSES:
            raise ValueError("unknown R0 surface class")
        metadata = (
            self.st_dev,
            self.st_ino,
            self.st_mode,
            self.st_uid,
            self.st_gid,
            self.st_nlink,
            self.st_size,
        )
        if self.presence == "ABSENT":
            if (
                self.object_type is not None
                or any(value is not None for value in metadata)
                or self.content_sha256 is not None
                or self.authority_hash is not None
            ):
                raise ValueError("absent R0 record has metadata")
            return
        if self.presence != "PRESENT" or self.object_type not in {
            "REGULAR",
            "DIRECTORY",
            "OTHER",
        }:
            raise ValueError("R0 record presence/type is invalid")
        for field, value in zip(
            (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
            ),
            metadata,
        ):
            _require_decimal(value, field)
        if self.object_type == "REGULAR":
            _require_hash(self.content_sha256, "content_sha256")
        elif self.content_sha256 is not None:
            raise ValueError("nonregular R0 record has content hash")
        if self.surface_class == "EXTERNAL_INTERPRETER":
            _require_hash(self.authority_hash, "authority_hash")
        elif self.authority_hash is not None:
            raise ValueError("unexpected R0 authority hash")

    def to_mapping(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }


def _r0_records(
    records: tuple[R0ManifestRecord, ...],
) -> list[dict[str, object]]:
    hashes = tuple(record.path_hash for record in records)
    if tuple(sorted(set(hashes))) != hashes:
        raise ValueError("R0 manifest records are not path-hash sorted")
    return [record.to_mapping() for record in records]


def _require_r0_coordinate(cut_label: str, barrier_id: str) -> None:
    if (
        cut_label not in {f"C{value}" for value in range(8)}
        or barrier_id not in R0_BARRIERS
        or not barrier_id.startswith(cut_label + ".")
    ):
        raise ValueError("R0 cut/barrier coordinate is invalid")


@dataclass(frozen=True)
class R0GovernedManifest:
    schema: str
    phase: str
    cut_label: str
    barrier_id: str
    exact_head: str
    records: tuple[R0ManifestRecord, ...]

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-r0-governed-manifest/v1"
            or self.phase not in {"BEFORE", "AFTER"}
            or not isinstance(self.exact_head, str)
            or re.fullmatch(r"[0-9a-f]{40}", self.exact_head) is None
        ):
            raise ValueError("R0 governed manifest identity is invalid")
        _require_r0_coordinate(self.cut_label, self.barrier_id)
        _r0_records(self.records)

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "phase": self.phase,
            "cut_label": self.cut_label,
            "barrier_id": self.barrier_id,
            "exact_head": self.exact_head,
            "records": _r0_records(self.records),
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-r0-governed-manifest/v1",
            self.to_mapping(),
        )


@dataclass(frozen=True)
class R0TargetManifest:
    schema: str
    cut_label: str
    barrier_id: str
    harness_root_hash: str
    records: tuple[R0ManifestRecord, ...]

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-r0-target-manifest/v1":
            raise ValueError("R0 target manifest schema is invalid")
        _require_r0_coordinate(self.cut_label, self.barrier_id)
        _require_hash(self.harness_root_hash, "harness_root_hash")
        _r0_records(self.records)

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "cut_label": self.cut_label,
            "barrier_id": self.barrier_id,
            "harness_root_hash": self.harness_root_hash,
            "records": _r0_records(self.records),
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-r0-target-manifest/v1",
            self.to_mapping(),
        )


@dataclass(frozen=True)
class R0ProcessIdentity:
    schema: str
    pid: str
    executable_path_hash: str
    executable_content_hash: str
    argv_hash: str
    environment_contract_hash: str
    spawn_nonce: str

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-process-identity/v1":
            raise ValueError("R0 process identity schema is invalid")
        _require_decimal(self.pid, "pid")
        for field in (
            "executable_path_hash",
            "executable_content_hash",
            "argv_hash",
            "environment_contract_hash",
            "spawn_nonce",
        ):
            _require_hash(getattr(self, field), field)

    def to_mapping(self) -> dict[str, str]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-process-identity/v1", self.to_mapping()
        )


@dataclass(frozen=True)
class R0ProcessKill:
    schema: str
    cut_label: str
    barrier_id: str
    pid: str
    signal: str
    observed_returncode: str
    started_mono_ns: str
    killed_mono_ns: str
    reaped_mono_ns: str
    process_identity_hash: str

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-r0-process-kill/v1"
            or self.signal != "SIGKILL"
        ):
            raise ValueError("R0 process-kill identity is invalid")
        _require_r0_coordinate(self.cut_label, self.barrier_id)
        for field in (
            "pid",
            "started_mono_ns",
            "killed_mono_ns",
            "reaped_mono_ns",
        ):
            _require_decimal(getattr(self, field), field)
        if (
            not isinstance(self.observed_returncode, str)
            or re.fullmatch(r"(0|-?[1-9][0-9]*)", self.observed_returncode)
            is None
        ):
            raise ValueError("R0 return code is invalid")
        _require_hash(
            self.process_identity_hash, "process_identity_hash"
        )
        if not (
            int(self.started_mono_ns)
            <= int(self.killed_mono_ns)
            <= int(self.reaped_mono_ns)
        ):
            raise ValueError("R0 process-kill times are not monotonic")

    def to_mapping(self) -> dict[str, str]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-r0-process-kill/v1", self.to_mapping()
        )


@dataclass(frozen=True)
class R0WriteObservationRecord:
    event_id: str
    path_hash: str
    event_flags: str
    observed_mono_ns: str

    FLAGS = frozenset(
        {
            "ITEM_CREATED",
            "ITEM_REMOVED",
            "ITEM_INODE_META_MOD",
            "ITEM_RENAMED",
            "ITEM_MODIFIED",
            "ITEM_FINDER_INFO_MOD",
            "ITEM_CHANGE_OWNER",
            "ITEM_XATTR_MOD",
            "MUST_SCAN_SUBDIRS",
            "ROOT_CHANGED",
            "MOUNT",
            "UNMOUNT",
        }
    )

    def __post_init__(self) -> None:
        _require_decimal(self.event_id, "event_id")
        _require_decimal(self.observed_mono_ns, "observed_mono_ns")
        _require_hash(self.path_hash, "path_hash")
        flags = self.event_flags.split("|")
        if (
            not flags
            or flags != sorted(set(flags), key=lambda item: item.encode())
            or not set(flags) <= self.FLAGS
        ):
            raise ValueError("R0 write-observation flags are invalid")

    def to_mapping(self) -> dict[str, str]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }


@dataclass(frozen=True)
class R0WriteObservation:
    schema: str
    observer: str
    available: bool
    records: tuple[R0WriteObservationRecord, ...]

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-r0-write-observation/v1"
            or type(self.available) is not bool
            or self.observer not in {"FSEVENTS", "NONE"}
            or (self.available and self.observer != "FSEVENTS")
            or (not self.available and (self.observer != "NONE" or self.records))
        ):
            raise ValueError("R0 write observation identity is invalid")
        ordering = tuple(
            (int(record.event_id), record.path_hash)
            for record in self.records
        )
        if tuple(sorted(set(ordering))) != ordering:
            raise ValueError("R0 write observations are not sorted")

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "observer": self.observer,
            "available": self.available,
            "records": [record.to_mapping() for record in self.records],
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-r0-write-observation/v1",
            self.to_mapping(),
        )


@dataclass(frozen=True)
class R0CutEvidence:
    schema: str
    cut_label: str
    barrier_id: str
    exact_head: str
    before_manifest_hash: str
    after_manifest_hash: str
    throwaway_target_manifest_hash: str
    external_write_observation_hash: str | None
    process_kill_hash: str
    receiver_proof_vector_hash: str
    claim_scope: str

    def __post_init__(self) -> None:
        if (
            self.schema != "awa-registration-r0-cut-evidence/v1"
            or re.fullmatch(r"[0-9a-f]{40}", self.exact_head) is None
            or self.claim_scope
            != "FINITE_GOVERNED_SURFACES_AND_OBSERVED_TARGETS"
        ):
            raise ValueError("R0 cut evidence identity is invalid")
        _require_r0_coordinate(self.cut_label, self.barrier_id)
        for field in (
            "before_manifest_hash",
            "after_manifest_hash",
            "throwaway_target_manifest_hash",
            "process_kill_hash",
            "receiver_proof_vector_hash",
        ):
            _require_hash(getattr(self, field), field)
        _require_hash(
            self.external_write_observation_hash,
            "external_write_observation_hash",
            nullable=True,
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }

    @property
    def digest(self) -> str:
        return _domain_hash(
            "awa-registration-r0-cut-evidence/v1", self.to_mapping()
        )


# V7 protected-private-runtime successor authorities. Historical v2/v3
# classes above remain parse-only compatibility for accepted-v5 evidence;
# current production authority is explicitly named by these v7 types.
DIRECT_RECEIPT_V4_FIELDS = (
    "schema",
    "owner_mode",
    "deployment_scope",
    "candidate_digest",
    "schema_hash",
    "profile_hash",
    "runtime_capability_hash",
    "writer_binary_hash",
    "writer_capability_hash",
    "tool_inventory_hash",
    "hook_projection_hash",
    "hook_matcher_mode",
    "hook_matcher_hash",
    "installed_file_hash",
    "projection_file_generation",
    "protocol_generation",
    "wrapper_runtime_hash",
    "installer_identity_hash",
    "installer_capability_hash",
    "owner_gate_digest",
    "canonical_root_hash",
    "member_id",
    "bundle_generation",
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
    "bootstrap_contract_hash",
    "private_runtime_contract_hash",
    "privileged_envelope_contract_hash",
    "admin_audit_contract_hash",
    "allowed_signers_contract_path_hash",
    "allowed_signers_contract_hash",
    "signer_public_key_sha256",
    "signer_fingerprint",
    "key_enrollment_digest",
    "key_current_enrollment_hash",
    "harness_root_hash",
)
DIRECT_BODY_V4_FIELDS = tuple(
    field for field in DIRECT_RECEIPT_V4_FIELDS if field != "owner_gate_digest"
)
OWNER_GATE_V3_FIELDS = (
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
)
OWNER_ENROLLMENT_V2_FIELDS = (
    "schema",
    "principal",
    "namespaces",
    "key_algorithm",
    "public_key_sha256",
    "openssh_fingerprint",
    "allowed_signers_relative_path",
    "allowed_signers_path_hash",
    "allowed_signers_contract_hash",
    "authorized",
)
OWNER_AUTHORIZATION_V2_FIELDS = (
    "schema",
    "repository",
    "authorized_by",
    "action",
    "principal",
    "namespaces",
    "key_algorithm",
    "public_key_sha256",
    "openssh_fingerprint",
    "allowed_signers_relative_path",
    "allowed_signers_path_hash",
    "allowed_signers_contract_hash",
    "key_enrollment_digest",
    "acceptance_normalized_digest",
    "authorization_nonce",
    "authorized",
)
OWNER_CURRENT_V2_FIELDS = (
    "schema",
    "sequence",
    "status",
    "principal",
    "namespaces",
    "key_algorithm",
    "public_key_sha256",
    "openssh_fingerprint",
    "allowed_signers_relative_path",
    "allowed_signers_path_hash",
    "allowed_signers_contract_hash",
    "key_enrollment_digest",
    "owner_authorization_digest",
    "previous_enrollment_hash",
    "created_wall_ns",
    "enrollment_hash",
)
PRIVATE_RUNTIME_ENVELOPE_FIELDS = (
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
)
V7_SOURCE_LOCK_SHA256 = (
    "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
)
V7_SIGNER_CONTRACT_HASH = (
    "690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3"
)
V7_SIGNER_PATH_HASH = (
    "e0adbc96112fc8d029c8837988eb70bf4e8b0bb747daaa41d8899ce8013a712b"
)
V7_SIGNER_PUBLIC_KEY_SHA256 = (
    "ccc9283906c612aed388f23bf5ef26f16a0a780926a447dbe8c7e71a94b4df63"
)
V7_SIGNER_FINGERPRINT = (
    "SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M"
)
V7_ACCEPTED_V6_DIGEST = (
    "1b23d1b1f50eb5f0d44cf18a5ad571c609ae7c373b6e1835368f368295ade452"
)
V7_PREVIOUS_ENROLLMENT_HASH = (
    "885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4"
)
V7_NAMESPACES = (
    "awa-private-runtime-release-envelope-v1",
    "awa-registration-owner-gate-v3",
)


def _domain_hash_lf(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii")
        + b"\0"
        + registration_jcs.canonical_bytes(value)
        + b"\n"
    ).hexdigest()


def _require_exact_field_set(
    value: Mapping[str, object], expected: tuple[str, ...], label: str
) -> dict[str, object]:
    result = dict(value)
    if set(result) != set(expected):
        raise ValueError(f"{label} field set mismatch")
    return result


def _validate_v7_scope(
    scope: object,
    canonical_root_hash: object,
    member_id: object,
    harness_root_hash: object,
) -> None:
    if scope not in {"R0_THROWAWAY", "R1_CANARY", "R2_DIRECT"}:
        raise ValueError("v7 deployment scope mismatch")
    values = (canonical_root_hash, member_id, harness_root_hash)
    for name, value in zip(
        ("canonical_root_hash", "member_id", "harness_root_hash"), values
    ):
        _require_hash(value, name, nullable=True)
    if scope == "R0_THROWAWAY" and values[:2] != (None, None):
        raise ValueError("R0 scope fields mismatch")
    if scope == "R0_THROWAWAY" and harness_root_hash is None:
        raise ValueError("R0 requires harness_root_hash")
    if scope == "R1_CANARY" and (
        canonical_root_hash is None
        or member_id is None
        or harness_root_hash is not None
    ):
        raise ValueError("R1 scope fields mismatch")
    if scope == "R2_DIRECT" and values != (None, None, None):
        raise ValueError("R2 scope fields mismatch")


class _V7MappingAuthority:
    FIELDS: tuple[str, ...] = ()
    SCHEMA = ""
    DOMAIN = ""
    DIGEST_FIELD: str | None = None
    DIGEST_LF = True

    def __init__(self, **values: object):
        self._value = _require_exact_field_set(
            values, self.FIELDS, self.__class__.__name__
        )
        self._validate()

    def __getattr__(self, name: str) -> object:
        if name in self._value:
            return self._value[name]
        raise AttributeError(name)

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and self._value == other._value

    def _validate(self) -> None:
        if self._value.get("schema") != self.SCHEMA:
            raise ValueError(f"{self.__class__.__name__} schema mismatch")

    def to_mapping(self) -> dict[str, object]:
        return dict(self._value)

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self._value) + b"\n"

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]):
        return cls(**dict(value))

    @classmethod
    def from_bytes(cls, raw: bytes):
        if (
            not isinstance(raw, bytes)
            or not raw.endswith(b"\n")
            or raw.endswith(b"\n\n")
            or b"\r" in raw
            or b"\0" in raw
        ):
            raise ValueError(f"{cls.__name__} framing is invalid")
        value = registration_jcs.parse_canonical(raw[:-1])
        if registration_jcs.canonical_bytes(value) + b"\n" != raw:
            raise ValueError(f"{cls.__name__} bytes are not canonical")
        if not isinstance(value, dict):
            raise ValueError(f"{cls.__name__} must be an object")
        return cls.from_mapping(value)

    @property
    def digest(self) -> str:
        value = self.to_mapping()
        if self.DIGEST_FIELD:
            value.pop(self.DIGEST_FIELD)
        return (
            _domain_hash_lf(self.DOMAIN, value)
            if self.DIGEST_LF
            else _domain_hash(self.DOMAIN, value)
        )


class OwnerKeyEnrollmentV2(_V7MappingAuthority):
    FIELDS = OWNER_ENROLLMENT_V2_FIELDS
    SCHEMA = "awa-registration-owner-key-enrollment/v2"
    DOMAIN = SCHEMA

    def _validate(self) -> None:
        super()._validate()
        expected = {
            "principal": "KleinPerkins",
            "namespaces": list(V7_NAMESPACES),
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256": V7_SIGNER_PUBLIC_KEY_SHA256,
            "openssh_fingerprint": V7_SIGNER_FINGERPRINT,
            "allowed_signers_relative_path":
                "contracts/awa-registration-owner-signers.v2",
            "allowed_signers_path_hash": V7_SIGNER_PATH_HASH,
            "allowed_signers_contract_hash": V7_SIGNER_CONTRACT_HASH,
            "authorized": True,
        }
        if any(self._value.get(key) != value for key, value in expected.items()):
            raise ValueError("v2 owner enrollment authority mismatch")


class OwnerKeyAuthorizationV2(_V7MappingAuthority):
    FIELDS = OWNER_AUTHORIZATION_V2_FIELDS
    SCHEMA = "awa-registration-owner-key-authorization/v2"
    DOMAIN = SCHEMA

    def _validate(self) -> None:
        super()._validate()
        expected = {
            "repository": "KleinPerkins/awa",
            "authorized_by": "KleinPerkins",
            "action": "ENROLL",
            "principal": "KleinPerkins",
            "namespaces": list(V7_NAMESPACES),
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256": V7_SIGNER_PUBLIC_KEY_SHA256,
            "openssh_fingerprint": V7_SIGNER_FINGERPRINT,
            "allowed_signers_relative_path":
                "contracts/awa-registration-owner-signers.v2",
            "allowed_signers_path_hash": V7_SIGNER_PATH_HASH,
            "allowed_signers_contract_hash": V7_SIGNER_CONTRACT_HASH,
            "authorized": True,
        }
        if any(self._value.get(key) != value for key, value in expected.items()):
            raise ValueError("v2 owner authorization authority mismatch")
        for name in (
            "key_enrollment_digest",
            "acceptance_normalized_digest",
            "authorization_nonce",
        ):
            _require_hash(self._value[name], name)


class OwnerKeyCurrentV2(_V7MappingAuthority):
    FIELDS = OWNER_CURRENT_V2_FIELDS
    SCHEMA = "awa-registration-owner-key-current/v2"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "enrollment_hash"

    def _validate(self) -> None:
        super()._validate()
        _require_decimal(self._value["sequence"], "sequence")
        _require_decimal(self._value["created_wall_ns"], "created_wall_ns")
        if self._value["status"] not in {"ACTIVE", "REVOKED"}:
            raise ValueError("v2 owner current status mismatch")
        if self._value["previous_enrollment_hash"] != V7_PREVIOUS_ENROLLMENT_HASH:
            raise ValueError("v2 owner current predecessor mismatch")
        for name in (
            "key_enrollment_digest",
            "owner_authorization_digest",
            "enrollment_hash",
        ):
            _require_hash(self._value[name], name)
        enrollment = OwnerKeyEnrollmentV2(
            schema="awa-registration-owner-key-enrollment/v2",
            principal=self._value["principal"],
            namespaces=self._value["namespaces"],
            key_algorithm=self._value["key_algorithm"],
            public_key_sha256=self._value["public_key_sha256"],
            openssh_fingerprint=self._value["openssh_fingerprint"],
            allowed_signers_relative_path=self._value[
                "allowed_signers_relative_path"
            ],
            allowed_signers_path_hash=self._value[
                "allowed_signers_path_hash"
            ],
            allowed_signers_contract_hash=self._value[
                "allowed_signers_contract_hash"
            ],
            authorized=True,
        )
        if self._value["key_enrollment_digest"] != enrollment.digest:
            raise ValueError("v2 owner current enrollment digest mismatch")
        if self._value["enrollment_hash"] != self.digest:
            raise ValueError("v2 owner current self-digest mismatch")


class PrivateRuntimeReleaseEnvelope(_V7MappingAuthority):
    FIELDS = PRIVATE_RUNTIME_ENVELOPE_FIELDS
    SCHEMA = "awa-private-runtime-release-envelope/v1"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "release_envelope_digest"

    def _validate(self) -> None:
        super()._validate()
        if (
            self._value["repository"] != "KleinPerkins/awa"
            or re.fullmatch(r"[0-9a-f]{40}", self._value["exact_head"])
            is None
            or self._value["source_lock_sha256"] != V7_SOURCE_LOCK_SHA256
        ):
            raise ValueError("private runtime release identity mismatch")
        for name in PRIVATE_RUNTIME_ENVELOPE_FIELDS:
            if name.endswith(("_sha256", "_digest", "_hash")):
                _require_hash(self._value[name], name)
        _require_decimal(self._value["archive_size"], "archive_size")
        _require_decimal(self._value["minimum_epoch"], "minimum_epoch")
        if int(self._value["archive_size"]) == 0 or int(
            self._value["minimum_epoch"]
        ) == 0:
            raise ValueError("private runtime release positive value required")
        if self._value["release_envelope_digest"] != self.digest:
            raise ValueError("private runtime release self-digest mismatch")


class DirectReceiptV4(_V7MappingAuthority):
    FIELDS = DIRECT_RECEIPT_V4_FIELDS
    SCHEMA = "awa-registration-direct-receipt/v4"
    DOMAIN = SCHEMA

    def _validate(self) -> None:
        super()._validate()
        if (
            self._value["owner_mode"] != "DIRECT"
            or self._value["hook_matcher_mode"] != "ENUMERATED"
            or self._value["signer_fingerprint"] != V7_SIGNER_FINGERPRINT
            or self._value["source_lock_sha256"] != V7_SOURCE_LOCK_SHA256
            or self._value["allowed_signers_contract_path_hash"]
            != V7_SIGNER_PATH_HASH
            or self._value["allowed_signers_contract_hash"]
            != V7_SIGNER_CONTRACT_HASH
            or self._value["signer_public_key_sha256"]
            != V7_SIGNER_PUBLIC_KEY_SHA256
        ):
            raise ValueError("direct receipt v4 fixed authority mismatch")
        _validate_v7_scope(
            self._value["deployment_scope"],
            self._value["canonical_root_hash"],
            self._value["member_id"],
            self._value["harness_root_hash"],
        )
        for name in (
            "projection_file_generation",
            "protocol_generation",
            "bundle_generation",
        ):
            _require_decimal(self._value[name], name)
            if int(self._value[name]) == 0:
                raise ValueError(f"{name} must be positive")
        nullable = {
            "canonical_root_hash",
            "member_id",
            "harness_root_hash",
        }
        for name, value in self._value.items():
            if name.endswith(("_hash", "_sha256", "_digest")) and name not in nullable:
                _require_hash(value, name)

    @property
    def body_mapping(self) -> dict[str, object]:
        return {
            field: self._value[field] for field in DIRECT_BODY_V4_FIELDS
        }

    @property
    def body_hash(self) -> str:
        return _domain_hash(
            "awa-registration-direct-receipt-authority/v3",
            self.body_mapping,
        )

    @property
    def digest(self) -> str:
        return _domain_hash_lf(self.DOMAIN, self._value)


class OwnerGateV3(_V7MappingAuthority):
    FIELDS = OWNER_GATE_V3_FIELDS
    SCHEMA = "awa-registration-owner-gate/v3"
    DOMAIN = SCHEMA
    DIGEST_LF = False

    def _validate(self) -> None:
        super()._validate()
        if (
            self._value["repository"] != "KleinPerkins/awa"
            or self._value["authorized_by"] != "KleinPerkins"
            or self._value["authorized"] is not True
            or self._value["signer_fingerprint"] != V7_SIGNER_FINGERPRINT
            or self._value["signer_public_key_sha256"]
            != V7_SIGNER_PUBLIC_KEY_SHA256
            or self._value["allowed_signers_contract_path_hash"]
            != V7_SIGNER_PATH_HASH
            or self._value["allowed_signers_contract_hash"]
            != V7_SIGNER_CONTRACT_HASH
            or self._value["source_lock_sha256"] != V7_SOURCE_LOCK_SHA256
            or self._value["accepted_v6_normalized_digest"]
            != V7_ACCEPTED_V6_DIGEST
            or re.fullmatch(
                r"[0-9a-f]{40}", self._value["implementation_exact_head"]
            )
            is None
        ):
            raise ValueError("owner gate v3 fixed authority mismatch")
        _validate_v7_scope(
            self._value["deployment_scope"],
            self._value["canonical_root_hash"],
            self._value["member_id"],
            self._value["harness_root_hash"],
        )
        nullable = {
            "canonical_root_hash",
            "member_id",
            "harness_root_hash",
        }
        for name, value in self._value.items():
            if name.endswith(("_hash", "_sha256", "_digest")) and name not in nullable:
                _require_hash(value, name)


_V4_GATE_DUPLICATED_FIELDS = tuple(
    field
    for field in OWNER_GATE_V3_FIELDS
    if field
    in set(DIRECT_RECEIPT_V4_FIELDS)
    and field not in {"schema", "owner_gate_digest"}
)


def verify_direct_receipt_owner_gate_v3(
    receipt: DirectReceiptV4, gate: OwnerGateV3
) -> None:
    if gate.direct_receipt_body_hash != receipt.body_hash:
        raise ValueError("owner gate v3 receipt-body hash mismatch")
    for field in _V4_GATE_DUPLICATED_FIELDS:
        if getattr(receipt, field) != getattr(gate, field):
            raise ValueError(f"owner gate v3 duplicate mismatch: {field}")
    if receipt.owner_gate_digest != gate.digest:
        raise ValueError("direct receipt v4 owner-gate digest mismatch")


def owner_signature_verify_command(
    *,
    allowed_signers_path: Path,
    signature_path: Path,
    namespace: str,
) -> tuple[str, ...]:
    if namespace not in {
        "awa-private-runtime-release-envelope-v1",
        "awa-registration-owner-gate-v3",
    }:
        raise ValueError("owner verification namespace refused")
    for path in (allowed_signers_path, signature_path):
        if not path.is_absolute():
            raise ValueError("owner verification path must be absolute")
    return (
        "/usr/bin/ssh-keygen",
        "-Y",
        "verify",
        "-f",
        str(allowed_signers_path),
        "-I",
        "KleinPerkins",
        "-n",
        namespace,
        "-s",
        str(signature_path),
    )


def verify_owner_signature_public_only(
    payload: bytes,
    *,
    allowed_signers_path: Path,
    signature_path: Path,
    namespace: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    command = owner_signature_verify_command(
        allowed_signers_path=allowed_signers_path,
        signature_path=signature_path,
        namespace=namespace,
    )
    result = runner(
        command,
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise ValueError("public owner signature verification failed")


@dataclass(frozen=True)
class V7AuthorityDAG:
    bundle_entry_plain_hash: str
    import_manifest_hash: str
    installed_file_hash: str
    bundle_digest: str
    bootstrap_authority_hash: str
    runtime_release_envelope_digest: str
    expected_denial_vector_hash: str

    def __post_init__(self) -> None:
        for field in fields(self):
            _require_hash(getattr(self, field.name), field.name)
        if self.bundle_entry_plain_hash == self.installed_file_hash:
            raise ValueError(
                "bundle entry plain hash and installed file hash are distinct nodes"
            )

    @property
    def signed_expected_authority_hash(self) -> str:
        return _domain_hash(
            "awa-registration-v7-signed-expected-authority/v1",
            {
                "bootstrap_authority_hash": self.bootstrap_authority_hash,
                "bundle_digest": self.bundle_digest,
                "expected_denial_vector_hash":
                    self.expected_denial_vector_hash,
                "runtime_release_envelope_digest":
                    self.runtime_release_envelope_digest,
            },
        )

    def compare_observed(self, observed_denial_vector_hash: str) -> bool:
        _require_hash(
            observed_denial_vector_hash, "observed_denial_vector_hash"
        )
        return observed_denial_vector_hash == self.expected_denial_vector_hash


# V9 product closure authorities. Bundle-manifest/v2 is intentionally not
# represented as executable authority: its accepted field set is circular.
_MODULE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")


def _v9_relative_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != unicodedata.normalize("NFC", value)
        or not 1 <= len(value.encode("utf-8")) <= 4096
        or value.startswith("/")
        or "\\" in value
        or "\0" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("v9 relative path is invalid")
    return value


@dataclass(frozen=True)
class ImportRecordV2:
    kind: str
    logical_name: str
    relative_path: str
    owner_module: str | None
    fd_target: str
    mode: str
    size: str
    sha256: str

    def __post_init__(self) -> None:
        if self.kind not in {"PACKAGE_INITIALIZER", "MODULE", "RESOURCE"}:
            raise ValueError("import record kind is invalid")
        _v9_relative_path(self.relative_path)
        _require_decimal(self.fd_target, "fd_target")
        _require_decimal(self.size, "size")
        _require_hash(self.sha256, "sha256")
        if int(self.fd_target) < 16 or int(self.size) > 8 * 1024 * 1024:
            raise ValueError("import record bound is invalid")
        if self.mode != "444":
            raise ValueError("import record mode is invalid")
        if self.kind == "PACKAGE_INITIALIZER":
            if (
                _MODULE_NAME.fullmatch(self.logical_name) is None
                or self.owner_module is not None
                or self.relative_path
                != self.logical_name.replace(".", "/") + "/__init__.py"
            ):
                raise ValueError("package initializer mapping is invalid")
        elif self.kind == "MODULE":
            if (
                _MODULE_NAME.fullmatch(self.logical_name) is None
                or self.owner_module is not None
                or self.relative_path
                != self.logical_name.replace(".", "/") + ".py"
            ):
                raise ValueError("module mapping is invalid")
        else:
            if (
                not isinstance(self.owner_module, str)
                or _MODULE_NAME.fullmatch(self.owner_module) is None
                or not self.logical_name.startswith(self.owner_module + ":")
            ):
                raise ValueError("resource owner is invalid")

    def to_mapping(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ImportRecordV2":
        expected = {field.name for field in fields(cls)}
        if set(value) != expected:
            raise ValueError("import record fields are not exact")
        return cls(**dict(value))


@dataclass(frozen=True)
class ImportManifestV2:
    schema: str
    records: tuple[ImportRecordV2, ...]
    record_count: str
    aggregate_size: str
    import_manifest_hash: str

    @classmethod
    def create(cls, records: tuple[ImportRecordV2, ...]) -> "ImportManifestV2":
        ordered = tuple(sorted(records, key=lambda item: item.relative_path.encode()))
        if records != ordered or not 1 <= len(records) <= 505:
            raise ValueError("import records are not ordered or bounded")
        paths = [record.relative_path for record in records]
        names = [(record.kind, record.logical_name) for record in records]
        fds = [int(record.fd_target) for record in records]
        if (
            len(set(paths)) != len(paths)
            or len(set(names)) != len(names)
            or fds != list(range(16, 16 + len(records)))
        ):
            raise ValueError("import record uniqueness is invalid")
        modules = {record.logical_name for record in records if record.kind == "MODULE"}
        packages = {
            record.logical_name
            for record in records
            if record.kind == "PACKAGE_INITIALIZER"
        }
        resources = {
            (record.owner_module, record.logical_name.split(":", 1)[1])
            for record in records
            if record.kind == "RESOURCE"
        }
        for owner, resource_name in resources:
            package = owner.rpartition(".")[0] if owner else ""
            record = next(
                item for item in records
                if item.kind == "RESOURCE"
                and item.owner_module == owner
                and item.logical_name == f"{owner}:{resource_name}"
            )
            if (
                _RESOURCE_NAME.fullmatch(resource_name) is None
                or not package
                or record.relative_path
                != package.replace(".", "/") + "/" + resource_name
                or owner not in modules
                or package not in packages
            ):
                raise ValueError("resource mapping is invalid")
        if (
            ("engine.registration_schema", "registration_schema.sql")
            not in resources
            or "engine.registration_receiver" not in modules
            or "engine.registration_host" not in modules
            or "engine.registration_hook_runtime" not in modules
            or "engine.registration_schema" not in modules
            or "engine" not in packages
        ):
            raise ValueError("mandatory retained import closure is absent")
        total = sum(int(record.size) for record in records)
        if total > 64 * 1024 * 1024:
            raise ValueError("import aggregate exceeds bound")
        body = {
            "schema": "awa-registration-import-manifest/v2",
            "records": [record.to_mapping() for record in records],
            "record_count": str(len(records)),
            "aggregate_size": str(total),
        }
        return cls(
            **{**body, "records": records},
            import_manifest_hash=_domain_hash_lf(
                "awa-registration-import-manifest/v2", body
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "records": [record.to_mapping() for record in self.records],
            "record_count": self.record_count,
            "aggregate_size": self.aggregate_size,
            "import_manifest_hash": self.import_manifest_hash,
        }

    def to_bytes(self) -> bytes:
        return registration_jcs.canonical_bytes(self.to_mapping()) + b"\n"

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, object]
    ) -> "ImportManifestV2":
        expected = {
            "schema",
            "records",
            "record_count",
            "aggregate_size",
            "import_manifest_hash",
        }
        if set(value) != expected:
            raise ValueError("import manifest fields are not exact")
        records_value = value.get("records")
        if not isinstance(records_value, list):
            raise ValueError("import manifest records are invalid")
        records = tuple(
            ImportRecordV2.from_mapping(record)
            if isinstance(record, Mapping)
            else (_ for _ in ()).throw(
                ValueError("import manifest record is invalid")
            )
            for record in records_value
        )
        observed = cls.create(records)
        if observed.to_mapping() != dict(value):
            raise ValueError("import manifest authority is inconsistent")
        return observed

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ImportManifestV2":
        if (
            not isinstance(raw, bytes)
            or not raw.endswith(b"\n")
            or raw.endswith(b"\n\n")
            or b"\r" in raw
            or b"\0" in raw
        ):
            raise ValueError("import manifest framing is invalid")
        value = registration_jcs.parse_canonical(raw[:-1])
        if (
            not isinstance(value, dict)
            or registration_jcs.canonical_bytes(value) + b"\n" != raw
        ):
            raise ValueError("import manifest bytes are not canonical")
        return cls.from_mapping(value)


@dataclass(frozen=True)
class ProfileTargetV2:
    role: str
    path: str
    kind: str
    mode: str

    def to_mapping(self) -> dict[str, str]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


_PROFILE_TARGET_SHAPE = (
    ("state_parent", "directory", "0700"),
    ("db", "file", "0600"),
    ("wal", "file", "0600"),
    ("shm", "file", "0600"),
    ("proof_parent", "directory", "0700"),
    ("projection_parent", "directory", "0700"),
    ("legacy_parent", "directory", "0700"),
    ("root", "directory", "0700"),
    ("git_dir", "directory", "0700"),
    ("git_common", "directory", "0700"),
)


class HostAuthorityV2(_V7MappingAuthority):
    FIELDS = (
        "schema", "registration_db_path", "writer_capability_path",
        "profile_targets", "inventory", "proof_parent", "projection_parent",
        "legacy_parent", "host_tick_receipt_path", "profile_hash",
        "runtime_capability_hash", "writer_binary_hash",
        "writer_capability_hash", "tool_inventory_hash",
        "hook_projection_hash", "hook_matcher_mode", "hook_matcher_hash",
        "projection_file_generation", "protocol_generation",
        "installer_identity_hash", "installer_capability_hash", "storage_dev",
        "host_authority_digest",
    )
    SCHEMA = "awa-registration-host-authority/v2"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "host_authority_digest"

    @classmethod
    def create(cls, **values: object) -> "HostAuthorityV2":
        targets = tuple(values.pop("profile_targets"))
        inventory = tuple(values.pop("inventory"))
        ordered_inventory = _sorted_unique_mappings(
            inventory, lambda item: item.mapping()
        )
        body = {
            "schema": cls.SCHEMA,
            **values,
            "profile_targets": [item.to_mapping() for item in targets],
            "inventory": ordered_inventory,
            "tool_inventory_hash": tool_inventory_hash(inventory),
            "hook_matcher_mode": "ENUMERATED",
        }
        return cls(
            **body,
            host_authority_digest=_domain_hash_lf(cls.DOMAIN, body),
        )

    def _validate(self) -> None:
        super()._validate()
        targets = self._value["profile_targets"]
        if (
            not isinstance(targets, list)
            or len(targets) != 10
            or [
                (item.get("role"), item.get("kind"), item.get("mode"))
                for item in targets
                if isinstance(item, dict)
            ] != list(_PROFILE_TARGET_SHAPE)
        ):
            raise ValueError("host profile targets are not exact")
        for item in targets:
            if set(item) != {"role", "path", "kind", "mode"}:
                raise ValueError("host profile target fields are not exact")
            validate_interpreter_path(item["path"])
        by_role = {item["role"]: item for item in targets}
        db = self._value["registration_db_path"]
        if (
            by_role["db"]["path"] != db
            or by_role["state_parent"]["path"] != str(Path(db).parent)
            or by_role["wal"]["path"] != db + "-wal"
            or by_role["shm"]["path"] != db + "-shm"
            or by_role["proof_parent"]["path"] != self._value["proof_parent"]
            or by_role["projection_parent"]["path"] != self._value["projection_parent"]
            or by_role["legacy_parent"]["path"] != self._value["legacy_parent"]
            or self._value["writer_capability_path"]
            != "authority/writer-capability.json"
            or self._value["hook_matcher_mode"] != "ENUMERATED"
        ):
            raise ValueError("host path relation is invalid")
        inventory = self._value["inventory"]
        if not isinstance(inventory, list) or not 1 <= len(inventory) <= 512:
            raise ValueError("host inventory is invalid")
        entries = tuple(InventoryEntry(**item) for item in inventory)
        if [item.mapping() for item in entries] != _sorted_unique_mappings(
            entries, lambda item: item.mapping()
        ):
            raise ValueError("host inventory order is invalid")
        if self._value["tool_inventory_hash"] != tool_inventory_hash(entries):
            raise ValueError("host inventory digest mismatch")
        for name in (
            "profile_hash", "runtime_capability_hash", "writer_binary_hash",
            "writer_capability_hash", "tool_inventory_hash",
            "hook_projection_hash", "hook_matcher_hash",
            "installer_identity_hash", "installer_capability_hash",
        ):
            _require_hash(self._value[name], name)
        for name in ("projection_file_generation", "protocol_generation", "storage_dev"):
            _require_decimal(self._value[name], name)
        body = self.to_mapping()
        claim = body.pop("host_authority_digest")
        if claim != _domain_hash_lf(self.DOMAIN, body):
            raise ValueError("host authority digest mismatch")


@dataclass(frozen=True)
class BundleRecordV3:
    relative_path: str
    kind: str
    mode: str
    size: str
    sha256: str

    def to_mapping(self) -> dict[str, str]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


class BundleManifestV3(_V7MappingAuthority):
    FIELDS = (
        "schema", "generation", "bundle_entry_plain_hash",
        "installed_file_hash", "import_manifest_hash",
        "host_authority_digest", "records", "record_count",
        "aggregate_size", "bundle_digest",
    )
    SCHEMA = "awa-registration-bundle-manifest/v3"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "bundle_digest"

    @classmethod
    def create(
        cls,
        *,
        generation: str,
        import_manifest: ImportManifestV2,
        host_authority: HostAuthorityV2,
        writer_capability_hash: str,
        installed_file_hash: str,
        payload_bytes: Mapping[str, bytes],
    ) -> "BundleManifestV3":
        _require_decimal(generation, "generation")
        _require_hash(writer_capability_hash, "writer_capability_hash")
        _require_hash(installed_file_hash, "installed_file_hash")
        if set(payload_bytes) != {
            record.relative_path for record in import_manifest.records
        }:
            raise ValueError("bundle payload set mismatch")
        records = [
            BundleRecordV3(
                record.relative_path,
                record.kind,
                "0444",
                record.size,
                record.sha256,
            )
            for record in import_manifest.records
        ]
        authorities = (
            ("authority/import-manifest.json", import_manifest.to_bytes()),
            (
                "authority/host-authority.json",
                host_authority.to_bytes(),
            ),
        )
        records.extend(
            BundleRecordV3(
                path, "AUTHORITY", "0444", str(len(raw)),
                hashlib.sha256(raw).hexdigest(),
            )
            for path, raw in authorities
        )
        records.append(
            BundleRecordV3(
                "authority/writer-capability.json", "AUTHORITY", "0444",
                "0", writer_capability_hash,
            )
        )
        ordered = sorted(records, key=lambda item: item.relative_path.encode())
        receiver = next(
            raw for path, raw in payload_bytes.items()
            if path == "engine/registration_receiver.py"
        )
        plain = hashlib.sha256(
            b"awa-registration-bundle-entry-plain/v1\0"
            + b"engine.registration_receiver\0"
            + receiver
        ).hexdigest()
        total = sum(int(record.size) for record in ordered)
        body = {
            "schema": cls.SCHEMA,
            "generation": generation,
            "bundle_entry_plain_hash": plain,
            "installed_file_hash": installed_file_hash,
            "import_manifest_hash": import_manifest.import_manifest_hash,
            "host_authority_digest": host_authority.host_authority_digest,
            "records": [record.to_mapping() for record in ordered],
            "record_count": str(len(ordered)),
            "aggregate_size": str(total),
        }
        return cls(**body, bundle_digest=_domain_hash_lf(cls.DOMAIN, body))

    def _validate(self) -> None:
        super()._validate()
        _require_decimal(self._value["generation"], "generation")
        for name in (
            "bundle_entry_plain_hash", "installed_file_hash",
            "import_manifest_hash", "host_authority_digest",
        ):
            _require_hash(self._value[name], name)
        if "bundle_relative_dir" in self._value:
            raise ValueError("bundle directory is derived, not manifest authority")
        records_value = self._value["records"]
        if not isinstance(records_value, list) or not records_value:
            raise ValueError("bundle records are invalid")
        expected_fields = {field.name for field in fields(BundleRecordV3)}
        records: list[BundleRecordV3] = []
        for value in records_value:
            if not isinstance(value, dict) or set(value) != expected_fields:
                raise ValueError("bundle record fields are not exact")
            record = BundleRecordV3(**value)
            _v9_relative_path(record.relative_path)
            if record.kind not in {
                "PACKAGE_INITIALIZER",
                "MODULE",
                "RESOURCE",
                "AUTHORITY",
            }:
                raise ValueError("bundle record kind is invalid")
            if record.mode != "0444":
                raise ValueError("bundle record mode is invalid")
            _require_decimal(record.size, "bundle record size")
            _require_hash(record.sha256, "bundle record sha256")
            records.append(record)
        ordered = sorted(
            records, key=lambda item: item.relative_path.encode("utf-8")
        )
        if (
            records != ordered
            or len({record.relative_path for record in records})
            != len(records)
            or self._value["record_count"] != str(len(records))
            or self._value["aggregate_size"]
            != str(sum(int(record.size) for record in records))
        ):
            raise ValueError("bundle record inventory is inconsistent")
        by_path = {record.relative_path: record for record in records}
        import_record = by_path.get("authority/import-manifest.json")
        host_record = by_path.get("authority/host-authority.json")
        writer_record = by_path.get("authority/writer-capability.json")
        if (
            import_record is None
            or host_record is None
            or writer_record is None
            or import_record.kind != "AUTHORITY"
            or host_record.kind != "AUTHORITY"
            or writer_record.kind != "AUTHORITY"
        ):
            raise ValueError("bundle authority inventory is incomplete")
        body = self.to_mapping()
        claim = body.pop("bundle_digest")
        if claim != _domain_hash_lf(self.DOMAIN, body):
            raise ValueError("bundle digest mismatch")

    @property
    def bundle_relative_dir(self) -> str:
        return f"versions/{self.generation}-{self.bundle_digest}"


# Historical test/API name; emitted and validated bytes are v3 only.
BundleManifestV2 = BundleManifestV3


class BundleProjectionV2(_V7MappingAuthority):
    FIELDS = (
        "schema", "generation", "bundle_digest", "import_manifest_hash",
        "host_authority_digest", "candidate_digest", "installed_file_hash",
        "wrapper_runtime_hash", "projection_file_generation",
        "protocol_generation", "bundle_projection_hash",
    )
    SCHEMA = "awa-registration-bundle-projection/v2"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "bundle_projection_hash"

    @classmethod
    def create(cls, **values: object) -> "BundleProjectionV2":
        body = {"schema": cls.SCHEMA, **values}
        return cls(
            **body,
            bundle_projection_hash=_domain_hash_lf(cls.DOMAIN, body),
        )

    def _validate(self) -> None:
        super()._validate()
        for name in ("generation", "projection_file_generation", "protocol_generation"):
            _require_decimal(self._value[name], name)
        for name in self.FIELDS:
            if name not in {
                "schema", "generation", "projection_file_generation",
                "protocol_generation", "bundle_projection_hash",
            }:
                _require_hash(self._value[name], name)
        body = self.to_mapping()
        claim = body.pop("bundle_projection_hash")
        if claim != _domain_hash_lf(self.DOMAIN, body):
            raise ValueError("bundle projection digest mismatch")


class RuntimeCurrentV2(_V7MappingAuthority):
    FIELDS = (
        "schema", "runtime_epoch", "active_manifest_sha256",
        "previous_manifest_sha256", "active_release_envelope_digest",
        "installed_at_wall_ns", "capability_digest",
        "qualification_packet_digest", "predecessor_runtime_current_digest",
        "runtime_current_digest",
    )
    SCHEMA = "awa-registration-private-runtime-current/v2"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "runtime_current_digest"

    @classmethod
    def create(cls, **values: object) -> "RuntimeCurrentV2":
        body = {"schema": cls.SCHEMA, **values}
        return cls(**body, runtime_current_digest=_domain_hash_lf(cls.DOMAIN, body))

    def _validate(self) -> None:
        super()._validate()
        _require_decimal(self._value["runtime_epoch"], "runtime_epoch")
        _require_decimal(self._value["installed_at_wall_ns"], "installed_at_wall_ns")
        first = self._value["runtime_epoch"] == "1"
        for name in self.FIELDS:
            if name in {"schema", "runtime_epoch", "installed_at_wall_ns", "runtime_current_digest"}:
                continue
            _require_hash(
                self._value[name], name,
                nullable=first and name in {
                    "previous_manifest_sha256",
                    "predecessor_runtime_current_digest",
                },
            )
        body = self.to_mapping()
        claim = body.pop("runtime_current_digest")
        if claim != _domain_hash_lf(self.DOMAIN, body):
            raise ValueError("runtime current digest mismatch")


class ProductCurrentV1(_V7MappingAuthority):
    FIELDS = (
        "schema", "selection_epoch", "bundle_generation",
        "bundle_relative_dir", "bundle_digest", "bundle_projection_hash",
        "direct_receipt_digest", "owner_gate_digest", "import_manifest_hash",
        "host_authority_digest", "runtime_current_digest",
        "predecessor_product_current_digest", "product_current_digest",
    )
    SCHEMA = "awa-registration-product-current/v1"
    DOMAIN = SCHEMA
    DIGEST_FIELD = "product_current_digest"

    @classmethod
    def create(cls, **values: object) -> "ProductCurrentV1":
        generation = values["bundle_generation"]
        digest = values["bundle_digest"]
        body = {
            "schema": cls.SCHEMA,
            **values,
            "bundle_relative_dir": f"versions/{generation}-{digest}",
        }
        return cls(**body, product_current_digest=_domain_hash_lf(cls.DOMAIN, body))

    def _validate(self) -> None:
        super()._validate()
        _require_decimal(self._value["selection_epoch"], "selection_epoch")
        _require_decimal(self._value["bundle_generation"], "bundle_generation")
        if self._value["bundle_relative_dir"] != (
            f"versions/{self._value['bundle_generation']}-"
            f"{self._value['bundle_digest']}"
        ):
            raise ValueError("product current bundle directory mismatch")
        first = self._value["selection_epoch"] == "1"
        for name in self.FIELDS:
            if name in {
                "schema", "selection_epoch", "bundle_generation",
                "bundle_relative_dir", "product_current_digest",
            }:
                continue
            _require_hash(
                self._value[name], name,
                nullable=first and name == "predecessor_product_current_digest",
            )
        body = self.to_mapping()
        claim = body.pop("product_current_digest")
        if claim != _domain_hash_lf(self.DOMAIN, body):
            raise ValueError("product current digest mismatch")


def retained_product_versions(
    selections: tuple[ProductCurrentV1, ...],
) -> frozenset[str]:
    if not selections:
        return frozenset()
    retained = [selections[-1].bundle_relative_dir]
    for item in reversed(selections[:-1]):
        if item.bundle_relative_dir != retained[0]:
            retained.append(item.bundle_relative_dir)
            break
    return frozenset(retained)
