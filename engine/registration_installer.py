"""Body C authenticated installer and journal-free C0-C7 cutover driver."""

from __future__ import annotations

import os
import secrets
import stat
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from . import (
    registration_jcs,
    registration_lock,
    registration_projection,
    registration_schema,
    registration_store,
)


class ExternalOwnership(PermissionError):
    """External hook ownership has no M1 persistence or activation path."""


class ReceiptUnavailable(RuntimeError):
    """The exact private DIRECT receipt cannot be established."""


class CutoverRefused(RuntimeError):
    """Cutover cannot safely continue from current authority."""


class Cut(Enum):
    C0 = "C0"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"
    C6 = "C6"
    C7 = "C7"


_CANDIDATE_SEAL = object()


class AuthorizedCandidate:
    __slots__ = ("receipt", "_seal")

    def __init__(
        self,
        receipt: registration_projection.DirectReceipt,
        *,
        _seal: object,
    ) -> None:
        if _seal is not _CANDIDATE_SEAL:
            raise CutoverRefused(
                "candidate authorization is installer-owned"
            )
        object.__setattr__(self, "receipt", receipt)
        object.__setattr__(self, "_seal", _seal)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise CutoverRefused("candidate authorization is immutable")


def authorize_candidate(
    *,
    owner_mode: str,
    receipt: registration_projection.DirectReceipt,
    owner_gate_bytes: bytes,
    owner_gate_signature: bytes,
    owner_gate_verifier: Callable[[bytes, bytes], bool],
    inventory: tuple[registration_projection.InventoryEntry, ...],
    matcher_proof: registration_projection.MatcherProof,
    hook_rows: tuple[registration_projection.HookRow, ...],
) -> AuthorizedCandidate:
    if owner_mode != "direct":
        raise ExternalOwnership(
            "external projection ownership is unsupported in M1"
        )
    registration_projection.verify_receipt_owner_gate(
        receipt,
        owner_gate_bytes,
        owner_gate_signature,
        verifier=owner_gate_verifier,
    )
    registration_projection.validate_candidate_evidence(
        receipt,
        inventory=inventory,
        matcher_proof=matcher_proof,
        rows=hook_rows,
    )
    return AuthorizedCandidate(receipt, _seal=_CANDIDATE_SEAL)


@dataclass(frozen=True)
class ProtocolState:
    mode: str
    staged: bool
    current_is_candidate: bool


class FileAuthority(Protocol):
    def preflight(self) -> None: ...

    def candidate_installed(self) -> bool: ...

    def install_candidate(self) -> None: ...

    def new_projection_active(self) -> bool: ...

    def project_new_receiver(self) -> None: ...

    def old_entrypoints_disabled(self) -> bool: ...

    def disable_old_entrypoints(self) -> None: ...

    def old_bytes_present(self) -> bool: ...

    def clean_old_bytes(self) -> None: ...

    def verify_current(self) -> None: ...


class ControlAuthority(Protocol):
    def protocol_state(self) -> ProtocolState: ...

    def begin_drain(self) -> None: ...

    def activate_current(self) -> None: ...

    def stage_and_adopt(self) -> None: ...

    def advance_generation(self) -> None: ...

    def begin_repair(self) -> None: ...


def authenticate_installer(
    *,
    owner_mode: str,
    candidate: registration_store.ProtocolCandidate,
    installer_identity: bytes,
    installer_capability: bytes,
    protocol_lock_receipt: bytes,
    control_binding: bytes,
    before_persist: Callable[[], None] | None = None,
) -> registration_store.ControlCapability:
    # This check is intentionally first. No directory, receipt, protocol, or
    # status object may be constructed for external ownership in M1.
    if owner_mode != "direct":
        raise ExternalOwnership(
            "external projection ownership is unsupported in M1"
        )
    for label, value in (
        ("installer identity", installer_identity),
        ("installer capability", installer_capability),
        ("protocol-lock receipt", protocol_lock_receipt),
        ("control binding", control_binding),
    ):
        if not isinstance(value, bytes) or not value:
            raise ValueError(f"{label} is unavailable")
    control = registration_store.authenticate_control(
        installer_identity=installer_identity,
        installer_capability=installer_capability,
        protocol_lock_receipt=protocol_lock_receipt,
        control_binding=control_binding,
        expected_identity_hash=candidate.installer_identity_hash,
        expected_capability_hash=candidate.installer_capability_hash,
    )
    if before_persist is not None:
        before_persist()
    return control


