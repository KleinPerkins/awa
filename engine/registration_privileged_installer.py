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
import stat
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

PACKET_ROOT_INDEX_SCHEMA = (
    "awa-registration-private-runtime-qualification-packet-root-index/v2"
)
PACKET_ROOT_DOMAIN = (
    "awa-registration-private-runtime-qualification-packet-root/v2"
)
BOUND_INPUT_INDEX_SCHEMA = (
    "awa-registration-private-runtime-qualification-bound-input-index/v2"
)
BOUND_INPUT_DOMAIN = (
    "awa-registration-private-runtime-qualification-bound-input-root/v2"
)
EVIDENCE_INDEX_SCHEMA = (
    "awa-registration-private-runtime-qualification-evidence-index/v2"
)
EVIDENCE_DOMAIN = (
    "awa-registration-private-runtime-qualification-evidence-root/v2"
)
QUALIFICATION_PACKET_SCHEMA = (
    "awa-registration-private-runtime-qualification/v2"
)
QUALIFICATION_READBACK_SCHEMA = (
    "awa-registration-private-runtime-qualification-readback/v1"
)
QUALIFICATION_READBACK_FIELDS = frozenset(
    {
        "schema", "repository", "exact_head", "packet_root_digest",
        "bound_input_index_digest", "evidence_root_digest",
        "qualification_packet_digest", "packet_file_count",
        "input_blob_count", "evidence_blob_count",
        "static_contract_set_equal", "verified", "verifier_digest",
    }
)
FINAL_PACKET_PAYLOAD_FIELDS = (
    "source_lock",
    "github_attestation",
    "normalizer_source",
    "signing_recipe_source",
    "capability",
    "compile_options",
    "builds",
    "byte_comparison",
    "selected_build_id",
    "final_archives",
    "sbom_license_inventory",
    "relocation_load_image_evidence",
    "registration_test_evidence",
    "full_test_evidence",
    "qualification_allowed_signers",
    "qualification_fixtures",
    "privileged_qualification_context",
    "preprompt_rejection_evidence",
    "admin_qualification_evidence",
    "parent_death_evidence",
    "executed_identities",
    "securityagent_result",
    "private_key_deletion",
    "product_authority_evidence",
    "fd_topology_evidence",
    "retained_import_evidence",
    "transaction_recovery_evidence",
    "shell_startup_evidence",
)
FINAL_PACKET_FIELDS = frozenset(
    {
        "schema",
        "repository",
        "exact_head",
        "packet_root_index_digest",
        "packet_root_digest",
        "bound_input_index_digest",
        *FINAL_PACKET_PAYLOAD_FIELDS,
        "evidence_index_digest",
        "evidence_root_digest",
        "packet_digest",
    }
)
PACKET_RECORD_FIELDS = frozenset(
    {"path", "role", "domain", "size", "sha256", "mode", "media_type", "encoding"}
)
_BLOB_RECORD_FIELD_SETS = (
    PACKET_RECORD_FIELDS,
    PACKET_RECORD_FIELDS | {"packet_root_digest"},
)
_FINAL_OBJECT_FIELDS = {
    "source_lock": frozenset({"object", "blob", "sha256"}),
    "github_attestation": frozenset(
        {
            "repository", "artifact_name", "artifact_sha256", "release",
            "selection_rule", "matching_record_count", "predicate_type",
            "payload_type", "bundle_media_type", "oidc_issuer",
            "certificate_issuer", "subject_name", "subject_sha256",
            "subject_count", "build_type", "builder_id",
            "workflow_repository", "workflow_name", "workflow_path",
            "workflow_ref", "workflow_sha", "event_name", "run_invocation",
            "bundle", "payload", "certificate", "verification_command",
            "rejected_records", "verified", "digest",
        }
    ),
    "capability": frozenset({"object", "digest"}),
    "compile_options": frozenset({"object", "digest"}),
    "byte_comparison": frozenset(
        {
            "schema", "build_a_manifest_sha256", "build_b_manifest_sha256",
            "build_a_archive_sha256", "build_b_archive_sha256",
            "tree_comparison", "archive_comparison", "equal", "digest",
        }
    ),
    "sbom_license_inventory": frozenset(
        {
            "schema", "build_a_sbom_sha256", "build_b_sbom_sha256",
            "build_a_license_inventory_sha256",
            "build_b_license_inventory_sha256", "equal", "digest",
        }
    ),
    "registration_test_evidence": frozenset(
        {
            "command", "exit_code", "passed", "failed", "skipped", "stdout",
            "stderr", "started_wall_ns", "completed_wall_ns", "digest",
        }
    ),
    "full_test_evidence": frozenset(
        {
            "command", "exit_code", "passed", "failed", "skipped", "stdout",
            "stderr", "started_wall_ns", "completed_wall_ns", "digest",
        }
    ),
    "qualification_allowed_signers": frozenset({"object", "blob", "digest"}),
    "qualification_fixtures": frozenset(
        {
            "schema", "qualification_nonce", "qualification_root",
            "runtime_archive_sha256", "q1", "q2", "digest",
        }
    ),
    "privileged_qualification_context": frozenset({"object", "digest"}),
    "preprompt_rejection_evidence": frozenset(
        {
            "schema", "exact_head", "validator_source_sha256", "cases",
            "syscall_denial_trace", "path_remapped_harness", "digest",
        }
    ),
    "admin_qualification_evidence": frozenset(
        {
            "schema", "exact_head", "packet_root_digest",
            "qualification_context_digest",
            "qualification_allowed_signers_digest", "qualification_nonce",
            "request_id", "qualification_root", "authorization_result",
            "operation_results", "audit_receipts", "cleanup_result",
            "no_residue", "digest",
        }
    ),
    "parent_death_evidence": frozenset(
        {
            "schema", "exact_head", "platform_bootstrap_contract_sha256",
            "cases", "syscall_trace", "operator_message_results", "digest",
        }
    ),
    "securityagent_result": frozenset(
        {
            "schema", "invocation_id", "prompt_count", "result",
            "osascript_exit_code", "error_number", "stdout", "stderr",
            "started_wall_ns", "completed_wall_ns", "packet_root_digest",
            "digest",
        }
    ),
    "private_key_deletion": frozenset(
        {
            "schema", "qualification_nonce", "public_key_openssh",
            "public_key_wire_sha256", "deleted_wall_ns",
            "private_material_absent", "open_fd_matches",
            "packet_private_blob_matches", "packet_root_digest", "digest",
        }
    ),
    "product_authority_evidence": frozenset(
        {
            "schema", "product_current", "bundle_manifest",
            "bundle_projection", "import_manifest", "host_authority",
            "direct_receipt", "owner_gate", "installed_layout",
            "retention_cases", "equality_results", "digest",
        }
    ),
    "fd_topology_evidence": frozenset(
        {
            "schema", "launch_context", "source_fd_map", "target_fd_map",
            "fault_cases", "ready_measurements", "go_measurements", "digest",
        }
    ),
    "retained_import_evidence": frozenset(
        {
            "schema", "manifest_digest", "first_import", "package_cases",
            "module_cases", "relative_import_cases", "resource_cases",
            "filesystem_open_trace", "bytecode_write_trace", "digest",
        }
    ),
    "transaction_recovery_evidence": frozenset(
        {
            "schema", "production_fixture", "qualification_fixture",
            "fault_cases", "recovery_cases", "immutable_phase_chains",
            "by_request_pointer_cases", "preprepared_null_transaction_cases",
            "asset_role_operation_cases", "nonce_mode_cases",
            "static_contract_set_cases", "asset_index_cases",
            "result_receipts", "head_current_receipt_equalities",
            "remove_evidence", "digest",
        }
    ),
    "shell_startup_evidence": frozenset(
        {
            "schema", "script_hashes", "sentinel_cases",
            "executed_startup_files", "inherited_environment",
            "product_prebootstrap_imports", "digest",
        }
    ),
}
_BUILD_FIELDS = frozenset(
    {
        "build_id", "clean_root_id", "toolchain", "manifest",
        "signature_inventory", "transcript", "archive", "sbom",
        "license_inventory", "registration_tests", "full_tests",
    }
)
_TOOLCHAIN_FIELDS = frozenset(
    {
        "codesign_path", "codesign_project", "codesign_sha256", "clt_version",
        "sdk_version", "target_triple",
    }
)
_RELOCATION_FIELDS = frozenset(
    {
        "relocation_id", "root_hash", "command", "loaded_image_count",
        "loaded_images", "dependency_escapes", "exit_code", "digest",
    }
)
_EXECUTED_IDENTITY_FIELDS = frozenset(
    {
        "role", "path", "dev", "ino", "pid", "pidversion",
        "mapped_vnode_dev", "mapped_vnode_ino", "cdhash", "sha256",
        "packet_root_digest", "digest",
    }
)
_FIXTURE_FIELDS = frozenset(
    {
        "fixture_id", "epoch", "marker_relative_path", "marker_bytes_base64",
        "marker_size", "marker_sha256", "build_a_manifest_sha256",
        "build_b_manifest_sha256", "manifest_sha256",
        "release_envelope_digest", "synthetic_signature_sha256",
    }
)
ROOT_REQUIRED_ROLES = frozenset(
    {
        "QUALIFICATION_ALLOWED_SIGNERS",
        "Q1_MANIFEST",
        "Q1_ENVELOPE",
        "Q1_SIGNATURE",
        "Q2_MANIFEST",
        "Q2_ENVELOPE",
        "Q2_SIGNATURE",
    }
)


def _is_blob_record(value: object) -> bool:
    return isinstance(value, dict) and set(value) in _BLOB_RECORD_FIELD_SETS


