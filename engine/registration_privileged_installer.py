"""Protected private-runtime authority and synthetic privileged lifecycle.

The pure validators and in-memory backend are the ordinary verification
surface.  They make no privileged call and never write a production path.
Native authorization and real qualification remain separately gated.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Iterable, Mapping


PRODUCTION_ROOT = "/Library/Application Support/AWA"
QUALIFICATION_ROOT_PREFIX = (
    "/Library/Application Support/AWA-qualification-"
)
ROOT_ADMIN_PATH = PRODUCTION_ROOT + "/bin/awa-private-runtime-admin"
OWNER_NAMESPACE = "awa-private-runtime-release-envelope-v1"
OWNER_GATE_NAMESPACE = "awa-registration-owner-gate-v3"
QUALIFICATION_NAMESPACE = "awa-private-runtime-qualification-release-v1"
SOURCE_LOCK_SHA256 = (
    "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
)
OWNER_V1_SHA256 = (
    "9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e"
)
OWNER_V2_SHA256 = (
    "690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3"
)
OWNER_PUBLIC_KEY_SHA256 = (
    "ccc9283906c612aed388f23bf5ef26f16a0a780926a447dbe8c7e71a94b4df63"
)
OWNER_FINGERPRINT = (
    "SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M"
)
OWNER_PUBLIC_KEY = (
    "AAAAC3NzaC1lZDI1NTE5AAAAIE+scgn2qp86lkQWcVDpJ+SXT/pVF0DntlxGVnmnFyEp"
)
OWNER_V1_BYTES = (
    'KleinPerkins namespaces="awa-registration-owner-gate-v2" '
    f"ssh-ed25519 {OWNER_PUBLIC_KEY}\n"
).encode("ascii")
OWNER_V2_BYTES = (
    'KleinPerkins namespaces="awa-private-runtime-release-envelope-v1,'
    'awa-registration-owner-gate-v3" '
    f"ssh-ed25519 {OWNER_PUBLIC_KEY}\n"
).encode("ascii")

OPERATIONS = ("INSTALL", "UPDATE", "ROLLBACK", "REMOVE", "QUALIFY")
OUTCOMES = ("SUCCESS", "REFUSED", "FAILED", "CANCELLED")
REFUSAL_CODES = frozenset(
    {
        "ARGUMENT_INVALID",
        "AUTHORITY_INVALID",
        "CONTEXT_MISMATCH",
        "EPOCH_MISMATCH",
        "LOCKED",
        "MODE_ROOT_MISMATCH",
        "NONCE_REPLAY",
        "OPERATION_INVALID",
        "PACKET_ROOT_MISMATCH",
        "SIGNATURE_INVALID",
        "STATE_INVALID",
    }
)
FAILURE_CODES = frozenset(
    {
        "AUDIT_FAILED",
        "CLEANUP_FAILED",
        "FILESYSTEM_FAILED",
        "INTERNAL_FAILED",
        "SPAWN_FAILED",
    }
)
PARTIAL_STATES = (
    "NONE",
    "STAGED_UNPUBLISHED",
    "VERSION_PUBLISHED",
    "CURRENT_PUBLISHED",
    "REMOVAL_IN_PROGRESS",
)
TERMINALS = (
    "FAILED_CLEANED",
    "FAILED_RESIDUE",
    "NO_ROOT_PROCESS",
    "REFUSED_BEFORE_WRITE",
    "SUCCESS_COMMITTED",
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UINT = re.compile(r"^(?:0|[1-9][0-9]*)$")
REQUEST_FIELDS = (
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
)
CURRENT_FIELDS = (
    "schema",
    "epoch",
    "active_manifest_sha256",
    "previous_manifest_sha256",
    "active_release_envelope_digest",
    "installed_at_wall_ns",
    "installer_audit_digest",
    "predecessor_current_digest",
    "current_digest",
)
AUDIT_FIELDS = (
    "schema",
    "mode",
    "receipt_origin",
    "request_id",
    "operation",
    "requested_uid",
    "target_root",
    "packet_root_digest",
    "qualification_context_digest",
    "qualification_allowed_signers_digest",
    "pre_epoch",
    "post_epoch",
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
    "envelope_sha256",
    "owner_signature_sha256",
    "synthetic_signature_sha256",
    "state_machine_terminal",
    "outcome",
    "reason_code",
    "predecessor_audit_digest",
    "root_receipt_link_digest",
    "partial_stage_state",
    "cleanup_digest",
    "installed_paths_hash",
    "removed_paths_hash",
    "started_wall_ns",
    "completed_wall_ns",
    "receipt_digest",
)
EXACT_ROOT_DIRECTORIES = (
    "/Library",
    "/Library/Application Support",
    PRODUCTION_ROOT,
    PRODUCTION_ROOT + "/bin",
    PRODUCTION_ROOT + "/bootstrap",
    PRODUCTION_ROOT + "/bootstrap/v1",
    PRODUCTION_ROOT + "/runtime",
    PRODUCTION_ROOT + "/runtime/audit",
    PRODUCTION_ROOT + "/runtime/locks",
    PRODUCTION_ROOT + "/runtime/versions",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_json_value(value: object, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int:
        if value < 0 or value > (1 << 64) - 1:
            raise ValueError(f"{path}: integer outside unsigned 64-bit")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"{path}: non-text object key")
        for key, child in value.items():
            _validate_json_value(child, f"{path}.{key}")
        return
    raise ValueError(f"{path}: unsupported JSON type {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    _validate_json_value(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_lf_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def authority_digest(
    domain: str, value: Mapping[str, object], *, terminal_lf: bool = True
) -> str:
    framed = canonical_bytes(dict(value))
    if terminal_lf:
        framed += b"\n"
    return _sha256(domain.encode("ascii") + b"\0" + framed)


def _parse_canonical_lf(raw: bytes) -> dict:
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\x00" in raw
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        raise ValueError("authority framing refused")

    def pairs(rows: list[tuple[str, object]]) -> dict:
        value: dict[str, object] = {}
        for key, item in rows:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    value = json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_float=lambda _: (_ for _ in ()).throw(
            ValueError("floats are forbidden")
        ),
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("non-finite numbers are forbidden")
        ),
    )
    if not isinstance(value, dict) or canonical_lf_bytes(value) != raw:
        raise ValueError("authority is not a canonical JCS+LF object")
    return value


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _require_hex_or_null(name: str, value: object) -> None:
    if value is not None and not _is_hex64(value):
        raise ValueError(f"{name} must be lowercase 64-hex or null")


def _require_uint(name: str, value: object, *, positive: bool = False) -> int:
    if not isinstance(value, str) or UINT.fullmatch(value) is None:
        raise ValueError(f"{name} must be canonical unsigned decimal text")
    number = int(value)
    if number > (1 << 64) - 1 or (positive and number == 0):
        raise ValueError(f"{name} is outside its unsigned range")
    return number


def _parse_allowed_signers(raw: bytes, *, expected: bytes) -> dict:
    if raw != expected:
        raise ValueError("allowed-signers bytes differ from frozen contract")
    line = raw.decode("ascii").rstrip("\n")
    principal, namespace_field, algorithm, encoded = line.split(" ")
    prefix = 'namespaces="'
    if not namespace_field.startswith(prefix) or not namespace_field.endswith('"'):
        raise ValueError("allowed-signers namespace field malformed")
    namespaces = tuple(namespace_field[len(prefix) : -1].split(","))
    wire = base64.b64decode(encoded, validate=True)
    fingerprint = base64.b64encode(hashlib.sha256(wire).digest()).decode(
        "ascii"
    ).rstrip("=")
    return {
        "principal": principal,
        "namespaces": namespaces,
        "algorithm": algorithm,
        "public_key_openssh": f"{algorithm} {encoded}",
        "public_key_sha256": _sha256(wire),
        "openssh_fingerprint": "SHA256:" + fingerprint,
    }


def validate_owner_signers_v1(raw: bytes) -> dict:
    if _sha256(raw) != OWNER_V1_SHA256:
        raise ValueError("owner-signers v1 hash mismatch")
    return _parse_allowed_signers(raw, expected=OWNER_V1_BYTES)


def validate_owner_signers_v2(raw: bytes) -> dict:
    if _sha256(raw) != OWNER_V2_SHA256:
        raise ValueError("owner-signers v2 hash mismatch")
    value = _parse_allowed_signers(raw, expected=OWNER_V2_BYTES)
    if (
        value["namespaces"] != (OWNER_NAMESPACE, OWNER_GATE_NAMESPACE)
        or value["public_key_sha256"] != OWNER_PUBLIC_KEY_SHA256
        or value["openssh_fingerprint"] != OWNER_FINGERPRINT
    ):
        raise ValueError("owner-signers v2 public authority mismatch")
    return value


@dataclass(frozen=True)
class PrivilegedRequest:
    schema: str
    mode: str
    operation: str
    requested_uid: str
    request_id: str
    target_root: str
    packet_root_digest: str
    qualification_context_digest: str | None
    qualification_allowed_signers_digest: str | None
    pre_current_digest: str | None
    target_release_envelope_digest: str | None
    target_manifest_sha256: str | None
    target_epoch: str | None
    previous_manifest_sha256: str | None
    current_manifest_sha256: str | None
    new_manifest_sha256: str | None
    q1_envelope_digest: str | None
    q1_manifest_sha256: str | None
    q2_envelope_digest: str | None
    q2_manifest_sha256: str | None
    created_wall_ns: str
    expires_wall_ns: str
    request_digest: str

    @classmethod
    def create(cls, **values: object) -> "PrivilegedRequest":
        body = {"schema": "awa-registration-privileged-request/v1", **values}
        if set(body) != set(REQUEST_FIELDS) - {"request_digest"}:
            missing = (set(REQUEST_FIELDS) - {"request_digest"}) - set(body)
            extra = set(body) - (set(REQUEST_FIELDS) - {"request_digest"})
            raise ValueError(f"privileged request fields: missing={missing} extra={extra}")
        body["request_digest"] = authority_digest(
            "awa-registration-privileged-request/v1", body
        )
        return cls.from_mapping(body)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "PrivilegedRequest":
        if set(mapping) != set(REQUEST_FIELDS):
            raise ValueError("privileged request field set mismatch")
        value = cls(**{field.name: mapping[field.name] for field in fields(cls)})
        value.validate()
        return value

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PrivilegedRequest":
        return cls.from_mapping(_parse_canonical_lf(raw))

    @classmethod
    def synthetic_qualification(
        cls,
        *,
        operation: str,
        requested_uid: str,
        request_id: str,
        qualification_nonce: str,
        packet_root_digest: str,
        qualification_context_digest: str,
        qualification_allowed_signers_digest: str,
        current: "CurrentRecord | None",
        q1_envelope_digest: str,
        q1_manifest_sha256: str,
        q2_envelope_digest: str,
        q2_manifest_sha256: str,
        created_wall_ns: str,
    ) -> "PrivilegedRequest":
        created = _require_uint("created_wall_ns", created_wall_ns)
        root = QUALIFICATION_ROOT_PREFIX + qualification_nonce
        pre = current.current_digest if current else None
        previous = current.active_manifest_sha256 if current else None
        target_envelope: str | None
        target_manifest: str | None
        target_epoch: str | None
        current_manifest: str | None
        new_manifest: str | None
        if operation == "INSTALL":
            target_envelope = q1_envelope_digest
            target_manifest = q1_manifest_sha256
            target_epoch = "1"
            previous = None
            current_manifest = q1_manifest_sha256
            new_manifest = q1_manifest_sha256
        elif operation == "UPDATE":
            target_envelope = q2_envelope_digest
            target_manifest = q2_manifest_sha256
            target_epoch = str(int(current.epoch) + 1) if current else "2"
            current_manifest = q2_manifest_sha256
            new_manifest = q2_manifest_sha256
        elif operation == "ROLLBACK":
            target_envelope = q1_envelope_digest
            target_manifest = q1_manifest_sha256
            target_epoch = str(int(current.epoch) + 1) if current else "3"
            current_manifest = q1_manifest_sha256
            new_manifest = None
        elif operation == "REMOVE":
            target_envelope = None
            target_manifest = None
            target_epoch = str(int(current.epoch) + 1) if current else "4"
            current_manifest = None
            new_manifest = None
        elif operation == "QUALIFY":
            target_envelope = target_manifest = target_epoch = None
            previous = current_manifest = new_manifest = None
        else:
            raise ValueError("synthetic operation is not in the closed enum")
        return cls.create(
            mode="QUALIFY",
            operation=operation,
            requested_uid=requested_uid,
            request_id=request_id,
            target_root=root,
            packet_root_digest=packet_root_digest,
            qualification_context_digest=qualification_context_digest,
            qualification_allowed_signers_digest=qualification_allowed_signers_digest,
            pre_current_digest=pre,
            target_release_envelope_digest=target_envelope,
            target_manifest_sha256=target_manifest,
            target_epoch=target_epoch,
            previous_manifest_sha256=previous,
            current_manifest_sha256=current_manifest,
            new_manifest_sha256=new_manifest,
            q1_envelope_digest=q1_envelope_digest,
            q1_manifest_sha256=q1_manifest_sha256,
            q2_envelope_digest=q2_envelope_digest,
            q2_manifest_sha256=q2_manifest_sha256,
            created_wall_ns=created_wall_ns,
            expires_wall_ns=str(created + 900_000_000_000),
        )

    def validate(self) -> None:
        if self.schema != "awa-registration-privileged-request/v1":
            raise ValueError("privileged request schema mismatch")
        if self.mode not in {"PRODUCTION", "QUALIFY"}:
            raise ValueError("privileged request mode refused")
        if self.operation not in OPERATIONS:
            raise ValueError("privileged request operation refused")
        _require_uint("requested_uid", self.requested_uid)
        if not _is_hex64(self.request_id):
            raise ValueError("request ID must be lowercase 64-hex")
        if not _is_hex64(self.packet_root_digest):
            raise ValueError("packet root digest malformed")
        for name in (
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
            _require_hex_or_null(name, getattr(self, name))
        if self.target_epoch is not None:
            _require_uint("target_epoch", self.target_epoch, positive=True)
        created = _require_uint("created_wall_ns", self.created_wall_ns)
        expires = _require_uint("expires_wall_ns", self.expires_wall_ns)
        if expires <= created or expires - created > 900_000_000_000:
            raise ValueError("privileged request expiry window refused")
        if self.mode == "PRODUCTION":
            if self.target_root != PRODUCTION_ROOT:
                raise ValueError("production mode/root mismatch")
            qualification = (
                self.qualification_context_digest,
                self.qualification_allowed_signers_digest,
                self.q1_envelope_digest,
                self.q1_manifest_sha256,
                self.q2_envelope_digest,
                self.q2_manifest_sha256,
            )
            if any(item is not None for item in qualification):
                raise ValueError("production request contains qualification authority")
        else:
            suffix = self.target_root.removeprefix(QUALIFICATION_ROOT_PREFIX)
            if not _is_hex64(suffix):
                raise ValueError("qualification mode/root mismatch")
            if any(
                item is None
                for item in (
                    self.qualification_context_digest,
                    self.qualification_allowed_signers_digest,
                    self.q1_envelope_digest,
                    self.q1_manifest_sha256,
                    self.q2_envelope_digest,
                    self.q2_manifest_sha256,
                )
            ):
                raise ValueError("qualification bindings are incomplete")
        body = self.to_mapping()
        claimed = body.pop("request_digest")
        expected = authority_digest(
            "awa-registration-privileged-request/v1", body
        )
        if claimed != expected:
            raise ValueError("privileged request digest mismatch")

    @property
    def digest(self) -> str:
        return self.request_digest

    def to_mapping(self) -> dict:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def to_bytes(self) -> bytes:
        return canonical_lf_bytes(self.to_mapping())

    def replace(self, **changes: object) -> "PrivilegedRequest":
        mapping = self.to_mapping()
        mapping.update(changes)
        mapping.pop("request_digest", None)
        return self.create(**{key: value for key, value in mapping.items() if key != "schema"})


@dataclass(frozen=True)
class ValidationContext:
    operation: str
    request_digest: str
    now_wall_ns: str
    signature_valid: bool
    path_metadata_valid: bool
    packet_root_digest: str
    qualification_context_digest: str | None
    qualification_allowed_signers_digest: str | None

    @classmethod
    def synthetic(cls, **values: object) -> "ValidationContext":
        return cls(**values)


@dataclass(frozen=True)
class ValidationDecision:
    allowed: bool
    decision: str
    denial_class: str | None
    reason_code: str


def validate_privileged_request(
    request: PrivilegedRequest, context: ValidationContext
) -> ValidationDecision:
    """Pure validation over captured bytes/scalars; performs no syscall."""

    expected_checks = (
        (
            context.operation == request.operation,
            "OPERATION_MISMATCH",
        ),
        (
            context.request_digest == request.request_digest,
            "REQUEST_DIGEST_MISMATCH",
        ),
        (
            context.packet_root_digest == request.packet_root_digest,
            "PACKET_ROOT_MISMATCH",
        ),
        (
            context.qualification_context_digest
            == request.qualification_context_digest,
            "QUALIFICATION_CONTEXT_MISMATCH",
        ),
        (
            context.qualification_allowed_signers_digest
            == request.qualification_allowed_signers_digest,
            "QUALIFICATION_TRUST_MISMATCH",
        ),
    )
    for accepted, reason in expected_checks:
        if not accepted:
            return ValidationDecision(
                False, "REFUSE", "EXPECTED_MISMATCH", reason
            )
    now = _require_uint("now_wall_ns", context.now_wall_ns)
    if now < int(request.created_wall_ns) or now > int(request.expires_wall_ns):
        return ValidationDecision(
            False, "REFUSE", "EXPECTED_MISMATCH", "REQUEST_EXPIRED"
        )
    if not context.signature_valid:
        return ValidationDecision(
            False, "REFUSE", "OBSERVED_DRIFT", "SIGNATURE_INVALID"
        )
    if not context.path_metadata_valid:
        return ValidationDecision(
            False, "REFUSE", "OBSERVED_DRIFT", "PATH_METADATA_DRIFT"
        )
    return ValidationDecision(True, "ALLOW", None, "VALIDATED")


def inline_bootstrap_source() -> bytes:
    """Return exact reviewed root-admin bytes used as inline bootstrap B."""

    path = Path(__file__).resolve().parents[1] / "kernel/bin/awa-private-runtime-admin.py"
    raw = path.read_bytes()
    if b"\r" in raw or b"\x00" in raw or not raw.endswith(b"\n"):
        raise ValueError("inline bootstrap source framing refused")
    return raw


def inline_bootstrap_program(source: bytes | None = None) -> str:
    raw = inline_bootstrap_source() if source is None else source
    encoded = base64.b64encode(raw).decode("ascii")
    return (
        "import base64;exec(compile(base64.b64decode('"
        + encoded
        + "'),'<awa-inline-bootstrap>','exec'))"
    )


def _applescript_literal(value: str) -> str:
    if "\r" in value or "\x00" in value:
        raise ValueError("AppleScript literal contains forbidden bytes")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_initial_authorization_script(
    source: bytes | None = None,
) -> str:
    program = _applescript_literal(inline_bootstrap_program(source))
    return (
        "on run argv\n"
        '  if (count of argv) is not 2 then error "AWA_ARGV_REFUSED" number 1708\n'
        "  set uidText to item 1 of argv\n"
        "  set requestText to item 2 of argv\n"
        f'  set pyCode to "{program}"\n'
        '  set commandText to "/usr/bin/env -i LANG=C LC_ALL=C '
        '/usr/bin/python3 -I -S -B -c " & quoted form of pyCode & " " & '
        "quoted form of uidText & \" \" & quoted form of requestText\n"
        "  try\n"
        "    do shell script commandText with administrator privileges\n"
        "  on error errorMessage number errorNumber\n"
        '    if errorNumber is -128 then error "AWA_AUTH_CANCELLED" number 1708\n'
        '    error "AWA_AUTH_FAILED" number 1708\n'
        "  end try\n"
        "end run\n"
    )


def _validate_uid_request(requested_uid: str, request_id: str) -> None:
    _require_uint("requested_uid", requested_uid)
    if len(requested_uid) > 10 or not _is_hex64(request_id):
        raise ValueError("UID/request ID refused")


def render_initial_osascript_argv(
    requested_uid: str, request_id: str, source: bytes | None = None
) -> tuple[str, ...]:
    _validate_uid_request(requested_uid, request_id)
    return (
        "/usr/bin/osascript",
        "-l",
        "AppleScript",
        "-e",
        render_initial_authorization_script(source),
        "--",
        requested_uid,
        request_id,
    )


def render_admin_authorization_script() -> str:
    return (
        "on run argv\n"
        '  if (count of argv) is not 3 then error "AWA_ARGV_REFUSED" number 1708\n'
        "  set operationText to item 1 of argv\n"
        "  set uidText to item 2 of argv\n"
        "  set requestText to item 3 of argv\n"
        f'  set adminPath to "{ROOT_ADMIN_PATH}"\n'
        '  set commandText to "/usr/bin/env -i LANG=C LC_ALL=C " & '
        'quoted form of adminPath & " " & quoted form of operationText & " " & '
        'quoted form of uidText & " " & quoted form of requestText\n'
        "  try\n"
        "    do shell script commandText with administrator privileges\n"
        "  on error errorMessage number errorNumber\n"
        '    if errorNumber is -128 then error "AWA_AUTH_CANCELLED" number 1708\n'
        '    error "AWA_AUTH_FAILED" number 1708\n'
        "  end try\n"
        "end run\n"
    )


@dataclass(frozen=True)
class RenderDecision:
    decision: str
    reason_code: str
    shell_argv: tuple[str, ...] | None
    osascript_argv: tuple[str, ...] | None


def render_admin_command(
    *, operation: str, requested_uid: str, request_id: str
) -> RenderDecision:
    try:
        _validate_uid_request(requested_uid, request_id)
    except ValueError:
        return RenderDecision("REFUSE", "ARGUMENT_INVALID", None, None)
    if operation not in OPERATIONS:
        return RenderDecision("REFUSE", "OPERATION_INVALID", None, None)
    shell = (
        "/usr/bin/env",
        "-i",
        "LANG=C",
        "LC_ALL=C",
        ROOT_ADMIN_PATH,
        operation,
        requested_uid,
        request_id,
    )
    script = render_admin_authorization_script()
    osascript = (
        "/usr/bin/osascript",
        "-l",
        "AppleScript",
        "-e",
        script,
        "--",
        operation,
        requested_uid,
        request_id,
    )
    return RenderDecision("ALLOW", "VALIDATED", shell, osascript)


def build_qualification_allowed_signers(
    *,
    exact_head: str,
    qualification_nonce: str,
    public_key_openssh: str,
) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", exact_head):
        raise ValueError("qualification exact head malformed")
    if not _is_hex64(qualification_nonce):
        raise ValueError("qualification nonce malformed")
    parts = public_key_openssh.split(" ")
    if len(parts) != 2 or parts[0] != "ssh-ed25519":
        raise ValueError("qualification public key must be bare ssh-ed25519")
    wire = base64.b64decode(parts[1], validate=True)
    wire_sha = _sha256(wire)
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(wire).digest()
    ).decode("ascii").rstrip("=")
    line = (
        'AWAQualification namespaces="'
        + QUALIFICATION_NAMESPACE
        + '" '
        + public_key_openssh
        + "\n"
    )
    body = {
        "schema": "awa-registration-qualification-allowed-signers/v1",
        "mode": "QUALIFY",
        "repository": "KleinPerkins/awa",
        "exact_head": exact_head,
        "qualification_nonce": qualification_nonce,
        "qualification_root": QUALIFICATION_ROOT_PREFIX + qualification_nonce,
        "principal": "AWAQualification",
        "namespaces": [QUALIFICATION_NAMESPACE],
        "key_algorithm": "ssh-ed25519",
        "public_key_openssh": public_key_openssh,
        "public_key_wire_sha256": wire_sha,
        "openssh_fingerprint": fingerprint,
        "allowed_signers_line": line,
        "allowed_signers_sha256": _sha256(line.encode("ascii")),
    }
    body["contract_digest"] = authority_digest(
        "awa-registration-qualification-allowed-signers/v1", body
    )
    return body


Q_MARKERS = {
    "Q1": (
        "1",
        b"AWA-QUALIFICATION-Q1\n",
        "c01efa502dabedbfe5d9d1a7cfff4f186e74d99ffa2e9f9c6c1a9fa8b529e541",
    ),
    "Q2": (
        "2",
        b"AWA-QUALIFICATION-Q2\n",
        "6b80282df498fa05da5ff173e56e701c54cc093841041c10cc4a47e4fe657fc3",
    ),
}


def build_synthetic_qualification_fixture(
    *,
    fixture: str,
    exact_head: str,
    qualification_nonce: str,
    qualification_root: str,
    runtime_digest: str,
    qualification_allowed_signers_digest: str,
    synthetic_signature: bytes,
) -> dict:
    if fixture not in Q_MARKERS:
        raise ValueError("qualification fixture must be Q1 or Q2")
    if qualification_root != QUALIFICATION_ROOT_PREFIX + qualification_nonce:
        raise ValueError("qualification fixture root/nonce mismatch")
    epoch, marker, marker_sha = Q_MARKERS[fixture]
    if _sha256(marker) != marker_sha or len(marker) != 21:
        raise ValueError("qualification marker invariant failed")
    manifest_body = {
        "schema": "awa-registration-qualification-fixture-manifest/v1",
        "fixture_id": fixture,
        "epoch": epoch,
        "runtime_archive_sha256": runtime_digest,
        "marker": {
            "path": "qualification/MARKER",
            "mode": "0444",
            "size": "21",
            "sha256": marker_sha,
        },
    }
    manifest_body["manifest_digest"] = authority_digest(
        manifest_body["schema"], manifest_body
    )
    envelope_body = {
        "schema": "awa-private-runtime-qualification-release-envelope/v1",
        "repository": "KleinPerkins/awa",
        "mode": "QUALIFY",
        "exact_head": exact_head,
        "qualification_nonce": qualification_nonce,
        "qualification_root": qualification_root,
        "fixture_id": fixture,
        "epoch": epoch,
        "runtime_archive_sha256": runtime_digest,
        "fixture_manifest_digest": manifest_body["manifest_digest"],
        "marker_sha256": marker_sha,
        "qualification_allowed_signers_digest": qualification_allowed_signers_digest,
    }
    envelope_body["release_envelope_digest"] = authority_digest(
        envelope_body["schema"], envelope_body
    )
    return {
        "fixture_id": fixture,
        "epoch": epoch,
        "marker_bytes_base64": base64.b64encode(marker).decode("ascii"),
        "manifest": manifest_body,
        "envelope": envelope_body,
        "signature_namespace": QUALIFICATION_NAMESPACE,
        "synthetic_signature_sha256": _sha256(synthetic_signature),
    }


def qualification_fixture_digest(value: Mapping[str, object]) -> str:
    return authority_digest("awa-registration-qualification-fixture/v1", value)


@dataclass(frozen=True)
class CurrentRecord:
    schema: str
    epoch: str
    active_manifest_sha256: str
    previous_manifest_sha256: str | None
    active_release_envelope_digest: str
    installed_at_wall_ns: str
    installer_audit_digest: str
    predecessor_current_digest: str
    current_digest: str

    @classmethod
    def create(
        cls,
        *,
        epoch: str,
        active_manifest_sha256: str,
        previous_manifest_sha256: str | None,
        active_release_envelope_digest: str,
        installed_at_wall_ns: str,
        installer_audit_digest: str,
        predecessor_current_digest: str,
    ) -> "CurrentRecord":
        body = {
            "schema": "awa-private-runtime-current/v1",
            "epoch": epoch,
            "active_manifest_sha256": active_manifest_sha256,
            "previous_manifest_sha256": previous_manifest_sha256,
            "active_release_envelope_digest": active_release_envelope_digest,
            "installed_at_wall_ns": installed_at_wall_ns,
            "installer_audit_digest": installer_audit_digest,
            "predecessor_current_digest": predecessor_current_digest,
        }
        body["current_digest"] = authority_digest(
            "awa-private-runtime-current/v1", body
        )
        value = cls(**body)
        value.validate()
        return value

    def validate(self) -> None:
        if self.schema != "awa-private-runtime-current/v1":
            raise ValueError("current schema mismatch")
        _require_uint("epoch", self.epoch, positive=True)
        _require_uint("installed_at_wall_ns", self.installed_at_wall_ns)
        for name in (
            "active_manifest_sha256",
            "active_release_envelope_digest",
            "installer_audit_digest",
            "predecessor_current_digest",
            "current_digest",
        ):
            if not _is_hex64(getattr(self, name)):
                raise ValueError(f"current {name} malformed")
        _require_hex_or_null(
            "previous_manifest_sha256", self.previous_manifest_sha256
        )
        body = self.to_mapping()
        claimed = body.pop("current_digest")
        if claimed != authority_digest("awa-private-runtime-current/v1", body):
            raise ValueError("current digest mismatch")

    def to_mapping(self) -> dict:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def to_bytes(self) -> bytes:
        return canonical_lf_bytes(self.to_mapping())

    @property
    def file_sha256(self) -> str:
        return _sha256(self.to_bytes())

    @property
    def version_root(self) -> str:
        return (
            PRODUCTION_ROOT
            + "/runtime/versions/"
            + self.active_manifest_sha256
        )


def _paths_hash(paths: Iterable[str]) -> str:
    framed = b"".join(
        path.encode("utf-8") + b"\n"
        for path in sorted(set(paths), key=lambda item: item.encode("utf-8"))
    )
    return _sha256(b"awa-registration-admin-paths/v1\0" + framed)


def _audit_null_fields(
    operation: str,
    outcome: str,
    *,
    mode: str,
    partial_state: str = "NONE",
    first_root_receipt: bool = True,
) -> frozenset[str]:
    nulls: set[str] = set()
    if mode == "PRODUCTION":
        nulls.update(
            {
                "qualification_context_digest",
                "qualification_allowed_signers_digest",
                "synthetic_signature_sha256",
                "q1_envelope_digest",
                "q1_manifest_sha256",
                "q2_envelope_digest",
                "q2_manifest_sha256",
            }
        )
    else:
        nulls.add("owner_signature_sha256")
    if operation in {"INSTALL", "QUALIFY"}:
        nulls.add("pre_current_digest")
    if operation in {"REMOVE", "QUALIFY"}:
        nulls.update(
            {"target_release_envelope_digest", "target_manifest_sha256"}
        )
    if operation == "QUALIFY":
        nulls.add("target_epoch")
    if outcome == "SUCCESS":
        if operation == "INSTALL":
            nulls.add("previous_manifest_sha256")
        elif operation in {"UPDATE"}:
            pass
        elif operation == "ROLLBACK":
            nulls.add("new_manifest_sha256")
        elif operation == "REMOVE":
            nulls.update(
                {"current_manifest_sha256", "new_manifest_sha256"}
            )
        elif operation == "QUALIFY":
            nulls.update(
                {
                    "previous_manifest_sha256",
                    "current_manifest_sha256",
                    "new_manifest_sha256",
                }
            )
    else:
        if operation in {"INSTALL", "QUALIFY"}:
            nulls.update(
                {
                    "previous_manifest_sha256",
                    "current_manifest_sha256",
                    "new_manifest_sha256",
                }
            )
        elif operation in {"UPDATE", "ROLLBACK", "REMOVE"}:
            nulls.update({"current_manifest_sha256", "new_manifest_sha256"})
        if outcome != "FAILED" or partial_state != "CURRENT_PUBLISHED":
            nulls.add("post_epoch")
    if outcome == "CANCELLED":
        nulls.update(
            {
                "post_epoch",
                "predecessor_audit_digest",
                "root_receipt_link_digest",
                "partial_stage_state",
                "cleanup_digest",
                "installed_paths_hash",
                "removed_paths_hash",
            }
        )
    else:
        if first_root_receipt:
            nulls.add("predecessor_audit_digest")
    return frozenset(nulls)


ADMIN_AUDIT_MATRIX = {
    (operation, outcome): _audit_null_fields(
        operation,
        outcome,
        mode="QUALIFY" if operation == "QUALIFY" else "PRODUCTION",
    )
    for operation in OPERATIONS
    for outcome in OUTCOMES
}


class AdminAuditReceipt:
    def __init__(self, value: Mapping[str, object]):
        self._value = dict(value)

    def __getattr__(self, name: str) -> object:
        if name in self._value:
            return self._value[name]
        raise AttributeError(name)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, AdminAuditReceipt) and self._value == other._value

    def to_mapping(self) -> dict:
        return dict(self._value)

    def to_bytes(self) -> bytes:
        return canonical_lf_bytes(self._value)

    def null_fields(self) -> frozenset[str]:
        return frozenset(
            key for key, value in self._value.items() if value is None
        )

    def validate(self) -> None:
        if set(self._value) != set(AUDIT_FIELDS):
            raise ValueError("admin audit field set mismatch")
        if self.schema != "awa-registration-admin-audit-receipt/v1":
            raise ValueError("admin audit schema mismatch")
        if self.mode not in {"PRODUCTION", "QUALIFY"}:
            raise ValueError("admin audit mode mismatch")
        if self.operation not in OPERATIONS or self.outcome not in OUTCOMES:
            raise ValueError("admin audit enum mismatch")
        if self.partial_stage_state is not None and self.partial_stage_state not in PARTIAL_STATES:
            raise ValueError("admin audit partial state mismatch")
        if self.state_machine_terminal not in TERMINALS:
            raise ValueError("admin audit terminal mismatch")
        if self.outcome == "SUCCESS" and self.reason_code != "OK":
            raise ValueError("successful admin audit reason must be OK")
        if self.outcome == "REFUSED" and self.reason_code not in REFUSAL_CODES:
            raise ValueError("refused admin audit reason mismatch")
        if self.outcome == "FAILED" and self.reason_code not in FAILURE_CODES:
            raise ValueError("failed admin audit reason mismatch")
        if self.outcome == "CANCELLED" and self.reason_code != "AUTH_CANCELLED":
            raise ValueError("cancelled admin audit reason mismatch")
        body = self.to_mapping()
        claimed = body.pop("receipt_digest")
        if claimed != authority_digest(
            "awa-registration-admin-audit-receipt/v1", body
        ):
            raise ValueError("admin audit receipt digest mismatch")
        expected = _audit_null_fields(
            self.operation,
            self.outcome,
            mode=self.mode,
            partial_state=self.partial_stage_state or "NONE",
            first_root_receipt=self.predecessor_audit_digest is None,
        )
        if self.null_fields() != expected:
            raise ValueError(
                f"admin audit null matrix mismatch: {self.null_fields()} != {expected}"
            )

    @classmethod
    def synthetic_for_matrix(
        cls, row: tuple[str, str]
    ) -> "AdminAuditReceipt":
        operation, outcome = row
        mode = "QUALIFY" if operation == "QUALIFY" else "PRODUCTION"
        nulls = ADMIN_AUDIT_MATRIX[row]
        value: dict[str, object] = {
            field: "1" * 64 for field in AUDIT_FIELDS
        }
        value.update(
            {
                "schema": "awa-registration-admin-audit-receipt/v1",
                "mode": mode,
                "receipt_origin": (
                    "CLIENT_AUTH" if outcome == "CANCELLED" else "ROOT_ADMIN"
                ),
                "request_id": "1" * 64,
                "operation": operation,
                "requested_uid": "501",
                "target_root": (
                    QUALIFICATION_ROOT_PREFIX + "2" * 64
                    if mode == "QUALIFY"
                    else PRODUCTION_ROOT
                ),
                "pre_epoch": "0" if operation in {"INSTALL", "QUALIFY"} else "1",
                "post_epoch": (
                    "4"
                    if operation == "QUALIFY"
                    else "1"
                ),
                "target_epoch": "1",
                "state_machine_terminal": {
                    "SUCCESS": "SUCCESS_COMMITTED",
                    "REFUSED": "REFUSED_BEFORE_WRITE",
                    "FAILED": "FAILED_CLEANED",
                    "CANCELLED": "NO_ROOT_PROCESS",
                }[outcome],
                "outcome": outcome,
                "reason_code": {
                    "SUCCESS": "OK",
                    "REFUSED": "STATE_INVALID",
                    "FAILED": "FILESYSTEM_FAILED",
                    "CANCELLED": "AUTH_CANCELLED",
                }[outcome],
                "partial_stage_state": "NONE",
                "started_wall_ns": "1",
                "completed_wall_ns": "2",
            }
        )
        for field in nulls:
            value[field] = None
        body = dict(value)
        body.pop("receipt_digest")
        value["receipt_digest"] = authority_digest(
            "awa-registration-admin-audit-receipt/v1", body
        )
        receipt = cls(value)
        receipt.validate()
        return receipt


@dataclass(frozen=True)
class PathMetadata:
    owner: str = "root"
    group: str = "wheel"
    mode: str = "755"
    symlink: bool = False
    link_count: int = 1


@dataclass(frozen=True)
class BackendSnapshot:
    current: CurrentRecord | None
    runtime_roots: dict[str, bytes]
    managed_roots: frozenset[str]
    directories: tuple[str, ...]
    metadata: dict[str, PathMetadata]
    trust_material: dict[str, bytes]


class SyntheticBackendFault(RuntimeError):
    pass


class MemoryAdminBackend:
    """In-memory root backend; it cannot touch the host filesystem."""

    FAULT_POINTS = (
        "stage:write",
        "payload:sync",
        "version:publish",
        "current:replace",
        "parent:sync",
        "audit:append",
    )

    def __init__(self) -> None:
        self.current: CurrentRecord | None = None
        self.runtime_roots: dict[str, bytes] = {}
        self.managed_roots: set[str] = set()
        self.directories = EXACT_ROOT_DIRECTORIES
        self.metadata = {
            path: PathMetadata() for path in EXACT_ROOT_DIRECTORIES
        }
        self.trust_material = {
            "owner-signers-v2": OWNER_V2_BYTES,
        }
        self.events: list[str] = []
        self.fail_at: str | None = None
        self.receipts: dict[str, AdminAuditReceipt] = {}
        self.request_digests: dict[str, str] = {}
        self.clock = 10

    def checkpoint(self, event: str) -> None:
        self.events.append(event)
        if self.fail_at == event:
            raise SyntheticBackendFault(event)

    def snapshot(self) -> BackendSnapshot:
        return BackendSnapshot(
            self.current,
            copy.deepcopy(self.runtime_roots),
            frozenset(self.managed_roots),
            tuple(self.directories),
            copy.deepcopy(self.metadata),
            copy.deepcopy(self.trust_material),
        )

    def restore(self, snapshot: BackendSnapshot) -> None:
        self.current = snapshot.current
        self.runtime_roots = copy.deepcopy(snapshot.runtime_roots)
        self.managed_roots = set(snapshot.managed_roots)

    def tick(self) -> str:
        self.clock += 1
        return str(self.clock)


class PrivateRuntimeInstaller:
    def __init__(self, backend: MemoryAdminBackend):
        if not isinstance(backend, MemoryAdminBackend):
            raise TypeError("ordinary verification requires MemoryAdminBackend")
        self.backend = backend

    def _receipt(
        self,
        request: PrivilegedRequest,
        *,
        outcome: str,
        reason: str,
        pre: CurrentRecord | None,
        post: CurrentRecord | None,
        installed: Iterable[str] = (),
        removed: Iterable[str] = (),
    ) -> AdminAuditReceipt:
        nulls = _audit_null_fields(
            request.operation,
            outcome,
            mode=request.mode,
        )
        value: dict[str, object] = {
            "schema": "awa-registration-admin-audit-receipt/v1",
            "mode": request.mode,
            "receipt_origin": (
                "CLIENT_AUTH" if outcome == "CANCELLED" else "ROOT_ADMIN"
            ),
            "request_id": request.request_id,
            "operation": request.operation,
            "requested_uid": request.requested_uid,
            "target_root": request.target_root,
            "packet_root_digest": request.packet_root_digest,
            "qualification_context_digest": request.qualification_context_digest,
            "qualification_allowed_signers_digest": request.qualification_allowed_signers_digest,
            "pre_epoch": pre.epoch if pre else "0",
            "post_epoch": (
                post.epoch
                if post
                else (
                    request.target_epoch
                    if outcome == "SUCCESS"
                    and request.operation == "REMOVE"
                    else None
                )
            ),
            "pre_current_digest": pre.current_digest if pre else None,
            "target_release_envelope_digest": request.target_release_envelope_digest,
            "target_manifest_sha256": request.target_manifest_sha256,
            "target_epoch": request.target_epoch,
            "previous_manifest_sha256": request.previous_manifest_sha256,
            "current_manifest_sha256": (
                post.active_manifest_sha256 if post else None
            ),
            "new_manifest_sha256": request.new_manifest_sha256,
            "q1_envelope_digest": request.q1_envelope_digest,
            "q1_manifest_sha256": request.q1_manifest_sha256,
            "q2_envelope_digest": request.q2_envelope_digest,
            "q2_manifest_sha256": request.q2_manifest_sha256,
            "envelope_sha256": _sha256(request.to_bytes()),
            "owner_signature_sha256": (
                "a" * 64 if request.mode == "PRODUCTION" else None
            ),
            "synthetic_signature_sha256": (
                "b" * 64 if request.mode == "QUALIFY" else None
            ),
            "state_machine_terminal": {
                "SUCCESS": "SUCCESS_COMMITTED",
                "REFUSED": "REFUSED_BEFORE_WRITE",
                "FAILED": "FAILED_CLEANED",
                "CANCELLED": "NO_ROOT_PROCESS",
            }[outcome],
            "outcome": outcome,
            "reason_code": reason,
            "predecessor_audit_digest": None,
            "root_receipt_link_digest": request.request_digest,
            "partial_stage_state": "NONE",
            "cleanup_digest": _sha256(b"synthetic-cleanup"),
            "installed_paths_hash": _paths_hash(installed),
            "removed_paths_hash": _paths_hash(removed),
            "started_wall_ns": self.backend.tick(),
            "completed_wall_ns": self.backend.tick(),
        }
        for name in nulls:
            value[name] = None
        body = dict(value)
        value["receipt_digest"] = authority_digest(
            "awa-registration-admin-audit-receipt/v1", body
        )
        receipt = AdminAuditReceipt(value)
        receipt.validate()
        return receipt

    def _refuse(
        self,
        request: PrivilegedRequest,
        reason: str,
        pre: CurrentRecord | None,
    ) -> AdminAuditReceipt:
        receipt = self._receipt(
            request,
            outcome="REFUSED",
            reason=reason,
            pre=pre,
            post=None,
        )
        self.backend.receipts[request.request_id] = receipt
        return receipt

    def apply(self, request: PrivilegedRequest) -> AdminAuditReceipt:
        request.validate()
        prior_digest = self.backend.request_digests.get(request.request_id)
        if prior_digest is not None:
            if prior_digest == request.request_digest:
                return self.backend.receipts[request.request_id]
            return self._refuse(request, "NONCE_REPLAY", self.backend.current)
        self.backend.request_digests[request.request_id] = request.request_digest
        pre = self.backend.current
        if request.operation == "QUALIFY":
            return self._refuse(request, "STATE_INVALID", pre)
        if request.operation == "INSTALL":
            if pre is not None:
                return self._refuse(request, "STATE_INVALID", pre)
            if request.target_epoch != "1":
                return self._refuse(request, "EPOCH_MISMATCH", pre)
        else:
            if pre is None:
                return self._refuse(request, "STATE_INVALID", pre)
            if request.pre_current_digest != pre.current_digest:
                return self._refuse(request, "CONTEXT_MISMATCH", pre)
            if int(request.target_epoch or "0") != int(pre.epoch) + 1:
                return self._refuse(request, "EPOCH_MISMATCH", pre)
        if request.operation == "ROLLBACK" and (
            pre is None
            or pre.previous_manifest_sha256 is None
            or request.target_manifest_sha256
            != pre.previous_manifest_sha256
        ):
            return self._refuse(request, "STATE_INVALID", pre)

        snapshot = self.backend.snapshot()
        installed: list[str] = []
        removed: list[str] = []
        try:
            target = request.target_manifest_sha256
            if request.operation in {"INSTALL", "UPDATE"}:
                assert target is not None
                self.backend.checkpoint("stage:write")
                self.backend.checkpoint("payload:sync")
                self.backend.runtime_roots[target] = (
                    b"synthetic-private-runtime:" + target.encode("ascii")
                )
                self.backend.managed_roots.add(target)
                self.backend.checkpoint("version:publish")
                installed.append(
                    PRODUCTION_ROOT + "/runtime/versions/" + target
                )
            audit_seed = authority_digest(
                "awa-registration-synthetic-installer-audit/v1",
                {"request_digest": request.request_digest},
            )
            if request.operation == "REMOVE":
                for digest in sorted(self.backend.managed_roots):
                    removed.append(
                        PRODUCTION_ROOT + "/runtime/versions/" + digest
                    )
                    self.backend.runtime_roots.pop(digest, None)
                self.backend.managed_roots.clear()
                post = None
            else:
                assert target is not None
                if request.operation == "ROLLBACK":
                    previous = pre.active_manifest_sha256  # type: ignore[union-attr]
                else:
                    previous = (
                        pre.active_manifest_sha256 if pre is not None else None
                    )
                post = CurrentRecord.create(
                    epoch=request.target_epoch or "1",
                    active_manifest_sha256=target,
                    previous_manifest_sha256=previous,
                    active_release_envelope_digest=(
                        request.target_release_envelope_digest or "c" * 64
                    ),
                    installed_at_wall_ns=self.backend.tick(),
                    installer_audit_digest=audit_seed,
                    predecessor_current_digest=(
                        pre.current_digest if pre is not None else "0" * 64
                    ),
                )
                keep = {target}
                if previous is not None:
                    keep.add(previous)
                for digest in tuple(self.backend.managed_roots):
                    if digest not in keep:
                        self.backend.runtime_roots.pop(digest, None)
                        self.backend.managed_roots.remove(digest)
            self.backend.checkpoint("current:replace")
            self.backend.current = post
            self.backend.checkpoint("parent:sync")
            receipt = self._receipt(
                request,
                outcome="SUCCESS",
                reason="OK",
                pre=pre,
                post=post,
                installed=installed,
                removed=removed,
            )
            self.backend.checkpoint("audit:append")
            self.backend.receipts[request.request_id] = receipt
            return receipt
        except SyntheticBackendFault:
            self.backend.restore(snapshot)
            receipt = self._receipt(
                request,
                outcome="FAILED",
                reason="FILESYSTEM_FAILED",
                pre=pre,
                post=None,
            )
            self.backend.receipts[request.request_id] = receipt
            return receipt


class QualificationLifecycle:
    """One-root Q1→Q2→Q1→remove synthetic qualification orchestrator."""

    def __init__(self, installer: PrivateRuntimeInstaller) -> None:
        self.installer = installer

    def run(
        self,
        parent: PrivilegedRequest,
        operations: Iterable[PrivilegedRequest],
    ) -> tuple[AdminAuditReceipt, tuple[AdminAuditReceipt, ...]]:
        parent.validate()
        if parent.mode != "QUALIFY" or parent.operation != "QUALIFY":
            raise ValueError("qualification parent request refused")
        children = tuple(operations)
        if tuple(request.operation for request in children) != (
            "INSTALL",
            "UPDATE",
            "ROLLBACK",
            "REMOVE",
        ):
            raise ValueError("qualification lifecycle sequence refused")
        common_fields = (
            "requested_uid",
            "target_root",
            "packet_root_digest",
            "qualification_context_digest",
            "qualification_allowed_signers_digest",
            "q1_envelope_digest",
            "q1_manifest_sha256",
            "q2_envelope_digest",
            "q2_manifest_sha256",
        )
        for request in children:
            request.validate()
            if (
                request.mode != "QUALIFY"
                or any(
                    getattr(request, field) != getattr(parent, field)
                    for field in common_fields
                )
            ):
                raise ValueError("qualification child binding mismatch")
        receipts: list[AdminAuditReceipt] = []
        expected = (
            ("INSTALL", "1", parent.q1_manifest_sha256),
            ("UPDATE", "2", parent.q2_manifest_sha256),
            ("ROLLBACK", "3", parent.q1_manifest_sha256),
            ("REMOVE", "4", None),
        )
        for request, (operation, epoch, manifest) in zip(
            children, expected, strict=True
        ):
            receipt = self.installer.apply(request)
            if (
                receipt.outcome != "SUCCESS"
                or receipt.operation != operation
                or receipt.post_epoch != epoch
                or receipt.current_manifest_sha256 != manifest
            ):
                raise ValueError("qualification child lifecycle failed")
            receipts.append(receipt)
        if self.installer.backend.current is not None:
            raise ValueError("qualification root remained active")
        template = AdminAuditReceipt.synthetic_for_matrix(
            ("QUALIFY", "SUCCESS")
        ).to_mapping()
        template.update(
            {
                "mode": "QUALIFY",
                "receipt_origin": "ROOT_ADMIN",
                "request_id": parent.request_id,
                "operation": "QUALIFY",
                "requested_uid": parent.requested_uid,
                "target_root": parent.target_root,
                "packet_root_digest": parent.packet_root_digest,
                "qualification_context_digest": (
                    parent.qualification_context_digest
                ),
                "qualification_allowed_signers_digest": (
                    parent.qualification_allowed_signers_digest
                ),
                "pre_epoch": "0",
                "post_epoch": "4",
                "pre_current_digest": None,
                "target_release_envelope_digest": None,
                "target_manifest_sha256": None,
                "target_epoch": None,
                "previous_manifest_sha256": None,
                "current_manifest_sha256": None,
                "new_manifest_sha256": None,
                "q1_envelope_digest": parent.q1_envelope_digest,
                "q1_manifest_sha256": parent.q1_manifest_sha256,
                "q2_envelope_digest": parent.q2_envelope_digest,
                "q2_manifest_sha256": parent.q2_manifest_sha256,
                "envelope_sha256": _sha256(parent.to_bytes()),
                "owner_signature_sha256": None,
                "synthetic_signature_sha256": "b" * 64,
                "state_machine_terminal": "SUCCESS_COMMITTED",
                "outcome": "SUCCESS",
                "reason_code": "OK",
                "predecessor_audit_digest": receipts[-1].receipt_digest,
                "root_receipt_link_digest": parent.request_digest,
                "partial_stage_state": "NONE",
                "cleanup_digest": _sha256(b"qualification-cleanup"),
                "installed_paths_hash": _paths_hash(()),
                "removed_paths_hash": _paths_hash(()),
                "started_wall_ns": self.installer.backend.tick(),
                "completed_wall_ns": self.installer.backend.tick(),
            }
        )
        body = dict(template)
        body.pop("receipt_digest")
        template["receipt_digest"] = authority_digest(
            "awa-registration-admin-audit-receipt/v1", body
        )
        parent_receipt = AdminAuditReceipt(template)
        parent_receipt.validate()
        self.installer.backend.receipts[parent.request_id] = parent_receipt
        return parent_receipt, tuple(receipts)


PACKET_ROOT_ROLES = frozenset(
    {
        "INLINE_BOOTSTRAP_B",
        "INITIAL_APPLESCRIPT",
        "ADMIN_APPLESCRIPT",
        "INITIAL_SHELL_TEMPLATE",
        "ADMIN_SHELL_TEMPLATE",
        "INITIAL_COMMAND",
        "ADMIN_INSTALL_COMMAND",
        "ADMIN_UPDATE_COMMAND",
        "ADMIN_ROLLBACK_COMMAND",
        "ADMIN_REMOVE_COMMAND",
        "ADMIN_QUALIFY_COMMAND",
        "QUALIFICATION_ALLOWED_SIGNERS",
        "ROOT_ADMIN",
        "ROOT_ENTRYPOINT",
        "PLATFORM_BOOTSTRAP",
        "CHILD_BOOTSTRAP",
        "STATIC_CONTRACT",
        "SOURCE_LOCK",
        "ATTESTATION_BUNDLE",
        "ATTESTATION_PAYLOAD",
        "ATTESTATION_CERTIFICATE",
        "SHA256SUMS",
        "PYTHON_JSON",
        "Q1_MANIFEST",
        "Q1_ENVELOPE",
        "Q1_SIGNATURE",
        "Q2_MANIFEST",
        "Q2_ENVELOPE",
        "Q2_SIGNATURE",
        "NORMALIZER_SOURCE",
        "SIGNING_RECIPE_SOURCE",
        "BUILD_MANIFEST",
        "BUILD_SIGNATURE_INVENTORY",
        "BUILD_TRANSCRIPT",
        "BUILD_ARCHIVE",
        "BUILD_SBOM",
        "BUILD_LICENSE_INVENTORY",
        "TEST_STDOUT",
        "TEST_STDERR",
        "TREE_COMPARISON",
        "ARCHIVE_COMPARISON",
        "LOADED_IMAGES",
        "DEPENDENCY_ESCAPES",
        "PURE_VALIDATOR_REJECTION_EVIDENCE",
    }
)
BOUND_ROLES = frozenset({"PRIVILEGED_REQUEST", "PRIVILEGED_CONTEXT"})
EVIDENCE_ROLES = frozenset(
    {
        "AUTHORIZATION_RESULT",
        "OPERATION_STDOUT",
        "OPERATION_STDERR",
        "CLEANUP_RESULT",
        "SECURITYAGENT_STDOUT",
        "SECURITYAGENT_STDERR",
        "PARENT_DEATH_EVIDENCE",
        "PARENT_DEATH_SYSCALL_TRACE",
        "PARENT_DEATH_OPERATOR_MESSAGES",
    }
)


class QualificationPacketBuilder:
    """Three-index, content-addressed packet assembler for bounded fixtures."""

    def __init__(
        self,
        *,
        exact_head: str,
        accepted_digest: str,
        c_runtime_scope_hash: str,
    ) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", exact_head):
            raise ValueError("packet exact head malformed")
        if not _is_hex64(accepted_digest) or not _is_hex64(c_runtime_scope_hash):
            raise ValueError("packet plan/scope digest malformed")
        self.exact_head = exact_head
        self.accepted_digest = accepted_digest
        self.c_runtime_scope_hash = c_runtime_scope_hash
        self._blobs: dict[str, bytes] = {}
        self._roles: dict[str, str] = {}
        self._root: list[dict] = []
        self._bound: list[dict] = []
        self._evidence: list[dict] = []
        self._packet_root: str | None = None

    def _add(
        self,
        *,
        collection: str,
        role: str,
        domain: str,
        content: bytes,
        media_type: str,
        encoding: str,
    ) -> str:
        allowed = {
            "root": PACKET_ROOT_ROLES,
            "bound": BOUND_ROLES,
            "evidence": EVIDENCE_ROLES,
        }[collection]
        if role not in allowed:
            raise ValueError(f"role {role!r} is not allowed in {collection}")
        if collection == "root" and b"packet_root_digest" in content:
            raise ValueError("packet-root blob may not contain packet root digest")
        if encoding not in {"BINARY", "UTF8", "UTF8_LF", "JCS_LF"}:
            raise ValueError("packet blob encoding refused")
        digest = _sha256(content)
        if digest in self._roles:
            raise ValueError("one content digest may not alias packet roles")
        self._roles[digest] = role
        self._blobs[digest] = bytes(content)
        prefix = "inputs" if collection != "evidence" else "evidence"
        record = {
            "path": f"{prefix}/sha256/{digest}",
            "role": role,
            "domain": domain,
            "size": str(len(content)),
            "sha256": digest,
            "mode": "0444",
            "media_type": media_type,
            "encoding": encoding,
        }
        if collection != "root":
            if self._packet_root is None:
                raise ValueError("packet root must be final before bound/evidence")
            record["packet_root_digest"] = self._packet_root
        getattr(self, f"_{collection}").append(record)
        return digest

    def add_packet_root_blob(
        self,
        *,
        role: str,
        domain: str,
        content: bytes,
        media_type: str = "application/octet-stream",
        encoding: str = "BINARY",
    ) -> str:
        if self._packet_root is not None:
            raise ValueError("packet root is already final")
        return self._add(
            collection="root",
            role=role,
            domain=domain,
            content=content,
            media_type=media_type,
            encoding=encoding,
        )

    def _index(
        self, *, schema: str, domain: str, records: list[dict], root_bound: bool
    ) -> tuple[dict, bytes]:
        body: dict[str, object] = {
            "schema": schema,
            "records": sorted(
                records,
                key=lambda row: (
                    row["path"].encode("utf-8"),
                    row["role"].encode("utf-8"),
                ),
            ),
        }
        if root_bound:
            body["packet_root_digest"] = self._packet_root
        body["index_digest"] = authority_digest(domain, body)
        return body, canonical_lf_bytes(body)

    def finalize_packet_root(self) -> str:
        if self._packet_root is not None:
            return self._packet_root
        index, _ = self._index(
            schema=(
                "awa-registration-private-runtime-qualification-"
                "packet-root-index/v1"
            ),
            domain=(
                "awa-registration-private-runtime-qualification-"
                "packet-root/v1"
            ),
            records=self._root,
            root_bound=False,
        )
        self._packet_root = index["index_digest"]
        return self._packet_root

    def add_bound_blob(self, **values: object) -> str:
        return self._add(collection="bound", **values)  # type: ignore[arg-type]

    def add_evidence_blob(self, **values: object) -> str:
        return self._add(collection="evidence", **values)  # type: ignore[arg-type]

    def finalize(self) -> dict:
        self.finalize_packet_root()
        root, root_bytes = self._index(
            schema=(
                "awa-registration-private-runtime-qualification-"
                "packet-root-index/v1"
            ),
            domain=(
                "awa-registration-private-runtime-qualification-"
                "packet-root/v1"
            ),
            records=self._root,
            root_bound=False,
        )
        bound, bound_bytes = self._index(
            schema=(
                "awa-registration-private-runtime-qualification-"
                "bound-input-index/v1"
            ),
            domain=(
                "awa-registration-private-runtime-qualification-"
                "bound-input-root/v1"
            ),
            records=self._bound,
            root_bound=True,
        )
        evidence, evidence_bytes = self._index(
            schema=(
                "awa-registration-private-runtime-qualification-"
                "evidence-index/v1"
            ),
            domain=(
                "awa-registration-private-runtime-qualification-"
                "evidence-root/v1"
            ),
            records=self._evidence,
            root_bound=True,
        )
        return {
            "packet_root_index": root,
            "packet_root_index_bytes": root_bytes,
            "packet_root_digest": root["index_digest"],
            "bound_index": bound,
            "bound_index_bytes": bound_bytes,
            "bound_index_digest": bound["index_digest"],
            "evidence_index": evidence,
            "evidence_index_bytes": evidence_bytes,
            "evidence_index_digest": evidence["index_digest"],
            "blobs": dict(self._blobs),
        }


V8_STATIC_CONTRACT_HASHES = {
    "contracts/awa-contract.v1.json":
        "408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9",
    "contracts/awa-contract.v2.json":
        "db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a",
    "contracts/awa-contract.v3.json":
        "fdc093ae25f868a50b7e3025a6554626baf7beeff987c9e9f0b92044d0de36b9",
    "contracts/awa-contract.v4.json":
        "f3d2e32295b0ce46f1611dbd062174b1075b309a0d81e08007b2a0f391694ae3",
    "contracts/awa-registration-admin-audit.v1.json":
        "a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a",
    "contracts/awa-registration-admin-audit.v2.json":
        "b5daa0798f5f5ed049806662b89fa22b98b37d2a163188de449ca9003b4882e2",
    "contracts/awa-registration-admin-audit.v3.json":
        "f9cd88d74b1d3e6171ae4859efde7ee7934f09118a7aa56cf1fa73ec62937efa",
    "contracts/awa-registration-owner-signers.v1":
        "9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e",
    "contracts/awa-registration-owner-signers.v2":
        "690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3",
    "contracts/awa-registration-platform-bootstrap.v1.json":
        "4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c",
    "contracts/awa-registration-platform-bootstrap.v2.json":
        "404267a5e0e444a82ae662dedaaad94661cc8fb3a349d4da4eb0523ae6fa28b9",
    "contracts/awa-registration-platform-bootstrap.v3.json":
        "ce82d498500b183e308791f12db85d2b3ddbc3f6b0b2d132ad0c6de1165628f0",
    "contracts/awa-registration-private-runtime.v1.json":
        "f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321",
    "contracts/awa-registration-private-runtime.v2.json":
        "91fc77c3aef7d8bf5b563993c3ae2c8766205a41cb6a23b735259805c485d4a8",
    "contracts/awa-registration-private-runtime.v3.json":
        "29fc38b6fac0ce9edda4a6ea01156b180c4b48f8d6b52b68e58addd269cb1a84",
    "contracts/awa-registration-privileged-envelope.v1.json":
        "7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034",
}


@dataclass(frozen=True)
class AdminAssetRecordV1:
    role: str
    logical_name: str
    content_path: str
    size: str
    mode: str
    sha256: str
    signature_digest: str | None
    request_id: str
    qualification_nonce: str | None
    context_digest: str

    def __post_init__(self) -> None:
        if not self.role or not self.logical_name or not self.content_path.startswith("/"):
            raise ValueError("admin asset identity is invalid")
        if UINT.fullmatch(self.size) is None or self.mode not in {"0444", "0555"}:
            raise ValueError("admin asset metadata is invalid")
        for value in (self.sha256, self.request_id, self.context_digest):
            if HEX64.fullmatch(value) is None:
                raise ValueError("admin asset digest is invalid")
        for value in (self.signature_digest, self.qualification_nonce):
            if value is not None and HEX64.fullmatch(value) is None:
                raise ValueError("admin asset optional digest is invalid")
        expected = (
            "/Library/Application Support/AWA-admin/v2/staging/sha256/"
            f"{self.sha256[:2]}/{self.sha256}.blob"
        )
        if self.content_path != expected:
            raise ValueError("admin asset path is not content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AdminAssetRecordV1":
        if set(value) != {field.name for field in fields(cls)}:
            raise ValueError("admin asset fields are not exact")
        return cls(**dict(value))


@dataclass(frozen=True)
class AdminAssetIndexV1:
    schema: str
    mode: str
    request_id: str
    operation: str
    qualification_nonce: str | None
    records: tuple[AdminAssetRecordV1, ...]
    record_count: str
    aggregate_size: str
    asset_index_digest: str

    @classmethod
    def create(
        cls,
        *,
        mode: str,
        request_id: str,
        operation: str,
        qualification_nonce: str | None,
        records: tuple[AdminAssetRecordV1, ...],
    ) -> "AdminAssetIndexV1":
        if mode not in {"PRODUCTION", "QUALIFY"} or operation not in OPERATIONS:
            raise ValueError("admin asset index mode/operation is invalid")
        if HEX64.fullmatch(request_id) is None:
            raise ValueError("admin asset request id is invalid")
        if (mode == "PRODUCTION" and qualification_nonce is not None) or (
            mode == "QUALIFY"
            and (
                qualification_nonce is None
                or HEX64.fullmatch(qualification_nonce) is None
            )
        ):
            raise ValueError("admin asset qualification nonce is invalid")
        ordering = tuple(
            sorted(
                records,
                key=lambda item: (
                    item.role.encode(), item.logical_name.encode()
                ),
            )
        )
        if records != ordering or len(set(
            (item.role, item.logical_name) for item in records
        )) != len(records):
            raise ValueError("admin asset records are not exact ordered set")
        if any(
            item.request_id != request_id
            or item.qualification_nonce != qualification_nonce
            for item in records
        ):
            raise ValueError("admin asset duplicated binding mismatch")
        static = {
            item.logical_name: item.sha256
            for item in records
            if item.role == "STATIC_CONTRACT_SET"
        }
        if static != V8_STATIC_CONTRACT_HASHES:
            raise ValueError("admin static contract set mismatch")
        body = {
            "schema": "awa-registration-admin-asset-index/v1",
            "mode": mode,
            "request_id": request_id,
            "operation": operation,
            "qualification_nonce": qualification_nonce,
            "records": [item.to_mapping() for item in records],
            "record_count": str(len(records)),
            "aggregate_size": str(sum(int(item.size) for item in records)),
        }
        return cls(
            **{**body, "records": records},
            asset_index_digest=authority_digest(
                "awa-registration-admin-asset-index/v1", body
            ),
        )

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "mode": self.mode,
            "request_id": self.request_id,
            "operation": self.operation,
            "qualification_nonce": self.qualification_nonce,
            "records": [item.to_mapping() for item in self.records],
            "record_count": self.record_count,
            "aggregate_size": self.aggregate_size,
            "asset_index_digest": self.asset_index_digest,
        }

    def to_bytes(self) -> bytes:
        return canonical_lf_bytes(self.to_mapping())

    @classmethod
    def from_bytes(cls, raw: bytes) -> "AdminAssetIndexV1":
        value = json.loads(raw)
        claim = value.pop("asset_index_digest")
        records = tuple(AdminAssetRecordV1.from_mapping(item) for item in value.pop("records"))
        result = cls.create(records=records, **{
            key: value[key]
            for key in ("mode", "request_id", "operation", "qualification_nonce")
        })
        if result.asset_index_digest != claim or result.to_bytes() != raw:
            raise ValueError("admin asset index digest/framing mismatch")
        return result


class _AdminMapping:
    FIELDS: tuple[str, ...] = ()
    DOMAIN = ""
    DIGEST_FIELD = ""

    def __init__(self, **values: object):
        if set(values) != set(self.FIELDS):
            raise ValueError("admin authority fields are not exact")
        self._value = dict(values)

    def __getattr__(self, name: str) -> object:
        if name in self._value:
            return self._value[name]
        raise AttributeError(name)

    def to_mapping(self) -> dict[str, object]:
        return dict(self._value)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object], *, verify_digest: bool = True):
        result = cls(**dict(value))
        if verify_digest:
            body = result.to_mapping()
            claim = body.pop(cls.DIGEST_FIELD)
            if claim != authority_digest(cls.DOMAIN, body):
                raise ValueError("admin authority digest mismatch")
        return result


class AdminTransactionV1(_AdminMapping):
    FIELDS = (
        "schema", "mode", "request_id", "operation", "qualification_nonce",
        "request_digest", "context_digest", "asset_index_digest",
        "pre_head_digest", "pre_runtime_current_digest",
        "pre_product_current_digest", "phase", "outcome",
        "target_direct_receipt_digest", "admin_receipt_digest",
        "result_runtime_current_digest", "result_product_current_digest",
        "predecessor_transaction_digest", "transaction_digest",
    )
    DOMAIN = "awa-registration-admin-transaction/v1"
    DIGEST_FIELD = "transaction_digest"


class AdminAuditReceiptV2(_AdminMapping):
    FIELDS = (
        "schema", "mode", "operation", "outcome", "reason_code",
        "qualification_nonce", "asset_index_digest", "transaction_digest",
        "runtime_current_digest", "product_current_digest", "receipt_digest",
    )
    DOMAIN = "awa-registration-admin-audit-receipt/v2"
    DIGEST_FIELD = "receipt_digest"

    @classmethod
    def synthetic_preprepared(
        cls, *, mode: str, operation: str, reason_code: str
    ) -> "AdminAuditReceiptV2":
        body = {
            "schema": "awa-registration-admin-audit/v2",
            "mode": mode,
            "operation": operation,
            "outcome": "REFUSED",
            "reason_code": reason_code,
            "qualification_nonce": None,
            "asset_index_digest": None,
            "transaction_digest": None,
            "runtime_current_digest": None,
            "product_current_digest": None,
        }
        return cls(
            **body,
            receipt_digest=authority_digest(cls.DOMAIN, body),
        )

    def validate(self) -> None:
        body = self.to_mapping()
        claim = body.pop("receipt_digest")
        if claim != authority_digest(self.DOMAIN, body):
            raise ValueError("admin receipt digest mismatch")
        if self.transaction_digest is None and self.asset_index_digest is not None:
            raise ValueError("preprepared receipt has asset index")


class AdminHeadV1(_AdminMapping):
    FIELDS = (
        "schema", "transaction_digest", "receipt_digest",
        "runtime_current_digest", "product_current_digest", "head_digest",
    )
    DOMAIN = "awa-registration-admin-head/v1"
    DIGEST_FIELD = "head_digest"


@dataclass(frozen=True)
class SyntheticAdminChainV2:
    transactions: tuple[AdminTransactionV1, ...]
    receipt: AdminAuditReceiptV2
    head: AdminHeadV1


def _transaction(**values: object) -> AdminTransactionV1:
    body = {"schema": "awa-registration-admin-transaction/v1", **values}
    return AdminTransactionV1(
        **body,
        transaction_digest=authority_digest(
            AdminTransactionV1.DOMAIN, body
        ),
    )


def synthetic_admin_success_chain_v2(
    *,
    mode: str,
    request_id: str,
    operation: str,
    qualification_nonce: str | None,
    request_digest: str,
    context_digest: str,
    asset_index: AdminAssetIndexV1,
    pre_head_digest: str,
    pre_runtime_current_digest: str,
    pre_product_current_digest: str,
) -> SyntheticAdminChainV2:
    common = {
        "mode": mode, "request_id": request_id, "operation": operation,
        "qualification_nonce": qualification_nonce,
        "request_digest": request_digest, "context_digest": context_digest,
        "asset_index_digest": asset_index.asset_index_digest,
        "pre_head_digest": pre_head_digest,
        "pre_runtime_current_digest": pre_runtime_current_digest,
        "pre_product_current_digest": pre_product_current_digest,
        "outcome": "SUCCESS", "target_direct_receipt_digest": None,
    }
    transactions: list[AdminTransactionV1] = []
    predecessor = None
    result_runtime = None
    result_product = None
    for phase in ("PREPARED", "FILES_PUBLISHED", "CURRENT_PUBLISHED"):
        if phase == "CURRENT_PUBLISHED":
            result_runtime = hashlib.sha256(b"runtime-result").hexdigest()
            result_product = hashlib.sha256(b"product-result").hexdigest()
        item = _transaction(
            **common, phase=phase, admin_receipt_digest=None,
            result_runtime_current_digest=result_runtime,
            result_product_current_digest=result_product,
            predecessor_transaction_digest=predecessor,
        )
        transactions.append(item)
        predecessor = item.transaction_digest
    receipt_body = {
        "schema": "awa-registration-admin-audit/v2", "mode": mode,
        "operation": operation, "outcome": "SUCCESS", "reason_code": "OK",
        "qualification_nonce": qualification_nonce,
        "asset_index_digest": asset_index.asset_index_digest,
        "transaction_digest": transactions[-1].transaction_digest,
        "runtime_current_digest": result_runtime,
        "product_current_digest": result_product,
    }
    receipt = AdminAuditReceiptV2(
        **receipt_body,
        receipt_digest=authority_digest(AdminAuditReceiptV2.DOMAIN, receipt_body),
    )
    for phase in ("RECEIPT_PUBLISHED", "COMMITTED"):
        item = _transaction(
            **common, phase=phase,
            admin_receipt_digest=receipt.receipt_digest,
            result_runtime_current_digest=result_runtime,
            result_product_current_digest=result_product,
            predecessor_transaction_digest=predecessor,
        )
        transactions.append(item)
        predecessor = item.transaction_digest
    head_body = {
        "schema": "awa-registration-admin-head/v1",
        "transaction_digest": transactions[-1].transaction_digest,
        "receipt_digest": receipt.receipt_digest,
        "runtime_current_digest": result_runtime,
        "product_current_digest": result_product,
    }
    head = AdminHeadV1(
        **head_body,
        head_digest=authority_digest(AdminHeadV1.DOMAIN, head_body),
    )
    return SyntheticAdminChainV2(tuple(transactions), receipt, head)


def verify_admin_success_chain_v2(
    transactions: tuple[AdminTransactionV1, ...],
    receipt: AdminAuditReceiptV2,
    head: AdminHeadV1,
) -> None:
    if tuple(item.phase for item in transactions) != (
        "PREPARED", "FILES_PUBLISHED", "CURRENT_PUBLISHED",
        "RECEIPT_PUBLISHED", "COMMITTED",
    ):
        raise ValueError("admin transaction phases are invalid")
    predecessor = None
    for item in transactions:
        body = item.to_mapping()
        claim = body.pop("transaction_digest")
        if (
            item.predecessor_transaction_digest != predecessor
            or claim != authority_digest(AdminTransactionV1.DOMAIN, body)
        ):
            raise ValueError("admin transaction ancestry is invalid")
        predecessor = claim
    receipt.validate()
    if (
        receipt.transaction_digest != transactions[2].transaction_digest
        or head.transaction_digest != transactions[-1].transaction_digest
        or head.receipt_digest != receipt.receipt_digest
    ):
        raise ValueError("admin receipt/head relation is invalid")
    body = head.to_mapping()
    claim = body.pop("head_digest")
    if claim != authority_digest(AdminHeadV1.DOMAIN, body):
        raise ValueError("admin head digest mismatch")
