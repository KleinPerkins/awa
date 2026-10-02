from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from engine import registration_schema, registration_store
from engine.tests.registration_harness import RegistrationHarness


_LEAF_BY_BRANCH = {
    (trigger, leaf.split("@", 1)[0]): f"{trigger}|{leaf.replace('@', '|')}"
    for trigger, leaves in registration_schema.LEAF_GROUPS.items()
    for leaf in leaves
}

_AUDIT_BRANCH = {
    "BOOTSTRAP": "bootstrap",
    "INSTALL_MEMBER": "install_member",
    "BIND_EPISODE": "bind_episode",
    "REACQUIRE_EFFECT": "reacquire",
    "OPEN_EFFECT": "open",
    "APPEND_ACTION": "append",
    "CLOSE_SUCCESS": "close_success",
    "CLOSE_CONFLICT": "close_conflict",
    "INVALIDATE_REQUESTED": "invalidate",
    "SET_PENDING": "set_pending",
    "REPLACE_PENDING": "replace_pending",
    "HANDOFF_RESOLVED": "handoff",
    "MARK_UNAVAILABLE": "mark_unavailable",
    "REBOOT_STATUS": "reboot",
    "SCHEDULE_STATUS": "schedule",
    "ACTIVATE": "activate",
    "BEGIN_DRAIN": "begin_drain",
    "STAGE_NEXT": "stage_next",
    "CANCEL_DRAIN": "cancel_drain",
    "ADOPT_EFFECT": "adopt",
    "ADVANCE_GENERATION": "advance",
    "PRE_EFFECT_DORMANT": "pre_effect_dormant",
    "ENTER_CONTAINMENT": "contain",
    "BEGIN_REPAIR": "begin_repair",
}


def _connection(
    store: registration_store.RegistrationStore,
) -> Any:
    return store._test_connection(registration_store._TEST_PROFILE_SEAL)


def _snapshot(store: registration_store.RegistrationStore) -> dict[str, Any]:
    return {
        "members": {
            row["member_id"]: dict(row)
            for row in _connection(store).execute(
                "SELECT * FROM registration_member"
            ).fetchall()
        },
        "statuses": {
            row["member_id"]: dict(row)
            for row in _connection(store).execute(
                "SELECT * FROM registration_runtime_status"
            ).fetchall()
        },
        "effects": {
            row["effect_id"]: dict(row)
            for row in _connection(store).execute(
                "SELECT * FROM registration_effect"
            ).fetchall()
        },
    }


def _leaf(trigger: str, branch: str) -> str:
    return _LEAF_BY_BRANCH[(trigger, branch)]