def _validate_final_packet_payload_shapes(
    values: Mapping[str, object],
) -> None:
    def string(value: object) -> bool:
        return type(value) is str

    def strings(value: object) -> bool:
        return (
            type(value) is list
            and all(type(item) is str for item in value)
        )

    def decimal(value: object) -> bool:
        return type(value) is str and UINT.fullmatch(value) is not None

    def blob(value: object) -> bool:
        if not _is_blob_record(value):
            return False
        assert isinstance(value, dict)
        return (
            all(
                type(value.get(field)) is str
                for field in (
                    "path", "role", "domain", "size", "sha256", "mode",
                    "media_type", "encoding",
                )
            )
            and decimal(value["size"])
            and _is_hex64(value["sha256"])
            and value["mode"] == "0444"
            and (
                "packet_root_digest" not in value
                or _is_hex64(value["packet_root_digest"])
            )
        )

    def dictionaries(value: object) -> bool:
        return type(value) is list and all(type(item) is dict for item in value)

    if set(values) != set(FINAL_PACKET_PAYLOAD_FIELDS):
        raise ValueError("final packet payload fields are not exact")
    for field, expected_fields in _FINAL_OBJECT_FIELDS.items():
        value = values.get(field)
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise ValueError(f"final packet {field} shape refused")
    for field in ("normalizer_source", "signing_recipe_source"):
        if not blob(values.get(field)):
            raise ValueError(f"final packet {field} blob refused")
    builds = values.get("builds")
    if (
        not isinstance(builds, list)
        or len(builds) != 2
        or [row.get("build_id") for row in builds if isinstance(row, dict)]
        != ["A", "B"]
    ):
        raise ValueError("final packet builds shape refused")
    for build in builds:
        if (
            not isinstance(build, dict)
            or set(build) != _BUILD_FIELDS
            or not _is_hex64(build.get("clean_root_id"))
            or not isinstance(build.get("toolchain"), dict)
            or set(build["toolchain"]) != _TOOLCHAIN_FIELDS
            or not isinstance(build.get("manifest"), dict)
            or set(build["manifest"]) != {"object", "digest"}
            or not isinstance(build.get("signature_inventory"), dict)
            or set(build["signature_inventory"]) != {"object", "digest"}
            or any(
                not blob(build.get(field))
                for field in (
                    "transcript", "archive", "sbom", "license_inventory"
                )
            )
            or any(
                not isinstance(build.get(field), dict)
                or set(build[field])
                != _FINAL_OBJECT_FIELDS["registration_test_evidence"]
                for field in ("registration_tests", "full_tests")
            )
        ):
            raise ValueError("final packet build record refused")
    if values.get("selected_build_id") != "A":
        raise ValueError("final packet selected build refused")
    archives = values.get("final_archives")
    if (
        not isinstance(archives, list)
        or len(archives) != 2
        or any(not blob(row) for row in archives)
    ):
        raise ValueError("final packet archive records refused")
    relocations = values.get("relocation_load_image_evidence")
    if (
        not isinstance(relocations, list)
        or len(relocations) != 2
        or any(
            not isinstance(row, dict) or set(row) != _RELOCATION_FIELDS
            for row in relocations
        )
        or [row["relocation_id"] for row in relocations]
        != sorted(
            [row["relocation_id"] for row in relocations],
            key=lambda value: str(value).encode("utf-8"),
        )
    ):
        raise ValueError("final packet relocation records refused")
    identities = values.get("executed_identities")
    if (
        not isinstance(identities, list)
        or not identities
        or any(
            not isinstance(row, dict)
            or set(row) != _EXECUTED_IDENTITY_FIELDS
            for row in identities
        )
        or identities
        != sorted(
            identities,
            key=lambda row: (
                str(row["path"]).encode("utf-8"),
                str(row["role"]).encode("utf-8"),
            ),
        )
    ):
        raise ValueError("final packet executed identities refused")
    fixtures = values["qualification_fixtures"]
    if (
        any(
            not isinstance(fixtures.get(key), dict)
            or set(fixtures[key]) != _FIXTURE_FIELDS
            for key in ("q1", "q2")
        )
        or [fixtures["q1"]["fixture_id"], fixtures["q2"]["fixture_id"]]
        != ["Q1", "Q2"]
    ):
        raise ValueError("final packet qualification fixtures refused")
    source_lock = values["source_lock"]
    if (
        type(source_lock["object"]) is not dict
        or not blob(source_lock["blob"])
        or not _is_hex64(source_lock["sha256"])
    ):
        raise ValueError("final packet source lock refused")
    github = values["github_attestation"]
    github_blob_fields = {"bundle", "payload", "certificate"}
    github_array_fields = {"verification_command", "rejected_records"}
    if (
        any(
            not string(value)
            for field, value in github.items()
            if field
            not in github_blob_fields | github_array_fields | {"verified"}
        )
        or any(not blob(github[field]) for field in github_blob_fields)
        or not strings(github["verification_command"])
        or not dictionaries(github["rejected_records"])
        or type(github["verified"]) is not bool
        or github["matching_record_count"] != "1"
        or not _is_hex64(github["digest"])
    ):
        raise ValueError("final packet GitHub attestation refused")
    capability = values["capability"]
    capability_object = capability["object"]
    capability_fields = {
        "schema", "platform", "os_build", "python_implementation",
        "python_version", "required_python_apis", "sqlite_runtime_version",
        "sqlite_source_id", "sqlite_compile_options_hash", "sqlite_vfs_name",
        "journal_mode", "synchronous", "fullfsync",
        "checkpoint_fullfsync", "foreign_keys",
        "connection_setconfig_available",
        "sqlite_dbconfig_defensive_available", "defensive",
        "trusted_schema", "locking_mode", "nofollow_available",
        "checkpoint_on_close", "probe_program_hash",
    }
    capability_bools = {
        "fullfsync", "checkpoint_fullfsync", "foreign_keys",
        "connection_setconfig_available",
        "sqlite_dbconfig_defensive_available", "defensive",
        "trusted_schema", "nofollow_available", "checkpoint_on_close",
    }
    if (
        type(capability_object) is not dict
        or set(capability_object) != capability_fields
        or any(
            type(capability_object[field]) is not bool
            for field in capability_bools
        )
        or not strings(capability_object["required_python_apis"])
        or any(
            not string(value)
            for field, value in capability_object.items()
            if field not in capability_bools | {"required_python_apis"}
        )
        or not _is_hex64(capability["digest"])
    ):
        raise ValueError("final packet capability refused")
    compile_options = values["compile_options"]
    compile_object = compile_options["object"]
    if (
        type(compile_object) is not dict
        or set(compile_object) != {"schema", "options"}
        or not string(compile_object["schema"])
        or not strings(compile_object["options"])
        or compile_object["options"]
        != sorted(set(compile_object["options"]), key=lambda item: item.encode())
        or not _is_hex64(compile_options["digest"])
    ):
        raise ValueError("final packet compile options refused")
    test_fields = ("registration_tests", "full_tests")
    for build in builds:
        toolchain = build["toolchain"]
        manifest = build["manifest"]
        manifest_object = manifest["object"]
        signatures = build["signature_inventory"]
        signature_object = signatures["object"]
        if (
            any(not string(value) for value in toolchain.values())
            or not _is_hex64(toolchain["codesign_sha256"])
            or type(manifest_object) is not dict
            or set(manifest_object)
            != {
                "schema", "source_lock_sha256", "normalizer_source_sha256",
                "signing_recipe_source_sha256", "record_framing_digest",
                "records",
            }
            or any(
                not string(manifest_object[field])
                for field in set(manifest_object) - {"records"}
            )
            or not dictionaries(manifest_object["records"])
            or any(
                set(row) != {"path", "mode", "size", "sha256", "macho"}
                or not all(
                    string(row[field])
                    for field in ("path", "mode", "size", "sha256")
                )
                or type(row["macho"]) is not bool
                for row in manifest_object["records"]
            )
            or not _is_hex64(manifest["digest"])
            or type(signature_object) is not dict
            or set(signature_object) != {"schema", "records"}
            or not string(signature_object["schema"])
            or not dictionaries(signature_object["records"])
            or any(
                set(row)
                != {"path", "identifier", "cdhash", "adhoc", "strict_valid"}
                or not all(
                    string(row[field])
                    for field in ("path", "identifier", "cdhash")
                )
                or type(row["adhoc"]) is not bool
                or type(row["strict_valid"]) is not bool
                for row in signature_object["records"]
            )
            or not _is_hex64(signatures["digest"])
        ):
            raise ValueError("final packet build nested authority refused")
        for field in test_fields:
            record = build[field]
            if (
                not strings(record["command"])
                or record["exit_code"] != "0"
                or any(
                    not decimal(record[name])
                    for name in (
                        "passed", "failed", "skipped", "started_wall_ns",
                        "completed_wall_ns",
                    )
                )
                or not blob(record["stdout"])
                or not blob(record["stderr"])
                or not _is_hex64(record["digest"])
            ):
                raise ValueError("final packet test record refused")
    for field in (
        "byte_comparison", "sbom_license_inventory",
        "registration_test_evidence", "full_test_evidence",
    ):
        record = values[field]
        if not _is_hex64(record["digest"]):
            raise ValueError(f"final packet {field} digest refused")
    if (
        type(values["byte_comparison"]["equal"]) is not bool
        or values["byte_comparison"]["equal"] is not True
        or not blob(values["byte_comparison"]["tree_comparison"])
        or not blob(values["byte_comparison"]["archive_comparison"])
        or type(values["sbom_license_inventory"]["equal"]) is not bool
        or values["sbom_license_inventory"]["equal"] is not True
    ):
        raise ValueError("final packet comparison evidence refused")
    for relocation in relocations:
        if (
            not all(
                string(relocation[field])
                for field in (
                    "relocation_id", "root_hash", "loaded_image_count",
                    "exit_code", "digest",
                )
            )
            or not strings(relocation["command"])
            or not decimal(relocation["loaded_image_count"])
            or relocation["exit_code"] != "0"
            or not blob(relocation["loaded_images"])
            or not blob(relocation["dependency_escapes"])
        ):
            raise ValueError("final packet relocation evidence refused")
    signers = values["qualification_allowed_signers"]
    if (
        type(signers["object"]) is not dict
        or not blob(signers["blob"])
        or not _is_hex64(signers["digest"])
        or any(
            not string(value)
            for field, value in signers["object"].items()
            if field != "namespaces"
        )
        or not strings(signers["object"].get("namespaces"))
    ):
        raise ValueError("final packet qualification signers refused")
    if any(
        any(
            type(value) is not str
            for value in fixtures[key].values()
        )
        for key in ("q1", "q2")
    ):
        raise ValueError("final packet fixture value refused")
    context = values["privileged_qualification_context"]
    if (
        type(context["object"]) is not dict
        or any(not string(value) for value in context["object"].values())
        or not _is_hex64(context["digest"])
    ):
        raise ValueError("final packet privileged context refused")
    for field in (
        "preprompt_rejection_evidence", "parent_death_evidence",
        "admin_qualification_evidence",
    ):
        record = values[field]
        for key, value in record.items():
            if key in {
                "cases", "operation_results", "audit_receipts"
            } and not dictionaries(value):
                raise ValueError(f"final packet {field} records refused")
        if not _is_hex64(record["digest"]):
            raise ValueError(f"final packet {field} digest refused")
    if type(values["admin_qualification_evidence"]["no_residue"]) is not bool:
        raise ValueError("final packet admin residue flag refused")
    for identity in identities:
        if any(
            value is not None and not string(value)
            for value in identity.values()
        ):
            raise ValueError("final packet executed identity value refused")
    security = values["securityagent_result"]
    if (
        any(
            not string(value)
            for field, value in security.items()
            if field not in {"stdout", "stderr"}
        )
        or not blob(security["stdout"])
        or not blob(security["stderr"])
        or security["prompt_count"] != "1"
        or security["result"] != "ACCEPTED"
    ):
        raise ValueError("final packet SecurityAgent result refused")
    deletion = values["private_key_deletion"]
    if (
        any(
            not string(value)
            for field, value in deletion.items()
            if field != "private_material_absent"
        )
        or type(deletion["private_material_absent"]) is not bool
        or deletion["private_material_absent"] is not True
        or deletion["open_fd_matches"] != "0"
        or deletion["packet_private_blob_matches"] != "0"
    ):
        raise ValueError("final packet key deletion refused")
    for field in (
        "product_authority_evidence", "fd_topology_evidence",
        "retained_import_evidence", "transaction_recovery_evidence",
        "shell_startup_evidence",
    ):
        record = values[field]
        if (
            not string(record["schema"])
            or not _is_hex64(record["digest"])
            or any(
                type(value) is list and not dictionaries(value)
                for key, value in record.items()
                if key not in {"schema", "digest"}
            )
        ):
            raise ValueError(f"final packet {field} value refused")
    retained = values["retained_import_evidence"]
    if not _is_hex64(retained["manifest_digest"]):
        raise ValueError("final packet retained manifest digest refused")


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
        static = {
            row["domain"]: row["sha256"]
            for row in self._root
            if row["role"] == "STATIC_CONTRACT"
        }
        if static != V8_STATIC_CONTRACT_HASHES:
            raise ValueError("packet static contract set mismatch")
        roles = {row["role"] for row in self._root}
        if not ROOT_REQUIRED_ROLES.issubset(roles):
            raise ValueError("packet qualification root inputs incomplete")
        index, _ = self._index(
            schema=PACKET_ROOT_INDEX_SCHEMA,
            domain=PACKET_ROOT_DOMAIN,
            records=self._root,
            root_bound=False,
        )
        self._packet_root = index["index_digest"]
        return self._packet_root

    def add_bound_blob(self, **values: object) -> str:
        return self._add(collection="bound", **values)  # type: ignore[arg-type]

    def add_evidence_blob(self, **values: object) -> str:
        return self._add(collection="evidence", **values)  # type: ignore[arg-type]

    def prepare(self) -> dict:
        self.finalize_packet_root()
        if not self._bound:
            raise ValueError("bound input index must be nonempty")
        root, root_bytes = self._index(
            schema=PACKET_ROOT_INDEX_SCHEMA,
            domain=PACKET_ROOT_DOMAIN,
            records=self._root,
            root_bound=False,
        )
        bound, bound_bytes = self._index(
            schema=BOUND_INPUT_INDEX_SCHEMA,
            domain=BOUND_INPUT_DOMAIN,
            records=self._bound,
            root_bound=True,
        )
        selected = {
            str(row["sha256"])
            for row in self._root + self._bound
        }
        result = {
            "packet_root_index": root,
            "packet_root_index_bytes": root_bytes,
            "packet_root_digest": root["index_digest"],
            "bound_index": bound,
            "bound_index_bytes": bound_bytes,
            "bound_index_digest": bound["index_digest"],
            "blobs": {
                digest: content
                for digest, content in self._blobs.items()
                if digest in selected
            },
        }
        validate_qualification_packet_prepare(result)
        return result

    def finalize(self, final_values: Mapping[str, object]) -> dict:
        self.finalize_packet_root()
        _validate_final_packet_payload_shapes(final_values)
        if not self._bound or not self._evidence:
            raise ValueError("bound input and evidence indexes must be nonempty")
        root, root_bytes = self._index(
            schema=PACKET_ROOT_INDEX_SCHEMA,
            domain=PACKET_ROOT_DOMAIN,
            records=self._root,
            root_bound=False,
        )
        bound, bound_bytes = self._index(
            schema=BOUND_INPUT_INDEX_SCHEMA,
            domain=BOUND_INPUT_DOMAIN,
            records=self._bound,
            root_bound=True,
        )
        evidence, evidence_bytes = self._index(
            schema=EVIDENCE_INDEX_SCHEMA,
            domain=EVIDENCE_DOMAIN,
            records=self._evidence,
            root_bound=True,
        )
        packet_body = {
            "schema": QUALIFICATION_PACKET_SCHEMA,
            "repository": "KleinPerkins/awa",
            "exact_head": self.exact_head,
            "packet_root_index_digest": root["index_digest"],
            "packet_root_digest": root["index_digest"],
            "bound_input_index_digest": bound["index_digest"],
            **dict(final_values),
            "evidence_index_digest": evidence["index_digest"],
            "evidence_root_digest": evidence["index_digest"],
        }
        packet = {
            **packet_body,
            "packet_digest": authority_digest(
                QUALIFICATION_PACKET_SCHEMA, packet_body
            ),
        }
        result = {
            "packet_root_index": root,
            "packet_root_index_bytes": root_bytes,
            "packet_root_digest": root["index_digest"],
            "bound_index": bound,
            "bound_index_bytes": bound_bytes,
            "bound_index_digest": bound["index_digest"],
            "evidence_index": evidence,
            "evidence_index_bytes": evidence_bytes,
            "evidence_index_digest": evidence["index_digest"],
            "packet": packet,
            "packet_bytes": canonical_lf_bytes(packet),
            "qualification_packet_digest": packet["packet_digest"],
            "blobs": dict(self._blobs),
        }
        validate_qualification_packet(result)
        return result


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

