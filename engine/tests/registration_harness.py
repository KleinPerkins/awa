"""Body A deterministic fault, free-space, and predecessor-state fixtures."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from engine import registration_hashes, registration_store


class RegistrationHarness:
    _IDENTITY = b"fixture-installer-identity"
    _CAPABILITY = b"fixture-installer-capability"
    _WRITER = b"fixture-writer-capability"

    def __init__(self, db_path: Path, *, measured_free_bytes: int) -> None:
        self.measured_free_bytes = measured_free_bytes
        self._counter = 0
        self._wall = 1_000_000
        self._mono = 0
        self._faults: dict[str, list[BaseException]] = {}
        self.sample_boot_id = "boot-a"
        self.store = registration_store.RegistrationStore(
            db_path,
            free_bytes=lambda _fd: self.measured_free_bytes,
            wall_ns=self._next_wall,
            operation_ids=self._next_operation_id,
            boot_id=lambda: self.sample_boot_id,
            mono_ns=self._next_mono,
            fault=self._inject_fault,
            _test_profile_seal=registration_store._TEST_PROFILE_SEAL,
        )
        self._counter = self.store.table_count(
            "registration_operation_audit"
        )

    @classmethod
    def open(
        cls, db_path: Path, *, measured_free_bytes: int
    ) -> "RegistrationHarness":
        return cls(db_path, measured_free_bytes=measured_free_bytes)

    def _next_wall(self) -> int:
        self._wall += 1
        return self._wall

    def _next_operation_id(self) -> str:
        self._counter += 1
        return hashlib.sha256(
            f"operation:{self._counter}".encode()
        ).hexdigest()

    def _next_mono(self) -> int:
        self._mono += 1
        return self._mono

    @property
    def connection(self) -> sqlite3.Connection:
        return self.store._test_connection(
            registration_store._TEST_PROFILE_SEAL
        )

    def inject_fault(self, point: str, error: BaseException) -> None:
        self._faults.setdefault(point, []).append(error)

    def _inject_fault(self, point: str) -> None:
        pending = self._faults.get(point)
        if pending:
            raise pending.pop(0)

    def candidate(self) -> registration_store.ProtocolCandidate:
        def digest(label: str) -> str:
            return hashlib.sha256(label.encode()).hexdigest()

        return registration_store.ProtocolCandidate(
            profile_hash=digest("profile"),
            runtime_capability_hash=digest("runtime"),
            writer_binary_hash=digest("writer-binary"),
            writer_capability_hash=registration_store._domain_hash(
                "awa-registration-writer-capability/v1", self._WRITER
            ),
            tool_inventory_hash=digest("tool-inventory"),
            hook_projection_hash=digest("hook-projection"),
            hook_matcher_mode="ENUMERATED",
            hook_matcher_hash=digest("hook-matcher"),
            projection_receipt_hash=digest("projection-receipt"),
            projection_file_generation=1,
            installer_identity_hash=registration_store._domain_hash(
                "awa-registration-installer-identity/v1", self._IDENTITY
            ),
            installer_capability_hash=registration_store._domain_hash(
                "awa-registration-installer-capability/v1", self._CAPABILITY
            ),
            storage_dev=1,
        )

    def control(self) -> registration_store.ControlCapability:
        candidate = self.candidate()
        return registration_store.authenticate_control(
            installer_identity=self._IDENTITY,
            installer_capability=self._CAPABILITY,
            protocol_lock_receipt=b"fixture-protocol-lock",
            control_binding=b"fixture-control-binding",
            expected_identity_hash=candidate.installer_identity_hash,
            expected_capability_hash=candidate.installer_capability_hash,
        )

    def data(self) -> registration_store.DataCapability:
        candidate = self.candidate()
        return registration_store.authenticate_data(
            self._WRITER, candidate.writer_capability_hash
        )

    def identity(
        self, *, ordinal: int = 1
    ) -> registration_store.MemberIdentity:
        def digest(label: str) -> str:
            return hashlib.sha256(
                f"{label}:{ordinal}".encode()
            ).hexdigest()

        root = f"/fixture/root-{ordinal}"
        return registration_store.MemberIdentity(
            canonical_root=root,
            root_dev=1,
            root_ino=ordinal,
            git_toplevel=root,
            git_dir=f"/fixture/git-{ordinal}",
            git_dir_dev=1,
            git_dir_ino=1000 + ordinal,
            git_common_dir=f"/fixture/common-{ordinal}",
            git_common_dev=1,
            git_common_ino=2000 + ordinal,
            proof_dev=1,
            projection_dev=1,
            legacy_state_dev=1,
            physical_basis_hash=digest("physical"),
            git_basis_hash=digest("git"),
            policy_basis_hash=digest("policy"),
            operation_basis_hash=digest("operation"),
            lifecycle_basis_hash=digest("lifecycle"),
            current_basis_hash=digest("current"),
        )

    def clean_intent(
        self, *, ordinal: int = 1
    ) -> registration_store.EffectIntent:
        def digest(label: str) -> str:
            return hashlib.sha256(
                f"{label}:{ordinal}".encode()
            ).hexdigest()

        return registration_store.EffectIntent(
            request_kind="CLEAN_ELIGIBLE",
            request_basis_hash=digest("current"),
            actions=tuple(
                registration_store.ActionSpec(
                    kind,
                    digest(f"action-{index}"),
                    (
                        digest("current")
                        if index == 4
                        else digest(f"post-{index}")
                    ),
                )
                for index, kind in enumerate(
                    (
                        "PUBLISH_EFFECT_PROOF",
                        "CONVERGE_LEGACY_LEASE",
                        "CONVERGE_LEGACY_LIFECYCLE",
                        "COLLECT_FINAL_BASIS",
                    ),
                    1,
                )
            ),
            external_growth_reservation_bytes=64 * 1024,
            outcome_reservation_bytes=64 * 1024,
            successor_reservation_bytes=64 * 1024,
        )

    def blocked_intent(
        self, request_kind: str = "BLOCKED_DIRTY", *, ordinal: int = 1
    ) -> registration_store.EffectIntent:
        return registration_store.EffectIntent(
            request_kind=request_kind,
            request_basis_hash=hashlib.sha256(
                f"current:{ordinal}".encode()
            ).hexdigest(),
            actions=(),
            external_growth_reservation_bytes=0,
            outcome_reservation_bytes=64 * 1024,
            successor_reservation_bytes=64 * 1024,
            blocked_basis_fingerprint=hashlib.sha256(
                f"blocked:{ordinal}".encode()
            ).hexdigest(),
        )

    def next_postcondition(self, member_id: str | None = None) -> str:
        if member_id is None:
            member_id = self.connection.execute(
                "SELECT member_id FROM registration_member ORDER BY member_id LIMIT 1"
            ).fetchone()[0]
        effect_id = self.connection.execute(
            "SELECT current_effect_id FROM registration_member WHERE member_id=?",
            (member_id,),
        ).fetchone()[0]
        count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM registration_effect_action "
                "WHERE effect_id=?",
                (effect_id,),
            ).fetchone()[0]
        )
        return str(
            self.connection.execute(
                f"SELECT postcondition_{count + 1}_hash "
                "FROM registration_effect WHERE effect_id=?",
                (effect_id,),
            ).fetchone()[0]
        )

    def seed_reboot_target(self, member_id: str, *, boot_id: str) -> None:
        """Seed an A01-only valid predecessor before the real T09 witness."""
        status = dict(
            self.connection.execute(
                "SELECT * FROM registration_runtime_status WHERE member_id=?",
                (member_id,),
            ).fetchone()
        )
        status.update(
            {
                "schedule_boot_id": boot_id,
                "observed_now_mono_ns": 1,
                "next_due_mono_ns": 1,
                "due_since_mono_ns": 1,
                "attempt_count": 0,
                "backoff_ns": 0,
            }
        )
        status["status_hash"] = registration_hashes.derive(
            "status_hash", status
        )
        trigger_sql = self.connection.execute(
            "SELECT sql FROM sqlite_schema "
            "WHERE name='trg_runtime_status_update'"
        ).fetchone()[0]
        external = sqlite3.connect(
            str(self.store.db_path), timeout=5.0, isolation_level=None
        )
        try:
            external.execute("BEGIN IMMEDIATE")
            external.execute("DROP TRIGGER trg_runtime_status_update")
            external.execute(
                "UPDATE registration_runtime_status SET "
                "schedule_boot_id=?,observed_now_mono_ns=?,next_due_mono_ns=?,"
                "due_since_mono_ns=?,attempt_count=?,backoff_ns=?,status_hash=? "
                "WHERE member_id=?",
                (
                    status["schedule_boot_id"],
                    status["observed_now_mono_ns"],
                    status["next_due_mono_ns"],
                    status["due_since_mono_ns"],
                    status["attempt_count"],
                    status["backoff_ns"],
                    status["status_hash"],
                    member_id,
                ),
            )
            external.execute(trigger_sql)
            external.execute("COMMIT")
        finally:
            external.close()

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "RegistrationHarness":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