def _observe(
    store: registration_store.RegistrationStore,
    before: dict[str, Any],
    operation_id: str,
) -> frozenset[str]:
    operation = dict(
        _connection(store).execute(
            "SELECT * FROM registration_operation_audit WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
    )
    kind = operation["operation_kind"]
    observed = {
        _leaf("trg_operation_audit_insert", _AUDIT_BRANCH[kind])
    }
    protocol = _connection(store).execute(
        "SELECT * FROM registration_protocol_epoch WHERE operation_id=?",
        (operation_id,),
    ).fetchone()
    if protocol is not None:
        transition = protocol["transition_kind"]
        if transition == "ENTER_CONTAINMENT":
            branch = {
                "DRAIN_BOOT_CHANGED": "contain_boot",
                "DRAIN_TIMEOUT": "contain_timeout",
                "ADOPTION_FAILED": "contain_adoption",
                "STORE_FAILURE": "contain_store",
            }[protocol["transition_reason_code"]]
        else:
            branch = {
                "BOOTSTRAP": "bootstrap",
                "ACTIVATE": "activate",
                "FIRST_EFFECT": "first_effect",
                "BEGIN_DRAIN": "begin_drain",
                "STAGE_NEXT": "stage_next",
                "CANCEL_DRAIN": "cancel_drain",
                "ADVANCE_GENERATION": "advance_generation",
                "PRE_EFFECT_DORMANT": "pre_effect_dormant",
                "BEGIN_REPAIR": "begin_repair",
            }[transition]
        observed.add(_leaf("trg_protocol_epoch_insert", branch))

    members = [
        dict(row)
        for row in _connection(store).execute(
            "SELECT * FROM registration_member WHERE write_operation_id=?",
            (operation_id,),
        ).fetchall()
    ]
    for member in members:
        old = before["members"].get(member["member_id"])
        if old is None:
            continue
        if kind == "INVALIDATE_REQUESTED":
            branch = "invalidate"
        elif kind == "OPEN_EFFECT":
            branch = "open"
        elif kind == "SET_PENDING":
            branch = "set_pending"
        elif kind == "REPLACE_PENDING":
            branch = "replace_pending"
        elif kind == "ADOPT_EFFECT":
            branch = (
                "adopt_replace"
                if operation["target_successor_effect_id"] is not None
                else "adopt_preserve"
            )
        elif kind == "CLOSE_SUCCESS":
            branch = "close_success"
        elif kind == "CLOSE_CONFLICT":
            branch = "close_conflict"
        elif kind == "HANDOFF_RESOLVED":
            if old["pending_effect_id"] is not None:
                branch = "handoff_pending"
            else:
                branch = {
                    "BASIS_CHANGED": "handoff_basis",
                    "CURRENT_CLOSURE_CHANGED": "handoff_closure",
                    "EXPLICIT_CONFLICT_RETRY": "handoff_conflict_retry",
                }[operation["target_cause_code"]]
        else:
            continue
        observed.add(_leaf("trg_member_update_state_machine", branch))

    episodes = _connection(store).execute(
        "SELECT 1 FROM registration_episode WHERE write_operation_id=?",
        (operation_id,),
    ).fetchone()
    if episodes is not None:
        observed.add(_leaf("trg_episode_insert", "bind"))

    created_effects = [
        dict(row)
        for row in _connection(store).execute(
            "SELECT * FROM registration_effect WHERE created_operation_id=?",
            (operation_id,),
        ).fetchall()
    ]
    for _effect in created_effects:
        branch = {
            "INSTALL_MEMBER": "install",
            "INVALIDATE_REQUESTED": "invalidate",
            "SET_PENDING": "set_pending",
            "REPLACE_PENDING": "replace_pending",
            "ADOPT_EFFECT": "adopt_replace",
        }.get(kind)
        if kind == "HANDOFF_RESOLVED":
            branch = {
                "BASIS_CHANGED": "handoff_basis",
                "CURRENT_CLOSURE_CHANGED": "handoff_closure",
                "EXPLICIT_CONFLICT_RETRY": "handoff_conflict_retry",
            }[operation["target_cause_code"]]
        if branch is not None:
            observed.add(_leaf("trg_effect_insert", branch))

    closed_effects = [
        dict(row)
        for row in _connection(store).execute(
            "SELECT * FROM registration_effect WHERE outcome_operation_id=?",
            (operation_id,),
        ).fetchall()
    ]
    for effect in closed_effects:
        if effect["outcome_kind"] == "SUCCESS":
            branch = "success"
        elif effect["outcome_kind"] == "LOGICAL_CONFLICT":
            branch = "conflict"
        else:
            branch = {
                "INVALIDATE_REQUESTED": "supersede_requested",
                "REPLACE_PENDING": "supersede_pending",
                "ADOPT_EFFECT": "supersede_adopted",
            }[kind]
        observed.add(_leaf("trg_effect_close", branch))

    actions = _connection(store).execute(
        "SELECT observation_kind FROM registration_effect_action "
        "WHERE write_operation_id=?",
        (operation_id,),
    ).fetchall()
    for action in actions:
        branch = {
            "OBSERVED_EXACT": "observed_exact",
            "APPLIED_VERIFIED": "applied_verified",
            "LOGICAL_CONFLICT": "logical_conflict",
        }[action["observation_kind"]]
        observed.add(_leaf("trg_effect_action_append", branch))

    inserted_statuses = [
        dict(row)
        for row in _connection(store).execute(
            "SELECT * FROM registration_runtime_status "
            "WHERE write_operation_id=? AND status_version=1",
            (operation_id,),
        ).fetchall()
    ]
    for status in inserted_statuses:
        effect = _connection(store).execute(
            "SELECT request_kind FROM registration_effect WHERE effect_id=?",
            (status["current_effect_id"],),
        ).fetchone()
        branch = {
            "CLEAN_ELIGIBLE": "clean",
            "BLOCKED_DIRTY": "dirty",
            "BLOCKED_OPERATION": "operation_blocked",
        }[effect["request_kind"]]
        observed.add(_leaf("trg_runtime_status_insert", branch))

    updated_statuses = [
        dict(row)
        for row in _connection(store).execute(
            "SELECT * FROM registration_runtime_status "
            "WHERE write_operation_id=? AND status_version>1",
            (operation_id,),
        ).fetchall()
    ]
    for status in updated_statuses:
        old_member = before["members"][status["member_id"]]
        old_status = before["statuses"][status["member_id"]]
        member = dict(
            _connection(store).execute(
                "SELECT * FROM registration_member WHERE member_id=?",
                (status["member_id"],),
            ).fetchone()
        )
        effect = dict(
            _connection(store).execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (status["current_effect_id"],),
            ).fetchone()
        )
        if kind == "REACQUIRE_EFFECT":
            branch = (
                "reacquire_adopted"
                if effect["required_protocol_generation"]
                != member["helper_generation"]
                else "reacquire_native"
            )
        elif kind == "OPEN_EFFECT":
            branch = "open"
        elif kind in {"CLOSE_SUCCESS", "CLOSE_CONFLICT"}:
            outcome = "success" if kind == "CLOSE_SUCCESS" else "conflict"
            suffix = (
                "pending"
                if old_member["pending_effect_id"] is not None
                else "idle"
            )
            branch = f"close_{outcome}_{suffix}"
        elif kind == "INVALIDATE_REQUESTED":
            branch = {
                "CLEAN_ELIGIBLE": "invalidate_clean",
                "BLOCKED_DIRTY": "invalidate_dirty",
                "BLOCKED_OPERATION": "invalidate_operation",
            }[effect["request_kind"]]
        elif kind == "HANDOFF_RESOLVED":
            cause = operation["target_cause_code"]
            if cause == "EXPLICIT_CONFLICT_RETRY":
                branch = "handoff_conflict_retry"
            else:
                prefix = (
                    "handoff_closure"
                    if cause == "CURRENT_CLOSURE_CHANGED"
                    else "handoff_basis"
                )
                suffix = {
                    "CLEAN_ELIGIBLE": "clean",
                    "BLOCKED_DIRTY": "dirty",
                    "BLOCKED_OPERATION": "operation",
                }[effect["request_kind"]]
                branch = f"{prefix}_{suffix}"
        elif kind == "ADOPT_EFFECT":
            branch = (
                "adopt_preserve"
                if old_status["executor_token_hash"] is not None
                else "adopt_install"
            )
        elif kind == "MARK_UNAVAILABLE":
            branch = "mark_unavailable"
        elif kind == "REBOOT_STATUS":
            if member["phase"] == "REQUESTED":
                branch = {
                    "CLEAN_ELIGIBLE": "reboot_requested_clean",
                    "BLOCKED_DIRTY": "reboot_requested_dirty",
                    "BLOCKED_OPERATION": "reboot_requested_operation",
                }[effect["request_kind"]]
            elif member["phase"] == "EFFECT_IN_FLIGHT":
                branch = "reboot_in_flight"
            elif member["pending_effect_id"] is not None:
                branch = "reboot_resolved_pending"
            elif member["current_outcome_kind"] == "SUCCESS":
                branch = "reboot_resolved_success"
            else:
                branch = "reboot_resolved_conflict"
        elif kind == "SCHEDULE_STATUS":
            branch = "schedule"
        else:
            continue
        observed.add(_leaf("trg_runtime_status_update", branch))
    return frozenset(observed)