_INDEX_MAX_BYTES = 16 * 1024 * 1024
_BLOB_MAX_BYTES = 512 * 1024 * 1024
_BLOB_AGGREGATE_MAX_BYTES = 2 * 1024 * 1024 * 1024
_INDEX_MAX_RECORDS = 4096
_READ_CHUNK = 1024 * 1024


def _parse_canonical_value(raw: bytes) -> object:
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\0" in raw
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        raise ValueError("JCS+LF framing refused")

    def pairs(rows: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in rows:
            if key in value:
                raise ValueError("duplicate JSON key refused")
            value[key] = item
        return value

    value = json.loads(
        raw[:-1].decode("utf-8", "strict"),
        object_pairs_hook=pairs,
        parse_float=lambda _: (_ for _ in ()).throw(
            ValueError("JSON float refused")
        ),
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("JSON constant refused")
        ),
    )
    if canonical_lf_bytes(value) != raw:
        raise ValueError("noncanonical JCS+LF refused")
    return value


def _validate_blob_encoding(content: bytes, encoding: object) -> None:
    if encoding == "BINARY":
        return
    if encoding not in {"UTF8", "UTF8_LF", "JCS_LF"}:
        raise ValueError("blob encoding refused")
    if content.startswith(b"\xef\xbb\xbf") or b"\0" in content:
        raise ValueError("UTF-8 blob framing refused")
    text = content.decode("utf-8", "strict")
    if text.encode("utf-8") != content:
        raise ValueError("UTF-8 blob round trip refused")
    if encoding in {"UTF8_LF", "JCS_LF"} and (
        not content
        or not content.endswith(b"\n")
        or content.endswith(b"\n\n")
        or b"\r" in content
    ):
        raise ValueError("LF blob framing refused")
    if encoding == "JCS_LF":
        _parse_canonical_value(content)


