from __future__ import annotations

import tempfile
import sqlite3
import multiprocessing
import time
import unittest
from pathlib import Path

from engine import registration_admission, registration_runtime, registration_store
from engine.tests.registration_harness import RegistrationHarness


def _event(root: str = "/fixture/root-1"):
    return registration_admission.RegistrationEvent(
        workspace_roots=(root,),
        conversation_id="conversation-1",
        generation_id="generation-1",
        source_contract="cursor-hook/v1",
        source_event="beforeShellExecution",
    )


def _observation(
    harness: RegistrationHarness, ordinal: int = 1
) -> registration_runtime.BasisObservation:
    identity = harness.identity(ordinal=ordinal)
    return registration_runtime.BasisObservation.from_identity(
        identity,
        request_kind="CLEAN_ELIGIBLE",
        workspace_roots_hash=f"{ordinal:064x}",
    )


class FakeActionHelper:
    def __init__(self, *, initially_exact: bool = False) -> None:
        self.exact = initially_exact
        self.inspect_count = 0
        self.apply_count = 0
        self.phases_at_io: list[str] = []
        self.store: registration_store.RegistrationStore | None = None
        self.member_id = ""

    def inspect(self, action: registration_runtime.ActionWork):
        self.inspect_count += 1
        if self.store is not None:
            authority = self.store.read_selected_authority(self.member_id)
            self.phases_at_io.append(authority.member["phase"])
        return registration_runtime.HelperObservation(
            kind=("EXACT" if self.exact else "ABSENT"),
            measured_postcondition_hash=(
                action.postcondition_hash if self.exact else "ff" * 32
            ),
            external_growth_bytes=0,
        )

    def apply(
        self,
        action: registration_runtime.ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        self.apply_count += 1
        self.exact = True


class FakeObservationCollector:
    def __init__(
        self, observation: registration_runtime.BasisObservation
    ) -> None:
        self.observation = observation
        self.calls = 0

    def collect_observation(self, _event):
        self.calls += 1
        return self.observation

    def collect(self, _event):
        self.calls += 1
        return self.observation.basis_sample


class ExplodingHelper(FakeActionHelper):
    def apply(self, action, execution) -> None:
        del action, execution
        raise OSError("helper failed")


def _return_false(_value):
    return False


def _return_true(_value):
    return True


def _identity_payload(value):
    return value


def _busy_forever(_value):
    while True:
        pass


def _admission_controller(harness, collector):
    candidate = harness.candidate()
    return registration_admission.AdmissionController(
        inventory=registration_admission.ToolInventory(
            ordinary=frozenset({"shell"}),
            task_launch=frozenset({"Task"}),
        ),
        collector=collector,
        store=registration_runtime.StoreAuthorityAdapter(harness.store),
        host_provider=lambda: registration_admission.HostEnvelope(
            True,
            candidate.profile_hash,
            candidate.hook_projection_hash,
            candidate.tool_inventory_hash,
            True,
            True,
            True,
        ),
        receipt_provider=lambda: registration_admission.DeploymentReceipt(
            "DIRECT",
            "R2_DIRECT",
            "99" * 32,
            None,
            None,
            "98" * 32,
        ),
        expected_candidate_digest="99" * 32,
    )


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationCoordinatorTest(unittest.TestCase):
    def _setup(self):
        temporary = tempfile.TemporaryDirectory()
        db = (
            Path(temporary.name)
            / "state"
            / "registration-v1"
            / "registration.db"
        )
        harness = RegistrationHarness.open(
            db, measured_free_bytes=2 * 1024**3
        )
        candidate = harness.candidate()
        harness.store.bootstrap(harness.control(), candidate)
        harness.store.activate(harness.control(), candidate)
        coordinator = registration_runtime.RegistrationCoordinator(
            store=harness.store,
            data=harness.data(),
            candidate=candidate,
        )
        return temporary, harness, coordinator

    def test_install_bind_and_four_actions_start_only_after_open(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            authority = harness.store.read_selected_authority(
                ensured.member_id, episode_id=ensured.episode_id
            )
            self.assertEqual(authority.member["phase"], "REQUESTED")
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            for helper in helpers.values():
                helper.store = harness.store
                helper.member_id = ensured.member_id
            result = coordinator.drive(ensured.member_id, helpers)
            self.assertEqual(result.outcome, "SUCCESS")
            self.assertTrue(
                all(
                    helper.phases_at_io
                    and set(helper.phases_at_io) == {"EFFECT_IN_FLIGHT"}
                    for helper in helpers.values()
                )
            )
            self.assertEqual(
                sum(helper.apply_count for helper in helpers.values()), 4
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_ack_loss_replay_observes_without_duplicate_apply(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            execution = coordinator.open_due(ensured.member_id)
            first = helpers[registration_runtime.ACTION_KINDS[0]]
            harness.inject_fault(
                "before_insert:registration_effect_action",
                RuntimeError("lost acknowledgement"),
            )
            with self.assertRaises(RuntimeError):
                coordinator.run_execution(execution, helpers)
            self.assertEqual(first.apply_count, 1)
            self.assertFalse(execution.held)
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertIsNone(authority.status["executor_token_hash"])
            self.assertEqual(authority.status["help_due"], 1)
            result = coordinator.drive(ensured.member_id, helpers)
            self.assertEqual(result.outcome, "SUCCESS")
            self.assertEqual(first.apply_count, 1)
        finally:
            harness.close()
            temporary.cleanup()

    def test_unavailable_appends_no_action_then_same_effect_reacquires(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            unavailable = registration_runtime.UnavailableHelper()
            helpers = {
                kind: (
                    unavailable
                    if index == 0
                    else FakeActionHelper()
                )
                for index, kind in enumerate(
                    registration_runtime.ACTION_KINDS
                )
            }
            first = coordinator.drive(ensured.member_id, helpers)
            self.assertEqual(first.outcome, "UNAVAILABLE")
            self.assertEqual(
                harness.store.table_count("registration_effect_action"), 0
            )
            effect_before = harness.store.read_selected_authority(
                ensured.member_id
            ).effect["effect_id"]
            helpers[registration_runtime.ACTION_KINDS[0]] = FakeActionHelper()
            second = coordinator.drive(ensured.member_id, helpers)
            self.assertEqual(second.outcome, "SUCCESS")
            effect_after = harness.store.read_selected_authority(
                ensured.member_id
            ).effect["effect_id"]
            self.assertEqual(effect_after, effect_before)
        finally:
            harness.close()
            temporary.cleanup()

    def test_adopted_same_effect_reacquires_without_multi_hop(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            harness.store.mark_unavailable(
                harness.data(), harness.candidate(), execution
            )
            harness.store.begin_drain(
                harness.control(), harness.candidate()
            )
            harness.store.stage_next(
                harness.control(),
                harness.candidate(),
                harness.candidate(),
                quiescence_proof_hash="aa" * 32,
            )
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            adopted = harness.store.adopt_effect(
                harness.control(),
                harness.candidate(),
                member_id=ensured.member_id,
                expected_member_hash=authority.member[
                    "member_tuple_hash"
                ],
                expected_status_hash=authority.status["status_hash"],
            )
            adopted.execution.close()
            harness.store.advance_generation(
                harness.control(),
                harness.candidate(),
                quiescence_proof_hash="bb" * 32,
            )
            status = harness.store.read_selected_authority(
                ensured.member_id
            ).status
            harness.store.mark_dead_executor_unavailable(
                harness.data(),
                harness.candidate(),
                member_id=ensured.member_id,
                expected_status_hash=status["status_hash"],
            )
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            result = coordinator.drive(ensured.member_id, helpers)
            self.assertEqual(result.outcome, "SUCCESS")
            audit = harness.connection.execute(
                "SELECT COUNT(*) FROM registration_operation_audit "
                "WHERE operation_kind='ADOPT_EFFECT'"
            ).fetchone()[0]
            self.assertEqual(audit, 1)
        finally:
            harness.close()
            temporary.cleanup()

    def test_adoption_replaces_pending_with_staged_basis(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            harness.store.mark_unavailable(
                harness.data(), harness.candidate(), execution
            )

            def changed(ordinal: int):
                observation = _observation(harness, ordinal=ordinal)
                identity = registration_store.MemberIdentity(
                    **{
                        **observation.identity.__dict__,
                        "canonical_root": "/fixture/root-1",
                        "git_toplevel": "/fixture/root-1",
                        "root_dev": 1,
                        "root_ino": 1,
                        "git_dir": "/fixture/git-1",
                        "git_dir_dev": 1,
                        "git_dir_ino": 1001,
                        "git_common_dir": "/fixture/common-1",
                        "git_common_dev": 1,
                        "git_common_ino": 2001,
                    }
                )
                return registration_runtime.BasisObservation(
                    **{**observation.__dict__, "identity": identity}
                )

            pending_observation = changed(2)
            coordinator.ensure(_event(), pending_observation)
            before = harness.store.read_selected_authority(
                ensured.member_id
            )
            old_pending = before.member["pending_effect_id"]
            harness.store.begin_drain(
                harness.control(), harness.candidate()
            )
            harness.store.stage_next(
                harness.control(),
                harness.candidate(),
                harness.candidate(),
                quiescence_proof_hash="aa" * 32,
            )
            staged = harness.store.read_selected_authority(
                ensured.member_id
            )
            replacement = changed(3)
            adopted = harness.store.adopt_effect(
                harness.control(),
                harness.candidate(),
                member_id=ensured.member_id,
                expected_member_hash=staged.member["member_tuple_hash"],
                expected_status_hash=staged.status["status_hash"],
                replacement_intent=registration_runtime._intent(
                    replacement
                ),
                replacement_basis_hash=(
                    replacement.identity.current_basis_hash
                ),
            )
            adopted.execution.close()
            after = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertNotEqual(
                after.member["pending_effect_id"], old_pending
            )
            new_pending = harness.connection.execute(
                "SELECT request_basis_hash,required_protocol_generation "
                "FROM registration_effect WHERE effect_id=?",
                (after.member["pending_effect_id"],),
            ).fetchone()
            self.assertEqual(
                new_pending["request_basis_hash"],
                replacement.identity.current_basis_hash,
            )
            self.assertEqual(
                new_pending["required_protocol_generation"], 2
            )
            prior = harness.connection.execute(
                "SELECT outcome_kind FROM registration_effect "
                "WHERE effect_id=?",
                (old_pending,),
            ).fetchone()
            self.assertEqual(prior["outcome_kind"], "SUPERSEDED")
        finally:
            harness.close()
            temporary.cleanup()

    def test_unchanged_success_same_event_is_zero_write(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            observation = _observation(harness)
            ensured = coordinator.ensure(_event(), observation)
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            coordinator.drive(ensured.member_id, helpers)
            before = harness.store.table_count("registration_operation_audit")
            again = coordinator.ensure(_event(), observation)
            after = harness.store.table_count("registration_operation_audit")
            self.assertEqual(again.member_id, ensured.member_id)
            self.assertEqual(after, before)
        finally:
            harness.close()
            temporary.cleanup()

    def test_basis_change_invalidates_requested_member_epoch(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            changed = _observation(harness, ordinal=2)
            changed = registration_runtime.BasisObservation(
                **{
                    **changed.__dict__,
                    "identity": registration_store.MemberIdentity(
                        **{
                            **changed.identity.__dict__,
                            "canonical_root": "/fixture/root-1",
                            "git_toplevel": "/fixture/root-1",
                            "root_dev": 1,
                            "root_ino": 1,
                            "git_dir": "/fixture/git-1",
                            "git_dir_dev": 1,
                            "git_dir_ino": 1001,
                            "git_common_dir": "/fixture/common-1",
                            "git_common_dev": 1,
                            "git_common_ino": 2001,
                        }
                    ),
                }
            )
            coordinator.ensure(_event(), changed)
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(authority.member["phase"], "REQUESTED")
            self.assertEqual(authority.member["member_epoch"], 2)
        finally:
            harness.close()
            temporary.cleanup()

    def test_inflight_basis_changes_set_then_replace_pending(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            execution.close()  # process-death fixture; active effect stays in flight

            def changed(ordinal: int):
                observation = _observation(harness, ordinal=ordinal)
                identity = registration_store.MemberIdentity(
                    **{
                        **observation.identity.__dict__,
                        "canonical_root": "/fixture/root-1",
                        "git_toplevel": "/fixture/root-1",
                        "root_dev": 1,
                        "root_ino": 1,
                        "git_dir": "/fixture/git-1",
                        "git_dir_dev": 1,
                        "git_dir_ino": 1001,
                        "git_common_dir": "/fixture/common-1",
                        "git_common_dev": 1,
                        "git_common_ino": 2001,
                    }
                )
                return registration_runtime.BasisObservation(
                    **{**observation.__dict__, "identity": identity}
                )

            coordinator.ensure(_event(), changed(2))
            first = harness.store.read_selected_authority(ensured.member_id)
            active = first.member["current_effect_id"]
            pending = first.member["pending_effect_id"]
            self.assertIsNotNone(pending)
            coordinator.ensure(_event(), changed(3))
            second = harness.store.read_selected_authority(ensured.member_id)
            self.assertEqual(second.member["current_effect_id"], active)
            self.assertNotEqual(second.member["pending_effect_id"], pending)
            prior = harness.connection.execute(
                "SELECT outcome_kind FROM registration_effect "
                "WHERE effect_id=?",
                (pending,),
            ).fetchone()
            self.assertEqual(prior["outcome_kind"], "SUPERSEDED")
        finally:
            harness.close()
            temporary.cleanup()

    def test_drive_handoffs_resolved_pending_then_completes_successor(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            harness.store.mark_unavailable(
                harness.data(), harness.candidate(), execution
            )
            changed = _observation(harness, ordinal=2)
            identity = registration_store.MemberIdentity(
                **{
                    **changed.identity.__dict__,
                    "canonical_root": "/fixture/root-1",
                    "git_toplevel": "/fixture/root-1",
                    "root_dev": 1,
                    "root_ino": 1,
                    "git_dir": "/fixture/git-1",
                    "git_dir_dev": 1,
                    "git_dir_ino": 1001,
                    "git_common_dir": "/fixture/common-1",
                    "git_common_dev": 1,
                    "git_common_ino": 2001,
                }
            )
            changed = registration_runtime.BasisObservation(
                **{**changed.__dict__, "identity": identity}
            )
            coordinator.ensure(_event(), changed)
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            coordinator.drive(ensured.member_id, helpers)
            pending = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(pending.member["phase"], "RESOLVED")
            self.assertIsNotNone(pending.member["pending_effect_id"])
            result = coordinator.drive(ensured.member_id, helpers)
            self.assertEqual(result.outcome, "SUCCESS")
            final = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(final.member["phase"], "RESOLVED")
            self.assertIsNone(final.member["pending_effect_id"])
            self.assertEqual(final.member["member_epoch"], 2)
        finally:
            harness.close()
            temporary.cleanup()

    def test_current_basis_supersedes_stale_resolved_pending_before_io(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            harness.store.mark_unavailable(
                harness.data(), harness.candidate(), execution
            )

            def changed(ordinal: int):
                observation = _observation(harness, ordinal=ordinal)
                identity = registration_store.MemberIdentity(
                    **{
                        **observation.identity.__dict__,
                        "canonical_root": "/fixture/root-1",
                        "git_toplevel": "/fixture/root-1",
                        "root_dev": 1,
                        "root_ino": 1,
                        "git_dir": "/fixture/git-1",
                        "git_dir_dev": 1,
                        "git_dir_ino": 1001,
                        "git_common_dir": "/fixture/common-1",
                        "git_common_dev": 1,
                        "git_common_ino": 2001,
                    }
                )
                return registration_runtime.BasisObservation(
                    **{**observation.__dict__, "identity": identity}
                )

            coordinator.ensure(_event(), changed(2))
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            coordinator.drive(ensured.member_id, helpers)
            resolved = harness.store.read_selected_authority(
                ensured.member_id
            )
            stale_pending = resolved.member["pending_effect_id"]
            self.assertIsNotNone(stale_pending)
            fresh = _observation(harness)
            coordinator.ensure(_event(), fresh)
            final = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(final.member["phase"], "REQUESTED")
            self.assertEqual(
                final.member["current_basis_hash"],
                fresh.identity.current_basis_hash,
            )
            self.assertEqual(final.member["member_epoch"], 3)
            stale = harness.connection.execute(
                "SELECT outcome_kind FROM registration_effect "
                "WHERE effect_id=?",
                (stale_pending,),
            ).fetchone()
            self.assertEqual(stale["outcome_kind"], "SUPERSEDED")
        finally:
            harness.close()
            temporary.cleanup()

    def test_resolved_basis_handoff_and_explicit_conflict_retry(self) -> None:
        for conflict in (False, True):
            with self.subTest(conflict=conflict):
                temporary, harness, coordinator = self._setup()
                try:
                    ensured = coordinator.ensure(
                        _event(), _observation(harness)
                    )
                    helpers = {
                        kind: FakeActionHelper()
                        for kind in registration_runtime.ACTION_KINDS
                    }
                    if conflict:
                        helpers[registration_runtime.ACTION_KINDS[0]] = (
                            registration_runtime.ConflictHelper()
                        )
                    result = coordinator.drive(ensured.member_id, helpers)
                    self.assertEqual(
                        result.outcome,
                        "LOGICAL_CONFLICT" if conflict else "SUCCESS",
                    )
                    changed = _observation(harness, ordinal=2)
                    identity = registration_store.MemberIdentity(
                        **{
                            **changed.identity.__dict__,
                            "canonical_root": "/fixture/root-1",
                            "git_toplevel": "/fixture/root-1",
                            "root_dev": 1,
                            "root_ino": 1,
                            "git_dir": "/fixture/git-1",
                            "git_dir_dev": 1,
                            "git_dir_ino": 1001,
                            "git_common_dir": "/fixture/common-1",
                            "git_common_dev": 1,
                            "git_common_ino": 2001,
                        }
                    )
                    changed = registration_runtime.BasisObservation(
                        **{**changed.__dict__, "identity": identity}
                    )
                    if conflict:
                        coordinator.retry_conflict(ensured.member_id, changed)
                    else:
                        coordinator.ensure(_event(), changed)
                    authority = harness.store.read_selected_authority(
                        ensured.member_id
                    )
                    self.assertEqual(authority.member["phase"], "REQUESTED")
                    self.assertEqual(authority.member["member_epoch"], 2)
                finally:
                    harness.close()
                    temporary.cleanup()

    def test_reboot_recovery_uses_typed_status_api(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            self.assertEqual(coordinator.recover_reboot("boot-a"), ())
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
            harness.sample_boot_id = "boot-b"
            recovered = coordinator.recover_reboot("boot-b")
            self.assertEqual(recovered, (ensured.member_id,))
            status = harness.store.read_selected_authority(
                ensured.member_id
            ).status
            self.assertEqual(status["schedule_boot_id"], "boot-b")
            self.assertEqual(status["backoff_ns"], 0)
        finally:
            harness.close()
            temporary.cleanup()

    def test_same_boot_dead_executor_uses_unavailable_then_reacquire(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            effect_id = execution.effect_id
            execution.close()
            coordinator.recover_same_boot_executor(ensured.member_id)
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertIsNone(authority.status["executor_token_hash"])
            self.assertEqual(authority.status["help_due"], 1)
            result = coordinator.drive(
                ensured.member_id,
                {
                    kind: FakeActionHelper()
                    for kind in registration_runtime.ACTION_KINDS
                },
            )
            self.assertEqual(result.effect_id, effect_id)
            self.assertEqual(result.outcome, "SUCCESS")
        finally:
            harness.close()
            temporary.cleanup()

    def test_blocked_dirty_member_has_no_timer_or_executor(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            identity = harness.identity()
            observation = registration_runtime.BasisObservation.from_identity(
                identity,
                request_kind="BLOCKED_DIRTY",
                workspace_roots_hash="01" * 32,
            )
            ensured = coordinator.ensure(_event(), observation)
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(
                authority.effect["request_kind"], "BLOCKED_DIRTY"
            )
            for field in (
                "schedule_boot_id",
                "observed_now_mono_ns",
                "next_due_mono_ns",
                "due_since_mono_ns",
                "attempt_count",
                "backoff_ns",
                "executor_token_hash",
            ):
                self.assertIsNone(authority.status[field])
            self.assertEqual(
                authority.status["reason_code"], "DIRTY_UNSUPPORTED"
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_service_task_never_persists_and_ordinary_tool_linearizes(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            observation = _observation(harness)
            collector = FakeObservationCollector(observation)
            inventory = registration_admission.ToolInventory(
                ordinary=frozenset({"shell"}),
                task_launch=frozenset({"Task", "subagent"}),
            )
            candidate = harness.candidate()
            admission = registration_admission.AdmissionController(
                inventory=inventory,
                collector=collector,
                store=registration_runtime.StoreAuthorityAdapter(
                    harness.store
                ),
                host_provider=lambda: registration_admission.HostEnvelope(
                    host_tick_current=True,
                    profile_hash=candidate.profile_hash,
                    projection_hash=candidate.hook_projection_hash,
                    inventory_hash=candidate.tool_inventory_hash,
                    storage_ready=True,
                    parser_ready=True,
                    serializer_ready=True,
                ),
                receipt_provider=lambda: (
                    registration_admission.DeploymentReceipt(
                        owner_mode="DIRECT",
                        deployment_scope="R2_DIRECT",
                        candidate_digest="99" * 32,
                        canonical_root_hash=None,
                        member_id=None,
                        owner_gate_digest="98" * 32,
                    )
                ),
                expected_candidate_digest="99" * 32,
            )
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            service = registration_runtime.RegistrationService(
                coordinator=coordinator,
                admission=admission,
                collector=collector,
                inventory=inventory,
                helpers=helpers,
            )
            payload = {
                "hook_event_name": "beforeShellExecution",
                "workspace_roots": ["/fixture/root-1"],
                "conversation_id": "conversation-1",
                "generation_id": "generation-1",
                "prompt": "PRIVATE_PROMPT_SENTINEL",
                "attachments": ["PRIVATE_ATTACHMENT_SENTINEL"],
            }
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            task = service.handle(payload, "Task")
            self.assertEqual(task.reason, "TASK_SUBAGENT_DENIED")
            self.assertEqual(collector.calls, 0)
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
            ordinary = service.handle(payload, "shell")
            self.assertTrue(ordinary.allowed)
            self.assertEqual(ordinary.reason, "READY")
            for suffix in ("", "-wal", "-shm"):
                path = Path(f"{harness.store.db_path}{suffix}")
                if path.exists():
                    data = path.read_bytes()
                    self.assertNotIn(b"PRIVATE_PROMPT_SENTINEL", data)
                    self.assertNotIn(b"PRIVATE_ATTACHMENT_SENTINEL", data)
        finally:
            harness.close()
            temporary.cleanup()

    def test_receipt_scope_preflight_blocks_all_registration_io(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            observation = _observation(harness)
            collector = FakeObservationCollector(observation)
            candidate = harness.candidate()
            inventory = registration_admission.ToolInventory(
                ordinary=frozenset({"shell"}),
                task_launch=frozenset({"Task"}),
            )
            admission = registration_admission.AdmissionController(
                inventory=inventory,
                collector=collector,
                store=registration_runtime.StoreAuthorityAdapter(
                    harness.store
                ),
                host_provider=lambda: registration_admission.HostEnvelope(
                    True,
                    candidate.profile_hash,
                    candidate.hook_projection_hash,
                    candidate.tool_inventory_hash,
                    True,
                    True,
                    True,
                ),
                receipt_provider=lambda: (
                    registration_admission.DeploymentReceipt(
                        "DIRECT",
                        "R1_CANARY",
                        "99" * 32,
                        "ff" * 32,
                        observation.basis_sample.member_id,
                        "98" * 32,
                    )
                ),
                expected_candidate_digest="99" * 32,
            )
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            service = registration_runtime.RegistrationService(
                coordinator=coordinator,
                admission=admission,
                collector=collector,
                inventory=inventory,
                helpers=helpers,
            )
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            decision = service.handle(
                {
                    "hook_event_name": "beforeShellExecution",
                    "workspace_roots": ["/fixture/root-1"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
                "shell",
            )
            self.assertEqual(decision.reason, "ROOT_UNSUPPORTED")
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
            self.assertEqual(
                sum(helper.inspect_count for helper in helpers.values()), 0
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_low_free_service_denies_with_zero_registration_write(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            collector = FakeObservationCollector(_observation(harness))
            inventory = registration_admission.ToolInventory(
                ordinary=frozenset({"shell"}),
                task_launch=frozenset({"Task"}),
            )
            service = registration_runtime.RegistrationService(
                coordinator=coordinator,
                admission=_admission_controller(harness, collector),
                collector=collector,
                inventory=inventory,
                helpers={},
            )
            harness.measured_free_bytes = (
                registration_store.FILESYSTEM_SAFETY_FLOOR
            )
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            decision = service.handle(
                {
                    "hook_event_name": "beforeShellExecution",
                    "workspace_roots": ["/fixture/root-1"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
                "shell",
            )
            self.assertEqual(decision.reason, "STORAGE_DEGRADED")
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_native_ioerr_never_manufactures_registration_success(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            collector = FakeObservationCollector(_observation(harness))
            service = registration_runtime.RegistrationService(
                coordinator=coordinator,
                admission=_admission_controller(harness, collector),
                collector=collector,
                inventory=registration_admission.ToolInventory(
                    ordinary=frozenset({"shell"}),
                    task_launch=frozenset({"Task"}),
                ),
                helpers={},
            )
            harness.inject_fault(
                "before_commit",
                registration_store.InjectedSQLiteFault(
                    sqlite3.SQLITE_IOERR
                ),
            )
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            decision = service.handle(
                {
                    "hook_event_name": "beforeShellExecution",
                    "workspace_roots": ["/fixture/root-1"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
                "shell",
            )
            self.assertEqual(decision.reason, "STORE_UNAVAILABLE")
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_helper_failure_marks_unavailable_and_service_denies(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            observation = _observation(harness)
            collector = FakeObservationCollector(observation)
            service = registration_runtime.RegistrationService(
                coordinator=coordinator,
                admission=_admission_controller(harness, collector),
                collector=collector,
                inventory=registration_admission.ToolInventory(
                    ordinary=frozenset({"shell"}),
                    task_launch=frozenset({"Task"}),
                ),
                helpers={
                    **{
                        kind: FakeActionHelper()
                        for kind in registration_runtime.ACTION_KINDS
                    },
                    registration_runtime.ACTION_KINDS[0]: ExplodingHelper(),
                },
            )
            decision = service.handle(
                {
                    "hook_event_name": "beforeShellExecution",
                    "workspace_roots": ["/fixture/root-1"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
                "shell",
            )
            self.assertEqual(decision.reason, "STORE_UNAVAILABLE")
            member_id = registration_runtime.derive_member_id(
                observation.identity
            )
            authority = harness.store.read_selected_authority(member_id)
            self.assertIsNone(authority.status["executor_token_hash"])
            self.assertEqual(authority.status["help_due"], 1)
            self.assertEqual(
                harness.store.table_count("registration_effect_action"), 0
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_failed_mark_falls_back_to_exact_dead_executor_takeover(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            harness.inject_fault(
                "before_insert:registration_operation_audit",
                RuntimeError("first unavailable write failed"),
            )
            helpers = {
                **{
                    kind: FakeActionHelper()
                    for kind in registration_runtime.ACTION_KINDS
                },
                registration_runtime.ACTION_KINDS[0]: ExplodingHelper(),
            }
            with self.assertRaises(OSError):
                coordinator.run_execution(execution, helpers)
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertIsNone(authority.status["executor_token_hash"])
            self.assertEqual(authority.status["help_due"], 1)
            self.assertFalse(execution.held)
        finally:
            harness.close()
            temporary.cleanup()

    def test_root_mismatch_is_bounded_denial_not_exception(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            collector = FakeObservationCollector(
                _observation(harness, ordinal=2)
            )
            service = registration_runtime.RegistrationService(
                coordinator=coordinator,
                admission=_admission_controller(harness, collector),
                collector=collector,
                inventory=registration_admission.ToolInventory(
                    ordinary=frozenset({"shell"}),
                    task_launch=frozenset({"Task"}),
                ),
                helpers={},
            )
            decision = service.handle(
                {
                    "hook_event_name": "beforeShellExecution",
                    "workspace_roots": ["/fixture/root-1"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
                "shell",
            )
            self.assertEqual(decision.reason, "ROOT_UNSUPPORTED")
        finally:
            harness.close()
            temporary.cleanup()

    def test_unrelated_member_commit_does_not_deny_green_member(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            first_observation = _observation(harness, ordinal=1)
            first = coordinator.ensure(_event(), first_observation)
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            coordinator.drive(first.member_id, helpers)
            second_event = _event("/fixture/root-2")
            second_observation = _observation(harness, ordinal=2)
            second = coordinator.ensure(second_event, second_observation)

            class ChurnCollector:
                def __init__(self):
                    self.calls = 0

                def collect(self, _event_value):
                    self.calls += 1
                    if self.calls == 2:
                        changed = _observation(harness, ordinal=3)
                        identity = registration_store.MemberIdentity(
                            **{
                                **changed.identity.__dict__,
                                "canonical_root": "/fixture/root-2",
                                "git_toplevel": "/fixture/root-2",
                                "root_dev": 1,
                                "root_ino": 2,
                                "git_dir": "/fixture/git-2",
                                "git_dir_dev": 1,
                                "git_dir_ino": 1002,
                                "git_common_dir": "/fixture/common-2",
                                "git_common_dev": 1,
                                "git_common_ino": 2002,
                            }
                        )
                        changed = registration_runtime.BasisObservation(
                            **{**changed.__dict__, "identity": identity}
                        )
                        coordinator.ensure(second_event, changed)
                    return first_observation.basis_sample

            candidate = harness.candidate()
            controller = registration_admission.AdmissionController(
                inventory=registration_admission.ToolInventory(
                    ordinary=frozenset({"shell"}),
                    task_launch=frozenset({"Task"}),
                ),
                collector=ChurnCollector(),
                store=registration_runtime.StoreAuthorityAdapter(
                    harness.store
                ),
                host_provider=lambda: registration_admission.HostEnvelope(
                    True,
                    candidate.profile_hash,
                    candidate.hook_projection_hash,
                    candidate.tool_inventory_hash,
                    True,
                    True,
                    True,
                ),
                receipt_provider=lambda: (
                    registration_admission.DeploymentReceipt(
                        "DIRECT",
                        "R2_DIRECT",
                        "99" * 32,
                        None,
                        None,
                        "98" * 32,
                    )
                ),
                expected_candidate_digest="99" * 32,
            )
            decision = controller.admit(
                {
                    "hook_event_name": "beforeShellExecution",
                    "workspace_roots": ["/fixture/root-1"],
                    "conversation_id": "conversation-1",
                    "generation_id": "generation-1",
                },
                "shell",
                member_id=first.member_id,
                episode_id=first.episode_id,
            )
            self.assertTrue(decision.allowed)
            self.assertNotEqual(first.member_id, second.member_id)
        finally:
            harness.close()
            temporary.cleanup()


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class FairnessSchedulerTest(unittest.TestCase):
    def test_closed_tick_budget_constants(self) -> None:
        self.assertEqual(registration_runtime.TICK_LANES, 8)
        self.assertEqual(
            registration_runtime.TICK_INTERVAL_NS, 15_000_000_000
        )
        self.assertEqual(
            registration_runtime.HELPER_DEADLINE_SECONDS, 2.0
        )
        self.assertEqual(
            registration_runtime.SERVICE_BUDGET_SECONDS, 5.0
        )

    def test_mutating_open_requires_yield_resolver_before_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                opened = []
                with self.assertRaises(ValueError):
                    scheduler.tick_phased(
                        boot_id="boot-a",
                        now_mono_ns=0,
                        open_attempt=lambda due: opened.append(due),
                        run_helper=_identity_payload,
                        commit_result=lambda _due, _token, _result: True,
                    )
                self.assertEqual(opened, [])

    def test_bare_mutating_token_never_enters_spawn_helper_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=lambda due: coordinator.authorize_due(
                        due,
                        current_basis_hash=due.current_basis_hash,
                    ),
                    run_helper=_busy_forever,
                    commit_result=lambda _due, _token, _result: True,
                    yield_result=lambda _due, execution: (
                        harness.store.mark_unavailable(
                            harness.data(), candidate, execution
                        )
                        is not None
                    ),
                )
                self.assertFalse(receipt.fairness_suspended)
                self.assertEqual(len(receipt.missed_member_ids), 1)
                authority = harness.store.read_selected_authority(
                    receipt.missed_member_ids[0]
                )
                self.assertIsNone(authority.status["executor_token_hash"])

    def test_member_execution_payload_overrides_nonmutating_misconfiguration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=lambda due: (
                        coordinator.authorize_due(
                            due,
                            current_basis_hash=due.current_basis_hash,
                        )
                    ),
                    run_helper=_busy_forever,
                    commit_result=lambda _due, _token, _result: True,
                    open_mutates_authority=False,
                )
                self.assertFalse(receipt.fairness_suspended)
                self.assertEqual(len(receipt.missed_member_ids), 1)
                authority = harness.store.read_selected_authority(
                    receipt.missed_member_ids[0]
                )
                self.assertIsNone(authority.status["executor_token_hash"])

    def test_explicit_execution_helper_payload_is_diverted_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )

                def miswired(due):
                    execution = coordinator.authorize_due(
                        due,
                        current_basis_hash=due.current_basis_hash,
                    )
                    return registration_runtime.LaneAuthorization(
                        execution, execution
                    )

                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=miswired,
                    run_helper=_busy_forever,
                    commit_result=lambda _due, _token, _result: True,
                    yield_result=lambda _due, execution: (
                        harness.store.mark_unavailable(
                            harness.data(), candidate, execution
                        )
                        is not None
                    ),
                )
                self.assertFalse(receipt.fairness_suspended)
                self.assertEqual(len(receipt.missed_member_ids), 1)
                authority = harness.store.read_selected_authority(
                    receipt.missed_member_ids[0]
                )
                self.assertIsNone(authority.status["executor_token_hash"])

    def test_more_than_eight_continue_and_selected_misses_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                for ordinal in range(1, 11):
                    harness.store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                first = scheduler.tick(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    attempt=_return_false,
                )
                self.assertEqual(len(first.selected_member_ids), 8)
                self.assertEqual(len(first.snapshot_token), 64)
                self.assertEqual(
                    [member for member, _hash in first.selected_status_hashes],
                    list(first.selected_member_ids),
                )
                self.assertEqual(first.missed_member_ids, first.selected_member_ids)
                self.assertEqual(
                    {member for member, reason in first.member_reasons},
                    set(first.selected_member_ids),
                )
                self.assertEqual(
                    {reason for _member, reason in first.member_reasons},
                    {"HOST_STARVED"},
                )
                self.assertFalse(first.fairness_suspended)
                second = scheduler.tick(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    attempt=_return_true,
                )
                self.assertEqual(len(second.selected_member_ids), 2)
                self.assertTrue(
                    set(first.selected_member_ids).isdisjoint(
                        second.selected_member_ids
                    )
                )

    def test_open_and_commit_slices_are_serial_in_selected_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                for ordinal in range(1, 4):
                    harness.store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                opened = []
                committed = []

                def open_attempt(due):
                    opened.append(due.member_id)
                    return due.member_id

                def commit_result(due, _token, result):
                    committed.append(due.member_id)
                    return result == due.member_id

                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=open_attempt,
                    run_helper=_identity_payload,
                    commit_result=commit_result,
                    open_mutates_authority=False,
                )
                self.assertEqual(opened, list(receipt.selected_member_ids))
                self.assertEqual(committed, list(receipt.selected_member_ids))
                self.assertEqual(receipt.missed_member_ids, ())

    def test_failed_schedule_write_suspends_fairness_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                for ordinal in range(1, 4):
                    harness.store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                harness.inject_fault(
                    "before_insert:registration_operation_audit",
                    RuntimeError("schedule unavailable"),
                )
                receipt = scheduler.tick(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    attempt=_return_false,
                )
                self.assertTrue(receipt.fairness_suspended)
                self.assertEqual(len(receipt.selected_member_ids), 3)
                scheduled = harness.connection.execute(
                    "SELECT COUNT(*) FROM registration_operation_audit "
                    "WHERE operation_kind='SCHEDULE_STATUS'"
                ).fetchone()[0]
                self.assertEqual(scheduled, 2)

    def test_opened_lane_failure_resolves_through_mark_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                def authorize(due):
                    return registration_runtime.LaneAuthorization(
                        False,
                        coordinator.authorize_due(
                            due,
                            current_basis_hash=due.current_basis_hash,
                        ),
                    )
                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=authorize,
                    run_helper=_identity_payload,
                    commit_result=lambda _due, _token, _result: False,
                    yield_result=lambda _due, execution: (
                        harness.store.mark_unavailable(
                            harness.data(), candidate, execution
                        )
                        is not None
                    ),
                )
                self.assertFalse(receipt.fairness_suspended)
                self.assertEqual(len(receipt.missed_member_ids), 1)
                member_id = receipt.missed_member_ids[0]
                authority = harness.store.read_selected_authority(member_id)
                self.assertIsNone(authority.status["executor_token_hash"])
                self.assertEqual(authority.status["help_due"], 1)

    def test_slow_committed_open_still_yields_executor_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )

                def slow_authorize(due):
                    execution = coordinator.authorize_due(
                        due,
                        current_basis_hash=due.current_basis_hash,
                    )
                    deadline = (
                        time.monotonic()
                        + registration_runtime.OPEN_SLICE_SECONDS
                        + 0.01
                    )
                    while time.monotonic() < deadline:
                        pass
                    return registration_runtime.LaneAuthorization(
                        False, execution
                    )

                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=slow_authorize,
                    run_helper=_identity_payload,
                    commit_result=lambda _due, _token, _result: False,
                    yield_result=lambda _due, execution: (
                        harness.store.mark_unavailable(
                            harness.data(), candidate, execution
                        )
                        is not None
                    ),
                )
                self.assertFalse(receipt.fairness_suspended)
                self.assertEqual(len(receipt.missed_member_ids), 1)
                authority = harness.store.read_selected_authority(
                    receipt.missed_member_ids[0]
                )
                self.assertIsNone(authority.status["executor_token_hash"])
                self.assertEqual(authority.status["help_due"], 1)

    def test_failed_yield_callback_uses_dead_executor_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )

                def authorize(due):
                    return registration_runtime.LaneAuthorization(
                        False,
                        coordinator.authorize_due(
                            due,
                            current_basis_hash=due.current_basis_hash,
                        ),
                    )

                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=authorize,
                    run_helper=_identity_payload,
                    commit_result=lambda _due, _token, _result: False,
                    yield_result=lambda _due, _execution: False,
                )
                self.assertFalse(receipt.fairness_suspended)
                authority = harness.store.read_selected_authority(
                    receipt.missed_member_ids[0]
                )
                self.assertIsNone(authority.status["executor_token_hash"])
                self.assertEqual(authority.status["help_due"], 1)

    def test_failed_dead_takeover_enters_explicit_recovery_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )

                def authorize(due):
                    return registration_runtime.LaneAuthorization(
                        False,
                        coordinator.authorize_due(
                            due,
                            current_basis_hash=due.current_basis_hash,
                        ),
                    )

                def failed_yield(_due, _execution):
                    harness.inject_fault(
                        "before_insert:registration_operation_audit",
                        RuntimeError("store unavailable"),
                    )
                    return False

                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=authorize,
                    run_helper=_identity_payload,
                    commit_result=lambda _due, _token, _result: False,
                    yield_result=failed_yield,
                )
                self.assertTrue(receipt.fairness_suspended)
                self.assertEqual(
                    receipt.recovery_member_ids,
                    receipt.missed_member_ids,
                )
                recovery = scheduler.recover_suspended(receipt)
                self.assertEqual(
                    recovery.recovered_member_ids,
                    receipt.recovery_member_ids,
                )
                self.assertEqual(recovery.unavailable_member_ids, ())
                authority = harness.store.read_selected_authority(
                    receipt.recovery_member_ids[0]
                )
                self.assertIsNone(authority.status["executor_token_hash"])

    def test_tick_authorizes_reacquire_for_help_due_inflight_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                execution = coordinator.open_due(
                    registration_runtime.derive_member_id(harness.identity())
                )
                harness.store.mark_unavailable(
                    harness.data(), candidate, execution
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                def authorize(due):
                    return registration_runtime.LaneAuthorization(
                        False,
                        coordinator.authorize_due(
                            due,
                            current_basis_hash=due.current_basis_hash,
                        ),
                    )
                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=authorize,
                    run_helper=_identity_payload,
                    commit_result=lambda _due, _token, _result: False,
                    yield_result=lambda _due, reacquired: (
                        harness.store.mark_unavailable(
                            harness.data(), candidate, reacquired
                        )
                        is not None
                    ),
                )
                self.assertFalse(receipt.fairness_suspended)
                self.assertEqual(len(receipt.missed_member_ids), 1)
                reacquires = harness.connection.execute(
                    "SELECT COUNT(*) FROM registration_operation_audit "
                    "WHERE operation_kind='REACQUIRE_EFFECT'"
                ).fetchone()[0]
                self.assertEqual(reacquires, 1)

    def test_tick_rejects_stale_fresh_basis_before_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                coordinator = registration_runtime.RegistrationCoordinator(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                due = harness.store.list_due_candidates(
                    boot_id="boot-a", now_mono_ns=100
                )[0]
                before = harness.store.table_count(
                    "registration_operation_audit"
                )
                with self.assertRaises(registration_store.StaleAuthority):
                    coordinator.authorize_due(
                        due, current_basis_hash="ff" * 32
                    )
                self.assertEqual(
                    harness.store.table_count(
                        "registration_operation_audit"
                    ),
                    before,
                )

    def test_tick_handoffs_resolved_pending_and_opens_successor(self) -> None:
        temporary, harness, coordinator = (
            RegistrationCoordinatorTest()._setup()
        )
        try:
            ensured = coordinator.ensure(_event(), _observation(harness))
            execution = coordinator.open_due(ensured.member_id)
            harness.store.mark_unavailable(
                harness.data(), harness.candidate(), execution
            )
            changed = _observation(harness, ordinal=2)
            identity = registration_store.MemberIdentity(
                **{
                    **changed.identity.__dict__,
                    "canonical_root": "/fixture/root-1",
                    "git_toplevel": "/fixture/root-1",
                    "root_dev": 1,
                    "root_ino": 1,
                    "git_dir": "/fixture/git-1",
                    "git_dir_dev": 1,
                    "git_dir_ino": 1001,
                    "git_common_dir": "/fixture/common-1",
                    "git_common_dev": 1,
                    "git_common_ino": 2001,
                }
            )
            changed = registration_runtime.BasisObservation(
                **{**changed.__dict__, "identity": identity}
            )
            coordinator.ensure(_event(), changed)
            coordinator.drive(
                ensured.member_id,
                {
                    kind: FakeActionHelper()
                    for kind in registration_runtime.ACTION_KINDS
                },
            )
            resolved = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(resolved.member["phase"], "RESOLVED")
            self.assertIsNotNone(resolved.member["pending_effect_id"])
            scheduler = registration_runtime.FairnessScheduler(
                store=harness.store,
                data=harness.data(),
                candidate=harness.candidate(),
            )

            def authorize(due):
                return registration_runtime.LaneAuthorization(
                    False,
                    coordinator.authorize_due(
                        due,
                        current_basis_hash=due.pending_basis_hash,
                    ),
                )

            receipt = scheduler.tick_phased(
                boot_id="boot-a",
                now_mono_ns=100,
                open_attempt=authorize,
                run_helper=_identity_payload,
                commit_result=lambda _due, _token, _result: False,
                yield_result=lambda _due, successor_execution: (
                    harness.store.mark_unavailable(
                        harness.data(),
                        harness.candidate(),
                        successor_execution,
                    )
                    is not None
                ),
            )
            self.assertFalse(receipt.fairness_suspended)
            after = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(after.member["phase"], "EFFECT_IN_FLIGHT")
            self.assertIsNone(after.member["pending_effect_id"])
            self.assertEqual(after.status["help_due"], 1)
        finally:
            harness.close()
            temporary.cleanup()

    def test_hung_attempt_is_killed_with_no_worker_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                harness.store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                before = {child.pid for child in multiprocessing.active_children()}
                started = time.monotonic()
                receipt = scheduler.tick(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    attempt=_busy_forever,
                )
                self.assertLess(
                    time.monotonic() - started,
                    registration_runtime.SERVICE_BUDGET_SECONDS,
                )
                self.assertEqual(len(receipt.missed_member_ids), 1)
                self.assertEqual(
                    {child.pid for child in multiprocessing.active_children()},
                    before,
                )


if __name__ == "__main__":
    unittest.main()