class Scenario:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db = (
            Path(self.temp.name)
            / "state"
            / "registration-v1"
            / "registration.db"
        )
        self.harness = RegistrationHarness.open(
            db, measured_free_bytes=2 * 1024**3
        )
        self.store = self.harness.store
        self.candidate = self.harness.candidate()

    def close(self) -> None:
        self.harness.close()
        self.temp.cleanup()

    def bootstrap(self) -> registration_store.OperationResult:
        return self.store.bootstrap(self.harness.control(), self.candidate)

    def writable(self) -> None:
        self.bootstrap()
        self.store.activate(self.harness.control(), self.candidate)

    def install(
        self, kind: str = "CLEAN_ELIGIBLE", ordinal: int = 1
    ) -> dict[str, Any]:
        intent = (
            self.harness.clean_intent(ordinal=ordinal)
            if kind == "CLEAN_ELIGIBLE"
            else self.harness.blocked_intent(kind, ordinal=ordinal)
        )
        self.store.install_member(
            self.harness.data(),
            self.candidate,
            self.harness.identity(ordinal=ordinal),
            intent,
            sample_boot_id=self.harness.sample_boot_id,
            sample_mono_ns=ordinal,
        )
        return self.current()

    def current(self) -> dict[str, Any]:
        row = self.harness.connection.execute(
            "SELECT m.*,e.request_tuple_hash,e.outcome_tuple_hash,"
            "s.status_hash FROM registration_member m "
            "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
            "JOIN registration_runtime_status s USING(member_id) "
            "ORDER BY m.member_id LIMIT 1"
        ).fetchone()
        return dict(row)

    def open(self) -> registration_store.ExecutionResult:
        row = self.current()
        return self.store.open_effect(
            self.harness.data(),
            self.candidate,
            member_id=row["member_id"],
            expected_member_hash=row["member_tuple_hash"],
            expected_effect_hash=row["request_tuple_hash"],
            expected_status_hash=row["status_hash"],
            executor_secret=b"a" * 32,
        )

    def resolve(
        self,
        outcome: str,
        *,
        pending_kind: str | None = None,
    ) -> None:
        opened = self.open()
        execution = opened.execution
        if pending_kind is not None:
            self.store.mark_unavailable(
                self.harness.data(), self.candidate, execution
            )
            row = self.current()
            identity = self.harness.identity(ordinal=2)
            intent = (
                self.harness.clean_intent(ordinal=2)
                if pending_kind == "CLEAN_ELIGIBLE"
                else self.harness.blocked_intent(pending_kind, ordinal=2)
            )
            self.store.set_pending(
                self.harness.data(),
                self.candidate,
                member_id=row["member_id"],
                expected_member_hash=row["member_tuple_hash"],
                expected_effect_hash=row["request_tuple_hash"],
                expected_status_hash=row["status_hash"],
                basis_hash=identity.current_basis_hash,
                intent=intent,
            )
            row = self.current()
            execution = self.store.reacquire_effect(
                self.harness.data(),
                self.candidate,
                member_id=row["member_id"],
                expected_member_hash=row["member_tuple_hash"],
                expected_effect_hash=row["request_tuple_hash"],
                expected_status_hash=row["status_hash"],
                executor_secret=b"b" * 32,
            ).execution
        if outcome == "SUCCESS":
            for index in range(4):
                self.store.append_action(
                    self.harness.data(),
                    self.candidate,
                    execution,
                    observation_kind="OBSERVED_EXACT",
                    measured_postcondition_hash=(
                        self.harness.next_postcondition()
                    ),
                )
            self.store.close_success(
                self.harness.data(),
                self.candidate,
                execution,
                final_basis_hash=self.harness.identity().current_basis_hash,
            )
        else:
            self.store.append_action(
                self.harness.data(),
                self.candidate,
                execution,
                observation_kind="LOGICAL_CONFLICT",
                measured_postcondition_hash="55" * 32,
            )
            self.store.close_conflict(
                self.harness.data(),
                self.candidate,
                execution,
                conflict_code="PROOF_POSTCONDITION_DIVERGENT",
                expected_hash="66" * 32,
                observed_hash="77" * 32,
            )