def _validate_packet_index(
    value: object,
    *,
    schema: str,
    domain: str,
    packet_root_digest: str | None,
) -> list[dict[str, object]]:
    allowed_roles = {
        PACKET_ROOT_INDEX_SCHEMA: PACKET_ROOT_ROLES,
        BOUND_INPUT_INDEX_SCHEMA: BOUND_ROLES,
        EVIDENCE_INDEX_SCHEMA: EVIDENCE_ROLES,
    }.get(schema)
    if allowed_roles is None:
        raise ValueError("packet index authority refused")
    expected_fields = (
        {"schema", "records", "index_digest"}
        if packet_root_digest is None
        else {"schema", "packet_root_digest", "records", "index_digest"}
    )
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise ValueError("packet index fields refused")
    if value.get("schema") != schema:
        raise ValueError("packet index schema refused")
    if packet_root_digest is not None and value.get(
        "packet_root_digest"
    ) != packet_root_digest:
        raise ValueError("packet index root binding refused")
    records = value.get("records")
    if not isinstance(records, list) or not records or len(records) > _INDEX_MAX_RECORDS:
        raise ValueError("packet index record count refused")
    record_fields = (
        PACKET_RECORD_FIELDS
        if packet_root_digest is None
        else PACKET_RECORD_FIELDS | {"packet_root_digest"}
    )
    if any(not isinstance(row, dict) or set(row) != record_fields for row in records):
        raise ValueError("packet record fields refused")
    ordering = sorted(
        records,
        key=lambda row: (
            str(row["path"]).encode("utf-8"),
            str(row["role"]).encode("utf-8"),
        ),
    )
    if records != ordering:
        raise ValueError("packet record ordering refused")
    if len({(row["path"], row["role"]) for row in records}) != len(records):
        raise ValueError("duplicate packet record refused")
    for row in records:
        if packet_root_digest is not None and row.get(
            "packet_root_digest"
        ) != packet_root_digest:
            raise ValueError("packet record root binding refused")
        size = row.get("size")
        if (
            not isinstance(size, str)
            or UINT.fullmatch(size) is None
            or int(size) > _BLOB_MAX_BYTES
            or row.get("mode") != "0444"
            or not _is_hex64(row.get("sha256"))
            or row.get("encoding") not in {"BINARY", "UTF8", "UTF8_LF", "JCS_LF"}
            or not isinstance(row.get("domain"), str)
            or not isinstance(row.get("media_type"), str)
            or not isinstance(row.get("role"), str)
            or row.get("role") not in allowed_roles
        ):
            raise ValueError("packet record metadata refused")
        prefix = "evidence/sha256/" if schema == EVIDENCE_INDEX_SCHEMA else "inputs/sha256/"
        if row.get("path") != prefix + str(row["sha256"]):
            raise ValueError("packet record content address refused")
        if (
            schema == BOUND_INPUT_INDEX_SCHEMA
            and row["encoding"] != "JCS_LF"
        ) or (
            str(row["role"]).endswith("_SIGNATURE")
            and row["encoding"] != "BINARY"
        ) or (
            row["role"]
            in {
                "AUTHORIZATION_RESULT",
                "CLEANUP_RESULT",
                "PARENT_DEATH_EVIDENCE",
            }
            and row["encoding"] != "JCS_LF"
        ):
            raise ValueError("packet record role encoding refused")
    body = dict(value)
    claim = body.pop("index_digest")
    if claim != authority_digest(domain, body):
        raise ValueError("packet index digest refused")
    return records


def validate_qualification_packet_prepare(packet: Mapping[str, object]) -> None:
    expected = {
        "packet_root_index",
        "packet_root_index_bytes",
        "packet_root_digest",
        "bound_index",
        "bound_index_bytes",
        "bound_index_digest",
        "blobs",
    }
    if set(packet) != expected:
        raise ValueError("qualification packet prepare fields refused")
    root_digest = packet.get("packet_root_digest")
    if not _is_hex64(root_digest):
        raise ValueError("packet root digest refused")
    root = packet.get("packet_root_index")
    bound = packet.get("bound_index")
    root_records = _validate_packet_index(
        root,
        schema=PACKET_ROOT_INDEX_SCHEMA,
        domain=PACKET_ROOT_DOMAIN,
        packet_root_digest=None,
    )
    bound_records = _validate_packet_index(
        bound,
        schema=BOUND_INPUT_INDEX_SCHEMA,
        domain=BOUND_INPUT_DOMAIN,
        packet_root_digest=str(root_digest),
    )
    if (
        not isinstance(root, dict)
        or root.get("index_digest") != root_digest
        or not isinstance(bound, dict)
        or packet.get("bound_index_digest") != bound.get("index_digest")
        or packet.get("packet_root_index_bytes") != canonical_lf_bytes(root)
        or packet.get("bound_index_bytes") != canonical_lf_bytes(bound)
    ):
        raise ValueError("qualification packet prepare digest refused")
    blobs = packet.get("blobs")
    records = root_records + bound_records
    if (
        not isinstance(blobs, dict)
        or len({row["sha256"] for row in records}) != len(records)
        or set(blobs) != {row["sha256"] for row in records}
    ):
        raise ValueError("qualification packet prepare blobs refused")
    aggregate = 0
    for row in records:
        content = blobs[row["sha256"]]
        if not isinstance(content, bytes):
            raise ValueError("qualification packet prepare blob type refused")
        aggregate += len(content)
        if (
            len(content) != int(str(row["size"]))
            or _sha256(content) != row["sha256"]
        ):
            raise ValueError("qualification packet prepare blob refused")
        _validate_blob_encoding(content, row["encoding"])
    if aggregate > _BLOB_AGGREGATE_MAX_BYTES:
        raise ValueError("qualification packet prepare aggregate refused")
    static = {
        str(row["domain"]): str(row["sha256"])
        for row in root_records
        if row["role"] == "STATIC_CONTRACT"
    }
    if static != V8_STATIC_CONTRACT_HASHES or not ROOT_REQUIRED_ROLES.issubset(
        {str(row["role"]) for row in root_records}
    ):
        raise ValueError("qualification packet prepare roots incomplete")


def validate_qualification_packet(packet: Mapping[str, object]) -> None:
    expected = {
        "packet_root_index",
        "packet_root_index_bytes",
        "packet_root_digest",
        "bound_index",
        "bound_index_bytes",
        "bound_index_digest",
        "evidence_index",
        "evidence_index_bytes",
        "evidence_index_digest",
        "packet",
        "packet_bytes",
        "qualification_packet_digest",
        "blobs",
    }
    if set(packet) != expected:
        raise ValueError("qualification packet result fields refused")
    root_digest = packet.get("packet_root_digest")
    if not _is_hex64(root_digest):
        raise ValueError("packet root digest refused")
    root = packet.get("packet_root_index")
    bound = packet.get("bound_index")
    evidence = packet.get("evidence_index")
    root_records = _validate_packet_index(
        root,
        schema=PACKET_ROOT_INDEX_SCHEMA,
        domain=PACKET_ROOT_DOMAIN,
        packet_root_digest=None,
    )
    if not isinstance(root, dict) or root.get("index_digest") != root_digest:
        raise ValueError("packet root equality refused")
    bound_records = _validate_packet_index(
        bound,
        schema=BOUND_INPUT_INDEX_SCHEMA,
        domain=BOUND_INPUT_DOMAIN,
        packet_root_digest=str(root_digest),
    )
    evidence_records = _validate_packet_index(
        evidence,
        schema=EVIDENCE_INDEX_SCHEMA,
        domain=EVIDENCE_DOMAIN,
        packet_root_digest=str(root_digest),
    )
    if (
        not isinstance(bound, dict)
        or packet.get("bound_index_digest") != bound.get("index_digest")
        or not isinstance(evidence, dict)
        or packet.get("evidence_index_digest") != evidence.get("index_digest")
    ):
        raise ValueError("packet index result digest refused")
    if packet.get("packet_root_index_bytes") != canonical_lf_bytes(root):
        raise ValueError("packet root bytes refused")
    if packet.get("bound_index_bytes") != canonical_lf_bytes(bound):
        raise ValueError("bound input bytes refused")
    if packet.get("evidence_index_bytes") != canonical_lf_bytes(evidence):
        raise ValueError("evidence bytes refused")
    final = packet.get("packet")
    if (
        not isinstance(final, dict)
        or set(final) != FINAL_PACKET_FIELDS
        or final.get("schema") != QUALIFICATION_PACKET_SCHEMA
        or final.get("repository") != "KleinPerkins/awa"
        or not re.fullmatch(r"[0-9a-f]{40}", str(final.get("exact_head", "")))
        or final.get("packet_root_index_digest") != root_digest
        or final.get("packet_root_digest") != root_digest
        or final.get("bound_input_index_digest") != bound.get("index_digest")
        or final.get("evidence_index_digest") != evidence.get("index_digest")
        or final.get("evidence_root_digest") != evidence.get("index_digest")
    ):
        raise ValueError("final qualification packet fields refused")
    final_body = dict(final)
    final_claim = final_body.pop("packet_digest")
    _validate_final_packet_payload_shapes(
        {field: final[field] for field in FINAL_PACKET_PAYLOAD_FIELDS}
    )
    if (
        final_claim != authority_digest(QUALIFICATION_PACKET_SCHEMA, final_body)
        or packet.get("qualification_packet_digest") != final_claim
        or final_claim == root_digest
        or packet.get("packet_bytes") != canonical_lf_bytes(final)
    ):
        raise ValueError("final qualification packet digest refused")
    blobs = packet.get("blobs")
    if not isinstance(blobs, dict) or any(
        not _is_hex64(key) or not isinstance(value, bytes)
        for key, value in blobs.items()
    ):
        raise ValueError("packet blobs refused")
    all_records = root_records + bound_records + evidence_records
    if len({row["sha256"] for row in all_records}) != len(all_records):
        raise ValueError("packet blob role alias refused")
    if set(blobs) != {row["sha256"] for row in all_records}:
        raise ValueError("packet blob set refused")
    aggregate = 0
    for row in all_records:
        content = blobs[row["sha256"]]
        aggregate += len(content)
        if (
            len(content) != int(str(row["size"]))
            or _sha256(content) != row["sha256"]
        ):
            raise ValueError("packet blob size/hash refused")
        _validate_blob_encoding(content, row["encoding"])
    if aggregate > _BLOB_AGGREGATE_MAX_BYTES:
        raise ValueError("packet blob aggregate refused")
    static = {
        str(row["domain"]): str(row["sha256"])
        for row in root_records
        if row["role"] == "STATIC_CONTRACT"
    }
    if static != V8_STATIC_CONTRACT_HASHES:
        raise ValueError("packet static contract equality refused")
    if not ROOT_REQUIRED_ROLES.issubset(
        {str(row["role"]) for row in root_records}
    ):
        raise ValueError("packet qualification roots incomplete")
    root_text = str(root_digest).encode("ascii")
    if any(root_text in blobs[row["sha256"]] for row in root_records):
        raise ValueError("packet root cycle refused")


