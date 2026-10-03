from __future__ import annotations

import hashlib
import tempfile
import sqlite3
import multiprocessing
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import (
    registration_admission,
    registration_lock,
    registration_runtime,
    registration_store,
)
from engine.tests.registration_harness import RegistrationHarness


def _event(root: str = "/fixture/root-1"):
    return registration_admission.RegistrationEvent(
        workspace_roots=(root,),
        conversation_id="conversation-1",
        generation_id="generation-1",
        source_contract="cursor-hook/v1",
        source_event="beforeShellExecution",
    )


def _fixed_observation(
    observation: registration_runtime.BasisObservation,
    *,
    identity: registration_store.MemberIdentity | None = None,
) -> registration_runtime.BasisObservation:
    values = {
        **observation.__dict__,
        "identity": identity or observation.identity,
    }
    values.pop("fresh_provider", None)
    holder = {}
    fixed = registration_runtime.BasisObservation(
        **values,
        fresh_provider=lambda: holder["value"],
    )
    holder["value"] = fixed
    return fixed


def _observation(
    harness: RegistrationHarness, ordinal: int = 1
) -> registration_runtime.BasisObservation:
    identity = harness.identity(ordinal=ordinal)
    return _fixed_observation(
        registration_runtime.BasisObservation.from_identity(
            identity,
            request_kind="CLEAN_ELIGIBLE",
            workspace_roots_hash=f"{ordinal:064x}",
        )
    )


def _same_member_observation(
    harness: RegistrationHarness, ordinal: int
) -> registration_runtime.BasisObservation:
    stale = _observation(harness)
    observed = _observation(harness, ordinal=ordinal)
    identity = registration_store.MemberIdentity(
        **{
            **observed.identity.__dict__,
            "canonical_root": stale.identity.canonical_root,
            "git_toplevel": stale.identity.git_toplevel,
            "root_dev": stale.identity.root_dev,
            "root_ino": stale.identity.root_ino,
            "git_dir": stale.identity.git_dir,
            "git_dir_dev": stale.identity.git_dir_dev,
            "git_dir_ino": stale.identity.git_dir_ino,
            "git_common_dir": stale.identity.git_common_dir,
            "git_common_dev": stale.identity.git_common_dev,
            "git_common_ino": stale.identity.git_common_ino,
        }
    )
    return _fixed_observation(observed, identity=identity)


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


def _overlap_worker(payload):
    active, maximum, gate = payload
    with active.get_lock():
        active.value += 1
        maximum.value = max(maximum.value, active.value)
        if active.value == registration_runtime.TICK_LANES:
            gate.set()
    if not gate.wait(5):
        raise RuntimeError("concurrent lane gate timed out")
    with active.get_lock():
        active.value -= 1
    return True


def _mutating_overlap_worker(payload):
    db_path, due, active, maximum, gate = payload
    with RegistrationHarness.open(
        Path(db_path), measured_free_bytes=4 * 1024**3
    ) as harness:
        harness._mono = 1_000
        execution = harness.store.open_effect(
            harness.data(),
            harness.candidate(),
            member_id=due.member_id,
            expected_member_hash=due.member_tuple_hash,
            expected_effect_hash=due.effect_tuple_hash,
            expected_status_hash=due.status_hash,
            operation_id=hashlib.sha256(
                f"open:{due.member_id}".encode("ascii")
            ).hexdigest(),
        ).execution
        with active.get_lock():
            active.value += 1
            maximum.value = max(maximum.value, active.value)
            if active.value == registration_runtime.TICK_LANES:
                gate.set()
        if not gate.wait(10):
            raise RuntimeError("mutating lane overlap timed out")
        harness.store.mark_unavailable(
            harness.data(),
            harness.candidate(),
            execution,
            operation_id=hashlib.sha256(
                f"mark:{due.member_id}".encode("ascii")
            ).hexdigest(),
        )
        with active.get_lock():
            active.value -= 1
        return due.member_id


def _ensure_process(db_path, started, release, results) -> None:
    try:
        with RegistrationHarness.open(
            Path(db_path), measured_free_bytes=2 * 1024**3
        ) as harness:
            coordinator = registration_runtime.RegistrationCoordinator(
                store=harness.store,
                data=harness.data(),
                candidate=harness.candidate(),
            )
            observation = _observation(harness)
            started.put(True)
            if not release.wait(10):
                raise RuntimeError("duplicate ensure release timed out")
            handle = coordinator.ensure(
                _event(),
                observation,
                fresh_provider=lambda: _observation(harness),
            )
            results.put(("ok", handle.member_id, handle.episode_id))
    except BaseException as error:
        results.put(("error", type(error).__name__, str(error)))


