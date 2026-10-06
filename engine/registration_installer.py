"""Body C authenticated installer and journal-free C0-C7 cutover driver."""

from __future__ import annotations

import ast
import hashlib
import os
import secrets
import stat
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Protocol

from . import (
    registration_jcs,
    registration_lock,
    registration_projection,
    registration_profile,
    registration_schema,
    registration_store,
)


class ExternalOwnership(PermissionError):
    """External hook ownership has no M1 persistence or activation path."""


class ReceiptUnavailable(RuntimeError):
    """The exact private DIRECT receipt cannot be established."""


class CutoverRefused(RuntimeError):
    """Cutover cannot safely continue from current authority."""


def _manifest_module_path(root: Path, module: str) -> Path:
    if (
        not isinstance(module, str)
        or not module
        or any(
            not part or not part.isidentifier()
            for part in module.split(".")
        )
    ):
        raise CutoverRefused("import-manifest module name is invalid")
    relative = Path(*module.split(".")).with_suffix(".py")
    path = root / relative
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise CutoverRefused("import-manifest path escaped bundle") from exc
    return path


def _manifest_file(
    root: Path,
    path: Path,
    *,
    kind: str,
    logical_name: str,
    owner_module: str | None,
    fd_target: int,
) -> registration_projection.ImportRecordV2:
    try:
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            raise CutoverRefused("import-manifest file identity is unsafe")
        payload = path.read_bytes()
        rebound = path.lstat()
        if (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (
            rebound.st_dev,
            rebound.st_ino,
            rebound.st_size,
            rebound.st_mtime_ns,
        ):
            raise CutoverRefused("import-manifest file changed while reading")
    except (OSError, ValueError) as exc:
        if isinstance(exc, CutoverRefused):
            raise
        raise CutoverRefused("import-manifest file is unavailable") from exc
    return registration_projection.ImportRecordV2(
        kind=kind,
        logical_name=logical_name,
        relative_path=relative,
        owner_module=owner_module,
        fd_target=str(fd_target),
        mode="444",
        size=str(len(payload)),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _resolved_product_imports(
    *,
    tree: ast.AST,
    current_module: str,
    package_root: str,
) -> set[str]:
    discovered: set[str] = set()
    current_package = current_module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            dynamic = (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
            ) or (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
                and node.func.attr == "import_module"
            )
            if dynamic:
                raise CutoverRefused(
                    "dynamic product import is unsupported"
                )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == package_root or alias.name.startswith(
                    package_root + "."
                ):
                    discovered.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = current_package.split(".")
                keep = len(package_parts) - node.level + 1
                if keep < 1:
                    raise CutoverRefused(
                        "relative import escaped product package"
                    )
                base = ".".join(package_parts[:keep])
                if node.module:
                    base = f"{base}.{node.module}"
            else:
                base = node.module or ""
            if base == package_root or base.startswith(package_root + "."):
                if node.module:
                    discovered.add(base)
                for alias in node.names:
                    if alias.name != "*":
                        discovered.add(f"{base}.{alias.name}")
            elif node.level:
                raise CutoverRefused(
                    "relative import escaped product package"
                )
    return discovered


def generate_import_manifest(
    bundle_root: Path,
) -> registration_projection.ImportManifestV2:
    """Generate the receiver-rooted closed static product-import manifest."""
    root = Path(bundle_root)
    try:
        root = root.resolve(strict=True)
        metadata = root.lstat()
    except OSError as exc:
        raise CutoverRefused("bundle root is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
    ):
        raise CutoverRefused("bundle root identity is unsafe")
    package_root = "engine"
    pending = ["engine.registration_receiver"]
    visited: set[str] = set()
    files: dict[str, tuple[Path, str, str, str | None]] = {}
    while pending:
        module = pending.pop(0)
        if module in visited:
            continue
        candidate = _manifest_module_path(root, module)
        if not candidate.is_file():
            package_candidate = (
                root / Path(*module.split(".")) / "__init__.py"
            )
            if package_candidate.is_file():
                candidate = package_candidate
        if not candidate.is_file():
            # `from package import symbol` may identify an attribute rather
            # than a module. It is ignored only when its containing module
            # has already been resolved.
            parent = module.rsplit(".", 1)[0] if "." in module else ""
            if parent in visited:
                continue
            raise CutoverRefused(
                f"unresolved product import: {module}"
            )
        try:
            source = candidate.read_bytes()
            tree = ast.parse(source, filename=str(candidate))
        except (OSError, SyntaxError, UnicodeError) as exc:
            raise CutoverRefused(
                f"product import could not be parsed: {module}"
            ) from exc
        visited.add(module)
        files[candidate.relative_to(root).as_posix()] = (
            candidate,
            (
                "PACKAGE_INITIALIZER"
                if candidate.name == "__init__.py"
                else "MODULE"
            ),
            module,
            None,
        )
        relative = candidate.relative_to(root)
        for parent in tuple(relative.parents)[:-1]:
            initializer = root / parent / "__init__.py"
            if not initializer.is_file():
                raise CutoverRefused(
                    "package initializer is missing"
                )
            package_name = ".".join(parent.parts)
            files[initializer.relative_to(root).as_posix()] = (
                initializer,
                "PACKAGE_INITIALIZER",
                package_name,
                None,
            )
        for imported in sorted(
            _resolved_product_imports(
                tree=tree,
                current_module=module,
                package_root=package_root,
            ),
            key=lambda value: value.encode("utf-8"),
        ):
            if imported not in visited and imported not in pending:
                pending.append(imported)
    schema_resource = root / "engine/registration_schema.sql"
    if (
        "engine.registration_schema" not in visited
        or not schema_resource.is_file()
    ):
        raise CutoverRefused("mandatory schema resource is unavailable")
    files[schema_resource.relative_to(root).as_posix()] = (
        schema_resource,
        "RESOURCE",
        "engine.registration_schema:registration_schema.sql",
        "engine.registration_schema",
    )
    records = tuple(
        _manifest_file(
            root,
            files[path][0],
            kind=files[path][1],
            logical_name=files[path][2],
            owner_module=files[path][3],
            fd_target=16 + ordinal,
        )
        for ordinal, path in enumerate(
            sorted(files, key=lambda value: value.encode("utf-8"))
        )
    )
    return registration_projection.ImportManifestV2.create(records)


def generate_bundle_manifest(
    *,
    generation: str,
    import_manifest: registration_projection.ImportManifestV2,
    host_authority: registration_projection.HostAuthorityV2,
    writer_capability_hash: str,
    installed_file_hash: str,
    payload_bytes: Mapping[str, bytes],
) -> registration_projection.BundleManifestV3:
    """Construct only the accepted acyclic bundle-manifest v3 authority."""
    return registration_projection.BundleManifestV3.create(
        generation=generation,
        import_manifest=import_manifest,
        host_authority=host_authority,
        writer_capability_hash=writer_capability_hash,
        installed_file_hash=installed_file_hash,
        payload_bytes=payload_bytes,
    )


def measure_external_interpreter(
    selection: registration_projection.InterpreterSelection,
    capability: registration_profile.InterpreterCapability,
) -> tuple[dict[str, object], str]:
    """Descriptor-walk and bind one explicitly authorized interpreter."""
    if not isinstance(
        selection, registration_projection.InterpreterSelection
    ) or not isinstance(
        capability, registration_profile.InterpreterCapability
    ):
        raise CutoverRefused(
            "interpreter selection and capability must be validated"
        )
    path = Path(
        registration_projection.validate_interpreter_path(
            selection.interpreter_path
        )
    )
    components = path.parts
    if len(components) < 2 or components[0] != "/":
        raise CutoverRefused("interpreter path has no final component")
    descriptors: list[int] = []
    records: list[dict[str, object]] = []
    final_fd = -1
    try:
        current_fd = os.open(
            "/",
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        descriptors.append(current_fd)
        parent_components = ("/", *components[1:-1])
        for ordinal, component in enumerate(parent_components):
            if ordinal:
                current_fd = os.open(
                    component,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current_fd,
                )
                descriptors.append(current_fd)
            metadata = os.fstat(current_fd)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, os.geteuid()}
                or metadata.st_mode & 0o022
                or metadata.st_nlink < 1
            ):
                raise CutoverRefused(
                    "interpreter ancestor is unsafe"
                )
            records.append(
                {
                    "ordinal": str(ordinal),
                    "component_hash": hashlib.sha256(
                        b"awa-registration-path-component/v1\0"
                        + component.encode("utf-8")
                    ).hexdigest(),
                    "st_dev": str(metadata.st_dev),
                    "st_ino": str(metadata.st_ino),
                    "st_mode": str(metadata.st_mode),
                    "st_uid": str(metadata.st_uid),
                    "st_gid": str(metadata.st_gid),
                    "st_nlink": str(metadata.st_nlink),
                    "object_type": "DIRECTORY",
                }
            )
        final_fd = os.open(
            components[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current_fd,
        )
        metadata = os.fstat(final_fd)
        visible = path.lstat()
        identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or metadata.st_mode & 0o022
            or metadata.st_mode & stat.S_IXUSR == 0
            or metadata.st_nlink != 1
            or identity
            != (
                visible.st_dev,
                visible.st_ino,
                visible.st_mode,
                visible.st_uid,
                visible.st_gid,
                visible.st_nlink,
                visible.st_size,
                visible.st_mtime_ns,
            )
        ):
            raise CutoverRefused("interpreter file authority is unsafe")
        content = bytearray()
        while True:
            chunk = os.read(final_fd, 65_536)
            if not chunk:
                break
            content.extend(chunk)
        after = os.fstat(final_fd)
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
            raise CutoverRefused(
                "interpreter changed while measuring"
            )
        external = {
            "schema": "awa-registration-external-interpreter/v1",
            "selection_hash": selection.digest,
            "path": str(path),
            "path_hash": registration_projection.interpreter_path_hash(
                str(path)
            ),
            "ancestry_hash": (
                registration_projection.interpreter_ancestry_hash(records)
            ),
            "st_uid": str(metadata.st_uid),
            "st_gid": str(metadata.st_gid),
            "st_mode": str(metadata.st_mode),
            "st_dev": str(metadata.st_dev),
            "st_ino": str(metadata.st_ino),
            "st_nlink": str(metadata.st_nlink),
            "st_size": str(metadata.st_size),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "capability_probe_hash": capability.digest,
            "probe_program_hash": capability.probe_program_hash,
        }
        digest = registration_profile.external_interpreter_hash(
            external,
            capability=capability,
        )
        return external, digest
    except (OSError, ValueError, registration_profile.ProfileError) as exc:
        if isinstance(exc, CutoverRefused):
            raise
        raise CutoverRefused(
            "interpreter measurement is unavailable"
        ) from exc
    finally:
        if final_fd >= 0:
            os.close(final_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


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
    __slots__ = ("receipt", "owner_gate", "enrollment_hash", "_seal")

    def __init__(
        self,
        receipt: registration_projection.DirectReceipt,
        *,
        owner_gate: registration_projection.OwnerGate,
        enrollment_hash: str,
        _seal: object,
    ) -> None:
        if _seal is not _CANDIDATE_SEAL:
            raise CutoverRefused(
                "candidate authorization is installer-owned"
            )
        registration_projection.validate_receipt_against_gate(
            receipt, owner_gate
        )
        if (
            not isinstance(enrollment_hash, str)
            or len(enrollment_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in enrollment_hash
            )
        ):
            raise CutoverRefused("candidate enrollment hash is invalid")
        object.__setattr__(self, "receipt", receipt)
        object.__setattr__(self, "owner_gate", owner_gate)
        object.__setattr__(self, "enrollment_hash", enrollment_hash)
        object.__setattr__(self, "_seal", _seal)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise CutoverRefused("candidate authorization is immutable")


def authorize_candidate(
    *,
    owner_mode: str,
    receipt: registration_projection.DirectReceipt,
    owner_gate_bytes: bytes,
    owner_gate_signature_path: Path,
    bundle_root: Path,
    current_enrollment_path: Path,
    expected_enrollment_hash: str,
    inventory: tuple[registration_projection.InventoryEntry, ...],
    matcher_proof: registration_projection.MatcherProof,
    hook_rows: tuple[registration_projection.HookRow, ...],
) -> AuthorizedCandidate:
    if owner_mode != "direct":
        raise ExternalOwnership(
            "external projection ownership is unsupported in M1"
        )
    owner_gate = registration_projection.verify_owner_gate_signature(
        owner_gate_bytes,
        signature_path=owner_gate_signature_path,
        bundle_root=bundle_root,
        current_receipt_path=current_enrollment_path,
        expected_enrollment_hash=expected_enrollment_hash,
    )
    registration_projection.validate_receipt_against_gate(
        receipt,
        owner_gate,
    )
    registration_projection.validate_candidate_evidence(
        receipt,
        inventory=inventory,
        matcher_proof=matcher_proof,
        rows=hook_rows,
    )
    current_descriptor, current_raw = (
        registration_projection._authority_descriptor(
            current_enrollment_path,
            modes=frozenset({0o600}),
            limit=65_536,
        )
    )
    try:
        current = registration_projection.CurrentOwnerKey.from_bytes(
            current_raw
        )
    finally:
        os.close(current_descriptor)
    if current.enrollment_hash != expected_enrollment_hash:
        raise CutoverRefused(
            "current owner-key enrollment changed after verification"
        )
    return AuthorizedCandidate(
        receipt,
        owner_gate=owner_gate,
        enrollment_hash=current.enrollment_hash,
        _seal=_CANDIDATE_SEAL,
    )


@dataclass(frozen=True)
class ProtocolState:
    mode: str
    staged: bool
    current_is_candidate: bool
    adoption_pass_complete: bool = False
    custody_empty: bool = False


class FileAuthority(Protocol):
    def preflight(self) -> None: ...

    def candidate_installed(self) -> bool: ...

    def install_candidate(self) -> None: ...

    def new_projection_active(self) -> bool: ...

    def project_new_receiver(self) -> None: ...

    def prove_staged(self, phase: str) -> None: ...

    def restore_old_projection(self) -> None: ...

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

    def stage_candidate(self) -> None: ...

    def reconcile_adoption(self) -> None: ...

    def advance_generation(self) -> None: ...

    def cancel_drain(self) -> None: ...

    def enter_containment(self, reason: str) -> None: ...

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


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_immutable_file(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.path.lexists(path):
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != mode
            or metadata.st_nlink != 1
            or path.read_bytes() != payload
        ):
            raise CutoverRefused("immutable bundle entry drifted")
        return
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    primary: BaseException | None = None
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError("short immutable bundle write")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except BaseException as close_error:
            if primary is None:
                raise
            if hasattr(primary, "add_note"):
                primary.add_note(
                    f"secondary descriptor close failure: {close_error!r}"
                )
    _fsync_directory(path.parent)


class ImmutableBundleAuthority:
    """Generation-qualified immutable bundle plus one atomic active pointer."""

    def __init__(
        self,
        *,
        root: Path,
        authorization: AuthorizedCandidate,
        manifest: registration_projection.BundleManifest,
        projection: registration_projection.BundleProjection,
        launcher_config: registration_projection.LauncherConfig,
        payloads: Mapping[str, bytes],
        expected_denial_proof: (
            registration_projection.StagedDenialProof
        ),
        inventory: tuple[
            registration_projection.InventoryEntry, ...
        ],
        denial_requests: Mapping[
            tuple[str, str, str, str], bytes
        ],
        denial_runner: Callable[
            [
                str,
                str,
                registration_projection.InventoryEntry,
                bytes,
            ],
            tuple[bytes, int],
        ],
        old_pointer: (
            registration_projection.ActiveBundlePointer | None
        ) = None,
    ) -> None:
        self.root = Path(root)
        if (
            not self.root.is_absolute()
            or os.path.normpath(str(self.root)) != str(self.root)
        ):
            raise ValueError("runtime root must be canonical absolute")
        if (
            not isinstance(authorization, AuthorizedCandidate)
            or authorization._seal is not _CANDIDATE_SEAL
        ):
            raise CutoverRefused(
                "bundle files require authorized candidate evidence"
            )
        receipt = authorization.receipt
        if (
            manifest.digest != receipt.bundle_digest
            or projection.digest != receipt.bundle_projection_hash
            or projection.bundle_digest != manifest.digest
            or projection.generation != receipt.bundle_generation
            or launcher_config.bundle_generation
            != receipt.bundle_generation
            or launcher_config.file_hash
            != projection.runtime_config_hash
            or manifest.import_manifest_hash
            != receipt.import_manifest_hash
            or manifest.external_interpreter_hash
            != receipt.external_interpreter_hash
            or manifest.interpreter_capability_hash
            != receipt.interpreter_capability_hash
            or manifest.allowed_signers_contract_hash
            != receipt.allowed_signers_contract_hash
            or projection.bundle_digest != receipt.bundle_digest
            or projection.import_manifest_hash
            != receipt.import_manifest_hash
            or projection.external_interpreter_hash
            != receipt.external_interpreter_hash
            or projection.interpreter_capability_hash
            != receipt.interpreter_capability_hash
            or projection.allowed_signers_contract_hash
            != receipt.allowed_signers_contract_hash
            or launcher_config.external_interpreter_hash
            != receipt.external_interpreter_hash
            or launcher_config.interpreter_capability_hash
            != receipt.interpreter_capability_hash
            or launcher_config.import_manifest_hash
            != receipt.import_manifest_hash
            or expected_denial_proof.digest
            != receipt.denial_proof_vector_hash
        ):
            raise CutoverRefused(
                "bundle authority does not match DIRECT receipt"
            )
        if not callable(denial_runner):
            raise CutoverRefused("denial runner is unavailable")
        payload_map = dict(payloads)
        if set(payload_map) != {entry.path for entry in manifest.entries}:
            raise CutoverRefused("bundle payload set is not exact")
        for entry in manifest.entries:
            payload = payload_map[entry.path]
            if (
                not isinstance(payload, bytes)
                or len(payload) != int(entry.size)
                or hashlib.sha256(payload).hexdigest() != entry.sha256
            ):
                raise CutoverRefused(
                    f"bundle payload mismatch: {entry.path}"
                )
        import_payload = payload_map["import-manifest.json"]
        try:
            import_manifest = (
                registration_projection.ImportManifest.from_bytes(
                    import_payload
                )
            )
        except ValueError as exc:
            raise CutoverRefused(
                "bundle import manifest is invalid"
            ) from exc
        if import_manifest.digest != receipt.import_manifest_hash:
            raise CutoverRefused("bundle import authority mismatch")
        by_path = {entry.path: entry for entry in manifest.entries}
        expected_role = {
            "PACKAGE_INITIALIZER": "PACKAGE_INITIALIZER",
            "MODULE": "RUNTIME",
        }
        for record in import_manifest.records:
            entry = by_path.get(record.path)
            if (
                entry is None
                or entry.role != expected_role[record.role]
                or entry.mode != record.mode
                or entry.size != record.size
                or entry.sha256 != record.sha256
            ):
                raise CutoverRefused(
                    "shared runtime path differs across manifests"
                )
        if (
            payload_map["runtime-config.json"]
            != launcher_config.to_bytes()
        ):
            raise CutoverRefused("runtime config payload mismatch")
        role_paths = {
            entry.role: entry.path
            for entry in manifest.entries
            if entry.role
            in {
                "RECEIVER",
                "LAUNCHER",
                "IMPORT_MANIFEST",
                "SIGNER_CONTRACT",
                "CONFIG",
            }
        }
        if role_paths != {
            "RECEIVER": "bin/awa-registration-receiver",
            "LAUNCHER": "bin/awa-registration-launcher",
            "IMPORT_MANIFEST": "import-manifest.json",
            "SIGNER_CONTRACT": (
                "contracts/awa-registration-owner-signers.v1"
            ),
            "CONFIG": "runtime-config.json",
        }:
            raise CutoverRefused("bundle execution paths are not exact")
        if (
            projection.receiver_relative_path != role_paths["RECEIVER"]
            or projection.launcher_relative_path != role_paths["LAUNCHER"]
            or launcher_config.entry_module
            not in import_manifest.entry_modules
            or by_path["import-manifest.json"].sha256
            != hashlib.sha256(import_payload).hexdigest()
            or by_path["runtime-config.json"].sha256
            != launcher_config.file_hash
            or by_path[
                "contracts/awa-registration-owner-signers.v1"
            ].sha256
            != receipt.allowed_signers_contract_hash
        ):
            raise CutoverRefused("bundle execution authority is incomplete")
        receiver_payload = payload_map[role_paths["RECEIVER"]]
        if (
            hashlib.sha256(
                b"awa-registration-installed-file/v1\0"
                + receiver_payload
            ).hexdigest()
            != receipt.installed_file_hash
        ):
            raise CutoverRefused("installed receiver hash is not bound")
        runtime_entries = tuple(
            entry
            for entry in manifest.entries
            if entry.role in {"PACKAGE_INITIALIZER", "RUNTIME"}
        )
        if (
            registration_projection.wrapper_runtime_v2_hash(
                bundle_digest=manifest.digest,
                launcher_hash=by_path[
                    "bin/awa-registration-launcher"
                ].sha256,
                import_manifest_hash=import_manifest.digest,
                external_interpreter_hash=(
                    receipt.external_interpreter_hash
                ),
                interpreter_capability_hash=(
                    receipt.interpreter_capability_hash
                ),
                launcher_config_hash=launcher_config.file_hash,
                runtime_records=runtime_entries,
            )
            != receipt.wrapper_runtime_hash
        ):
            raise CutoverRefused("wrapper runtime authority is incomplete")
        contract_path_hash = hashlib.sha256(
            b"awa-registration-owner-signers-path/v1\0"
            b"contracts/awa-registration-owner-signers.v1"
        ).hexdigest()
        if (
            contract_path_hash
            != receipt.allowed_signers_contract_path_hash
        ):
            raise CutoverRefused("signer contract path is not bound")
        try:
            public_hash, fingerprint, contract_hash = (
                registration_projection._parse_allowed_signers(
                    payload_map[
                        "contracts/awa-registration-owner-signers.v1"
                    ]
                )
            )
        except ValueError as exc:
            raise CutoverRefused(
                "signer contract payload is invalid"
            ) from exc
        if (
            public_hash != receipt.signer_public_key_sha256
            or fingerprint != receipt.signer_fingerprint
            or contract_hash != receipt.allowed_signers_contract_hash
        ):
            raise CutoverRefused(
                "signer contract identity is not receipt-bound"
            )
        inventory_map: dict[
            tuple[str, str, str, str],
            registration_projection.InventoryEntry,
        ] = {}
        for entry in inventory:
            key = (
                entry.event,
                entry.server_or_empty,
                entry.discriminator,
                entry.serializer_schema,
            )
            if key in inventory_map:
                raise CutoverRefused(
                    "denial inventory observable is duplicated"
                )
            inventory_map[key] = entry
        requests = dict(denial_requests)
        if not inventory_map or set(requests) != set(inventory_map):
            raise CutoverRefused(
                "denial requests do not match signed inventory"
            )
        expected_records = {
            (
                record.event,
                record.server_or_empty,
                record.discriminator,
                record.serializer_schema,
                record.seam,
            ): record
            for record in expected_denial_proof.records
        }
        expected_keys = {
            (*key, seam)
            for key in inventory_map
            for seam in {"DIRECT_RECEIVER", "SHADOW_INSTALLED"}
        }
        if set(expected_records) != expected_keys:
            raise CutoverRefused(
                "expected denial proof does not cover inventory"
            )
        for key, entry in inventory_map.items():
            request = requests[key]
            if not isinstance(request, bytes) or not request:
                raise CutoverRefused("synthetic denial request is invalid")
            request_hash = hashlib.sha256(request).hexdigest()
            for seam in {"DIRECT_RECEIVER", "SHADOW_INSTALLED"}:
                record = expected_records[(*key, seam)]
                if (
                    record.role != entry.role
                    or record.bundle_digest != manifest.digest
                    or record.request_hash != request_hash
                ):
                    raise CutoverRefused(
                        "expected denial record is not signed inventory"
                    )
        self.authorization = authorization
        self.receipt = receipt
        self.manifest = manifest
        self.projection = projection
        self.launcher_config = launcher_config
        self.payloads = payload_map
        self.expected_denial_proof = expected_denial_proof
        self.inventory = inventory_map
        self.denial_requests = requests
        self.denial_runner = denial_runner
        self.old_pointer = old_pointer
        self.bundle_relative_dir = (
            f"bundles/{manifest.generation}-{manifest.digest}"
        )
        self.bundle_dir = self.root / self.bundle_relative_dir
        self.pointer_path = self.root / "active-bundle.json"
        self.disabled_old_path = (
            self.root / "old-entrypoint-disabled.json"
        )
        self.candidate_pointer = (
            registration_projection.ActiveBundlePointer(
                schema="awa-registration-active-bundle/v1",
                generation=manifest.generation,
                bundle_relative_dir=self.bundle_relative_dir,
                bundle_digest=manifest.digest,
                bundle_projection_hash=projection.digest,
                direct_receipt_hash=receipt.digest,
                external_interpreter_hash=(
                    receipt.external_interpreter_hash
                ),
                interpreter_capability_hash=(
                    receipt.interpreter_capability_hash
                ),
            )
        )

    def _read_pointer(
        self,
    ) -> registration_projection.ActiveBundlePointer | None:
        try:
            metadata = self.pointer_path.lstat()
        except FileNotFoundError:
            return None
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise CutoverRefused("active bundle pointer is unsafe")
        try:
            return registration_projection.ActiveBundlePointer.from_bytes(
                self.pointer_path.read_bytes()
            )
        except (OSError, ValueError) as exc:
            raise CutoverRefused(
                "active bundle pointer is invalid"
            ) from exc

    def preflight(self) -> None:
        if os.path.lexists(self.root) and self.root.is_symlink():
            raise CutoverRefused("runtime root is a symlink")
        if self.candidate_installed():
            self.verify_current()

    def candidate_installed(self) -> bool:
        if not os.path.lexists(self.bundle_dir):
            return False
        return self._verify_partial_bundle()

    def install_candidate(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        (self.root / "bundles").mkdir(
            parents=True, exist_ok=True, mode=0o700
        )
        if not os.path.lexists(self.bundle_dir):
            self.bundle_dir.mkdir(mode=0o700)
            _fsync_directory(self.bundle_dir.parent)
        else:
            self._verify_partial_bundle()
        for entry in self.manifest.entries:
            _write_immutable_file(
                self.bundle_dir / entry.path,
                self.payloads[entry.path],
                int(entry.mode),
            )
        _write_immutable_file(
            self.bundle_dir / "direct-receipt.json",
            self.receipt.to_bytes(),
            0o600,
        )
        _write_immutable_file(
            self.bundle_dir / "bundle-manifest.json",
            self.manifest.to_bytes(),
            0o600,
        )
        _write_immutable_file(
            self.bundle_dir / "bundle-projection.json",
            self.projection.to_bytes(),
            0o600,
        )
        self._verify_bundle()

    def _verify_partial_bundle(self) -> bool:
        if (
            not self.bundle_dir.is_dir()
            or self.bundle_dir.is_symlink()
        ):
            raise CutoverRefused("bundle directory is unsafe")
        directory_metadata = self.bundle_dir.stat()
        if (
            directory_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(directory_metadata.st_mode) != 0o700
        ):
            raise CutoverRefused("bundle directory is unsafe")
        expected_files = {
            *(entry.path for entry in self.manifest.entries),
            "direct-receipt.json",
            "bundle-manifest.json",
            "bundle-projection.json",
        }
        expected_directories = {
            parent.as_posix()
            for name in expected_files
            for parent in Path(name).parents
            if parent != Path(".")
        }
        observed_files: set[str] = set()
        for path in self.bundle_dir.rglob("*"):
            relative = path.relative_to(self.bundle_dir).as_posix()
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise CutoverRefused("bundle contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                if (
                    relative not in expected_directories
                    or metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o700
                ):
                    raise CutoverRefused(
                        "bundle directory inventory drifted"
                    )
                continue
            if not stat.S_ISREG(metadata.st_mode) or relative not in (
                expected_files
            ):
                raise CutoverRefused("bundle file inventory drifted")
            observed_files.add(relative)
        entries = {entry.path: entry for entry in self.manifest.entries}
        for relative in observed_files:
            path = self.bundle_dir / relative
            if relative in entries:
                entry = entries[relative]
                metadata = path.lstat()
                payload = registration_projection._regular_bytes(path)
                if (
                    metadata.st_uid != os.geteuid()
                    or metadata.st_nlink != 1
                    or stat.S_IMODE(metadata.st_mode) != int(entry.mode)
                    or len(payload) != int(entry.size)
                    or hashlib.sha256(payload).hexdigest()
                    != entry.sha256
                ):
                    raise CutoverRefused(
                        "partial bundle payload drifted"
                    )
            elif relative == "direct-receipt.json":
                if DirectReceiptStore(path).read() != self.receipt:
                    raise CutoverRefused(
                        "partial bundle receipt drifted"
                    )
            elif relative == "bundle-manifest.json":
                if (
                    registration_projection.BundleManifest.from_bytes(
                        registration_projection._regular_bytes(path)
                    )
                    != self.manifest
                ):
                    raise CutoverRefused(
                        "partial bundle manifest drifted"
                    )
            elif (
                registration_projection.BundleProjection.from_bytes(
                    registration_projection._regular_bytes(path)
                )
                != self.projection
            ):
                raise CutoverRefused(
                    "partial bundle projection drifted"
                )
        return observed_files == expected_files

    def _verify_bundle(self) -> None:
        if not self._verify_partial_bundle():
            raise CutoverRefused("immutable bundle is incomplete")
        expected = {
            *(entry.path for entry in self.manifest.entries),
            "direct-receipt.json",
            "bundle-manifest.json",
            "bundle-projection.json",
        }
        observed = {
            path.relative_to(self.bundle_dir).as_posix()
            for path in self.bundle_dir.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if observed != expected:
            raise CutoverRefused("bundle file inventory is not exact")
        for entry in self.manifest.entries:
            path = self.bundle_dir / entry.path
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != int(entry.mode)
            ):
                raise CutoverRefused("bundle payload identity drifted")
            payload = path.read_bytes()
            if (
                len(payload) != int(entry.size)
                or hashlib.sha256(payload).hexdigest() != entry.sha256
            ):
                raise CutoverRefused("bundle payload bytes drifted")
        if (
            DirectReceiptStore(
                self.bundle_dir / "direct-receipt.json"
            ).read()
            != self.receipt
            or registration_projection.BundleManifest.from_bytes(
                (self.bundle_dir / "bundle-manifest.json").read_bytes()
            )
            != self.manifest
            or registration_projection.BundleProjection.from_bytes(
                (self.bundle_dir / "bundle-projection.json").read_bytes()
            )
            != self.projection
        ):
            raise CutoverRefused("bundle non-payload authority drifted")

    def new_projection_active(self) -> bool:
        return self._read_pointer() == self.candidate_pointer

    def project_new_receiver(self) -> None:
        self._verify_bundle()
        if self.old_entrypoints_disabled():
            raise CutoverRefused(
                "old-entrypoint state exists before pointer switch"
            )
        current = self._read_pointer()
        if (
            self.old_pointer is not None
            and current not in {self.old_pointer, self.candidate_pointer}
        ):
            raise CutoverRefused("active pointer is not restorable")
        _atomic_private_write(
            self.pointer_path,
            self.candidate_pointer.to_bytes(),
            mode=0o600,
        )

    def prove_staged(self, phase: str) -> None:
        if phase not in {"PRE_SWITCH", "POST_SWITCH"}:
            raise CutoverRefused("unknown denial-proof phase")
        if phase == "PRE_SWITCH" and self.new_projection_active():
            raise CutoverRefused("pre-switch proof ran after switch")
        if phase == "POST_SWITCH" and not self.new_projection_active():
            raise CutoverRefused("post-switch proof lacks candidate pointer")
        records = []
        for key, entry in self.inventory.items():
            request = self.denial_requests[key]
            request_hash = hashlib.sha256(request).hexdigest()
            for seam in ("DIRECT_RECEIVER", "SHADOW_INSTALLED"):
                output, exit_code = self.denial_runner(
                    phase, seam, entry, request
                )
                if (
                    not isinstance(output, bytes)
                    or type(exit_code) is not int
                    or exit_code <= 0
                ):
                    raise CutoverRefused(
                        "denial execution result is malformed"
                    )
                records.append(
                    registration_projection.DenialProofRecord(
                        event=entry.event,
                        server_or_empty=entry.server_or_empty,
                        discriminator=entry.discriminator,
                        serializer_schema=entry.serializer_schema,
                        role=entry.role,
                        seam=seam,
                        bundle_digest=self.manifest.digest,
                        request_hash=request_hash,
                        output_hash=hashlib.sha256(output).hexdigest(),
                        exit_code=str(exit_code),
                    )
                )
        records.sort(
            key=lambda record: registration_jcs.canonical_bytes(
                record.to_mapping()
            )
        )
        observed = registration_projection.StagedDenialProof(
            schema="awa-registration-staged-denial-proof/v2",
            records=tuple(records),
        )
        if observed != self.expected_denial_proof:
            raise CutoverRefused("staged denial proof did not match")

    def restore_old_projection(self) -> None:
        if self.old_pointer is None:
            raise CutoverRefused("old active pointer is unavailable")
        disabled = self.old_entrypoints_disabled()
        _atomic_private_write(
            self.pointer_path, self.old_pointer.to_bytes(), mode=0o600
        )
        if disabled:
            self.disabled_old_path.unlink()
            _fsync_directory(self.root)

    def _disabled_payload(self) -> bytes:
        return registration_jcs.canonical_bytes(
            {
                "schema": (
                    "awa-registration-old-entrypoint-disabled/v1"
                ),
                "candidate_pointer_hash": self.candidate_pointer.digest,
                "old_pointer_hash": (
                    None
                    if self.old_pointer is None
                    else self.old_pointer.digest
                ),
            }
        ) + b"\n"

    def old_entrypoints_disabled(self) -> bool:
        try:
            descriptor, raw = (
                registration_projection._authority_descriptor(
                    self.disabled_old_path,
                    modes=frozenset({0o600}),
                    limit=4_096,
                )
            )
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as exc:
            raise CutoverRefused(
                "old-entrypoint disable authority is unsafe"
            ) from exc
        try:
            return raw == self._disabled_payload()
        finally:
            os.close(descriptor)

    def disable_old_entrypoints(self) -> None:
        if not self.new_projection_active():
            raise CutoverRefused(
                "candidate pointer is not active"
            )
        self.prove_staged("POST_SWITCH")
        _atomic_private_write(
            self.disabled_old_path,
            self._disabled_payload(),
            mode=0o600,
        )

    def old_bytes_present(self) -> bool:
        if self.old_pointer is None:
            return False
        return (self.root / self.old_pointer.bundle_relative_dir).exists()

    def clean_old_bytes(self) -> None:
        self.verify_current()
        if self.old_pointer is None:
            return
        old = self.root / self.old_pointer.bundle_relative_dir
        if old == self.bundle_dir:
            raise CutoverRefused("candidate bundle cannot be retired")
        if not old.exists():
            return
        for path in sorted(
            old.rglob("*"),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise CutoverRefused("old bundle contains a symlink")
            if stat.S_ISDIR(metadata.st_mode):
                path.rmdir()
            elif stat.S_ISREG(metadata.st_mode):
                path.unlink()
            else:
                raise CutoverRefused(
                    "old bundle contains an unsupported object"
                )
        old.rmdir()
        _fsync_directory(old.parent)
        try:
            self.disabled_old_path.unlink()
        except FileNotFoundError:
            pass
        _fsync_directory(self.root)

    def verify_current(self) -> None:
        self._verify_bundle()
        pointer = self._read_pointer()
        if pointer is not None and pointer not in {
            self.candidate_pointer,
            self.old_pointer,
        }:
            raise CutoverRefused("active pointer does not match authority")
        if self.old_entrypoints_disabled() and (
            pointer != self.candidate_pointer
        ):
            raise CutoverRefused(
                "disabled old entrypoint lacks candidate pointer"
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
        protocol = self.control.protocol_state()
        if not protocol.staged and not protocol.current_is_candidate:
            return Cut.C1
        if not self.files.new_projection_active():
            return Cut.C2
        if protocol.current_is_candidate:
            return (
                Cut.C6 if self.files.old_bytes_present() else Cut.C7
            )
        if not self.files.old_entrypoints_disabled():
            return Cut.C3
        if (
            protocol.mode in {"DRAINING", "CONTAINMENT"}
            and protocol.staged
            and (
                not protocol.adoption_pass_complete
                or not protocol.custody_empty
            )
        ):
            return Cut.C4
        if (
            protocol.mode in {"DRAINING", "CONTAINMENT"}
            and protocol.staged
            and protocol.adoption_pass_complete
            and protocol.custody_empty
        ):
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
            protocol = self.control.protocol_state()
            if protocol.mode == "DORMANT":
                self.control.activate_current()
            self.control.begin_drain()
            self.control.stage_candidate()
            self.files.prove_staged("PRE_SWITCH")
        elif current is Cut.C2:
            self.files.verify_current()
            try:
                self.files.project_new_receiver()
            except BaseException:
                self.files.restore_old_projection()
                self.files.verify_current()
                raise
        elif current is Cut.C3:
            self.files.verify_current()
            try:
                self.files.disable_old_entrypoints()
            except BaseException:
                if not self.files.old_entrypoints_disabled():
                    self.files.restore_old_projection()
                    self.files.verify_current()
                raise
        elif current is Cut.C4:
            self.control.reconcile_adoption()
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
            self.control.enter_containment(containment_reason)
            return
        if (
            self.files.new_projection_active()
        ):
            self.files.restore_old_projection()
            self.files.verify_current()
        self.control.cancel_drain()


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
        current_profile_binding: (
            registration_profile.CurrentProfileBinding
        ),
        staged_profile_binding: (
            registration_profile.StagedProfileBinding
        ),
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
        if (
            type(current_profile_binding)
            is not registration_profile.CurrentProfileBinding
            or type(staged_profile_binding)
            is not registration_profile.StagedProfileBinding
            or current_profile_binding.digest != current.profile_hash
            or staged_profile_binding.digest != staged.profile_hash
            or current_profile_binding.storage_dev != current.storage_dev
            or staged_profile_binding.storage_dev != staged.storage_dev
            or staged_profile_binding.external_interpreter_digest
            != receipt.external_interpreter_hash
            or staged_profile_binding.interpreter_capability.digest
            != receipt.interpreter_capability_hash
        ):
            raise CutoverRefused(
                "cutover requires exact typed current/staged profiles"
            )
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
        self.current_profile_binding = current_profile_binding
        self.staged_profile_binding = staged_profile_binding
        self._adoption_pass_complete = False

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
            adoption_pass_complete=self._adoption_pass_complete,
            custody_empty=not self.store.unresolved_custody_obligations(),
        )

    def begin_drain(self) -> None:
        self.store.begin_drain(
            self.control,
            self.current,
            profile_binding=self.current_profile_binding,
        )

    def activate_current(self) -> None:
        self.store.activate(
            self.control,
            self.current,
            profile_binding=self.current_profile_binding,
        )

    def stage_and_adopt(self) -> None:
        self.stage_candidate()
        self.reconcile_adoption()

    def stage_candidate(self) -> None:
        protocol = self.store.current_protocol()
        if protocol is None:
            raise CutoverRefused("protocol authority is absent")
        if protocol["staged_generation"] is None:
            self.store.stage_next(
                self.control,
                self.current,
                self.staged,
                quiescence_proof_hash=self.quiescence_proof_hash,
                current_profile_binding=self.current_profile_binding,
                staged_profile_binding=self.staged_profile_binding,
            )

    def reconcile_adoption(self) -> None:
        self.adopter()
        self._adoption_pass_complete = (
            not self.store.unresolved_custody_obligations()
        )

    def advance_generation(self) -> None:
        self.store.advance_generation(
            self.control,
            self.current,
            quiescence_proof_hash=self.quiescence_proof_hash,
            staged_candidate=self.staged,
            current_profile_binding=self.current_profile_binding,
            staged_profile_binding=self.staged_profile_binding,
        )

    def cancel_drain(self) -> None:
        self.store.cancel_drain(
            self.control,
            self.current,
            quiescence_proof_hash=self.quiescence_proof_hash,
            profile_binding=self.current_profile_binding,
        )

    def enter_containment(
        self, reason: str = "ADOPTION_FAILED"
    ) -> None:
        self.store.enter_containment(
            self.control,
            self.current,
            reason=reason,
            profile_binding=self.current_profile_binding,
        )

    def contain_recovery_exhaustion(
        self,
        evidence: registration_store.RecoveryReserveExhausted,
    ) -> None:
        if type(evidence) is not registration_store.RecoveryReserveExhausted:
            raise CutoverRefused(
                "recovery exhaustion evidence is not store-authenticated"
            )
        protocol = self.store.current_protocol()
        authority = self.store.read_selected_authority(
            evidence.member_id
        )
        if (
            protocol is None
            or authority is None
            or protocol["protocol_hash"] != evidence.protocol_hash
            or protocol["staged_epoch_hash"]
            != evidence.staged_epoch_hash
            or authority.member["member_tuple_hash"]
            != evidence.member_tuple_hash
            or authority.effect["effect_id"] != evidence.effect_id
            or authority.status["status_hash"] != evidence.status_hash
            or authority.status["executor_token_hash"]
            != evidence.executor_token_hash
            or evidence.recovery_operation_count != "6"
            or evidence.recovery_bytes_consumed != "49152"
            or evidence.recovery_bytes_reserved != "49152"
        ):
            raise CutoverRefused(
                "recovery exhaustion no longer matches current authority"
            )
        self.store.enter_containment(
            self.control,
            self.current,
            reason="STORE_FAILURE",
        )

    def begin_repair(self) -> None:
        self.store.begin_repair(
            self.control,
            self.current,
            current_profile_binding=self.current_profile_binding,
            staged_candidate=self.staged,
            staged_profile_binding=self.staged_profile_binding,
        )