_READER_SCHEMAS = {
    "root": (
        "awa-registration-private-runtime-qualification-packet-root-index/v2",
        "awa-registration-private-runtime-qualification-packet-root/v2",
    ),
    "bound": (
        "awa-registration-private-runtime-qualification-bound-input-index/v2",
        "awa-registration-private-runtime-qualification-bound-input-root/v2",
    ),
    "evidence": (
        "awa-registration-private-runtime-qualification-evidence-index/v2",
        "awa-registration-private-runtime-qualification-evidence-root/v2",
    ),
}
_READER_FINAL_SCHEMA = "awa-registration-private-runtime-qualification/v2"
_READER_RECORD_FIELDS = frozenset(
    {"path", "role", "domain", "size", "sha256", "mode", "media_type", "encoding"}
)
_READER_FINAL_FIELDS = frozenset(
    {
        "schema",
        "repository",
        "exact_head",
        "packet_root_index_digest",
        "packet_root_digest",
        "bound_input_index_digest",
        "source_lock",
        "github_attestation",
        "normalizer_source",
        "signing_recipe_source",
        "capability",
        "compile_options",
        "builds",
        "byte_comparison",
        "selected_build_id",
        "final_archives",
        "sbom_license_inventory",
        "relocation_load_image_evidence",
        "registration_test_evidence",
        "full_test_evidence",
        "qualification_allowed_signers",
        "qualification_fixtures",
        "privileged_qualification_context",
        "preprompt_rejection_evidence",
        "admin_qualification_evidence",
        "parent_death_evidence",
        "executed_identities",
        "securityagent_result",
        "private_key_deletion",
        "product_authority_evidence",
        "fd_topology_evidence",
        "retained_import_evidence",
        "transaction_recovery_evidence",
        "shell_startup_evidence",
        "evidence_index_digest",
        "evidence_root_digest",
        "packet_digest",
    }
)
_READER_STATIC_CONTRACT_HASHES = {
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
_READER_ROOT_ROLES = frozenset(
    {
        "INLINE_BOOTSTRAP_B", "INITIAL_APPLESCRIPT", "ADMIN_APPLESCRIPT",
        "INITIAL_SHELL_TEMPLATE", "ADMIN_SHELL_TEMPLATE", "INITIAL_COMMAND",
        "ADMIN_INSTALL_COMMAND", "ADMIN_UPDATE_COMMAND",
        "ADMIN_ROLLBACK_COMMAND", "ADMIN_REMOVE_COMMAND",
        "ADMIN_QUALIFY_COMMAND", "QUALIFICATION_ALLOWED_SIGNERS",
        "ROOT_ADMIN", "ROOT_ENTRYPOINT", "PLATFORM_BOOTSTRAP",
        "CHILD_BOOTSTRAP", "STATIC_CONTRACT", "SOURCE_LOCK",
        "ATTESTATION_BUNDLE", "ATTESTATION_PAYLOAD",
        "ATTESTATION_CERTIFICATE", "SHA256SUMS", "PYTHON_JSON",
        "Q1_MANIFEST", "Q1_ENVELOPE", "Q1_SIGNATURE", "Q2_MANIFEST",
        "Q2_ENVELOPE", "Q2_SIGNATURE", "NORMALIZER_SOURCE",
        "SIGNING_RECIPE_SOURCE", "BUILD_MANIFEST",
        "BUILD_SIGNATURE_INVENTORY", "BUILD_TRANSCRIPT", "BUILD_ARCHIVE",
        "BUILD_SBOM", "BUILD_LICENSE_INVENTORY", "TEST_STDOUT",
        "TEST_STDERR", "TREE_COMPARISON", "ARCHIVE_COMPARISON",
        "LOADED_IMAGES", "DEPENDENCY_ESCAPES",
        "PURE_VALIDATOR_REJECTION_EVIDENCE",
    }
)
_READER_BOUND_ROLES = frozenset({"PRIVILEGED_REQUEST", "PRIVILEGED_CONTEXT"})
_READER_EVIDENCE_ROLES = frozenset(
    {
        "AUTHORIZATION_RESULT", "OPERATION_STDOUT", "OPERATION_STDERR",
        "CLEANUP_RESULT", "SECURITYAGENT_STDOUT", "SECURITYAGENT_STDERR",
        "PARENT_DEATH_EVIDENCE", "PARENT_DEATH_SYSCALL_TRACE",
        "PARENT_DEATH_OPERATOR_MESSAGES",
    }
)
_READER_REQUIRED_ROOT_ROLES = frozenset(
    {
        "QUALIFICATION_ALLOWED_SIGNERS", "Q1_MANIFEST", "Q1_ENVELOPE",
        "Q1_SIGNATURE", "Q2_MANIFEST", "Q2_ENVELOPE", "Q2_SIGNATURE",
    }
)


def _reader_validate_final_packet_payload_shapes(
    values: Mapping[str, object],
) -> None:
    object_fields = {
        "source_lock": "object blob sha256",
        "github_attestation": (
            "repository artifact_name artifact_sha256 release selection_rule "
            "matching_record_count predicate_type payload_type "
            "bundle_media_type oidc_issuer certificate_issuer subject_name "
            "subject_sha256 subject_count build_type builder_id "
            "workflow_repository workflow_name workflow_path workflow_ref "
            "workflow_sha event_name run_invocation bundle payload certificate "
            "verification_command rejected_records verified digest"
        ),
        "capability": "object digest",
        "compile_options": "object digest",
        "byte_comparison": (
            "schema build_a_manifest_sha256 build_b_manifest_sha256 "
            "build_a_archive_sha256 build_b_archive_sha256 tree_comparison "
            "archive_comparison equal digest"
        ),
        "sbom_license_inventory": (
            "schema build_a_sbom_sha256 build_b_sbom_sha256 "
            "build_a_license_inventory_sha256 "
            "build_b_license_inventory_sha256 equal digest"
        ),
        "registration_test_evidence": (
            "command exit_code passed failed skipped stdout stderr "
            "started_wall_ns completed_wall_ns digest"
        ),
        "full_test_evidence": (
            "command exit_code passed failed skipped stdout stderr "
            "started_wall_ns completed_wall_ns digest"
        ),
        "qualification_allowed_signers": "object blob digest",
        "qualification_fixtures": (
            "schema qualification_nonce qualification_root "
            "runtime_archive_sha256 q1 q2 digest"
        ),
        "privileged_qualification_context": "object digest",
        "preprompt_rejection_evidence": (
            "schema exact_head validator_source_sha256 cases "
            "syscall_denial_trace path_remapped_harness digest"
        ),
        "admin_qualification_evidence": (
            "schema exact_head packet_root_digest "
            "qualification_context_digest qualification_allowed_signers_digest "
            "qualification_nonce request_id qualification_root "
            "authorization_result operation_results audit_receipts "
            "cleanup_result no_residue digest"
        ),
        "parent_death_evidence": (
            "schema exact_head platform_bootstrap_contract_sha256 cases "
            "syscall_trace operator_message_results digest"
        ),
        "securityagent_result": (
            "schema invocation_id prompt_count result osascript_exit_code "
            "error_number stdout stderr started_wall_ns completed_wall_ns "
            "packet_root_digest digest"
        ),
        "private_key_deletion": (
            "schema qualification_nonce public_key_openssh "
            "public_key_wire_sha256 deleted_wall_ns private_material_absent "
            "open_fd_matches packet_private_blob_matches packet_root_digest digest"
        ),
        "product_authority_evidence": (
            "schema product_current bundle_manifest bundle_projection "
            "import_manifest host_authority direct_receipt owner_gate "
            "installed_layout retention_cases equality_results digest"
        ),
        "fd_topology_evidence": (
            "schema launch_context source_fd_map target_fd_map fault_cases "
            "ready_measurements go_measurements digest"
        ),
        "retained_import_evidence": (
            "schema manifest_digest first_import package_cases module_cases "
            "relative_import_cases resource_cases filesystem_open_trace "
            "bytecode_write_trace digest"
        ),
        "transaction_recovery_evidence": (
            "schema production_fixture qualification_fixture fault_cases "
            "recovery_cases immutable_phase_chains by_request_pointer_cases "
            "preprepared_null_transaction_cases asset_role_operation_cases "
            "nonce_mode_cases static_contract_set_cases asset_index_cases "
            "result_receipts head_current_receipt_equalities remove_evidence digest"
        ),
        "shell_startup_evidence": (
            "schema script_hashes sentinel_cases executed_startup_files "
            "inherited_environment product_prebootstrap_imports digest"
        ),
    }
    reader_payload_fields = _READER_FINAL_FIELDS - {
        "schema", "repository", "exact_head", "packet_root_index_digest",
        "packet_root_digest", "bound_input_index_digest",
        "evidence_index_digest", "evidence_root_digest", "packet_digest",
    }
    if set(values) != reader_payload_fields:
        raise ValueError("read-back payload fields refused")
    for field, names in object_fields.items():
        value = values.get(field)
        if type(value) is not dict or set(value) != set(names.split()):
            raise ValueError(f"read-back {field} shape refused")

    allowed_boolean_keys = {
        "verified", "fullfsync", "checkpoint_fullfsync", "foreign_keys",
        "connection_setconfig_available",
        "sqlite_dbconfig_defensive_available", "defensive",
        "trusted_schema", "nofollow_available", "checkpoint_on_close",
        "macho", "adhoc", "strict_valid", "equal", "no_residue",
        "private_material_absent",
    }

    def walk(value: object, key: str = "") -> None:
        if type(value) in {int, float}:
            raise ValueError("read-back numeric JSON value refused")
        if type(value) is bool and key not in allowed_boolean_keys:
            raise ValueError("read-back boolean field refused")
        if type(value) is dict:
            for child_key, child in value.items():
                if type(child_key) is not str:
                    raise ValueError("read-back non-string key refused")
                walk(child, child_key)
        elif type(value) is list:
            for child in value:
                walk(child, key)
        elif value is not None and type(value) not in {str, bool}:
            raise ValueError("read-back JSON type refused")

    walk(dict(values))

    def blob(value: object) -> bool:
        if type(value) is not dict:
            return False
        fields = set(value)
        if fields not in (
            _READER_RECORD_FIELDS,
            _READER_RECORD_FIELDS | {"packet_root_digest"},
        ):
            return False
        return (
            all(type(value[field]) is str for field in fields)
            and UINT.fullmatch(value["size"]) is not None
            and _is_hex64(value["sha256"])
            and value["mode"] == "0444"
        )

    github = values["github_attestation"]
    if (
        github["matching_record_count"] != "1"
        or type(github["verified"]) is not bool
        or type(github["verification_command"]) is not list
        or not all(
            type(item) is str for item in github["verification_command"]
        )
        or type(github["rejected_records"]) is not list
        or not all(type(item) is dict for item in github["rejected_records"])
        or any(not blob(github[field]) for field in ("bundle", "payload", "certificate"))
    ):
        raise ValueError("read-back GitHub attestation refused")
    for field in (
        "normalizer_source", "signing_recipe_source",
    ):
        if not blob(values[field]):
            raise ValueError("read-back source blob refused")
    source_lock = values["source_lock"]
    if type(source_lock["object"]) is not dict or not blob(source_lock["blob"]):
        raise ValueError("read-back source lock refused")
    capability = values["capability"]["object"]
    if type(capability) is not dict or len(capability) != 23:
        raise ValueError("read-back capability refused")
    compile_options = values["compile_options"]["object"]
    if (
        type(compile_options) is not dict
        or set(compile_options) != {"schema", "options"}
        or type(compile_options["options"]) is not list
        or not all(type(item) is str for item in compile_options["options"])
    ):
        raise ValueError("read-back compile options refused")
    builds = values.get("builds")
    if (
        type(builds) is not list
        or len(builds) != 2
        or [row.get("build_id") for row in builds if type(row) is dict]
        != ["A", "B"]
    ):
        raise ValueError("read-back builds refused")
    for build in builds:
        if (
            set(build)
            != {
                "build_id", "clean_root_id", "toolchain", "manifest",
                "signature_inventory", "transcript", "archive", "sbom",
                "license_inventory", "registration_tests", "full_tests",
            }
            or type(build["toolchain"]) is not dict
            or not _is_hex64(build["toolchain"].get("codesign_sha256"))
            or type(build["manifest"].get("object")) is not dict
            or type(build["signature_inventory"].get("object")) is not dict
            or any(
                not blob(build[field])
                for field in ("transcript", "archive", "sbom", "license_inventory")
            )
        ):
            raise ValueError("read-back build nested authority refused")
    if values.get("selected_build_id") != "A":
        raise ValueError("read-back selected build refused")
    for field, count in (
        ("final_archives", 2),
        ("relocation_load_image_evidence", 2),
    ):
        rows = values.get(field)
        if type(rows) is not list or len(rows) != count:
            raise ValueError(f"read-back {field} refused")
    if not all(blob(row) for row in values["final_archives"]):
        raise ValueError("read-back archive blob refused")
    identities = values.get("executed_identities")
    identity_fields = {
        "role", "path", "dev", "ino", "pid", "pidversion",
        "mapped_vnode_dev", "mapped_vnode_ino", "cdhash", "sha256",
        "packet_root_digest", "digest",
    }
    if type(identities) is not list or not identities or not all(
        type(row) is dict and set(row) == identity_fields
        for row in identities
    ):
        raise ValueError("read-back identities refused")
    for field in (
        "preprompt_rejection_evidence", "parent_death_evidence",
        "admin_qualification_evidence",
    ):
        record = values[field]
        for list_field in ("cases", "operation_results", "audit_receipts"):
            if list_field in record and (
                type(record[list_field]) is not list
                or not all(type(item) is dict for item in record[list_field])
            ):
                raise ValueError("read-back nested records refused")
    for field in (
        "product_authority_evidence", "fd_topology_evidence",
        "retained_import_evidence", "transaction_recovery_evidence",
        "shell_startup_evidence",
    ):
        for key, value in values[field].items():
            if (
                type(value) is list
                and not all(type(item) is dict for item in value)
            ):
                raise ValueError(f"read-back {field} records refused")
    if not _is_hex64(values["retained_import_evidence"]["manifest_digest"]):
        raise ValueError("read-back retained manifest digest refused")


def _reader_validate_encoding(content: bytes, encoding: object) -> None:
    if encoding == "BINARY":
        return
    if encoding not in {"UTF8", "UTF8_LF", "JCS_LF"}:
        raise ValueError("read-back blob encoding refused")
    if content.startswith(b"\xef\xbb\xbf") or b"\0" in content:
        raise ValueError("read-back UTF-8 framing refused")
    if content.decode("utf-8", "strict").encode("utf-8") != content:
        raise ValueError("read-back UTF-8 round trip refused")
    if encoding in {"UTF8_LF", "JCS_LF"} and (
        not content
        or not content.endswith(b"\n")
        or content.endswith(b"\n\n")
        or b"\r" in content
    ):
        raise ValueError("read-back LF framing refused")
    if encoding == "JCS_LF":
        _parse_canonical_value(content)


def _reader_validate_packet(
    *,
    root_index: object,
    root_bytes: bytes,
    bound_index: object,
    bound_bytes: bytes,
    evidence_index: object,
    evidence_bytes: bytes,
    final_packet: object,
    packet_bytes: bytes,
    blobs: Mapping[str, bytes],
) -> None:
    def validate_index(
        value: object,
        *,
        kind: str,
        packet_root: str | None,
    ) -> list[dict[str, object]]:
        schema, domain = _READER_SCHEMAS[kind]
        fields = (
            {"schema", "records", "index_digest"}
            if packet_root is None
            else {"schema", "packet_root_digest", "records", "index_digest"}
        )
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("read-back index fields refused")
        if value.get("schema") != schema or (
            packet_root is not None
            and value.get("packet_root_digest") != packet_root
        ):
            raise ValueError("read-back index authority refused")
        records = value.get("records")
        if (
            not isinstance(records, list)
            or not records
            or len(records) > _INDEX_MAX_RECORDS
        ):
            raise ValueError("read-back record count refused")
        record_fields = (
            _READER_RECORD_FIELDS
            if packet_root is None
            else _READER_RECORD_FIELDS | {"packet_root_digest"}
        )
        allowed_roles = {
            "root": _READER_ROOT_ROLES,
            "bound": _READER_BOUND_ROLES,
            "evidence": _READER_EVIDENCE_ROLES,
        }[kind]
        prefix = "evidence/sha256/" if kind == "evidence" else "inputs/sha256/"
        for row in records:
            if (
                not isinstance(row, dict)
                or set(row) != record_fields
                or row.get("role") not in allowed_roles
                or row.get("mode") != "0444"
                or row.get("encoding")
                not in {"BINARY", "UTF8", "UTF8_LF", "JCS_LF"}
                or not isinstance(row.get("domain"), str)
                or not isinstance(row.get("media_type"), str)
                or not isinstance(row.get("size"), str)
                or UINT.fullmatch(str(row.get("size"))) is None
                or int(str(row["size"])) > _BLOB_MAX_BYTES
                or not _is_hex64(row.get("sha256"))
                or row.get("path") != prefix + str(row.get("sha256"))
                or (
                    packet_root is not None
                    and row.get("packet_root_digest") != packet_root
                )
            ):
                raise ValueError("read-back record refused")
        ordered = sorted(
            records,
            key=lambda row: (
                str(row["path"]).encode("utf-8"),
                str(row["role"]).encode("utf-8"),
            ),
        )
        if records != ordered or len(
            {(row["path"], row["role"]) for row in records}
        ) != len(records):
            raise ValueError("read-back record order refused")
        body = dict(value)
        claim = body.pop("index_digest")
        if claim != authority_digest(domain, body):
            raise ValueError("read-back index digest refused")
        return records

    root_records = validate_index(root_index, kind="root", packet_root=None)
    if not isinstance(root_index, dict):
        raise ValueError("read-back root index refused")
    root_digest = root_index["index_digest"]
    bound_records = validate_index(
        bound_index, kind="bound", packet_root=str(root_digest)
    )
    evidence_records = validate_index(
        evidence_index, kind="evidence", packet_root=str(root_digest)
    )
    if (
        root_bytes != canonical_lf_bytes(root_index)
        or bound_bytes != canonical_lf_bytes(bound_index)
        or evidence_bytes != canonical_lf_bytes(evidence_index)
        or not isinstance(final_packet, dict)
        or set(final_packet) != _READER_FINAL_FIELDS
        or final_packet.get("schema") != _READER_FINAL_SCHEMA
        or final_packet.get("repository") != "KleinPerkins/awa"
        or re.fullmatch(
            r"[0-9a-f]{40}", str(final_packet.get("exact_head", ""))
        ) is None
        or final_packet.get("packet_root_index_digest") != root_digest
        or final_packet.get("packet_root_digest") != root_digest
        or not isinstance(bound_index, dict)
        or final_packet.get("bound_input_index_digest")
        != bound_index.get("index_digest")
        or not isinstance(evidence_index, dict)
        or final_packet.get("evidence_index_digest")
        != evidence_index.get("index_digest")
        or final_packet.get("evidence_root_digest")
        != evidence_index.get("index_digest")
        or packet_bytes != canonical_lf_bytes(final_packet)
    ):
        raise ValueError("read-back final packet refused")
    final_body = dict(final_packet)
    final_claim = final_body.pop("packet_digest")
    _reader_validate_final_packet_payload_shapes(
        {
            field: final_packet[field]
            for field in _READER_FINAL_FIELDS
            if field
            not in {
                "schema", "repository", "exact_head",
                "packet_root_index_digest", "packet_root_digest",
                "bound_input_index_digest", "evidence_index_digest",
                "evidence_root_digest", "packet_digest",
            }
        }
    )
    if (
        final_claim != authority_digest(_READER_FINAL_SCHEMA, final_body)
        or final_claim == root_digest
    ):
        raise ValueError("read-back final packet digest refused")
    records = root_records + bound_records + evidence_records
    if (
        len({row["sha256"] for row in records}) != len(records)
        or set(blobs) != {row["sha256"] for row in records}
    ):
        raise ValueError("read-back blob set refused")
    aggregate = 0
    for row in records:
        content = blobs[row["sha256"]]
        aggregate += len(content)
        if (
            len(content) != int(str(row["size"]))
            or _sha256(content) != row["sha256"]
        ):
            raise ValueError("read-back blob digest refused")
        _reader_validate_encoding(content, row["encoding"])
        if (
            row["role"] in _READER_BOUND_ROLES
            and row["encoding"] != "JCS_LF"
        ) or (
            str(row["role"]).endswith("_SIGNATURE")
            and row["encoding"] != "BINARY"
        ) or (
            row["role"]
            in {
                "AUTHORIZATION_RESULT",
                "CLEANUP_RESULT",
                "PARENT_DEATH_EVIDENCE",
            }
            and row["encoding"] != "JCS_LF"
        ):
            raise ValueError("read-back role encoding refused")
    if aggregate > _BLOB_AGGREGATE_MAX_BYTES:
        raise ValueError("read-back blob aggregate refused")
    static = {
        str(row["domain"]): str(row["sha256"])
        for row in root_records
        if row["role"] == "STATIC_CONTRACT"
    }
    if (
        static != _READER_STATIC_CONTRACT_HASHES
        or not _READER_REQUIRED_ROOT_ROLES.issubset(
            {str(row["role"]) for row in root_records}
        )
        or {str(row["role"]) for row in bound_records}
        != _READER_BOUND_ROLES
        or str(root_digest).encode("ascii")
        in b"".join(blobs[str(row["sha256"])] for row in root_records)
    ):
        raise ValueError("read-back authority closure refused")


def validate_qualification_packet_binding(
    *,
    packet_root_digest: str,
    qualification_packet_digest: str,
    readback: Mapping[str, object],
) -> None:
    if set(readback) != QUALIFICATION_READBACK_FIELDS:
        raise ValueError("qualification readback fields refused")
    body = dict(readback)
    verifier_digest = body.pop("verifier_digest")
    if (
        not _is_hex64(packet_root_digest)
        or not _is_hex64(qualification_packet_digest)
        or packet_root_digest == qualification_packet_digest
        or readback.get("schema") != QUALIFICATION_READBACK_SCHEMA
        or readback.get("repository") != "KleinPerkins/awa"
        or re.fullmatch(
            r"[0-9a-f]{40}", str(readback.get("exact_head", ""))
        ) is None
        or readback.get("verified") is not True
        or type(readback.get("verified")) is not bool
        or readback.get("static_contract_set_equal") is not True
        or type(readback.get("static_contract_set_equal")) is not bool
        or any(
            not isinstance(readback.get(field), str)
            or UINT.fullmatch(str(readback[field])) is None
            for field in (
                "packet_file_count", "input_blob_count", "evidence_blob_count"
            )
        )
        or any(
            not _is_hex64(readback.get(field))
            for field in (
                "packet_root_digest", "bound_input_index_digest",
                "evidence_root_digest", "qualification_packet_digest",
                "verifier_digest",
            )
        )
        or readback.get("packet_root_digest") != packet_root_digest
        or readback.get("qualification_packet_digest")
        != qualification_packet_digest
        or verifier_digest
        != authority_digest(QUALIFICATION_READBACK_SCHEMA, body)
    ):
        raise ValueError("typed qualification packet binding refused")


def _output_parent(output_root: Path) -> tuple[Path, str]:
    root = output_root.absolute()
    if root.name in {"", ".", ".."} or root.parent == root:
        raise ValueError("packet output root refused")
    return root.parent, root.name


def _directory_flags() -> int:
    required = ("O_DIRECTORY", "O_CLOEXEC", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise ValueError("descriptor-safe directory flags unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


def _open_dir_at(parent_fd: int, name: str, *, mode: int = 0o700) -> int:
    fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != mode
    ):
        os.close(fd)
        raise ValueError("packet directory metadata refused")
    return fd


def _write_file_at(directory_fd: int, name: str, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise ValueError("packet output file metadata refused")
        view = memoryview(content)
        offset = 0
        while offset < len(view):
            try:
                written = os.write(fd, view[offset:])
            except InterruptedError:
                continue
            if written <= 0:
                raise OSError("packet short write")
            offset += written
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    finally:
        os.close(fd)
    verify_fd = os.open(
        name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd
    )
    try:
        before = os.fstat(verify_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o444
            or before.st_size != len(content)
        ):
            raise ValueError("published packet file metadata refused")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                block = os.read(verify_fd, _READ_CHUNK)
            except InterruptedError:
                continue
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > len(content):
                raise ValueError("published packet file grew during read")
        after = os.fstat(verify_fd)
        if (
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
            )
            or total != before.st_size
            or b"".join(chunks) != content
        ):
            raise ValueError("published packet bytes refused")
    finally:
        os.close(verify_fd)


def _read_file_at(directory_fd: int, name: str, limit: int) -> bytes:
    fd = os.open(
        name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd
    )
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o444
            or before.st_size > limit
        ):
            raise ValueError("packet input file metadata refused")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                block = os.read(fd, min(_READ_CHUNK, limit + 1 - total))
            except InterruptedError:
                continue
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > limit:
                raise ValueError("packet input file bound refused")
        after = os.fstat(fd)
        if (
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
            )
            or total != before.st_size
        ):
            raise ValueError("packet input file changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def publish_qualification_packet_prepare(
    output_root: Path, packet: Mapping[str, object]
) -> None:
    validate_qualification_packet_prepare(packet)
    parent, name = _output_parent(output_root)
    parent_fd = os.open(parent, _directory_flags())
    root_fd = inputs_fd = input_hash_fd = evidence_fd = evidence_hash_fd = -1
    parent_identity = os.fstat(parent_fd)
    try:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise ValueError("packet output root already exists") from exc
        root_fd = _open_dir_at(parent_fd, name)
        for child in ("inputs", "evidence"):
            os.mkdir(child, 0o700, dir_fd=root_fd)
        inputs_fd = _open_dir_at(root_fd, "inputs")
        evidence_fd = _open_dir_at(root_fd, "evidence")
        os.mkdir("sha256", 0o700, dir_fd=inputs_fd)
        os.mkdir("sha256", 0o700, dir_fd=evidence_fd)
        input_hash_fd = _open_dir_at(inputs_fd, "sha256")
        evidence_hash_fd = _open_dir_at(evidence_fd, "sha256")
        _write_file_at(
            root_fd,
            "packet-root-index.json",
            packet["packet_root_index_bytes"],  # type: ignore[arg-type]
        )
        _write_file_at(
            root_fd,
            "bound-input-index.json",
            packet["bound_index_bytes"],  # type: ignore[arg-type]
        )
        records = (
            packet["packet_root_index"]["records"]  # type: ignore[index]
            + packet["bound_index"]["records"]  # type: ignore[index]
        )
        blobs = packet["blobs"]
        for row in records:
            _write_file_at(
                input_hash_fd,
                str(row["sha256"]),
                blobs[row["sha256"]],  # type: ignore[index]
            )
        for fd in (input_hash_fd, inputs_fd, evidence_hash_fd, evidence_fd, root_fd):
            os.fsync(fd)
        os.fsync(parent_fd)
        current = os.fstat(parent_fd)
        if (current.st_dev, current.st_ino) != (
            parent_identity.st_dev,
            parent_identity.st_ino,
        ):
            raise ValueError("packet parent identity changed")
    finally:
        for fd in (evidence_hash_fd, evidence_fd, input_hash_fd, inputs_fd, root_fd):
            if fd >= 0:
                os.close(fd)
        os.close(parent_fd)