def _latest_operation_id(scenario: Scenario) -> str:
    return str(
        scenario.harness.connection.execute(
            "SELECT operation_id FROM registration_operation_audit "
            "ORDER BY operation_seq DESC LIMIT 1"
        ).fetchone()[0]
    )


def run_scenario(name: str) -> frozenset[str]:
    scenario = Scenario()
    execution = None
    try:
        if name == "bootstrap":
            before = _snapshot(scenario.store)
            operation = scenario.bootstrap()
        elif name == "activate":
            scenario.bootstrap()
            before = _snapshot(scenario.store)
            operation = scenario.store.activate(
                scenario.harness.control(), scenario.candidate
            )
        elif name.startswith("install_"):
            scenario.writable()
            before = _snapshot(scenario.store)
            operation = scenario.store.install_member(
                scenario.harness.data(),
                scenario.candidate,
                scenario.harness.identity(),
                (
                    scenario.harness.clean_intent()
                    if name == "install_clean"
                    else scenario.harness.blocked_intent(
                        "BLOCKED_DIRTY"
                        if name == "install_dirty"
                        else "BLOCKED_OPERATION"
                    )
                ),
                sample_boot_id="boot-a",
                sample_mono_ns=1,
            )
        elif name == "bind":
            scenario.writable()
            row = scenario.install()
            before = _snapshot(scenario.store)
            operation = scenario.store.bind_episode(
                scenario.harness.data(),
                scenario.candidate,
                member_id=row["member_id"],
                source=registration_store.EpisodeSource(
                    "conversation-1",
                    "generation-1",
                    "cursor-hook/v1",
                    "beforeSubmitPrompt",
                    "aa" * 32,
                ),
            )
        elif name in {
            "begin_drain",
            "stage_next",
            "cancel_drain",
            "advance_generation",
            "pre_effect_dormant",
            "contain_boot",
            "contain_timeout",
            "contain_adoption",
            "contain_store",
            "begin_repair",
        }:
            scenario.writable()
            if name == "contain_store":
                before = _snapshot(scenario.store)
                operation = scenario.store.enter_containment(
                    scenario.harness.control(),
                    scenario.candidate,
                    reason="STORE_FAILURE",
                )
            else:
                if name == "begin_drain":
                    before = _snapshot(scenario.store)
                    operation = scenario.store.begin_drain(
                        scenario.harness.control(), scenario.candidate
                    )
                else:
                    scenario.store.begin_drain(
                        scenario.harness.control(), scenario.candidate
                    )
                    if name in {
                        "stage_next",
                        "cancel_drain",
                        "advance_generation",
                    }:
                        if name != "stage_next":
                            scenario.store.stage_next(
                                scenario.harness.control(),
                                scenario.candidate,
                                scenario.candidate,
                                quiescence_proof_hash="aa" * 32,
                            )
                        before = _snapshot(scenario.store)
                        if name == "stage_next":
                            operation = scenario.store.stage_next(
                                scenario.harness.control(),
                                scenario.candidate,
                                scenario.candidate,
                                quiescence_proof_hash="aa" * 32,
                            )
                        elif name == "cancel_drain":
                            operation = scenario.store.cancel_drain(
                                scenario.harness.control(),
                                scenario.candidate,
                                quiescence_proof_hash="aa" * 32,
                            )
                        else:
                            operation = scenario.store.advance_generation(
                                scenario.harness.control(),
                                scenario.candidate,
                                quiescence_proof_hash="aa" * 32,
                            )
                    elif name == "pre_effect_dormant":
                        before = _snapshot(scenario.store)
                        operation = scenario.store.pre_effect_dormant(
                            scenario.harness.control(),
                            scenario.candidate,
                            absence_proof_hash="aa" * 32,
                        )
                    elif name == "contain_boot":
                        scenario.harness.sample_boot_id = "boot-b"
                        before = _snapshot(scenario.store)
                        operation = scenario.store.enter_containment(
                            scenario.harness.control(),
                            scenario.candidate,
                            reason="DRAIN_BOOT_CHANGED",
                        )
                    elif name == "contain_timeout":
                        deadline = scenario.store.current_protocol()[
                            "drain_deadline_mono_ns"
                        ]
                        scenario.harness._mono = deadline
                        before = _snapshot(scenario.store)
                        operation = scenario.store.enter_containment(
                            scenario.harness.control(),
                            scenario.candidate,
                            reason="DRAIN_TIMEOUT",
                        )
                    elif name == "contain_adoption":
                        before = _snapshot(scenario.store)
                        operation = scenario.store.enter_containment(
                            scenario.harness.control(),
                            scenario.candidate,
                            reason="ADOPTION_FAILED",
                        )
                    else:
                        scenario.store.enter_containment(
                            scenario.harness.control(),
                            scenario.candidate,
                            reason="ADOPTION_FAILED",
                        )
                        before = _snapshot(scenario.store)
                        operation = scenario.store.begin_repair(
                            scenario.harness.control(), scenario.candidate
                        )
        else:
            return _run_member_scenario(scenario, name)
        return _observe(scenario.store, before, operation.operation_id)
    finally:
        if execution is not None and execution.held:
            execution.close()
        scenario.close()


