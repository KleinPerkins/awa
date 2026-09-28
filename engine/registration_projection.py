"""Body C closed inventory, hook projection, and DIRECT receipt authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
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
        return cls(**{field: value[field] for field in DIRECT_RECEIPT_FIELDS})

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
