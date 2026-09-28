"""Body C runtime assembly for Body A authority and Body B policy APIs."""

from __future__ import annotations

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
HOST_TICK_SCHEMA = "awa-registration-host-tick/v1"
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


def _host_tick_current(path: Path) -> bool:
    try:
        raw = _private_bytes(path)
        value = _strict_json(raw)
        now_mono_ns = registration_clock.mach_continuous_time_ns()
        return bool(
            isinstance(value, dict)
            and set(value)
            == {
                "schema",
                "boot_id",
                "written_mono_ns",
                "interval_ns",
                "snapshot_token",
                "selected_member_ids",
                "selected_status_hashes",
                "missed_member_ids",
                "member_reasons",
                "recovery_member_ids",
                "fairness_suspended",
            }
            and value["schema"] == HOST_TICK_SCHEMA
            and value["boot_id"] == identity.boot_id()
            and type(value["written_mono_ns"]) is int
            and type(value["interval_ns"]) is int
            and value["interval_ns"] > 0
            and value["fairness_suspended"] is False
            and 0 <= now_mono_ns - value["written_mono_ns"]
            <= 2 * value["interval_ns"]
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
    value = {
        "schema": HOST_TICK_SCHEMA,
        "boot_id": boot_id,
        "written_mono_ns": written_mono_ns,
        "interval_ns": registration_runtime.TICK_INTERVAL_NS,
        "snapshot_token": receipt.snapshot_token,
        "selected_member_ids": list(receipt.selected_member_ids),
        "selected_status_hashes": [
            list(row) for row in receipt.selected_status_hashes
        ],
        "missed_member_ids": list(receipt.missed_member_ids),
        "member_reasons": [list(row) for row in receipt.member_reasons],
        "recovery_member_ids": list(receipt.recovery_member_ids),
        "fairness_suspended": receipt.fairness_suspended,
    }
    payload = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")
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
        ordinary = frozenset(
            item.discriminator
            for item in inventory_entries
            if item.role == "ordinary"
        )
        launches = frozenset(
            item.discriminator
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
        self, payload: object, discriminator: str
    ) -> registration_admission.AdmissionDecision:
        # Body B remains the sole launch/ordinary policy oracle. Helpers are
        # selected only after the same exact event basis derives a member.
        try:
            event = registration_admission.parse_registration_event(payload)
            if discriminator in self.inventory.task_launch:
                return self.admission._deny("TASK_SUBAGENT_DENIED", 0)
            if discriminator not in self.inventory.ordinary:
                return self.admission._deny("UNKNOWN_DISCRIMINATOR", 0)
            observation = self.collector.collect_observation(event)
            preflight = self.admission.preflight(
                event, discriminator, observation.basis_sample
            )
            if preflight != "READY":
                return self.admission._deny(preflight, 0)
            handle = self.coordinator.ensure(event, observation)
            self.coordinator.drive(
                handle.member_id, self._helpers(event, handle.member_id)
            )
            return self.admission.admit(
                payload,
                discriminator,
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

    def tick(self) -> registration_runtime.TickReceipt:
        if self.receipt.deployment_scope == "R0_THROWAWAY":
            raise registration_hook_runtime.HookUnavailable(
                "R0 receipt is not runtime authority"
            )
        boot_id = identity.boot_id()
        now_mono_ns = registration_clock.mach_continuous_time_ns()
        if self.receipt.deployment_scope == "R1_CANARY":
            selected_ids = {
                candidate.member_id
                for candidate in self.store.list_due_candidates(
                    boot_id=boot_id,
                    now_mono_ns=now_mono_ns,
                    limit=registration_runtime.TICK_LANES + 1,
                )
            } | {
                candidate.member_id
                for candidate in self.store.list_reboot_candidates(
                    boot_id
                )
            }
            for member_id in selected_ids:
                authority = self.store.read_selected_authority(member_id)
                if (
                    authority is None
                    or member_id != self.receipt.member_id
                    or registration_admission.canonical_root_hash(
                        authority.member["canonical_root"]
                    )
                    != self.receipt.canonical_root_hash
                ):
                    raise registration_hook_runtime.HookUnavailable(
                        "R1 tick scope contains another member"
                    )
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
        )
        write_host_tick_receipt(
            self.host_tick_path,
            receipt,
            boot_id=boot_id,
            written_mono_ns=registration_clock.mach_continuous_time_ns(),
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