def publish_qualification_packet_finalize(
    output_root: Path, packet: Mapping[str, object]
) -> dict[str, object]:
    validate_qualification_packet(packet)
    parent, name = _output_parent(output_root)
    parent_fd = os.open(parent, _directory_flags())
    root_fd = inputs_fd = input_hash_fd = evidence_fd = evidence_hash_fd = -1
    try:
        root_fd = _open_dir_at(parent_fd, name)
        if set(os.listdir(root_fd)) != {
            "packet-root-index.json",
            "bound-input-index.json",
            "inputs",
            "evidence",
        }:
            raise ValueError("prepared packet root entries refused")
        inputs_fd = _open_dir_at(root_fd, "inputs")
        evidence_fd = _open_dir_at(root_fd, "evidence")
        if set(os.listdir(inputs_fd)) != {"sha256"} or set(
            os.listdir(evidence_fd)
        ) != {"sha256"}:
            raise ValueError("prepared packet content directories refused")
        input_hash_fd = _open_dir_at(inputs_fd, "sha256")
        evidence_hash_fd = _open_dir_at(evidence_fd, "sha256")
        if os.listdir(evidence_hash_fd):
            raise ValueError("prepared evidence directory is not empty")
        if _read_file_at(
            root_fd, "packet-root-index.json", _INDEX_MAX_BYTES
        ) != packet["packet_root_index_bytes"] or _read_file_at(
            root_fd, "bound-input-index.json", _INDEX_MAX_BYTES
        ) != packet["bound_index_bytes"]:
            raise ValueError("prepared packet indexes changed")
        input_records = (
            packet["packet_root_index"]["records"]  # type: ignore[index]
            + packet["bound_index"]["records"]  # type: ignore[index]
        )
        if set(os.listdir(input_hash_fd)) != {
            str(row["sha256"]) for row in input_records
        }:
            raise ValueError("prepared packet blob set changed")
        for row in input_records:
            if _read_file_at(
                input_hash_fd, str(row["sha256"]), _BLOB_MAX_BYTES
            ) != packet["blobs"][row["sha256"]]:  # type: ignore[index]
                raise ValueError("prepared packet blob changed")
        for row in packet["evidence_index"]["records"]:  # type: ignore[index]
            _write_file_at(
                evidence_hash_fd,
                str(row["sha256"]),
                packet["blobs"][row["sha256"]],  # type: ignore[index]
            )
        _write_file_at(
            root_fd,
            "evidence-index.json",
            packet["evidence_index_bytes"],  # type: ignore[arg-type]
        )
        _write_file_at(
            root_fd, "packet.json", packet["packet_bytes"]  # type: ignore[arg-type]
        )
        for fd in (evidence_hash_fd, evidence_fd, root_fd):
            os.fsync(fd)
        os.fsync(parent_fd)
    finally:
        for fd in (evidence_hash_fd, evidence_fd, input_hash_fd, inputs_fd, root_fd):
            if fd >= 0:
                os.close(fd)
        os.close(parent_fd)
    return verify_qualification_packet_directory(
        output_root,
        repository=str(packet["packet"]["repository"]),  # type: ignore[index]
        exact_head=str(packet["packet"]["exact_head"]),  # type: ignore[index]
        packet_root_digest=str(packet["packet_root_digest"]),
        bound_input_index_digest=str(packet["bound_index_digest"]),
        evidence_root_digest=str(packet["evidence_index_digest"]),
        qualification_packet_digest=str(packet["qualification_packet_digest"]),
    )