def _run_member_scenario(
    scenario: Scenario, name: str
) -> frozenset[str]:
    scenario.writable()
    scenario.install()
    execution = None
    try:
        if name == "open":
            before = _snapshot(scenario.store)
            result = scenario.open()
            execution = result.execution
            operation_id = result.operation.operation_id
        elif name.startswith("append_"):
            execution = scenario.open().execution
            before = _snapshot(scenario.store)
            kind = {
                "append_observed": "OBSERVED_EXACT",
                "append_applied": "APPLIED_VERIFIED",
                "append_conflict": "LOGICAL_CONFLICT",
            }[name]
            operation_id = scenario.store.append_action(
                scenario.harness.data(),
                scenario.candidate,
                execution,
                observation_kind=kind,
                measured_postcondition_hash=(
                    "11" * 32
                    if kind == "LOGICAL_CONFLICT"
                    else scenario.harness.next_postcondition()
                ),
            ).operation_id
        elif name in {"mark_unavailable", "reacquire_native"}:
            execution = scenario.open().execution
            if name == "mark_unavailable":
                before = _snapshot(scenario.store)
                operation_id = scenario.store.mark_unavailable(
                    scenario.harness.data(), scenario.candidate, execution
                ).operation_id
                execution = None
            else:
                scenario.store.mark_unavailable(
                    scenario.harness.data(), scenario.candidate, execution
                )
                execution = None
                row = scenario.current()
                before = _snapshot(scenario.store)
                result = scenario.store.reacquire_effect(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    executor_secret=b"b" * 32,
                )
                execution = result.execution
                operation_id = result.operation.operation_id
        elif name.startswith("close_"):
            pending = name.endswith("_pending")
            conflict = name.startswith("close_conflict")
            execution = scenario.open().execution
            if pending:
                scenario.store.mark_unavailable(
                    scenario.harness.data(), scenario.candidate, execution
                )
                execution = None
                row = scenario.current()
                identity = scenario.harness.identity(ordinal=2)
                scenario.store.set_pending(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    basis_hash=identity.current_basis_hash,
                    intent=scenario.harness.clean_intent(ordinal=2),
                )
                row = scenario.current()
                execution = scenario.store.reacquire_effect(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    executor_secret=b"b" * 32,
                ).execution
            if conflict:
                scenario.store.append_action(
                    scenario.harness.data(),
                    scenario.candidate,
                    execution,
                    observation_kind="LOGICAL_CONFLICT",
                    measured_postcondition_hash="11" * 32,
                )
            else:
                for index in range(4):
                    scenario.store.append_action(
                        scenario.harness.data(),
                        scenario.candidate,
                        execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            scenario.harness.next_postcondition()
                        ),
                    )
            before = _snapshot(scenario.store)
            if conflict:
                result = scenario.store.close_conflict(
                    scenario.harness.data(),
                    scenario.candidate,
                    execution,
                    conflict_code="PROOF_POSTCONDITION_DIVERGENT",
                    expected_hash="22" * 32,
                    observed_hash="33" * 32,
                )
            else:
                result = scenario.store.close_success(
                    scenario.harness.data(),
                    scenario.candidate,
                    execution,
                    final_basis_hash=scenario.harness.identity().current_basis_hash,
                )
            execution = None
            operation_id = result.operation_id
        elif name.startswith("invalidate_"):
            row = scenario.current()
            ordinal = 2
            identity = scenario.harness.identity(ordinal=ordinal)
            request_kind = {
                "invalidate_clean": "CLEAN_ELIGIBLE",
                "invalidate_dirty": "BLOCKED_DIRTY",
                "invalidate_operation": "BLOCKED_OPERATION",
            }[name]
            intent = (
                scenario.harness.clean_intent(ordinal=ordinal)
                if request_kind == "CLEAN_ELIGIBLE"
                else scenario.harness.blocked_intent(
                    request_kind, ordinal=ordinal
                )
            )
            before = _snapshot(scenario.store)
            operation_id = scenario.store.invalidate_requested(
                scenario.harness.data(),
                scenario.candidate,
                member_id=row["member_id"],
                expected_member_hash=row["member_tuple_hash"],
                expected_effect_hash=row["request_tuple_hash"],
                expected_status_hash=row["status_hash"],
                basis=registration_store.BasisUpdate(
                    identity.policy_basis_hash,
                    identity.operation_basis_hash,
                    identity.lifecycle_basis_hash,
                    identity.current_basis_hash,
                ),
                intent=intent,
            ).operation_id
        elif name in {"set_pending", "replace_pending"}:
            execution = scenario.open().execution
            execution.close()
            execution = None
            row = scenario.current()
            identity = scenario.harness.identity(ordinal=2)
            scenario_before = _snapshot(scenario.store)
            set_result = scenario.store.set_pending(
                scenario.harness.data(),
                scenario.candidate,
                member_id=row["member_id"],
                expected_member_hash=row["member_tuple_hash"],
                expected_effect_hash=row["request_tuple_hash"],
                expected_status_hash=row["status_hash"],
                basis_hash=identity.current_basis_hash,
                intent=scenario.harness.clean_intent(ordinal=2),
            )
            if name == "set_pending":
                before = scenario_before
                operation_id = set_result.operation_id
            else:
                row = scenario.current()
                pending = scenario.harness.connection.execute(
                    "SELECT request_tuple_hash FROM registration_effect "
                    "WHERE effect_id=?",
                    (row["pending_effect_id"],),
                ).fetchone()[0]
                identity = scenario.harness.identity(ordinal=3)
                before = _snapshot(scenario.store)
                operation_id = scenario.store.replace_pending(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=pending,
                    expected_status_hash=row["status_hash"],
                    basis_hash=identity.current_basis_hash,
                    intent=scenario.harness.clean_intent(ordinal=3),
                ).operation_id
        elif name.startswith("handoff_"):
            pending_kind = None
            outcome = "SUCCESS"
            cause = None
            request_kind = "CLEAN_ELIGIBLE"
            if name == "handoff_pending":
                pending_kind = "CLEAN_ELIGIBLE"
            elif name == "handoff_conflict_retry":
                outcome = "LOGICAL_CONFLICT"
                cause = "EXPLICIT_CONFLICT_RETRY"
            else:
                parts = name.split("_")
                cause = (
                    "CURRENT_CLOSURE_CHANGED"
                    if parts[1] == "closure"
                    else "BASIS_CHANGED"
                )
                request_kind = {
                    "clean": "CLEAN_ELIGIBLE",
                    "dirty": "BLOCKED_DIRTY",
                    "operation": "BLOCKED_OPERATION",
                }[parts[2]]
            scenario.resolve(outcome, pending_kind=pending_kind)
            row = scenario.current()
            before = _snapshot(scenario.store)
            if pending_kind is not None:
                result = scenario.store.handoff_resolved(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["outcome_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    basis=registration_store.BasisUpdate(
                        scenario.harness.identity(ordinal=2).policy_basis_hash,
                        scenario.harness.identity(ordinal=2).operation_basis_hash,
                        scenario.harness.identity(ordinal=2).lifecycle_basis_hash,
                        scenario.harness.identity(ordinal=2).current_basis_hash,
                    ),
                )
            else:
                identity = scenario.harness.identity(ordinal=2)
                intent = (
                    scenario.harness.clean_intent(ordinal=2)
                    if request_kind == "CLEAN_ELIGIBLE"
                    else scenario.harness.blocked_intent(
                        request_kind, ordinal=2
                    )
                )
                result = scenario.store.handoff_resolved(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["outcome_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    cause=cause,
                    basis=registration_store.BasisUpdate(
                        identity.policy_basis_hash,
                        identity.operation_basis_hash,
                        identity.lifecycle_basis_hash,
                        identity.current_basis_hash,
                    ),
                    intent=intent,
                )
            operation_id = result.operation_id
        elif name.startswith("adopt_") or name == "reacquire_adopted":
            execution = scenario.open().execution
            if name in {"adopt_install", "adopt_replace"}:
                scenario.store.mark_unavailable(
                    scenario.harness.data(), scenario.candidate, execution
                )
                execution = None
            else:
                execution.close()
                execution = None
            if name == "adopt_replace":
                row = scenario.current()
                identity = scenario.harness.identity(ordinal=2)
                scenario.store.set_pending(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    basis_hash=identity.current_basis_hash,
                    intent=scenario.harness.clean_intent(ordinal=2),
                )
            scenario.store.begin_drain(
                scenario.harness.control(), scenario.candidate
            )
            scenario.store.stage_next(
                scenario.harness.control(),
                scenario.candidate,
                scenario.candidate,
                quiescence_proof_hash="aa" * 32,
            )
            row = scenario.current()
            before = _snapshot(scenario.store)
            result = scenario.store.adopt_effect(
                scenario.harness.control(),
                scenario.candidate,
                member_id=row["member_id"],
                expected_member_hash=row["member_tuple_hash"],
                expected_status_hash=row["status_hash"],
                executor_secret=(
                    b"a" * 32
                    if name in {"adopt_preserve", "reacquire_adopted"}
                    else None
                ),
                replacement_intent=(
                    scenario.harness.clean_intent(ordinal=3)
                    if name == "adopt_replace"
                    else None
                ),
                replacement_basis_hash=(
                    scenario.harness.identity(ordinal=3).current_basis_hash
                    if name == "adopt_replace"
                    else None
                ),
            )
            execution = result.execution
            operation_id = result.operation.operation_id
            if name == "reacquire_adopted":
                execution.close()
                execution = None
                status = scenario.harness.connection.execute(
                    "SELECT member_id,status_hash FROM registration_runtime_status"
                ).fetchone()
                scenario.store.mark_dead_executor_unavailable(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=status["member_id"],
                    expected_status_hash=status["status_hash"],
                )
                scenario.store.advance_generation(
                    scenario.harness.control(),
                    scenario.candidate,
                    quiescence_proof_hash="bb" * 32,
                )
                row = scenario.current()
                before = _snapshot(scenario.store)
                result = scenario.store.reacquire_effect(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    executor_secret=b"b" * 32,
                )
                execution = result.execution
                operation_id = result.operation.operation_id
        elif name.startswith("reboot_"):
            variant = name.removeprefix("reboot_")
            if variant == "requested_clean":
                pass
            elif variant in {"requested_dirty", "requested_operation"}:
                # Replace the initial clean request with the selected blocked request.
                row = scenario.current()
                identity = scenario.harness.identity(ordinal=2)
                request_kind = (
                    "BLOCKED_DIRTY"
                    if variant == "requested_dirty"
                    else "BLOCKED_OPERATION"
                )
                scenario.store.invalidate_requested(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    basis=registration_store.BasisUpdate(
                        identity.policy_basis_hash,
                        identity.operation_basis_hash,
                        identity.lifecycle_basis_hash,
                        identity.current_basis_hash,
                    ),
                    intent=scenario.harness.blocked_intent(
                        request_kind, ordinal=2
                    ),
                )
                row = scenario.current()
                scenario.harness.seed_reboot_target(
                    row["member_id"], boot_id="boot-a"
                )
            elif variant == "in_flight":
                execution = scenario.open().execution
                execution.close()
                execution = None
            elif variant == "resolved_success":
                scenario.resolve("SUCCESS")
                row = scenario.current()
                scenario.harness.seed_reboot_target(
                    row["member_id"], boot_id="boot-a"
                )
            elif variant == "resolved_conflict":
                scenario.resolve("LOGICAL_CONFLICT")
                row = scenario.current()
                scenario.harness.seed_reboot_target(
                    row["member_id"], boot_id="boot-a"
                )
            elif variant == "resolved_pending":
                scenario.resolve("SUCCESS", pending_kind="CLEAN_ELIGIBLE")
            row = scenario.current()
            scenario.harness.sample_boot_id = "boot-b"
            before = _snapshot(scenario.store)
            if variant in {
                "requested_dirty",
                "requested_operation",
                "resolved_success",
                "resolved_conflict",
            }:
                operation_id = (
                    scenario.harness.reboot_sql_only_predecessor(
                        row["member_id"],
                        expected_status_hash=row["status_hash"],
                    ).operation_id
                )
            else:
                operation_id = scenario.store.reboot_status(
                    scenario.harness.data(),
                    scenario.candidate,
                    member_id=row["member_id"],
                    expected_status_hash=row["status_hash"],
                ).operation_id
        elif name == "schedule":
            row = scenario.current()
            before = _snapshot(scenario.store)
            operation_id = scenario.store.schedule_status(
                scenario.harness.data(),
                scenario.candidate,
                member_id=row["member_id"],
                expected_status_hash=row["status_hash"],
                attempt_count=1,
                backoff_ns=1,
            ).operation_id
        else:
            raise AssertionError(f"unknown registration leaf scenario: {name}")
        return _observe(scenario.store, before, operation_id)
    finally:
        if execution is not None and execution.held:
            execution.close()
        scenario.close()