def _fresh_interleaving_process(
    db_path,
    stale_ordinal,
    shared_ordinal,
    attempting,
    provider_entered,
    release_provider,
    results,
) -> None:
    try:
        with RegistrationHarness.open(
            Path(db_path), measured_free_bytes=2 * 1024**3
        ) as harness:
            coordinator = registration_runtime.RegistrationCoordinator(
                store=harness.store,
                data=harness.data(),
                candidate=harness.candidate(),
            )
            stale = (
                _observation(harness)
                if stale_ordinal == 1
                else _same_member_observation(harness, stale_ordinal)
            )
            attempting.set()

            def provider():
                provider_entered.set()
                if (
                    release_provider is not None
                    and not release_provider.wait(10)
                ):
                    raise RuntimeError("fresh provider release timed out")
                return _same_member_observation(
                    harness,
                    int(shared_ordinal.value),
                )

            handle = coordinator.ensure(
                _event(),
                stale,
                fresh_provider=provider,
            )
            authority = harness.store.read_selected_authority(
                handle.member_id
            )
            results.put(
                (
                    "ok",
                    handle.member_id,
                    authority.member["current_basis_hash"],
                )
            )
    except BaseException as error:
        results.put(("error", type(error).__name__, str(error)))


def _hold_executor_process(db_path, ready, release, results) -> None:
    try:
        with RegistrationHarness.open(
            Path(db_path), measured_free_bytes=2 * 1024**3
        ) as harness:
            member_id = registration_runtime.derive_member_id(
                harness.identity()
            )
            authority = harness.store.read_selected_authority(member_id)
            execution = harness.store.open_effect(
                harness.data(),
                harness.candidate(),
                member_id=member_id,
                expected_member_hash=authority.member["member_tuple_hash"],
                expected_effect_hash=authority.effect["request_tuple_hash"],
                expected_status_hash=authority.status["status_hash"],
            ).execution
            ready.set()
            if not release.wait(10):
                raise RuntimeError("executor release timed out")
            execution.close()
            results.put(("ok", member_id))
    except BaseException as error:
        results.put(("error", type(error).__name__, str(error)))