def verify_qualification_packet_directory(
    output_root: Path,
    *,
    repository: str,
    exact_head: str,
    packet_root_digest: str,
    bound_input_index_digest: str,
    evidence_root_digest: str,
    qualification_packet_digest: str,
) -> dict[str, object]:
    parent, name = _output_parent(output_root)
    parent_fd = os.open(parent, _directory_flags())
    root_fd = inputs_fd = input_hash_fd = evidence_fd = evidence_hash_fd = -1
    before_parent = os.fstat(parent_fd)
    try:
        root_fd = _open_dir_at(parent_fd, name)
        before_root = set(os.listdir(root_fd))
        if before_root != {
            "packet-root-index.json",
            "bound-input-index.json",
            "inputs",
            "evidence-index.json",
            "evidence",
            "packet.json",
        }:
            raise ValueError("qualification packet root entries refused")
        inputs_fd = _open_dir_at(root_fd, "inputs")
        evidence_fd = _open_dir_at(root_fd, "evidence")
        before_inputs = set(os.listdir(inputs_fd))
        before_evidence = set(os.listdir(evidence_fd))
        if before_inputs != {"sha256"} or before_evidence != {"sha256"}:
            raise ValueError("qualification packet directory entries refused")
        input_hash_fd = _open_dir_at(inputs_fd, "sha256")
        evidence_hash_fd = _open_dir_at(evidence_fd, "sha256")
        before_input_blobs = set(os.listdir(input_hash_fd))
        before_evidence_blobs = set(os.listdir(evidence_hash_fd))
        root_bytes = _read_file_at(
            root_fd, "packet-root-index.json", _INDEX_MAX_BYTES
        )
        bound_bytes = _read_file_at(
            root_fd, "bound-input-index.json", _INDEX_MAX_BYTES
        )
        evidence_bytes = _read_file_at(
            root_fd, "evidence-index.json", _INDEX_MAX_BYTES
        )
        packet_bytes = _read_file_at(root_fd, "packet.json", _INDEX_MAX_BYTES)
        root_index = _parse_canonical_lf(root_bytes)
        bound_index = _parse_canonical_lf(bound_bytes)
        evidence_index = _parse_canonical_lf(evidence_bytes)
        final_packet = _parse_canonical_lf(packet_bytes)
        input_records = root_index.get("records", []) + bound_index.get("records", [])
        evidence_records = evidence_index.get("records", [])
        if before_input_blobs != {
            str(row.get("sha256")) for row in input_records
        } or before_evidence_blobs != {
            str(row.get("sha256")) for row in evidence_records
        }:
            raise ValueError("qualification packet blob names refused")
        blobs: dict[str, bytes] = {}
        for row in input_records:
            digest = str(row.get("sha256"))
            blobs[digest] = _read_file_at(input_hash_fd, digest, _BLOB_MAX_BYTES)
        for row in evidence_records:
            digest = str(row.get("sha256"))
            blobs[digest] = _read_file_at(
                evidence_hash_fd, digest, _BLOB_MAX_BYTES
            )
        packet = {
            "packet_root_index": root_index,
            "packet_root_index_bytes": root_bytes,
            "packet_root_digest": root_index.get("index_digest"),
            "bound_index": bound_index,
            "bound_index_bytes": bound_bytes,
            "bound_index_digest": bound_index.get("index_digest"),
            "evidence_index": evidence_index,
            "evidence_index_bytes": evidence_bytes,
            "evidence_index_digest": evidence_index.get("index_digest"),
            "packet": final_packet,
            "packet_bytes": packet_bytes,
            "qualification_packet_digest": final_packet.get("packet_digest"),
            "blobs": blobs,
        }
        _reader_validate_packet(
            root_index=root_index,
            root_bytes=root_bytes,
            bound_index=bound_index,
            bound_bytes=bound_bytes,
            evidence_index=evidence_index,
            evidence_bytes=evidence_bytes,
            final_packet=final_packet,
            packet_bytes=packet_bytes,
            blobs=blobs,
        )
        expected = {
            "repository": repository,
            "exact_head": exact_head,
            "packet_root_digest": packet_root_digest,
            "bound_input_index_digest": bound_input_index_digest,
            "evidence_root_digest": evidence_root_digest,
            "qualification_packet_digest": qualification_packet_digest,
        }
        observed = {
            "repository": final_packet.get("repository"),
            "exact_head": final_packet.get("exact_head"),
            "packet_root_digest": root_index.get("index_digest"),
            "bound_input_index_digest": bound_index.get("index_digest"),
            "evidence_root_digest": evidence_index.get("index_digest"),
            "qualification_packet_digest": final_packet.get("packet_digest"),
        }
        if expected != observed:
            raise ValueError("qualification packet expected binding refused")
        if (
            root_bytes
            != _read_file_at(
                root_fd, "packet-root-index.json", _INDEX_MAX_BYTES
            )
            or bound_bytes
            != _read_file_at(
                root_fd, "bound-input-index.json", _INDEX_MAX_BYTES
            )
            or evidence_bytes
            != _read_file_at(
                root_fd, "evidence-index.json", _INDEX_MAX_BYTES
            )
            or packet_bytes
            != _read_file_at(root_fd, "packet.json", _INDEX_MAX_BYTES)
            or before_root != set(os.listdir(root_fd))
            or before_inputs != set(os.listdir(inputs_fd))
            or before_evidence != set(os.listdir(evidence_fd))
            or before_input_blobs != set(os.listdir(input_hash_fd))
            or before_evidence_blobs != set(os.listdir(evidence_hash_fd))
            or (before_parent.st_dev, before_parent.st_ino)
            != (os.fstat(parent_fd).st_dev, os.fstat(parent_fd).st_ino)
        ):
            raise ValueError("qualification packet changed during verification")
        readback_body: dict[str, object] = {
            "schema": QUALIFICATION_READBACK_SCHEMA,
            **observed,
            "packet_file_count": str(
                4 + len(input_records) + len(evidence_records)
            ),
            "input_blob_count": str(len(input_records)),
            "evidence_blob_count": str(len(evidence_records)),
            "static_contract_set_equal": True,
            "verified": True,
        }
        return {
            **readback_body,
            "verifier_digest": authority_digest(
                QUALIFICATION_READBACK_SCHEMA, readback_body
            ),
        }
    finally:
        for fd in (evidence_hash_fd, evidence_fd, input_hash_fd, inputs_fd, root_fd):
            if fd >= 0:
                os.close(fd)
        os.close(parent_fd)


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