def authenticate_with_protocol_lock(
    *,
    owner_mode: str,
    candidate: registration_store.ProtocolCandidate,
    installer_identity: bytes,
    installer_capability: bytes,
    control_binding: bytes,
    locks: registration_lock.LockManager,
) -> registration_store.ControlCapability:
    if owner_mode != "direct":
        raise ExternalOwnership(
            "external projection ownership is unsupported in M1"
        )
    with locks.acquire_protocol() as held:
        held.verify()
        metadata = os.fstat(held.descriptor)
        receipt = registration_jcs.canonical_bytes(
            {
                "schema": "awa-registration-protocol-lock-receipt/v1",
                "kind": held.kind,
                "key": held.key,
                "st_dev": str(metadata.st_dev),
                "st_ino": str(metadata.st_ino),
                "st_mode": str(stat.S_IMODE(metadata.st_mode)),
                "st_uid": str(metadata.st_uid),
                "st_nlink": str(metadata.st_nlink),
            }
        )
        return authenticate_installer(
            owner_mode=owner_mode,
            candidate=candidate,
            installer_identity=installer_identity,
            installer_capability=installer_capability,
            protocol_lock_receipt=receipt,
            control_binding=control_binding,
        )


class DirectReceiptStore:
    """One private same-directory atomic DIRECT receipt."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError("receipt path must be absolute")

    def _prepare_parent(self) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = parent.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ReceiptUnavailable("receipt parent is not private")

    def write(
        self, receipt: registration_projection.DirectReceipt
    ) -> None:
        self._prepare_parent()
        if os.path.lexists(self.path) and self.path.is_symlink():
            raise ReceiptUnavailable("receipt destination is a symlink")
        temporary = self.path.with_name(
            f".{self.path.name}.tmp-{secrets.token_hex(12)}"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            payload = receipt.to_bytes()
            view = memoryview(payload)
            offset = 0
            while offset < len(view):
                count = os.write(descriptor, view[offset:])
                if count <= 0:
                    raise OSError("short receipt write")
                offset += count
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        except Exception:
            os.close(descriptor)
            try:
                temporary.unlink()
            except OSError:
                pass
            raise
        else:
            os.close(descriptor)
        try:
            os.replace(temporary, self.path)
            parent_fd = os.open(
                self.path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def read(self) -> registration_projection.DirectReceipt:
        try:
            metadata = self.path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                raise ReceiptUnavailable("receipt identity is unsafe")
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                bound = os.fstat(descriptor)
                if (bound.st_dev, bound.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise ReceiptUnavailable(
                        "receipt changed while opening"
                    )
                raw = os.read(descriptor, 65_537)
            finally:
                os.close(descriptor)
            return registration_projection.DirectReceipt.from_bytes(raw)
        except ReceiptUnavailable:
            raise
        except (OSError, ValueError) as exc:
            raise ReceiptUnavailable(
                "DIRECT receipt is unavailable"
            ) from exc


def _atomic_private_write(
    path: Path, payload: bytes, *, mode: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.lstat()
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise CutoverRefused("installer destination parent is unsafe")
    temporary = path.with_name(
        f".{path.name}.tmp-{secrets.token_hex(12)}"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            count = os.write(descriptor, view[offset:])
            if count <= 0:
                raise OSError("short installer file write")
            offset += count
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        parent_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class RuntimeFileAuthority:
    """Versioned receiver bytes plus one atomic active projection."""

    PROJECTION_SCHEMA = "awa-registration-receiver-projection/v1"

    def __init__(
        self,
        *,
        root: Path,
        authorization: AuthorizedCandidate,
        candidate_bytes: bytes,
    ) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("runtime file root must be absolute")
        if not isinstance(candidate_bytes, bytes) or not candidate_bytes:
            raise ValueError("candidate receiver bytes are required")
        if (
            not isinstance(authorization, AuthorizedCandidate)
            or authorization._seal is not _CANDIDATE_SEAL
        ):
            raise CutoverRefused(
                "runtime files require authorized candidate evidence"
            )
        self.receipt = authorization.receipt
        self.candidate_bytes = candidate_bytes
        self.receiver_root = self.root / "receivers"
        self.candidate_path = (
            self.receiver_root
            / self.receipt.candidate_digest
            / "awa-registration-receiver"
        )
        self.old_receiver_path = (
            self.receiver_root / "old" / "awa-registration-receiver"
        )
        self.disabled_old_path = self.old_receiver_path.with_name(
            self.old_receiver_path.name + ".disabled"
        )
        self.projection_path = self.root / "active-projection.json"
        self.receipt_store = DirectReceiptStore(
            self.root / "direct-receipt.json"
        )

    def _projection(self) -> dict[str, object]:
        return {
            "schema": self.PROJECTION_SCHEMA,
            "candidate_digest": self.receipt.candidate_digest,
            "receiver": str(self.candidate_path),
            "installed_file_hash": self.receipt.installed_file_hash,
            "direct_receipt_hash": self.receipt.digest,
            "projection_file_generation": (
                self.receipt.projection_file_generation
            ),
        }

    def _read_projection(self) -> dict | None:
        try:
            metadata = self.projection_path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                raise CutoverRefused("active projection is unsafe")
            raw = self.projection_path.read_bytes()
            if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
                raise CutoverRefused("active projection is not canonical")
            value = registration_jcs.parse_canonical(raw[:-1])
            canonical = registration_jcs.canonical_bytes(value) + b"\n"
            if canonical != raw:
                raise CutoverRefused("active projection is not canonical")
        except FileNotFoundError:
            return None
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            registration_jcs.JcsError,
        ) as exc:
            raise CutoverRefused(
                "active projection is unavailable"
            ) from exc
        return value if isinstance(value, dict) else None

    def preflight(self) -> None:
        if os.path.lexists(self.root) and self.root.is_symlink():
            raise CutoverRefused("runtime file root is a symlink")
        if self.candidate_installed():
            self.verify_current()

    def candidate_installed(self) -> bool:
        if not self.candidate_path.exists():
            return False
        try:
            installed = registration_projection.installed_file_hash(
                self.candidate_path
            )
        except (OSError, ValueError) as exc:
            raise CutoverRefused(
                "candidate bytes are unavailable"
            ) from exc
        if installed != self.receipt.installed_file_hash:
            raise CutoverRefused("candidate bytes drifted")
        if not self.receipt_store.path.exists():
            return False
        try:
            receipt = self.receipt_store.read()
        except ReceiptUnavailable as exc:
            raise CutoverRefused("candidate receipt drifted") from exc
        if receipt != self.receipt:
            raise CutoverRefused("candidate receipt drifted")
        return True

    def install_candidate(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.receiver_root.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.receiver_root, 0o700)
        _atomic_private_write(
            self.candidate_path, self.candidate_bytes, mode=0o700
        )
        if (
            registration_projection.installed_file_hash(
                self.candidate_path
            )
            != self.receipt.installed_file_hash
        ):
            raise CutoverRefused("installed receiver hash mismatch")
        self.receipt_store.write(self.receipt)

    def new_projection_active(self) -> bool:
        projection = self._read_projection()
        return projection == self._projection()

    def project_new_receiver(self) -> None:
        self.verify_current()
        payload = (
            json.dumps(
                self._projection(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("ascii")
        _atomic_private_write(
            self.projection_path, payload, mode=0o600
        )

    def old_entrypoints_disabled(self) -> bool:
        old = os.path.lexists(self.old_receiver_path)
        disabled = os.path.lexists(self.disabled_old_path)
        if old and disabled:
            raise CutoverRefused("old receiver has split identity")
        if old and self.old_receiver_path.is_symlink():
            raise CutoverRefused("old receiver is a symlink")
        if disabled and self.disabled_old_path.is_symlink():
            raise CutoverRefused("disabled receiver is a symlink")
        return not old

    def disable_old_entrypoints(self) -> None:
        self.verify_current()
        if not self.new_projection_active():
            raise CutoverRefused(
                "new projection is not exact; last receiver retained"
            )
        if not os.path.lexists(self.old_receiver_path):
            return
        if os.path.lexists(self.disabled_old_path):
            raise CutoverRefused("disabled old receiver already exists")
        os.replace(self.old_receiver_path, self.disabled_old_path)
        parent_fd = os.open(
            self.old_receiver_path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    def old_bytes_present(self) -> bool:
        if os.path.lexists(self.old_receiver_path):
            raise CutoverRefused("old entrypoint is still enabled")
        return os.path.lexists(self.disabled_old_path)

    def clean_old_bytes(self) -> None:
        self.verify_current()
        if os.path.lexists(self.old_receiver_path):
            raise CutoverRefused("refusing to clean enabled old receiver")
        if os.path.lexists(self.disabled_old_path):
            self.disabled_old_path.unlink()
            parent_fd = os.open(
                self.disabled_old_path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)

    def verify_current(self) -> None:
        if not self.candidate_path.is_file():
            raise CutoverRefused("candidate receiver is absent")
        try:
            receipt = self.receipt_store.read()
            installed = registration_projection.installed_file_hash(
                self.candidate_path
            )
        except (OSError, ValueError, ReceiptUnavailable) as exc:
            raise CutoverRefused(
                "candidate receiver could not be verified"
            ) from exc
        if (
            receipt != self.receipt
            or installed != self.receipt.installed_file_hash
        ):
            raise CutoverRefused("candidate receiver identity mismatch")
        projection = self._read_projection()
        if projection is not None and projection != self._projection():
            raise CutoverRefused("active projection receipt mismatch")

    def seed_old_receiver(self, payload: bytes) -> None:
        """Disposable fixture helper; production cutover discovers old bytes."""
        _atomic_private_write(
            self.old_receiver_path, payload, mode=0o700
        )


class CutoverDriver:
    """Derive each restart solely from current files and protocol authority."""

    def __init__(
        self, files: FileAuthority, control: ControlAuthority
    ) -> None:
        self.files = files
        self.control = control

    def current_cut(self) -> Cut:
        if not self.files.candidate_installed():
            return Cut.C0
        if not self.files.new_projection_active():
            return Cut.C1
        if not self.files.old_entrypoints_disabled():
            return Cut.C2
        protocol = self.control.protocol_state()
        if protocol.current_is_candidate:
            return (
                Cut.C6 if self.files.old_bytes_present() else Cut.C7
            )
        if protocol.mode in {"DORMANT", "WRITABLE"} and not protocol.staged:
            return Cut.C3
        if protocol.mode in {"DRAINING", "CONTAINMENT"} and not protocol.staged:
            return Cut.C4
        if protocol.mode in {"DRAINING", "CONTAINMENT"} and protocol.staged:
            return Cut.C5
        raise CutoverRefused(
            "file receipt and protocol authority do not select a cut"
        )

    def step(self) -> Cut:
        self.files.preflight()
        current = self.current_cut()
        if current is Cut.C0:
            self.files.install_candidate()
        elif current is Cut.C1:
            self.files.verify_current()
            self.files.project_new_receiver()
        elif current is Cut.C2:
            # The exact new receiver is proven before the old receiver can
            # become unreachable.
            self.files.verify_current()
            self.files.disable_old_entrypoints()
        elif current is Cut.C3:
            protocol = self.control.protocol_state()
            if protocol.mode == "DORMANT":
                self.control.activate_current()
            else:
                self.control.begin_drain()
        elif current is Cut.C4:
            protocol = self.control.protocol_state()
            if protocol.mode == "CONTAINMENT":
                self.control.begin_repair()
            else:
                self.control.stage_and_adopt()
        elif current is Cut.C5:
            protocol = self.control.protocol_state()
            if protocol.mode == "CONTAINMENT":
                self.control.begin_repair()
            else:
                self.control.advance_generation()
        elif current is Cut.C6:
            self.files.verify_current()
            self.files.clean_old_bytes()
        else:
            self.files.verify_current()
            return Cut.C7
        return self.current_cut()

    def run_to_completion(self) -> Cut:
        for _ in range(16):
            if self.current_cut() is Cut.C7:
                self.files.preflight()
                self.files.verify_current()
                return Cut.C7
            self.step()
        raise CutoverRefused("cutover did not converge within C0-C7")

    def recover_failure(
        self,
        *,
        adoption_started: bool,
        containment_reason: str = "ADOPTION_FAILED",
    ) -> None:
        if containment_reason not in {
            "ADOPTION_FAILED",
            "DRAIN_BOOT_CHANGED",
            "DRAIN_TIMEOUT",
            "STORE_FAILURE",
        }:
            raise CutoverRefused("unknown containment reason")
        if adoption_started or containment_reason != "ADOPTION_FAILED":
            method = getattr(self.control, "enter_containment", None)
            if method is None:
                raise CutoverRefused(
                    "post-adoption failure requires containment"
                )
            method(containment_reason)
            return
        method = getattr(self.control, "cancel_drain", None)
        if method is None:
            raise CutoverRefused(
                "pre-adoption failure cannot cancel drain"
            )
        method()


class StoreControlAdapter:
    """Orchestrate only Body A typed CONTROL calls."""

    def __init__(
        self,
        *,
        store: registration_store.RegistrationStore,
        control: registration_store.ControlCapability,
        current: registration_store.ProtocolCandidate,
        staged: registration_store.ProtocolCandidate,
        authorization: AuthorizedCandidate,
        quiescence_proof_hash: str,
        adopter: Callable[[], None],
    ) -> None:
        self.store = store
        self.control = control
        self.current = current
        self.staged = staged
        if (
            not isinstance(authorization, AuthorizedCandidate)
            or authorization._seal is not _CANDIDATE_SEAL
        ):
            raise CutoverRefused(
                "protocol cutover needs authorized candidate evidence"
            )
        receipt = authorization.receipt
        protocol = store.current_protocol()
        if (
            protocol is None
            or not self._matches(protocol, current)
            or receipt.schema_hash != registration_schema.SCHEMA_SHA256
            or receipt.protocol_generation
            != str(int(protocol["protocol_generation"]) + 1)
            or receipt.profile_hash != staged.profile_hash
            or receipt.runtime_capability_hash
            != staged.runtime_capability_hash
            or receipt.writer_binary_hash != staged.writer_binary_hash
            or receipt.writer_capability_hash
            != staged.writer_capability_hash
            or receipt.tool_inventory_hash != staged.tool_inventory_hash
            or receipt.hook_projection_hash
            != staged.hook_projection_hash
            or receipt.hook_matcher_mode != staged.hook_matcher_mode
            or receipt.hook_matcher_hash != staged.hook_matcher_hash
            or receipt.projection_file_generation
            != str(staged.projection_file_generation)
            or receipt.installer_identity_hash
            != staged.installer_identity_hash
            or receipt.installer_capability_hash
            != staged.installer_capability_hash
            or receipt.digest != staged.projection_receipt_hash
            or staged.storage_dev != current.storage_dev
        ):
            raise CutoverRefused(
                "authorized receipt does not bind staged protocol candidate"
            )
        self.authorization = authorization
        self.quiescence_proof_hash = quiescence_proof_hash
        self.adopter = adopter

    @staticmethod
    def _matches(
        protocol: dict[str, object],
        candidate: registration_store.ProtocolCandidate,
    ) -> bool:
        return all(
            protocol[name] == getattr(candidate, name)
            for name in (
                "profile_hash",
                "runtime_capability_hash",
                "writer_binary_hash",
                "writer_capability_hash",
                "tool_inventory_hash",
                "hook_projection_hash",
                "hook_matcher_mode",
                "hook_matcher_hash",
                "projection_receipt_hash",
                "projection_file_generation",
                "installer_identity_hash",
                "installer_capability_hash",
                "storage_dev",
            )
        )

    def protocol_state(self) -> ProtocolState:
        protocol = self.store.current_protocol()
        if protocol is None:
            raise CutoverRefused("protocol authority is absent")
        return ProtocolState(
            mode=str(protocol["mode"]),
            staged=protocol["staged_generation"] is not None,
            current_is_candidate=self._matches(protocol, self.staged),
        )

    def begin_drain(self) -> None:
        self.store.begin_drain(self.control, self.current)

    def activate_current(self) -> None:
        self.store.activate(self.control, self.current)

    def stage_and_adopt(self) -> None:
        protocol = self.store.current_protocol()
        if protocol is None:
            raise CutoverRefused("protocol authority is absent")
        if protocol["staged_generation"] is None:
            self.store.stage_next(
                self.control,
                self.current,
                self.staged,
                quiescence_proof_hash=self.quiescence_proof_hash,
            )
        self.adopter()

    def advance_generation(self) -> None:
        self.store.advance_generation(
            self.control,
            self.current,
            quiescence_proof_hash=self.quiescence_proof_hash,
        )

    def cancel_drain(self) -> None:
        self.store.cancel_drain(
            self.control,
            self.current,
            quiescence_proof_hash=self.quiescence_proof_hash,
        )

    def enter_containment(
        self, reason: str = "ADOPTION_FAILED"
    ) -> None:
        self.store.enter_containment(
            self.control,
            self.current,
            reason=reason,
        )

    def begin_repair(self) -> None:
        self.store.begin_repair(self.control, self.current)