def _hold_grant_process(db_path, mode, granted, release) -> None:
    try:
        with RegistrationHarness.open(
            Path(db_path), measured_free_bytes=2 * 1024**3
        ) as harness:
            harness._mono = 1_000
            member_id = registration_runtime.derive_member_id(
                harness.identity()
            )
            authority = harness.store.read_selected_authority(member_id)
            if mode == "open":
                execution = harness.store.open_effect(
                    harness.data(),
                    harness.candidate(),
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    operation_id=hashlib.sha256(
                        f"grant:open:{member_id}".encode("ascii")
                    ).hexdigest(),
                ).execution
            elif mode == "reacquire":
                execution = harness.store.reacquire_effect(
                    harness.data(),
                    harness.candidate(),
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    operation_id=hashlib.sha256(
                        f"grant:reacquire:{member_id}".encode("ascii")
                    ).hexdigest(),
                ).execution
            else:
                raise ValueError("unknown grant mode")
            granted.put(("ok", execution.member_id))
            if not release.wait(30):
                raise RuntimeError("grant holder release timed out")
            execution.close()
    except BaseException as error:
        granted.put(("error", type(error).__name__, str(error)))


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
            status = harness.store.read_selected_authority(
                ensured.member_id
            ).status
            harness.store.mark_dead_executor_unavailable(
                harness.data(),
                harness.candidate(),
                member_id=ensured.member_id,
                expected_status_hash=status["status_hash"],
            )
            harness.store.advance_generation(
                harness.control(),
                harness.candidate(),
                quiescence_proof_hash="bb" * 32,
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
                return _fixed_observation(observation, identity=identity)

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
            ensured = coordinator.ensure(
                _event(),
                observation,
                fresh_provider=lambda: observation,
            )
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
            changed = _fixed_observation(
                changed,
                identity=registration_store.MemberIdentity(
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
                return _fixed_observation(observation, identity=identity)

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
            changed = _fixed_observation(changed, identity=identity)
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
            result = coordinator.drive(
                ensured.member_id,
                helpers,
                fresh_provider=lambda: changed,
            )
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
                return _fixed_observation(observation, identity=identity)

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
                    changed = _fixed_observation(
                        changed, identity=identity
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

    def test_ensure_collects_fresh_basis_inside_exact_member_scope(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            stale = _observation(harness)
            fresh = _same_member_observation(harness, 2)
            member_id = registration_runtime.derive_member_id(stale.identity)
            observed_locks = []

            def provider():
                observed_locks.append(
                    registration_lock._held()["member"]
                )
                return fresh

            handle = coordinator.ensure(
                _event(),
                stale,
                fresh_provider=provider,
            )
            self.assertEqual(handle.member_id, member_id)
            self.assertEqual(
                observed_locks,
                [f"member-{member_id}.lock"],
            )
            authority = harness.store.read_selected_authority(member_id)
            self.assertEqual(
                authority.member["current_basis_hash"],
                fresh.identity.current_basis_hash,
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_captured_stale_observation_cannot_regress_newer_basis(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            stale = _observation(harness)
            fresh = _same_member_observation(harness, 2)
            ensured = coordinator.ensure(
                _event(), stale, fresh_provider=lambda: stale
            )
            coordinator.ensure(
                _event(), stale, fresh_provider=lambda: fresh
            )
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            captured = registration_runtime.BasisObservation(
                **{**stale.__dict__, "fresh_provider": None}
            )
            with self.assertRaises(registration_store.StaleAuthority):
                coordinator.ensure(_event(), captured)
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(
                authority.member["current_basis_hash"],
                fresh.identity.current_basis_hash,
            )
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_old_new_observations_converge_to_under_lock_fresh_basis(self) -> None:
        context = multiprocessing.get_context("spawn")
        for order in ((1, 2), (2, 1)):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    candidate = harness.candidate()
                    harness.store.bootstrap(harness.control(), candidate)
                    harness.store.activate(harness.control(), candidate)
                shared_ordinal = context.Value("i", 1)
                first_attempting = context.Event()
                first_entered = context.Event()
                release_first = context.Event()
                second_attempting = context.Event()
                second_entered = context.Event()
                results = context.Queue()
                first = context.Process(
                    target=_fresh_interleaving_process,
                    args=(
                        str(db),
                        order[0],
                        shared_ordinal,
                        first_attempting,
                        first_entered,
                        release_first,
                        results,
                    ),
                )
                second = context.Process(
                    target=_fresh_interleaving_process,
                    args=(
                        str(db),
                        order[1],
                        shared_ordinal,
                        second_attempting,
                        second_entered,
                        None,
                        results,
                    ),
                )
                first.start()
                self.assertTrue(first_entered.wait(10))
                second.start()
                self.assertTrue(second_attempting.wait(10))
                self.assertFalse(second_entered.wait(0.1))
                shared_ordinal.value = 2
                release_first.set()
                first.join(20)
                second.join(20)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                observed = [
                    results.get(timeout=5),
                    results.get(timeout=5),
                ]
                self.assertTrue(
                    all(item[0] == "ok" for item in observed),
                    observed,
                )
                self.assertEqual(len({item[1] for item in observed}), 1)
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    expected = _same_member_observation(
                        harness, 2
                    ).identity.current_basis_hash
                    authority = harness.store.read_selected_authority(
                        observed[0][1]
                    )
                    self.assertEqual(
                        {item[2] for item in observed},
                        {expected},
                    )
                    self.assertEqual(
                        authority.member["current_basis_hash"],
                        expected,
                    )

    def test_duplicate_ensure_races_converge_at_2_8_32_processes(self) -> None:
        context = multiprocessing.get_context("spawn")
        for process_count in (2, 8, 32):
            with self.subTest(process_count=process_count):
                with tempfile.TemporaryDirectory() as tmp:
                    db = (
                        Path(tmp)
                        / "state"
                        / "registration-v1"
                        / "registration.db"
                    )
                    with RegistrationHarness.open(
                        db, measured_free_bytes=4 * 1024**3
                    ) as harness:
                        candidate = harness.candidate()
                        harness.store.bootstrap(
                            harness.control(), candidate
                        )
                        harness.store.activate(
                            harness.control(), candidate
                        )
                        before = harness.store.table_count(
                            "registration_operation_audit"
                        )
                    started = context.Queue()
                    release = context.Event()
                    results = context.Queue()
                    processes = [
                        context.Process(
                            target=_ensure_process,
                            args=(
                                str(db),
                                started,
                                release,
                                results,
                            ),
                        )
                        for _ in range(process_count)
                    ]
                    for process in processes:
                        process.start()
                    for _ in processes:
                        self.assertTrue(started.get(timeout=10))
                    release.set()
                    for process in processes:
                        process.join(30)
                        self.assertFalse(process.is_alive())
                    observed = [
                        results.get(timeout=5) for _ in processes
                    ]
                    self.assertTrue(
                        all(item[0] == "ok" for item in observed),
                        observed,
                    )
                    self.assertEqual(
                        len({item[1:] for item in observed}),
                        1,
                    )
                    with RegistrationHarness.open(
                        db, measured_free_bytes=4 * 1024**3
                    ) as harness:
                        self.assertEqual(
                            harness.store.table_count(
                                "registration_member"
                            ),
                            1,
                        )
                        self.assertEqual(
                            harness.store.table_count(
                                "registration_episode"
                            ),
                            1,
                        )
                        self.assertEqual(
                            harness.store.table_count(
                                "registration_operation_audit"
                            ),
                            before + 2,
                        )

    def test_recovery_exhaustion_maps_to_containment_unavailable(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(
                _event(),
                _observation(harness),
                fresh_provider=lambda: _observation(harness),
            )
            execution = coordinator.open_due(ensured.member_id)
            for _ in range(3):
                marked = harness.store.mark_unavailable(
                    harness.data(), harness.candidate(), execution
                )
                self.assertIsInstance(
                    marked, registration_store.OperationResult
                )
                authority = harness.store.read_selected_authority(
                    ensured.member_id
                )
                execution = harness.store.reacquire_effect(
                    harness.data(),
                    harness.candidate(),
                    member_id=ensured.member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                ).execution
            with self.assertRaises(
                registration_runtime.RecoveryContainmentUnavailable
            ) as captured:
                coordinator.run_execution(
                    execution,
                    {
                        registration_runtime.ACTION_KINDS[
                            0
                        ]: registration_runtime.UnavailableHelper()
                    },
                )
            self.assertFalse(execution.held)
            self.assertEqual(
                captured.exception.reason,
                "CONTAINMENT_UNAVAILABLE",
            )
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

    def test_same_boot_cursor_missing_stale_current_wrap_and_boundary(self) -> None:
        candidates = tuple(
            registration_store.SameBootCandidate(
                member_id=f"{ordinal:064x}",
                status_hash=f"{100 + ordinal:064x}",
                executor_token_hash=f"{200 + ordinal:064x}",
                executor_generation=2,
            )
            for ordinal in range(1, 11)
        )
        snapshot = registration_store.SameBootSnapshot(
            boot_id="boot-a",
            protocol_seq=7,
            protocol_hash="77" * 32,
            candidates=candidates,
        )
        snapshot_hash = registration_runtime.same_boot_snapshot_hash(
            snapshot
        )
        expected = hashlib.sha256(
            b"awa-registration-same-boot-snapshot/v1\0"
            + (
                '{"boot_id":"boot-a","candidates":['
                + ",".join(
                    (
                        '{"executor_generation":"2","executor_token_hash":"'
                        + candidate.executor_token_hash
                        + '","member_id":"'
                        + candidate.member_id
                        + '","status_hash":"'
                        + candidate.status_hash
                        + '"}'
                    )
                    for candidate in candidates
                )
                + '],"protocol_hash":"'
                + snapshot.protocol_hash
                + '","protocol_seq":"7","schema":'
                '"awa-registration-same-boot-snapshot/v1"}'
            ).encode("ascii")
        ).hexdigest()
        self.assertEqual(snapshot_hash, expected)

        missing = registration_runtime.select_same_boot_batch(
            snapshot, None
        )
        self.assertEqual(missing.candidates, candidates[:8])
        self.assertFalse(missing.wrapped)
        current = registration_runtime.SameBootCursor(
            boot_id="boot-a",
            protocol_seq=7,
            protocol_hash=snapshot.protocol_hash,
            selection_snapshot_hash=snapshot_hash,
            last_member_id=candidates[7].member_id,
            last_pre_status_hash=candidates[7].status_hash,
            last_post_status_hash=candidates[7].status_hash,
            outcome="BUSY_LIVE",
            batch_count=8,
            wrapped=False,
        )
        continued = registration_runtime.select_same_boot_batch(
            snapshot, current
        )
        self.assertEqual(continued.candidates, candidates[8:])
        stale = registration_runtime.SameBootCursor(
            **{**current.__dict__, "protocol_hash": "88" * 32}
        )
        self.assertEqual(
            registration_runtime.select_same_boot_batch(
                snapshot, stale
            ).candidates,
            candidates[:8],
        )
        at_end = registration_runtime.SameBootCursor(
            **{
                **current.__dict__,
                "last_member_id": candidates[-1].member_id,
                "last_pre_status_hash": candidates[-1].status_hash,
                "last_post_status_hash": candidates[-1].status_hash,
                "batch_count": 2,
            }
        )
        wrapped = registration_runtime.select_same_boot_batch(
            snapshot, at_end
        )
        self.assertEqual(wrapped.candidates, candidates[:8])
        self.assertTrue(wrapped.wrapped)
        completed = registration_runtime.select_same_boot_batch(
            snapshot,
            registration_runtime.SameBootCursor(
                **{**at_end.__dict__, "wrapped": True}
            ),
        )
        self.assertEqual(completed.candidates, ())

        without_last = registration_store.SameBootSnapshot(
            boot_id=snapshot.boot_id,
            protocol_seq=snapshot.protocol_seq,
            protocol_hash=snapshot.protocol_hash,
            candidates=candidates[:2] + candidates[8:],
        )
        absent_boundary = registration_runtime.SameBootCursor(
            **{
                **current.__dict__,
                "outcome": "NO_LONGER_CANDIDATE",
            }
        )
        self.assertEqual(
            registration_runtime.select_same_boot_batch(
                without_last, absent_boundary
            ).candidates,
            candidates[8:],
        )
        invalid_absent_boundary = registration_runtime.SameBootCursor(
            **{**absent_boundary.__dict__, "outcome": "BUSY_LIVE"}
        )
        self.assertEqual(
            registration_runtime.select_same_boot_batch(
                without_last, invalid_absent_boundary
            ).candidates,
            candidates[:2] + candidates[8:],
        )

    def test_same_boot_recovery_progresses_beyond_eight(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            for ordinal in range(1, 11):
                observation = _observation(harness, ordinal=ordinal)
                event = _event(observation.identity.canonical_root)
                ensured = coordinator.ensure(
                    event,
                    observation,
                    fresh_provider=lambda observation=observation: observation,
                )
                execution = coordinator.open_due(ensured.member_id)
                execution.close()
            first = coordinator.recover_same_boot_tick(boot_id="boot-a")
            self.assertEqual(len(first.examined), 8)
            self.assertEqual(
                {item.outcome for item in first.examined},
                {"CLEARED"},
            )
            second = coordinator.recover_same_boot_tick(
                boot_id="boot-a",
                cursor=first.cursor,
            )
            self.assertEqual(len(second.examined), 2)
            third = coordinator.recover_same_boot_tick(
                boot_id="boot-a",
                cursor=second.cursor,
            )
            self.assertEqual(third.examined, ())
            self.assertEqual(
                harness.store.select_same_boot_snapshot(
                    boot_id="boot-a"
                ).candidates,
                (),
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_same_boot_recovered_cursor_binds_final_status(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            observation = _observation(harness)
            ensured = coordinator.ensure(
                _event(),
                observation,
                fresh_provider=lambda: observation,
            )
            execution = coordinator.open_due(ensured.member_id)
            execution.close()
            helpers = {
                kind: FakeActionHelper()
                for kind in registration_runtime.ACTION_KINDS
            }
            batch = coordinator.recover_same_boot_tick(
                boot_id="boot-a",
                recover=lambda member_id: (
                    coordinator.drive(member_id, helpers).outcome == "SUCCESS"
                ),
            )
            self.assertEqual(len(batch.examined), 1)
            self.assertEqual(batch.examined[0].outcome, "RECOVERED")
            authority = harness.store.read_selected_authority(
                ensured.member_id
            )
            self.assertEqual(
                batch.examined[0].post_status_hash,
                authority.status["status_hash"],
            )
            self.assertEqual(
                batch.cursor.last_post_status_hash,
                authority.status["status_hash"],
            )
        finally:
            harness.close()
            temporary.cleanup()

    def test_same_boot_recovery_propagates_typed_containment_failure(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            observation = _observation(harness)
            ensured = coordinator.ensure(
                _event(),
                observation,
                fresh_provider=lambda: observation,
            )
            execution = coordinator.open_due(ensured.member_id)
            execution.close()
            failure = RuntimeError.__new__(
                registration_runtime.RecoveryContainmentUnavailable
            )
            RuntimeError.__init__(failure, "CONTAINMENT_UNAVAILABLE")

            def unavailable(_member_id):
                raise failure

            with self.assertRaises(
                registration_runtime.RecoveryContainmentUnavailable
            ):
                coordinator.recover_same_boot_tick(
                    boot_id="boot-a",
                    recover=unavailable,
                )
        finally:
            harness.close()
            temporary.cleanup()

    def test_same_boot_busy_lock_advances_without_mutation(self) -> None:
        context = multiprocessing.get_context("spawn")
        temporary, harness, coordinator = self._setup()
        try:
            ensured = coordinator.ensure(
                _event(),
                _observation(harness),
                fresh_provider=lambda: _observation(harness),
            )
            ready = context.Event()
            release = context.Event()
            results = context.Queue()
            holder = context.Process(
                target=_hold_executor_process,
                args=(
                    str(harness.store.db_path),
                    ready,
                    release,
                    results,
                ),
            )
            holder.start()
            self.assertTrue(ready.wait(10))
            before = harness.store.table_count(
                "registration_operation_audit"
            )
            batch = coordinator.recover_same_boot_tick(
                boot_id="boot-a"
            )
            self.assertEqual(len(batch.examined), 1)
            self.assertEqual(batch.examined[0].member_id, ensured.member_id)
            self.assertEqual(batch.examined[0].outcome, "BUSY_LIVE")
            self.assertEqual(
                batch.examined[0].pre_status_hash,
                batch.examined[0].post_status_hash,
            )
            self.assertEqual(
                harness.store.table_count("registration_operation_audit"),
                before,
            )
            release.set()
            holder.join(10)
            self.assertFalse(holder.is_alive())
            self.assertEqual(results.get(timeout=2)[0], "ok")
        finally:
            harness.close()
            temporary.cleanup()

    def test_blocked_dirty_member_has_no_timer_or_executor(self) -> None:
        temporary, harness, coordinator = self._setup()
        try:
            identity = harness.identity()
            observation = _fixed_observation(
                registration_runtime.BasisObservation.from_identity(
                    identity,
                    request_kind="BLOCKED_DIRTY",
                    workspace_roots_hash="01" * 32,
                )
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
                        changed = _fixed_observation(
                            changed, identity=identity
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

    def test_eight_worker_lanes_overlap_without_parent_authority(self) -> None:
        context = multiprocessing.get_context("spawn")
        active = context.Value("i", 0)
        maximum = context.Value("i", 0)
        gate = context.Event()
        jobs = [
            (
                f"{ordinal:064x}",
                _overlap_worker,
                (active, maximum, gate),
            )
            for ordinal in range(registration_runtime.TICK_LANES)
        ]
        results = registration_runtime._process_calls(jobs, timeout=5)
        self.assertEqual(set(results.values()), {True})
        self.assertEqual(maximum.value, registration_runtime.TICK_LANES)
        self.assertEqual(active.value, 0)
        self.assertEqual(multiprocessing.active_children(), [])

    def test_worker_start_failure_cleans_started_lanes(self) -> None:
        primary = RuntimeError("spawn unavailable")

        class Endpoint:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class Process:
            def __init__(self, *, fail):
                self.fail = fail
                self.alive = False
                self.terminated = False

            def start(self):
                if self.fail:
                    raise primary
                self.alive = True

            def is_alive(self):
                return self.alive

            def terminate(self):
                self.terminated = True
                self.alive = False

            def join(self, _timeout=None):
                return None

            def kill(self):
                self.alive = False

        class Context:
            def __init__(self):
                self.endpoints = []
                self.processes = []

            def Pipe(self, *, duplex):
                self.assert_false(duplex)
                receiving = Endpoint()
                sending = Endpoint()
                self.endpoints.extend((receiving, sending))
                return receiving, sending

            def Process(self, *, target, args):
                del target, args
                process = Process(fail=bool(self.processes))
                self.processes.append(process)
                return process

            @staticmethod
            def assert_false(value):
                if value:
                    raise AssertionError("pipe must be one-way")

        context = Context()
        with mock.patch.object(
            registration_runtime.multiprocessing,
            "get_context",
            return_value=context,
        ):
            with self.assertRaises(RuntimeError) as captured:
                registration_runtime._process_calls(
                    [
                        ("01" * 32, _return_true, True),
                        ("02" * 32, _return_true, True),
                    ],
                    timeout=1,
                )
        self.assertIs(captured.exception, primary)
        self.assertTrue(context.processes[0].terminated)
        self.assertFalse(context.processes[0].alive)
        self.assertTrue(all(endpoint.closed for endpoint in context.endpoints))

    def test_eight_mutating_lanes_hold_only_their_member_lock(self) -> None:
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=4 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                for ordinal in range(1, registration_runtime.TICK_LANES + 1):
                    harness.store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                selected = harness.store.list_due_candidates(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    limit=registration_runtime.TICK_LANES,
                )
                active = context.Value("i", 0)
                maximum = context.Value("i", 0)
                gate = context.Event()
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                receipt = scheduler.tick_phased(
                    boot_id="boot-a",
                    now_mono_ns=100,
                    open_attempt=lambda due: (
                        registration_runtime.LaneAuthorization(
                            (
                                str(db),
                                due,
                                active,
                                maximum,
                                gate,
                            ),
                            due,
                        )
                    ),
                    run_helper=_mutating_overlap_worker,
                    commit_result=lambda due, _token, result: (
                        result == due.member_id
                    ),
                    open_mutates_authority=False,
                )
                self.assertEqual(
                    set(receipt.selected_member_ids),
                    {due.member_id for due in selected},
                )
                self.assertEqual(receipt.missed_member_ids, ())
                self.assertEqual(
                    maximum.value, registration_runtime.TICK_LANES
                )
                self.assertEqual(active.value, 0)
                for due in selected:
                    authority = harness.store.read_selected_authority(
                        due.member_id
                    )
                    self.assertIsNone(
                        authority.status["executor_token_hash"]
                    )

    def test_killed_open_and_reacquire_grants_are_recovered(self) -> None:
        context = multiprocessing.get_context("spawn")
        for mode in ("open", "reacquire"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                db = (
                    Path(tmp)
                    / "state"
                    / "registration-v1"
                    / "registration.db"
                )
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
                    member_id = registration_runtime.derive_member_id(
                        harness.identity()
                    )
                    if mode == "reacquire":
                        authority = harness.store.read_selected_authority(
                            member_id
                        )
                        execution = harness.store.open_effect(
                            harness.data(),
                            candidate,
                            member_id=member_id,
                            expected_member_hash=authority.member[
                                "member_tuple_hash"
                            ],
                            expected_effect_hash=authority.effect[
                                "request_tuple_hash"
                            ],
                            expected_status_hash=authority.status[
                                "status_hash"
                            ],
                        ).execution
                        harness.store.mark_unavailable(
                            harness.data(), candidate, execution
                        )
                    granted = context.Queue()
                    release = context.Event()
                    holder = context.Process(
                        target=_hold_grant_process,
                        args=(str(db), mode, granted, release),
                    )
                    holder.start()
                    self.assertEqual(
                        granted.get(timeout=10),
                        ("ok", member_id),
                    )
                    self.assertTrue(holder.is_alive())
                    holder.kill()
                    holder.join(10)
                    self.assertFalse(holder.is_alive())
                    coordinator = (
                        registration_runtime.RegistrationCoordinator(
                            store=harness.store,
                            data=harness.data(),
                            candidate=candidate,
                        )
                    )
                    recovered = coordinator.recover_same_boot_tick(
                        boot_id="boot-a"
                    )
                    self.assertEqual(
                        tuple(item.member_id for item in recovered.examined),
                        (member_id,),
                    )
                    self.assertEqual(
                        tuple(item.outcome for item in recovered.examined),
                        ("CLEARED",),
                    )
                    result = coordinator.drive(
                        member_id,
                        {
                            kind: FakeActionHelper()
                            for kind in registration_runtime.ACTION_KINDS
                        },
                    )
                    self.assertEqual(result.outcome, "SUCCESS")
                    granted.close()
                    granted.join_thread()

    def test_r1_scope_positions_refuse_before_any_tick_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=4 * 1024**3
            ) as harness:
                candidate = harness.candidate()
                harness.store.bootstrap(harness.control(), candidate)
                harness.store.activate(harness.control(), candidate)
                for ordinal in range(1, 10):
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
                member_ids = sorted(
                    row[0]
                    for row in harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchall()
                )
                before = harness.store.table_count(
                    "registration_operation_audit"
                )
                for position in (1, 8, 9):
                    with self.subTest(position=position), mock.patch.object(
                        harness.store,
                        "select_r1_scope",
                        wraps=harness.store.select_r1_scope,
                    ) as selector, mock.patch.object(
                        harness.store,
                        "list_due_candidates",
                        wraps=harness.store.list_due_candidates,
                    ) as ordinary_due:
                        with self.assertRaises(
                            registration_runtime.R1ScopeRefused
                        ):
                            scheduler.tick(
                                boot_id="boot-a",
                                now_mono_ns=100,
                                attempt=_return_true,
                                authorized_member_id=member_ids[
                                    position - 1
                                ],
                            )
                        self.assertEqual(selector.call_count, 1)
                        self.assertEqual(ordinary_due.call_count, 0)
                        self.assertEqual(
                            harness.store.table_count(
                                "registration_operation_audit"
                            ),
                            before,
                        )

    def test_each_r1_outside_flag_refuses_with_zero_mutation(self) -> None:
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
                member_id = registration_runtime.derive_member_id(
                    harness.identity()
                )
                due = harness.store.list_due_candidates(
                    boot_id="boot-a", now_mono_ns=100
                )[0]
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                before = harness.store.table_count(
                    "registration_operation_audit"
                )
                for flag in (
                    "outside_scope_same_boot",
                    "outside_scope_due",
                    "outside_scope_reboot",
                ):
                    values = {
                        "authorized_same_boot": None,
                        "authorized_due": due,
                        "authorized_reboot": None,
                        "outside_scope_same_boot": False,
                        "outside_scope_due": False,
                        "outside_scope_reboot": False,
                    }
                    values[flag] = True
                    selection = registration_store.R1ScopeSelection(
                        **values
                    )
                    with self.subTest(flag=flag), mock.patch.object(
                        harness.store,
                        "select_r1_scope",
                        return_value=selection,
                    ) as selector:
                        with self.assertRaises(
                            registration_runtime.R1ScopeRefused
                        ):
                            scheduler.tick(
                                boot_id="boot-a",
                                now_mono_ns=100,
                                attempt=_return_true,
                                authorized_member_id=member_id,
                            )
                        self.assertEqual(selector.call_count, 1)
                        self.assertEqual(
                            harness.store.table_count(
                                "registration_operation_audit"
                            ),
                            before,
                        )

    def test_one_r1_preflight_token_covers_all_tick_lanes(self) -> None:
        for lane in ("same_boot", "reboot", "due"):
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as tmp:
                db = (
                    Path(tmp)
                    / "state"
                    / "registration-v1"
                    / "registration.db"
                )
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
                    member_id = registration_runtime.derive_member_id(
                        harness.identity()
                    )
                    coordinator = (
                        registration_runtime.RegistrationCoordinator(
                            store=harness.store,
                            data=harness.data(),
                            candidate=candidate,
                        )
                    )
                    boot_id = "boot-a"
                    if lane in {"same_boot", "reboot"}:
                        authority = harness.store.read_selected_authority(
                            member_id
                        )
                        execution = harness.store.open_effect(
                            harness.data(),
                            candidate,
                            member_id=member_id,
                            expected_member_hash=authority.member[
                                "member_tuple_hash"
                            ],
                            expected_effect_hash=authority.effect[
                                "request_tuple_hash"
                            ],
                            expected_status_hash=authority.status[
                                "status_hash"
                            ],
                        ).execution
                        execution.close()
                    if lane == "reboot":
                        boot_id = "boot-b"
                        harness.sample_boot_id = boot_id
                    scheduler = registration_runtime.FairnessScheduler(
                        store=harness.store,
                        data=harness.data(),
                        candidate=candidate,
                    )
                    with mock.patch.object(
                        harness.store,
                        "select_r1_scope",
                        wraps=harness.store.select_r1_scope,
                    ) as selector, mock.patch.object(
                        harness.store,
                        "list_due_candidates",
                        wraps=harness.store.list_due_candidates,
                    ) as ordinary_due, mock.patch.object(
                        harness.store,
                        "list_reboot_candidates",
                        wraps=harness.store.list_reboot_candidates,
                    ) as ordinary_reboot:
                        scope = coordinator.preflight_r1_tick(
                            authorized_member_id=member_id,
                            boot_id=boot_id,
                            now_mono_ns=100,
                        )
                        same_boot = coordinator.recover_r1_same_boot(scope)
                        reboot = coordinator.recover_reboot(
                            boot_id, r1_scope=scope
                        )
                        receipt = scheduler.tick(
                            boot_id=boot_id,
                            now_mono_ns=100,
                            attempt=_return_true,
                            r1_scope=scope,
                        )
                    self.assertEqual(selector.call_count, 1)
                    self.assertEqual(ordinary_due.call_count, 0)
                    self.assertEqual(ordinary_reboot.call_count, 0)
                    if lane == "same_boot":
                        self.assertEqual(same_boot.outcome, "CLEARED")
                        self.assertEqual(reboot, ())
                        self.assertEqual(receipt.selected_member_ids, ())
                    elif lane == "reboot":
                        self.assertIsNone(same_boot)
                        self.assertEqual(reboot, (member_id,))
                        self.assertEqual(receipt.selected_member_ids, ())
                    else:
                        self.assertIsNone(same_boot)
                        self.assertEqual(reboot, ())
                        self.assertEqual(
                            receipt.selected_member_ids, (member_id,)
                        )

    def test_r1_authorized_due_uses_atomic_selector_not_limit_nine(self) -> None:
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
                member_id = registration_runtime.derive_member_id(
                    harness.identity()
                )
                scheduler = registration_runtime.FairnessScheduler(
                    store=harness.store,
                    data=harness.data(),
                    candidate=candidate,
                )
                with mock.patch.object(
                    harness.store,
                    "select_r1_scope",
                    wraps=harness.store.select_r1_scope,
                ) as selector, mock.patch.object(
                    harness.store,
                    "list_due_candidates",
                    wraps=harness.store.list_due_candidates,
                ) as ordinary_due:
                    receipt = scheduler.tick(
                        boot_id="boot-a",
                        now_mono_ns=100,
                        attempt=_return_true,
                        authorized_member_id=member_id,
                    )
                self.assertEqual(selector.call_count, 1)
                self.assertEqual(ordinary_due.call_count, 0)
                self.assertEqual(receipt.selected_member_ids, (member_id,))

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
            changed = _fixed_observation(changed, identity=identity)
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
                        fresh_provider=lambda: changed,
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
