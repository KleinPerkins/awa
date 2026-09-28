"""Closed RFC-8785-compatible JSON used by ADR 0025 authority rows.

Persisted registration blobs deliberately contain only strings, booleans,
nulls, arrays, and objects. Relational integers are encoded as canonical
decimal strings before hashing, avoiding JSON number portability.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


MAX_BLOB_BYTES = 65_536
MAX_DEPTH = 16
MAX_NODES = 512
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")

PROHIBITED_KEYS = frozenset(
    {
        "prompt",
        "attachment",
        "transcript",
        "model",
        "task_text",
        "tool_input",
        "file_content",
        "environment",
        "credential",
        "authorization",
        "cookie",
        "secret",
        "raw_path",
        "user_message",
    }
)
PROHIBITED_SENTINELS = (
    "BEGIN PRIVATE KEY",
    "Bearer ",
    "ghp_",
    "xox",
    "\x00",
)


class JcsError(ValueError):
    pass


def _reject_number(value: str) -> Any:
    raise JcsError(f"JSON numbers are forbidden: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JcsError(f"duplicate key: {key}")
        result[key] = value
    return result


def _valid_unicode(value: str) -> bool:
    return not any(0xD800 <= ord(char) <= 0xDFFF for char in value)


def _validate_tree(
    value: Any,
    *,
    enforce_privacy: bool,
    depth: int = 0,
    nodes: list[int] | None = None,
) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > MAX_NODES:
        raise JcsError("JCS node limit exceeded")
    if depth > MAX_DEPTH:
        raise JcsError("JCS depth limit exceeded")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if not _valid_unicode(value):
            raise JcsError("invalid Unicode scalar")
        if enforce_privacy and any(token in value for token in PROHIBITED_SENTINELS):
            raise JcsError("prohibited content")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or not _valid_unicode(key):
                raise JcsError("object keys must be Unicode strings")
            if enforce_privacy and key in PROHIBITED_KEYS:
                raise JcsError("prohibited key")
            _validate_tree(
                child,
                enforce_privacy=enforce_privacy,
                depth=depth + 1,
                nodes=nodes,
            )
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for child in value:
            _validate_tree(
                child,
                enforce_privacy=enforce_privacy,
                depth=depth + 1,
                nodes=nodes,
            )
        return
    raise JcsError(f"unsupported JCS value type: {type(value).__name__}")


def canonical_bytes(value: Any, *, enforce_privacy: bool = True) -> bytes:
    _validate_tree(value, enforce_privacy=enforce_privacy)
    try:
        data = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise JcsError("JCS encoding failed") from exc
    if len(data) > MAX_BLOB_BYTES:
        raise JcsError("JCS byte limit exceeded")
    return data


def parse_canonical(raw: bytes, *, enforce_privacy: bool = True) -> Any:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BLOB_BYTES:
        raise JcsError("invalid JCS byte length")
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_int=_reject_number,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except JcsError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise JcsError("invalid JCS") from exc
    _validate_tree(value, enforce_privacy=enforce_privacy)
    if canonical_bytes(value, enforce_privacy=enforce_privacy) != raw:
        raise JcsError("noncanonical JCS bytes")
    return value


_BLOB_SCHEMAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "action_plan": (
        "awa-registration-action-plan/v1",
        (
            "actions",
            "external_growth_reservation_bytes",
            "outcome_reservation_bytes",
            "successor_reservation_bytes",
        ),
    ),
    "observation": (
        "awa-registration-observation/v1",
        (
            "effect_id",
            "event_seq",
            "ordinal",
            "kind",
            "measured_postcondition_hash",
            "external_growth_bytes",
            "detail_code",
        ),
    ),
    "completion": (
        "awa-registration-completion/v1",
        (
            "effect_id",
            "action_count",
            "ledger_head_hash",
            "final_basis_hash",
        ),
    ),
    "proof": (
        "awa-registration-proof/v1",
        (
            "effect_id",
            "member_id",
            "physical_basis_hash",
            "git_basis_hash",
            "policy_basis_hash",
            "lifecycle_basis_hash",
            "final_basis_hash",
        ),
    ),
    "certificate_inputs": (
        "awa-registration-certificate-inputs/v1",
        (
            "effect_id",
            "ledger_head_hash",
            "completion_hash",
            "proof_hash",
            "final_basis_hash",
            "helper_generation",
        ),
    ),
    "conflict": (
        "awa-registration-conflict/v1",
        (
            "effect_id",
            "ordinal",
            "conflict_code",
            "expected_hash",
            "observed_hash",
        ),
    ),
}

_ACTION_KINDS = (
    "PUBLISH_EFFECT_PROOF",
    "CONVERGE_LEGACY_LEASE",
    "CONVERGE_LEGACY_LIFECYCLE",
    "COLLECT_FINAL_BASIS",
)


def _validate_hash(value: Any, field: str) -> None:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise JcsError(f"{field} must be lowercase 64-hex")


def _validate_decimal(value: Any, field: str) -> None:
    if not isinstance(value, str) or DECIMAL.fullmatch(value) is None:
        raise JcsError(f"{field} must be canonical unsigned decimal")


def _derived_blob_object(kind: str, relation: Mapping[str, Any]) -> dict[str, Any]:
    try:
        schema, fields = _BLOB_SCHEMAS[kind]
    except KeyError as exc:
        raise JcsError(f"unknown blob kind: {kind}") from exc
    if set(relation) != set(fields):
        raise JcsError("relational blob field mismatch")
    result: dict[str, Any] = {"schema": schema}
    for field in fields:
        result[field] = relation[field]

    if kind == "action_plan":
        actions = result["actions"]
        if not isinstance(actions, list) or len(actions) != 4:
            raise JcsError("action plan must contain exactly four actions")
        for index, action in enumerate(actions, 1):
            if not isinstance(action, dict) or set(action) != {
                "ordinal",
                "kind",
                "action_hash",
                "postcondition_hash",
            }:
                raise JcsError("invalid action object")
            if action["ordinal"] != str(index) or action["kind"] != _ACTION_KINDS[index - 1]:
                raise JcsError("action order mismatch")
            _validate_hash(action["action_hash"], "action_hash")
            _validate_hash(action["postcondition_hash"], "postcondition_hash")
        for field in (
            "external_growth_reservation_bytes",
            "outcome_reservation_bytes",
            "successor_reservation_bytes",
        ):
            _validate_decimal(result[field], field)
    else:
        for field, value in result.items():
            if field == "schema":
                continue
            if field.endswith("_hash") or field.endswith("_id"):
                _validate_hash(value, field)
            elif field in {
                "event_seq",
                "ordinal",
                "external_growth_bytes",
                "action_count",
                "helper_generation",
            }:
                _validate_decimal(value, field)
            elif not isinstance(value, str):
                raise JcsError(f"{field} must be a string")
    _validate_tree(result, enforce_privacy=True)
    return result


def encode_blob(kind: str, relation: Mapping[str, Any]) -> bytes:
    return canonical_bytes(_derived_blob_object(kind, relation))


def validate_blob(
    kind: str, raw: bytes, relation: Mapping[str, Any]
) -> dict[str, Any]:
    expected = _derived_blob_object(kind, relation)
    parsed = parse_canonical(raw)
    if not isinstance(parsed, dict) or parsed != expected:
        raise JcsError("blob does not equal relational derivation")
    if raw != canonical_bytes(expected):
        raise JcsError("blob byte encoding mismatch")
    return parsed


def _row_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0:
            return str(value)
        return str(value)
    raise JcsError(f"unsupported relational hash value: {type(value).__name__}")


def row_hash(
    domain: str, columns: tuple[str, ...], row: Mapping[str, Any]
) -> str:
    if not domain or "\x00" in domain:
        raise JcsError("invalid row hash domain")
    if len(columns) != len(set(columns)):
        raise JcsError("duplicate row hash column")
    missing = [column for column in columns if column not in row]
    if missing:
        raise JcsError(f"missing row hash columns: {missing}")
    value = {column: _row_value(row[column]) for column in columns}
    return hashlib.sha256(
        domain.encode("ascii", "strict") + b"\0" + canonical_bytes(value)
    ).hexdigest()
