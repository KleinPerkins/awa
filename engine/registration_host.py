"""Body C runtime assembly for Body A authority and Body B policy APIs."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import (
    identity,
    paths,
    registration_admission,
    registration_basis,
    registration_clock,
    registration_hook_runtime,
    registration_jcs,
    registration_projection,
    registration_runtime,
    registration_store,
)


RUNTIME_SCHEMA = "awa-registration-runtime/v1"
HOST_TICK_SCHEMA = "awa-registration-host-tick/v2"
_HOST_TICK_FIELDS = {
    "schema",
    "boot_id",
    "written_mono_ns",
    "interval_ns",
    "protocol_seq",
    "protocol_hash",
    "same_boot_cursor",
    "same_boot_cursor_hash",
    "due_snapshot_hash",
    "fairness_suspended",
}
_CONFIG_FIELDS = {
    "schema",
    "direct_receipt_path",
    "writer_capability_path",
    "profile_targets",
    "inventory",
    "proof_parent",
    "projection_parent",
    "legacy_parent",
    "host_tick_receipt_path",
    "installed_file_path",
    "wrapper_path",
    "runtime_files",
}


def _strict_json(raw: bytes) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        raw.decode("utf-8", "strict"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(value)
        ),
    )


def _private_bytes(path: Path, *, limit: int = 65_536) -> bytes:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise registration_hook_runtime.HookUnavailable(
            "private runtime input is unsafe"
        )
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        rebound = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (
            rebound.st_dev,
            rebound.st_ino,
        ):
            raise registration_hook_runtime.HookUnavailable(
                "private runtime input changed"
            )
        raw = os.read(descriptor, limit + 1)
    finally:
        os.close(descriptor)
    if not 1 <= len(raw) <= limit:
        raise registration_hook_runtime.HookUnavailable(
            "private runtime input is unbounded"
        )
    return raw


def _config_path() -> Path:
    configured = os.environ.get("AWA_REGISTRATION_RUNTIME_CONFIG")
    if configured:
        path = Path(configured).expanduser()
    else:
        path = paths.config_home() / "awa" / "registration-runtime.json"
    if not path.is_absolute() or os.path.normpath(str(path)) != str(path):
        raise registration_hook_runtime.HookUnavailable(
            "registration runtime config path is unsupported"
        )
    return path


def _load_config() -> dict:
    try:
        value = _strict_json(_private_bytes(_config_path()))
    except registration_hook_runtime.HookUnavailable:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise registration_hook_runtime.HookUnavailable(
            "registration runtime config is unavailable"
        ) from exc
    if not isinstance(value, dict) or set(value) != _CONFIG_FIELDS:
        raise registration_hook_runtime.HookUnavailable(
            "registration runtime config is not closed"
        )
    if value["schema"] != RUNTIME_SCHEMA:
        raise registration_hook_runtime.HookUnavailable(
            "registration runtime schema is unsupported"
        )
    return value


def _absolute(value: object, field: str) -> Path:
    if not isinstance(value, str):
        raise registration_hook_runtime.HookUnavailable(
            f"{field} is unavailable"
        )
    path = Path(value)
    if (
        not path.is_absolute()
        or os.path.normpath(str(path)) != str(path)
        or os.path.realpath(path) != str(path)
    ):
        raise registration_hook_runtime.HookUnavailable(
            f"{field} is not canonical"
        )
    return path


def _profile_targets(value: object) -> list[tuple[str, Path, str, int]]:
    if not isinstance(value, list):
        raise registration_hook_runtime.HookUnavailable(
            "profile targets are unavailable"
        )
    result = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "path", "kind", "mode"}
            or not isinstance(item["role"], str)
            or item["kind"] not in {"file", "directory"}
            or type(item["mode"]) is not int
        ):
            raise registration_hook_runtime.HookUnavailable(
                "profile target is malformed"
            )
        result.append(
            (
                item["role"],
                _absolute(item["path"], f"{item['role']} path"),
                item["kind"],
                item["mode"],
            )
        )
    return result


def _inventory(value: object) -> tuple[registration_projection.InventoryEntry, ...]:
    if not isinstance(value, list):
        raise registration_hook_runtime.HookUnavailable(
            "tool inventory is unavailable"
        )
    try:
        return tuple(
            registration_projection.InventoryEntry(**item) for item in value
        )
    except (TypeError, ValueError) as exc:
        raise registration_hook_runtime.HookUnavailable(
            "tool inventory is malformed"
        ) from exc


def _verify_runtime_bytes(
    config: dict,
    receipt: registration_projection.DirectReceipt,
) -> None:
    bundle_value = os.environ.get("AWA_REGISTRATION_BUNDLE_ROOT")
    if receipt.schema == "awa-registration-direct-receipt/v3":
        if not bundle_value:
            raise registration_hook_runtime.HookUnavailable(
                "signed bundle root is unavailable"
            )
        bundle = _absolute(bundle_value, "signed bundle root")
        try:
            manifest = registration_projection.BundleManifest.from_bytes(
                _private_bytes(bundle / "bundle-manifest.json")
            )
            projection = (
                registration_projection.BundleProjection.from_bytes(
                    _private_bytes(bundle / "bundle-projection.json")
                )
            )
            import_manifest = (
                registration_projection.ImportManifest.from_bytes(
                    registration_projection._regular_bytes(
                        bundle / "import-manifest.json"
                    )
                )
            )
            by_path = {
                entry.path: entry for entry in manifest.entries
            }
            for entry in manifest.entries:
                payload = registration_projection._regular_bytes(
                    bundle / entry.path
                )
                metadata = (bundle / entry.path).lstat()
                if (
                    stat.S_IMODE(metadata.st_mode) != int(entry.mode)
                    or len(payload) != int(entry.size)
                    or hashlib.sha256(payload).hexdigest()
                    != entry.sha256
                ):
                    raise ValueError("bundle payload drifted")
            launcher = next(
                entry
                for entry in manifest.entries
                if entry.role == "LAUNCHER"
            )
            runtime_records = tuple(
                entry
                for entry in manifest.entries
                if entry.role in {"PACKAGE_INITIALIZER", "RUNTIME"}
            )
            wrapper_hash = (
                registration_projection.wrapper_runtime_v2_hash(
                    bundle_digest=manifest.digest,
                    launcher_hash=launcher.sha256,
                    import_manifest_hash=import_manifest.digest,
                    external_interpreter_hash=(
                        manifest.external_interpreter_hash
                    ),
                    interpreter_capability_hash=(
                        manifest.interpreter_capability_hash
                    ),
                    launcher_config_hash=(
                        by_path["runtime-config.json"].sha256
                    ),
                    runtime_records=runtime_records,
                )
            )
        except (
            OSError,
            StopIteration,
            KeyError,
            ValueError,
        ) as exc:
            raise registration_hook_runtime.HookUnavailable(
                "signed bundle identity is unavailable"
            ) from exc
        if (
            manifest.digest != receipt.bundle_digest
            or projection.digest != receipt.bundle_projection_hash
            or import_manifest.digest != receipt.import_manifest_hash
            or wrapper_hash != receipt.wrapper_runtime_hash
            or manifest.external_interpreter_hash
            != receipt.external_interpreter_hash
            or manifest.interpreter_capability_hash
            != receipt.interpreter_capability_hash
        ):
            raise registration_hook_runtime.HookUnavailable(
                "signed bundle identity drifted"
            )
        return
    installed = _absolute(
        config["installed_file_path"], "installed receiver path"
    )
    wrapper = _absolute(config["wrapper_path"], "hook wrapper path")
    values = config["runtime_files"]
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) for value in values)
    ):
        raise registration_hook_runtime.HookUnavailable(
            "runtime file inventory is unavailable"
        )
    runtime_files = tuple(
        _absolute(value, "runtime file path") for value in values
    )
    try:
        installed_hash = registration_projection.installed_file_hash(
            installed
        )
        runtime_hash = registration_projection.wrapper_runtime_hash(
            wrapper, runtime_files
        )
    except (OSError, ValueError) as exc:
        raise registration_hook_runtime.HookUnavailable(
            "installed wrapper/runtime identity is unavailable"
        ) from exc
    if (
        installed_hash != receipt.installed_file_hash
        or runtime_hash != receipt.wrapper_runtime_hash
    ):
        raise registration_hook_runtime.HookUnavailable(
            "installed wrapper/runtime identity drifted"
        )


def _serializer_ready() -> bool:
    try:
        decision = registration_admission.AdmissionDecision(
            False,
            "PARSER_REJECT",
            registration_admission.render_reason("PARSER_REJECT"),
            0,
        )
        for event in (
            "preToolUse",
            "subagentStart",
            "beforeShellExecution",
            "beforeReadFile",
            "beforeMCPExecution",
        ):
            value = _strict_json(
                registration_hook_runtime.serialize_decision(
                    event, decision
                )
            )
            if (
                not isinstance(value, dict)
                or value.get("permission") != "deny"
                or not isinstance(value.get("user_message"), str)
            ):
                return False
        return True
    except Exception:
        return False


def _cursor_from_value(value: object) -> registration_runtime.SameBootCursor:
    expected = {
        "schema",
        "boot_id",
        "protocol_seq",
        "protocol_hash",
        "selection_snapshot_hash",
        "last_member_id",
        "last_pre_status_hash",
        "last_post_status_hash",
        "outcome",
        "batch_count",
        "wrapped",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or value["schema"] != registration_runtime.SAME_BOOT_CURSOR_SCHEMA
    ):
        raise ValueError("same-boot cursor fields are not exact")
    for field in ("protocol_seq", "batch_count"):
        item = value[field]
        if (
            not isinstance(item, str)
            or not item.isascii()
            or not item.isdecimal()
            or (len(item) > 1 and item.startswith("0"))
        ):
            raise ValueError("same-boot cursor integer is malformed")
    return registration_runtime.SameBootCursor(
        boot_id=value["boot_id"],
        protocol_seq=int(value["protocol_seq"]),
        protocol_hash=value["protocol_hash"],
        selection_snapshot_hash=value["selection_snapshot_hash"],
        last_member_id=value["last_member_id"],
        last_pre_status_hash=value["last_pre_status_hash"],
        last_post_status_hash=value["last_post_status_hash"],
        outcome=value["outcome"],
        batch_count=int(value["batch_count"]),
        wrapped=value["wrapped"],
    )


def _read_host_tick(path: Path) -> tuple[dict, registration_runtime.SameBootCursor]:
    raw = _private_bytes(path)
    value = _strict_json(raw)
    if (
        not isinstance(value, dict)
        or set(value) != _HOST_TICK_FIELDS
        or value["schema"] != HOST_TICK_SCHEMA
        or registration_jcs.canonical_bytes(value) + b"\n" != raw
        or not isinstance(value["boot_id"], str)
        or not value["boot_id"]
        or type(value["fairness_suspended"]) is not bool
    ):
        raise ValueError("host-tick receipt is not exact")
    for field in ("written_mono_ns", "interval_ns", "protocol_seq"):
        item = value[field]
        if (
            not isinstance(item, str)
            or not item.isascii()
            or not item.isdecimal()
            or (len(item) > 1 and item.startswith("0"))
        ):
            raise ValueError("host-tick integer is malformed")
    cursor = _cursor_from_value(value["same_boot_cursor"])
    if (
        registration_runtime.same_boot_cursor_hash(cursor)
        != value["same_boot_cursor_hash"]
        or cursor.boot_id != value["boot_id"]
        or cursor.protocol_seq != int(value["protocol_seq"])
        or cursor.protocol_hash != value["protocol_hash"]
    ):
        raise ValueError("host-tick cursor binding is invalid")
    for field in (
        "protocol_hash",
        "same_boot_cursor_hash",
        "due_snapshot_hash",
    ):
        item = value[field]
        if (
            not isinstance(item, str)
            or len(item) != 64
            or any(character not in "0123456789abcdef" for character in item)
        ):
            raise ValueError(f"{field} is malformed")
    return value, cursor


def _host_tick_current(path: Path) -> bool:
    try:
        value, _cursor = _read_host_tick(path)
        now_mono_ns = registration_clock.mach_continuous_time_ns()
        return bool(
            value["boot_id"] == identity.boot_id()
            and int(value["interval_ns"]) > 0
            and value["fairness_suspended"] is False
            and 0 <= now_mono_ns - int(value["written_mono_ns"])
            <= 2 * int(value["interval_ns"])
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        registration_hook_runtime.HookUnavailable,
    ):
        return False


def write_host_tick_receipt(
    path: Path,
    receipt: registration_runtime.TickReceipt,
    *,
    boot_id: str,
    written_mono_ns: int,
    same_boot_cursor: registration_runtime.SameBootCursor,
) -> None:
    if not isinstance(receipt, registration_runtime.TickReceipt):
        raise ValueError("tick receipt type is invalid")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = path.parent.lstat()
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise registration_hook_runtime.HookUnavailable(
            "host-tick parent is unsafe"
        )
    if (
        not isinstance(
            same_boot_cursor, registration_runtime.SameBootCursor
        )
        or same_boot_cursor.boot_id != boot_id
    ):
        raise ValueError("same-boot cursor does not match host tick")
    value = {
        "schema": HOST_TICK_SCHEMA,
        "boot_id": boot_id,
        "written_mono_ns": str(written_mono_ns),
        "interval_ns": str(registration_runtime.TICK_INTERVAL_NS),
        "protocol_seq": str(same_boot_cursor.protocol_seq),
        "protocol_hash": same_boot_cursor.protocol_hash,
        "same_boot_cursor": same_boot_cursor.as_value(),
        "same_boot_cursor_hash": (
            registration_runtime.same_boot_cursor_hash(
                same_boot_cursor
            )
        ),
        "due_snapshot_hash": receipt.snapshot_token,
        "fairness_suspended": receipt.fairness_suspended,
    }
    payload = registration_jcs.canonical_bytes(value) + b"\n"
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    primary: BaseException | None = None
    try:
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            count = os.write(descriptor, view[offset:])
            if count <= 0:
                raise OSError("short host-tick receipt write")
            offset += count
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        if _private_bytes(path) != payload:
            raise registration_hook_runtime.HookUnavailable(
                "host-tick receipt changed after replace"
            )
        parent_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        if _private_bytes(path) != payload:
            raise registration_hook_runtime.HookUnavailable(
                "host-tick receipt changed after parent fsync"
            )
    except BaseException as exc:
        primary = exc
        raise
    finally:
        cleanup_error: BaseException | None = None
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException as exc:
                cleanup_error = exc
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if cleanup_error is not None:
            if primary is not None:
                if hasattr(primary, "add_note"):
                    primary.add_note(
                        "secondary host-tick cleanup failure: "
                        f"{cleanup_error!r}"
                    )
            else:
                raise cleanup_error


def _candidate_from_protocol(
    protocol: dict,
) -> registration_store.ProtocolCandidate:
    return registration_store.ProtocolCandidate(
        profile_hash=protocol["profile_hash"],
        runtime_capability_hash=protocol["runtime_capability_hash"],
        writer_binary_hash=protocol["writer_binary_hash"],
        writer_capability_hash=protocol["writer_capability_hash"],
        tool_inventory_hash=protocol["tool_inventory_hash"],
        hook_projection_hash=protocol["hook_projection_hash"],
        hook_matcher_mode=protocol["hook_matcher_mode"],
        hook_matcher_hash=protocol["hook_matcher_hash"],
        projection_receipt_hash=protocol["projection_receipt_hash"],
        projection_file_generation=protocol[
            "projection_file_generation"
        ],
        installer_identity_hash=protocol["installer_identity_hash"],
        installer_capability_hash=protocol[
            "installer_capability_hash"
        ],
        storage_dev=protocol["storage_dev"],
    )


def _require_runtime_receipt(
    receipt: registration_projection.DirectReceipt,
) -> None:
    if receipt.owner_mode != "DIRECT":
        raise registration_hook_runtime.HookUnavailable(
            "external ownership is unsupported"
        )
    if receipt.deployment_scope == "R0_THROWAWAY":
        raise registration_hook_runtime.HookUnavailable(
            "R0 receipt is predeployment evidence only"
        )


class HostService:
    def __init__(
        self,
        *,
        store: registration_store.RegistrationStore,
        candidate: registration_store.ProtocolCandidate,
        data: registration_store.DataCapability,
        receipt: registration_projection.DirectReceipt,
        collector: registration_basis.GitBasisCollector,
        inventory_entries: tuple[
            registration_projection.InventoryEntry, ...
        ],
        proof_parent: Path,
        host_tick_path: Path,
    ) -> None:
        self.store = store
        self.candidate = candidate
        self.data = data
        self.receipt = receipt
        self.collector = collector
        self.proof_parent = proof_parent
        self.host_tick_path = host_tick_path
        self.inventory_entries = inventory_entries
        self.inventory_tokens = {
            (
                item.event,
                item.server_or_empty,
                item.discriminator,
                item.serializer_schema,
            ): registration_projection._domain_hash(
                "awa-registration-observable-token/v1",
                item.mapping(),
            )
            for item in inventory_entries
        }
        ordinary = frozenset(
            self.inventory_tokens[
                (
                    item.event,
                    item.server_or_empty,
                    item.discriminator,
                    item.serializer_schema,
                )
            ]
            for item in inventory_entries
            if item.role == "ordinary"
        )
        launches = frozenset(
            self.inventory_tokens[
                (
                    item.event,
                    item.server_or_empty,
                    item.discriminator,
                    item.serializer_schema,
                )
            ]
            for item in inventory_entries
            if item.role == "task_launch"
        )
        self.inventory = registration_admission.ToolInventory(
            ordinary=ordinary,
            task_launch=launches,
        )
        self.coordinator = registration_runtime.RegistrationCoordinator(
            store=store,
            data=data,
            candidate=candidate,
        )
        self.admission = registration_admission.AdmissionController(
            inventory=self.inventory,
            collector=collector,
            store=registration_runtime.StoreAuthorityAdapter(store),
            host_provider=self._host_envelope,
            receipt_provider=receipt.deployment_receipt,
            expected_candidate_digest=receipt.candidate_digest,
        )

    def _host_envelope(self) -> registration_admission.HostEnvelope:
        protocol = self.store.current_protocol()
        if protocol is None:
            raise registration_hook_runtime.HookUnavailable(
                "protocol authority is absent"
            )
        return registration_admission.HostEnvelope(
            host_tick_current=_host_tick_current(self.host_tick_path),
            profile_hash=self.store.measured_profile_hash or "",
            projection_hash=self.receipt.hook_projection_hash,
            inventory_hash=self.receipt.tool_inventory_hash,
            storage_ready=self.store.storage_ready(),
            # Every caller reaches this snapshot only after the invocation's
            # real payload passed Body B's closed parser. Avoid a synthetic
            # filesystem-dependent parser probe that could contradict it.
            parser_ready=True,
            serializer_ready=_serializer_ready(),
            lifecycle_ready=True,
            proof_ready=True,
        )

    def _helpers(
        self,
        event: registration_admission.RegistrationEvent,
        member_id: str,
    ):
        proof = registration_jcs.canonical_bytes(
            {
                "schema": "awa-registration-effect-proof/v1",
                "member_id": member_id,
            }
        )
        return {
            "PUBLISH_EFFECT_PROOF": registration_runtime.ProofFileHelper(
                self.proof_parent / f"{member_id}.proof.json", proof
            ),
            "CONVERGE_LEGACY_LEASE": (
                registration_runtime.LegacyLeaseHelper(event.root)
            ),
            "CONVERGE_LEGACY_LIFECYCLE": (
                registration_runtime.LegacyLifecycleHelper(event.root)
            ),
            "COLLECT_FINAL_BASIS": registration_runtime.FinalBasisHelper(
                self.collector, event
            ),
        }

    def _probe_discriminator(self) -> str:
        return sorted(
            self.inventory.ordinary, key=lambda value: value.encode("utf-8")
        )[0]

    def handle(
        self,
        payload: object,
        invocation: registration_hook_runtime.ObservableInvocation,
    ) -> registration_admission.AdmissionDecision:
        # Body B remains the sole launch/ordinary policy oracle. Helpers are
        # selected only after the same exact event basis derives a member.
        try:
            event = registration_admission.parse_registration_event(payload)
            if not isinstance(
                invocation,
                registration_hook_runtime.ObservableInvocation,
            ):
                raise registration_hook_runtime.HookUnavailable(
                    "observable invocation is unavailable"
                )
            try:
                inventory_entry = (
                    registration_projection.lookup_inventory_entry(
                        self.inventory_entries,
                        event=invocation.event,
                        server_or_empty=invocation.server_or_empty,
                        discriminator=invocation.discriminator,
                        serializer_schema=invocation.serializer_schema,
                    )
                )
            except registration_projection.HookUnsupported:
                return self.admission._deny("UNKNOWN_DISCRIMINATOR", 0)
            if inventory_entry.role == "task_launch":
                return self.admission._deny("TASK_SUBAGENT_DENIED", 0)
            if inventory_entry.role != "ordinary":
                return self.admission._deny("UNKNOWN_DISCRIMINATOR", 0)
            inventory_token = self.inventory_tokens[
                (
                    inventory_entry.event,
                    inventory_entry.server_or_empty,
                    inventory_entry.discriminator,
                    inventory_entry.serializer_schema,
                )
            ]
            observation = self.collector.collect_observation(event)
            preflight = self.admission.preflight(
                event,
                inventory_token,
                observation.basis_sample,
            )
            if preflight != "READY":
                return self.admission._deny(preflight, 0)
            handle = self.coordinator.ensure(event, observation)
            self.coordinator.drive(
                handle.member_id, self._helpers(event, handle.member_id)
            )
            return self.admission.admit(
                payload,
                inventory_token,
                member_id=handle.member_id,
                episode_id=handle.episode_id,
            )
        except registration_hook_runtime.HookUnavailable:
            raise
        except registration_admission.BasisUnavailable as exc:
            reason = (
                exc.reason
                if exc.reason in registration_admission.RUNTIME_REASONS
                else "ROOT_UNSUPPORTED"
            )
            return self.admission._deny(reason, 0)
        except registration_admission.EventRefused:
            return registration_admission.AdmissionDecision(
                False,
                "PARSER_REJECT",
                registration_admission.PREIDENTITY_RESPONSE,
                0,
            )
        except registration_store.InsufficientSpace:
            return self.admission._deny("STORAGE_DEGRADED", 0)
        except registration_store.StaleAuthority:
            return self.admission._deny("BASIS_UNSTABLE", 0)
        except Exception as exc:
            raise registration_hook_runtime.HookUnavailable(
                "registration runtime could not establish authority"
            ) from exc

    def startup(self, payload: object) -> str:
        event = registration_admission.parse_registration_event(payload)
        observation = self.collector.collect_observation(event)
        reason = self.admission.preflight(
            event,
            self._probe_discriminator(),
            observation.basis_sample,
        )
        if reason != "READY":
            return reason
        handle = self.coordinator.ensure(event, observation)
        result = self.coordinator.drive(
            handle.member_id, self._helpers(event, handle.member_id)
        )
        return result.outcome

    def attempt_due(
        self, due: registration_store.DueCandidate
    ) -> bool:
        authority = self.store.read_selected_authority(due.member_id)
        if authority is None:
            return False
        event = registration_admission.RegistrationEvent(
            workspace_roots=(authority.member["canonical_root"],),
            conversation_id=f"tick-{due.member_id[:16]}",
            generation_id=f"tick-{due.member_epoch}",
            source_contract="awa-registration-host/v1",
            source_event="tick",
        )
        observation = self.collector.collect_observation(event)
        reason = self.admission.preflight(
            event,
            self._probe_discriminator(),
            observation.basis_sample,
        )
        if reason != "READY":
            return False
        execution = self.coordinator.authorize_due(
            due,
            current_basis_hash=observation.identity.current_basis_hash,
        )
        self.coordinator.run_execution(
            execution, self._helpers(event, due.member_id)
        )
        return True

    def _recover_same_boot_member(self, member_id: str) -> bool:
        authority = self.store.read_selected_authority(member_id)
        if authority is None:
            return False
        event = registration_admission.RegistrationEvent(
            workspace_roots=(authority.member["canonical_root"],),
            conversation_id=f"same-boot-{member_id[:16]}",
            generation_id=f"same-boot-{authority.member['member_epoch']}",
            source_contract="awa-registration-host/v1",
            source_event="same_boot",
        )
        observation = self.collector.collect_observation(event)
        reason = self.admission.preflight(
            event,
            self._probe_discriminator(),
            observation.basis_sample,
        )
        if reason != "READY":
            return False
        return (
            self.coordinator.drive(
                member_id, self._helpers(event, member_id)
            ).outcome
            == "SUCCESS"
        )

    def _previous_same_boot_cursor(
        self, *, boot_id: str, now_mono_ns: int
    ) -> registration_runtime.SameBootCursor | None:
        try:
            value, cursor = _read_host_tick(self.host_tick_path)
            interval = int(value["interval_ns"])
            written = int(value["written_mono_ns"])
            if (
                cursor.boot_id != boot_id
                or interval <= 0
                or not 0 <= now_mono_ns - written <= 2 * interval
            ):
                return None
            return cursor
        except BaseException:
            return None

    def tick(self) -> registration_runtime.TickReceipt:
        if self.receipt.deployment_scope == "R0_THROWAWAY":
            raise registration_hook_runtime.HookUnavailable(
                "R0 receipt is not runtime authority"
            )
        boot_id = identity.boot_id()
        now_mono_ns = registration_clock.mach_continuous_time_ns()
        r1_scope = None
        if self.receipt.deployment_scope == "R1_CANARY":
            if self.receipt.member_id is None:
                raise registration_hook_runtime.HookUnavailable(
                    "R1 receipt member is unavailable"
                )
            authority = self.store.read_selected_authority(
                self.receipt.member_id
            )
            if (
                authority is not None
                and registration_admission.canonical_root_hash(
                    authority.member["canonical_root"]
                )
                != self.receipt.canonical_root_hash
            ):
                raise registration_hook_runtime.HookUnavailable(
                    "R1 member root does not match receipt"
                )
            try:
                r1_scope = self.coordinator.preflight_r1_tick(
                    authorized_member_id=self.receipt.member_id,
                    boot_id=boot_id,
                    now_mono_ns=now_mono_ns,
                )
            except registration_runtime.R1ScopeRefused as exc:
                raise registration_hook_runtime.HookUnavailable(
                    "R1 tick scope contains another member"
                ) from exc
            protocol = self.store.current_protocol()
            if protocol is None:
                raise registration_hook_runtime.HookUnavailable(
                    "registration protocol is absent"
                )
            examined = self.coordinator.recover_r1_same_boot(
                r1_scope,
                recover=self._recover_same_boot_member,
            )
            candidate = r1_scope.selection.authorized_same_boot
            snapshot = registration_store.SameBootSnapshot(
                boot_id=boot_id,
                protocol_seq=int(protocol["protocol_seq"]),
                protocol_hash=str(protocol["protocol_hash"]),
                candidates=(() if candidate is None else (candidate,)),
            )
            snapshot_hash = registration_runtime.same_boot_snapshot_hash(
                snapshot
            )
            if examined is None:
                cursor = registration_runtime.SameBootCursor(
                    boot_id=boot_id,
                    protocol_seq=snapshot.protocol_seq,
                    protocol_hash=snapshot.protocol_hash,
                    selection_snapshot_hash=snapshot_hash,
                    last_member_id=None,
                    last_pre_status_hash=None,
                    last_post_status_hash=None,
                    outcome=None,
                    batch_count=0,
                    wrapped=False,
                )
            else:
                cursor = registration_runtime.SameBootCursor(
                    boot_id=boot_id,
                    protocol_seq=snapshot.protocol_seq,
                    protocol_hash=snapshot.protocol_hash,
                    selection_snapshot_hash=snapshot_hash,
                    last_member_id=examined.member_id,
                    last_pre_status_hash=examined.pre_status_hash,
                    last_post_status_hash=examined.post_status_hash,
                    outcome=examined.outcome,
                    batch_count=1,
                    wrapped=False,
                )
            self.coordinator.recover_reboot(
                boot_id, r1_scope=r1_scope
            )
        else:
            same_boot = self.coordinator.recover_same_boot_tick(
                boot_id=boot_id,
                cursor=self._previous_same_boot_cursor(
                    boot_id=boot_id,
                    now_mono_ns=now_mono_ns,
                ),
                recover=self._recover_same_boot_member,
            )
            cursor = same_boot.cursor
            self.coordinator.recover_reboot(boot_id)
        scheduler = registration_runtime.FairnessScheduler(
            store=self.store,
            data=self.data,
            candidate=self.candidate,
        )
        receipt = scheduler.tick(
            boot_id=boot_id,
            now_mono_ns=now_mono_ns,
            attempt=_tick_attempt,
            r1_scope=r1_scope,
        )
        write_host_tick_receipt(
            self.host_tick_path,
            receipt,
            boot_id=boot_id,
            written_mono_ns=registration_clock.mach_continuous_time_ns(),
            same_boot_cursor=cursor,
        )
        return receipt

    def __enter__(self) -> "HostService":
        return self

    def __exit__(self, *_: object) -> None:
        self.store.close()


@contextmanager
def open_service() -> Iterator[HostService]:
    config = _load_config()
    receipt_path = _absolute(
        config["direct_receipt_path"], "DIRECT receipt path"
    )
    bundle_root = os.environ.get("AWA_REGISTRATION_BUNDLE_ROOT")
    if bundle_root is not None and receipt_path != (
        _absolute(bundle_root, "signed bundle root")
        / "direct-receipt.json"
    ):
        raise registration_hook_runtime.HookUnavailable(
            "DIRECT receipt is outside the signed bundle"
        )
    try:
        receipt = registration_projection.DirectReceipt.from_bytes(
            _private_bytes(receipt_path)
        )
    except ValueError as exc:
        raise registration_hook_runtime.HookUnavailable(
            "DIRECT receipt is invalid"
        ) from exc
    _require_runtime_receipt(receipt)
    _verify_runtime_bytes(config, receipt)
    targets = _profile_targets(config["profile_targets"])
    try:
        store = registration_store.RegistrationStore.open_default(
            profile_targets=targets
        )
    except Exception as exc:
        raise registration_hook_runtime.HookUnavailable(
            "registration store is unavailable"
        ) from exc
    try:
        protocol = store.current_protocol()
        if protocol is None:
            raise registration_hook_runtime.HookUnavailable(
                "registration protocol is absent"
            )
        candidate = _candidate_from_protocol(protocol)
        if (
            receipt.schema_hash != protocol["schema_hash"]
            or receipt.protocol_generation
            != str(protocol["protocol_generation"])
            or receipt.digest != candidate.projection_receipt_hash
        ):
            raise registration_hook_runtime.HookUnavailable(
                "DIRECT receipt does not match protocol"
            )
        if any(
            receipt.to_mapping()[field]
            != (
                str(getattr(candidate, field))
                if field
                in {
                    "projection_file_generation",
                }
                else getattr(candidate, field)
            )
            for field in (
                "profile_hash",
                "runtime_capability_hash",
                "writer_binary_hash",
                "writer_capability_hash",
                "tool_inventory_hash",
                "hook_projection_hash",
                "hook_matcher_mode",
                "hook_matcher_hash",
                "projection_file_generation",
                "installer_identity_hash",
                "installer_capability_hash",
            )
        ):
            raise registration_hook_runtime.HookUnavailable(
                "DIRECT receipt does not match protocol"
            )
        capability = _private_bytes(
            _absolute(
                config["writer_capability_path"],
                "writer capability path",
            ),
            limit=4_096,
        )
        data = registration_store.authenticate_data(
            capability, candidate.writer_capability_hash
        )
        entries = _inventory(config["inventory"])
        if (
            registration_projection.tool_inventory_hash(entries)
            != receipt.tool_inventory_hash
        ):
            raise registration_hook_runtime.HookUnavailable(
                "tool inventory receipt mismatch"
            )
        proof_parent = _absolute(
            config["proof_parent"], "proof parent"
        )
        projection_parent = _absolute(
            config["projection_parent"], "projection parent"
        )
        legacy_parent = _absolute(
            config["legacy_parent"], "legacy parent"
        )
        service = HostService(
            store=store,
            candidate=candidate,
            data=data,
            receipt=receipt,
            collector=registration_basis.GitBasisCollector(
                proof_parent=proof_parent,
                projection_parent=projection_parent,
                legacy_parent=legacy_parent,
            ),
            inventory_entries=entries,
            proof_parent=proof_parent,
            host_tick_path=_absolute(
                config["host_tick_receipt_path"],
                "host tick receipt path",
            ),
        )
        yield service
    finally:
        store.close()


def _read_stdin() -> bytes:
    return sys.stdin.buffer.read(
        registration_hook_runtime.MAX_PAYLOAD_BYTES + 1
    )


def _tick_attempt(due: registration_store.DueCandidate) -> bool:
    try:
        with open_service() as service:
            return service.attempt_due(due)
    except BaseException:
        return False


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments == ["admission"]:
        return registration_hook_runtime.main()
    if arguments == ["startup"]:
        try:
            value = _strict_json(_read_stdin())
            with open_service() as service:
                service.startup(value)
            return 0
        except BaseException:
            return 1
    if arguments == ["tick"]:
        try:
            with open_service() as service:
                receipt = service.tick()
            return 1 if receipt.fairness_suspended else 0
        except BaseException:
            return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
