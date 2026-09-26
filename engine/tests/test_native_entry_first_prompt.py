"""ADR 0024 first-prompt native-entry recovery acceptance tests."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from engine import lease as lease_mod
from engine import lifecycle
from engine import lock as lock_mod
from engine import native_entry
from engine import state as state_mod
from engine.tests.helpers import EngineTestCase, git
from kernel.lib import awa_roots


class TestNativeEntryFirstPrompt(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.governed_root = Path(self._tmp.name) / "governed"
        self.governed_root.mkdir(mode=0o700)
        self.repo = Path(
            self.make_seeded_repo("governed/first-prompt-source")
        )
        self.policy = Path(self._tmp.name) / "policy.yml"
        self.policy.write_text(
            "version: 1\n"
            f"governed_roots:\n  - {self.governed_root}\n"
            "default: include\n"
            "default_mode: on\n"
            "include:\n  - '*'\n"
            "exclude:\n  - never-match\n"
            "detectors:\n"
            "  governed_markers:\n    - _ops/POLICY.md\n"
            "  foreign_hook_frameworks:\n    - pre-commit\n"
            "  read_only_paths: []\n"
            "overrides:\n  include: []\n  exclude: []\n",
            encoding="utf-8",
        )
        self.saved_policy = os.environ.get("AWA_POLICY")
        self.saved_root = os.environ.get("AWA_GOVERNED_ROOT")
        os.environ["AWA_POLICY"] = str(self.policy)
        os.environ["AWA_GOVERNED_ROOT"] = str(self.governed_root)

    def tearDown(self) -> None:
        if self.saved_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = self.saved_policy
        if self.saved_root is None:
            os.environ.pop("AWA_GOVERNED_ROOT", None)
        else:
            os.environ["AWA_GOVERNED_ROOT"] = self.saved_root
        super().tearDown()

    def _worktree(self, branch: str) -> Path:
        return Path(
            self.add_worktree(
                str(self.repo),
                branch,
                suffix=f".{branch.replace('/', '-')}.wt",
            )
        )

    @staticmethod
    def _payload(
        root: Path,
        *,
        event: str = "beforeSubmitPrompt",
        conversation: str = "conversation-one",
        generation: str = "generation-one",
        include_session: bool = False,
    ) -> dict:
        payload = {
            "hook_event_name": event,
            "workspace_roots": [str(root)],
            "conversation_id": conversation,
            "generation_id": generation,
        }
        if include_session or event == "sessionStart":
            payload["session_id"] = conversation
        return payload

    @staticmethod
    def _event_kinds(lease_id: str) -> list[str]:
        with state_mod.State() as state:
            return [
                event["kind"]
                for event in state.events(lease_id=lease_id, limit=50)
            ]

    def test_closed_event_envelopes_and_identity_mapping(self) -> None:
        root = self._worktree("feat/envelopes")
        eager = native_entry.parse_entry_payload(
            self._payload(root, event="sessionStart")
        )
        self.assertEqual(eager.source_event, "sessionStart")
        self.assertEqual(eager.session_id, "conversation-one")
        self.assertEqual(eager.conversation_id, eager.session_id)
        self.assertEqual(eager.source_generation_id, "generation-one")

        prompt = native_entry.parse_entry_payload(self._payload(root))
        self.assertEqual(prompt.source_event, "beforeSubmitPrompt")
        self.assertEqual(prompt.session_id, "conversation-one")

        wrapped = self._payload(root)
        wrapped["tool_input"] = {
            "hook_event_name": "beforeSubmitPrompt",
            "workspace_roots": [str(root)],
            "conversation_id": "conversation-one",
            "generation_id": "generation-one",
        }
        self.assertEqual(
            native_entry.parse_entry_payload(wrapped),
            prompt,
        )

        bad_payloads = [
            {
                **self._payload(root),
                "hook_event_name": "workspaceOpen",
            },
            {
                "hook_event_name": "beforeSubmitPrompt",
                "cwd": str(root),
                "conversation_id": "conversation-one",
                "generation_id": "generation-one",
            },
            {
                **self._payload(root, event="sessionStart"),
                "session_id": "different-session",
            },
            {
                **self._payload(root),
                "tool_input": {
                    "conversation_id": "different-conversation",
                },
            },
            {
                **self._payload(root),
                "tool_input": {
                    "generation_id": "different-generation",
                },
            },
            {
                **self._payload(root),
                "workspace_roots": [str(root), str(self.repo)],
            },
            {
                **self._payload(root),
                "workspace_roots": [str(root) + os.sep],
            },
            {
                **self._payload(root),
                "conversation_id": " conversation-one",
            },
            {
                **self._payload(root),
                "generation_id": "generation-one ",
            },
            {
                **self._payload(root),
                "session_id": "conversation-one ",
            },
            {
                **self._payload(root),
                "tool_input": {
                    "workspace_roots": [str(root) + os.sep + "."],
                },
            },
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(native_entry.EntryUnavailable):
                    native_entry.parse_entry_payload(payload)

    def test_environment_and_cwd_never_supply_registration_identity(self) -> None:
        root = self._worktree("feat/no-fallback")
        with mock.patch.dict(
            os.environ,
            {
                "DEV_SESSION_ID": "environment-session",
                "AWA_FINISH_CONVERSATION_ID": "environment-conversation",
                "GIT_DIR": str(self.repo / "wrong-git-dir"),
                "GIT_WORK_TREE": str(self.repo / "wrong-work-tree"),
            },
            clear=False,
        ):
            result = native_entry.register_event(
                {
                    "hook_event_name": "beforeSubmitPrompt",
                    "cwd": str(root),
                }
            )
        self.assertEqual(result.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(root)))
        self.assertEqual(native_entry.read_receipts(), [])

        poisoned = self._worktree("feat/poisoned-git-environment")
        with mock.patch.dict(
            os.environ,
            {
                "GIT_DIR": str(self.repo / "wrong-git-dir"),
                "GIT_WORK_TREE": str(self.repo / "wrong-work-tree"),
                "GIT_INDEX_FILE": str(self.repo / "wrong-index"),
            },
            clear=False,
        ):
            registered = native_entry.register_event(
                self._payload(
                    poisoned,
                    conversation="poisoned-git-environment",
                )
            )
        self.assertEqual(
            (registered.result, registered.action),
            ("success", "adopted"),
        )

    def test_first_prompt_binds_exact_session_and_writes_private_v2(self) -> None:
        root = self._worktree("feat/recovery")
        payload = {
            **self._payload(root),
            "prompt": "operator-private-prompt-7b3b",
            "model": "private-model-7b3b",
            "transcript_path": "/private/transcript-7b3b",
            "attachments": [{"name": "private-attachment-7b3b"}],
            "arbitrary_environment": "private-environment-7b3b",
        }
        result = native_entry.register_event(payload)
        self.assertEqual((result.result, result.action), ("success", "adopted"))
        self.assertEqual(native_entry.evidence_state(), "recovered")

        receipt = native_entry.read_receipts()[0]
        self.assertEqual(receipt["schema"], "awa-native-entry/v2")
        self.assertEqual(receipt["source_event"], "beforeSubmitPrompt")
        self.assertEqual(receipt["session_id"], "conversation-one")
        self.assertEqual(receipt["conversation_id"], "conversation-one")
        self.assertEqual(receipt["source_generation_id"], "generation-one")
        self.assertEqual(receipt["result"], "success")
        self.assertEqual(
            set(receipt),
            native_entry.RECEIPT_V2_KEYS,
        )
        raw = native_entry.receipt_path(
            str(root),
            "conversation-one",
        ).read_text(encoding="utf-8")
        for private in (
            "operator-private-prompt-7b3b",
            "private-model-7b3b",
            "/private/transcript-7b3b",
            "private-attachment-7b3b",
            "private-environment-7b3b",
        ):
            self.assertNotIn(private, raw)

        current, status = awa_roots.read_current_session(str(root))
        self.assertEqual(status, "ok")
        self.assertEqual(current["session_id"], "conversation-one")
        self.assertEqual(current["conversation_id"], "conversation-one")
        disposition = awa_roots.disposition(str(root))
        self.assertEqual(disposition["disposition"], "active")
        member = disposition["record"]["sessions"][
            awa_roots.session_key("conversation-one")
        ]
        self.assertEqual(member["session_id"], "conversation-one")

    def test_existing_conversation_moved_to_new_root_recovers_on_first_prompt(self) -> None:
        prior = self._worktree("feat/prior-root")
        moved = self._worktree("feat/moved-root")
        prior_identity = native_entry._observe_identity(str(prior))
        awa_roots.heartbeat(
            str(prior),
            branch=prior_identity.branch,
            common_dir=prior_identity.git_common_dir,
            session_id="moved-conversation",
        )
        bound = awa_roots.bind_current_session(
            str(prior),
            session_id="moved-conversation",
            conversation_id="moved-conversation",
            branch=prior_identity.branch,
            common_dir=prior_identity.git_common_dir,
            source="sessionStart",
        )
        self.assertTrue(bound["ok"], bound)

        recovered = native_entry.register_event(
            self._payload(
                moved,
                conversation="moved-conversation",
                generation="moved-first-prompt",
            )
        )
        self.assertEqual(
            (recovered.result, recovered.action),
            ("success", "adopted"),
        )
        current, status = awa_roots.read_current_session(str(moved))
        self.assertEqual(status, "ok")
        self.assertEqual(current["conversation_id"], "moved-conversation")
        self.assertEqual(current["session_id"], "moved-conversation")

    def test_later_prompt_generation_is_exact_success_noop(self) -> None:
        root = self._worktree("feat/later-generation")
        first = native_entry.register_event(
            self._payload(
                root,
                event="sessionStart",
                include_session=True,
            )
        )
        self.assertEqual((first.result, first.action), ("success", "adopted"))
        self.assertEqual(native_entry.evidence_state(), "eager")
        lease = lease_mod.read_lease(str(root))
        receipt_path = native_entry.receipt_path(
            str(root),
            "conversation-one",
        )
        before_bytes = receipt_path.read_bytes()
        before_events = self._event_kinds(lease["lease_id"])

        later = native_entry.register_event(
            self._payload(root, generation="generation-two")
        )
        self.assertEqual(
            (later.result, later.action, later.reason),
            ("success", None, "already_registered"),
        )
        self.assertEqual(receipt_path.read_bytes(), before_bytes)
        self.assertEqual(self._event_kinds(lease["lease_id"]), before_events)
        self.assertEqual(
            native_entry.read_receipts()[0]["source_generation_id"],
            "generation-one",
        )
        self.assertEqual(
            native_entry.read_receipts()[0]["source_event"],
            "sessionStart",
        )

    def test_exact_success_noop_rechecks_live_identity_before_return(self) -> None:
        root = self._worktree("feat/noop-final-recheck")
        first = native_entry.register_event(self._payload(root))
        self.assertEqual((first.result, first.action), ("success", "adopted"))
        initial = native_entry.read_receipts()[0]
        observed = native_entry._observe_identity(str(root))
        drifted = replace(observed, head="e" * 40)

        with mock.patch.object(
            native_entry,
            "_validated_registration_identity",
            side_effect=[observed, observed, drifted, drifted],
        ), mock.patch.object(
            lifecycle,
            "observe_identity",
            return_value=drifted,
        ):
            retried = native_entry.register_event(
                self._payload(root, generation="generation-after-noop-drift")
            )

        self.assertEqual((retried.result, retried.action), ("success", "repaired"))
        current = native_entry.read_receipts()[0]
        self.assertGreater(current["generation"], initial["generation"])
        self.assertEqual(
            current["source_generation_id"],
            "generation-after-noop-drift",
        )
        self.assertEqual(current["head"], drifted.head)

    def test_same_key_parallel_delivery_has_one_lifecycle_sequence(self) -> None:
        root = self._worktree("feat/same-key")
        payload = self._payload(root)
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def enter() -> None:
            try:
                barrier.wait(timeout=5)
                results.append(
                    native_entry.register_event(
                        payload,
                        lock_timeout=10.0,
                        deadline=time.monotonic() + 15.0,
                    )
                )
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        workers = [threading.Thread(target=enter) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(15)
        self.assertFalse(errors)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertEqual([result.result for result in results], ["success", "success"])
        lease = lease_mod.read_lease(str(root))
        events = self._event_kinds(lease["lease_id"])
        self.assertEqual(events.count("adopt"), 1)
        self.assertEqual(events.count("attest"), 1)
        self.assertEqual(len(native_entry.read_receipts()), 1)

    def test_crash_complete_pending_recovers_without_event_amplification(self) -> None:
        root = self._worktree("feat/crash-recovery")

        class SimulatedCrash(BaseException):
            pass

        with mock.patch.object(
            native_entry,
            "_publish_success",
            side_effect=SimulatedCrash(),
        ):
            crashed = native_entry.register_event(self._payload(root))
        self.assertEqual(crashed.result, "failed")
        receipt = native_entry.read_receipts()[0]
        self.assertEqual(receipt["result"], "pending")
        lease = lease_mod.read_lease(str(root))
        before_events = self._event_kinds(lease["lease_id"])
        self.assertEqual(before_events.count("adopt"), 1)
        self.assertEqual(before_events.count("attest"), 1)

        recovered = native_entry.register_event(self._payload(root))
        self.assertEqual(
            (recovered.result, recovered.action),
            ("success", "recovered"),
        )
        self.assertEqual(
            self._event_kinds(lease["lease_id"]),
            before_events,
        )

    def test_pending_precedes_lifecycle_and_success_follows_attestation(self) -> None:
        root = self._worktree("feat/transition-order")
        real_adopt = lifecycle.adopt
        observed_during_adopt: list[str] = []

        def inspect_pending(*args, **kwargs):
            records = native_entry.read_receipts()
            observed_during_adopt.extend(
                record["result"] for record in records
            )
            return real_adopt(*args, **kwargs)

        with mock.patch.object(lifecycle, "adopt", side_effect=inspect_pending):
            result = native_entry.register_event(self._payload(root))
        self.assertEqual(observed_during_adopt, ["pending"])
        self.assertEqual((result.result, result.action), ("success", "adopted"))
        receipt = native_entry.read_receipts()[0]
        self.assertEqual(receipt["result"], "success")
        lease = lease_mod.read_lease(str(root))
        with state_mod.State() as state:
            row = state.get_lease(lease["lease_id"])
            events = state.events(lease_id=lease["lease_id"], limit=10)
        self.assertTrue(row["attested_at"])
        self.assertEqual(
            [event["kind"] for event in reversed(events[:2])],
            ["adopt", "attest"],
        )

    def test_stale_pending_cas_cannot_downgrade_success(self) -> None:
        root = self._worktree("feat/stale-cas")
        result = native_entry.register_event(self._payload(root))
        self.assertEqual(result.result, "success")
        success = native_entry.read_receipts()[0]
        stale_pending = dict(success)
        stale_pending.update(
            {
                "generation": success["generation"] - 1,
                "result": "pending",
                "action": None,
                "lease_id": None,
                "reason": "registration_pending",
            }
        )
        changed = native_entry._publish_terminal_failure(
            stale_pending,
            result="failed",
            reason="registration_failed",
        )
        self.assertIsNone(changed)
        self.assertEqual(native_entry.read_receipts()[0], success)

    def test_registration_never_acquires_common_lock_while_receipt_locked(self) -> None:
        root = self._worktree("feat/lock-order")
        real_receipt = native_entry._receipt_lock
        real_common = lock_mod.common_dir_lock
        state = {"receipt_depth": 0}

        @contextlib.contextmanager
        def traced_receipt(*, deadline=None):
            with real_receipt(deadline=deadline) as opened:
                state["receipt_depth"] += 1
                try:
                    yield opened
                finally:
                    state["receipt_depth"] -= 1

        @contextlib.contextmanager
        def traced_common(*args, **kwargs):
            self.assertEqual(
                state["receipt_depth"],
                0,
                "common-directory lock acquired while receipt lock held",
            )
            with real_common(*args, **kwargs) as held:
                yield held

        with mock.patch.object(
            native_entry,
            "_receipt_lock",
            traced_receipt,
        ), mock.patch.object(
            lock_mod,
            "common_dir_lock",
            traced_common,
        ):
            result = native_entry.register_event(self._payload(root))
        self.assertEqual((result.result, result.action), ("success", "adopted"))
        self.assertEqual(state["receipt_depth"], 0)

    def test_strict_v1_is_legacy_only_without_v2_provenance(self) -> None:
        root = self._worktree("feat/v1-legacy")
        identity = native_entry._observe_identity(str(root))
        legacy = {
            "schema": "awa-native-entry/v1",
            "root": identity.root,
            "session_id": "legacy-session",
            "branch": identity.branch,
            "head": identity.head,
            "git_dir": identity.git_dir,
            "git_common_dir": identity.git_common_dir,
            "generation": 1,
            "timestamp": native_entry._now(),
            "result": "failed",
            "action": None,
            "lease_id": None,
            "reason": "registration_failed",
        }
        path = native_entry.receipt_path(str(root), "legacy-session")
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text(json.dumps(legacy, sort_keys=True) + "\n", encoding="utf-8")
        path.chmod(0o600)
        records = native_entry.read_receipts()
        self.assertEqual(records, [legacy])
        self.assertNotIn("source_event", records[0])
        self.assertNotIn("conversation_id", records[0])
        self.assertNotIn("source_generation_id", records[0])
        self.assertEqual(
            native_entry.candidate_common_dirs(),
            [identity.git_common_dir],
        )
        impossible_v1 = dict(legacy)
        impossible_v1.update(
            {
                "result": "success",
                "action": "recovered",
                "lease_id": "legacy-lease",
                "reason": "recovered",
            }
        )
        path.write_text(
            json.dumps(impossible_v1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        self.assertEqual(native_entry.read_receipts(), [])
        self.assertEqual(native_entry.evidence_state(), "conflict")

        impossible_v2 = dict(legacy)
        impossible_v2.update(
            {
                "schema": native_entry.SCHEMA_V2,
                "source_event": "beforeSubmitPrompt",
                "conversation_id": "legacy-session",
                "source_generation_id": "legacy-generation",
                "result": "pending",
                "reason": "registered",
            }
        )
        path.write_text(
            json.dumps(impossible_v2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        self.assertEqual(native_entry.read_receipts(), [])
        self.assertEqual(native_entry.evidence_state(), "conflict")

        path.write_text(
            json.dumps(legacy, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        mixed = dict(legacy)
        mixed["source_event"] = "sessionStart"
        path.write_text(json.dumps(mixed, sort_keys=True) + "\n", encoding="utf-8")
        path.chmod(0o600)
        self.assertEqual(native_entry.read_receipts(), [])
        self.assertEqual(native_entry.evidence_state(), "conflict")

    def test_exact_legacy_v1_success_remains_readable_without_inferred_source(self) -> None:
        root = self._worktree("feat/v1-success")
        result = native_entry.register_event(
            self._payload(root, conversation="legacy-success")
        )
        self.assertEqual(result.result, "success")
        v2 = native_entry.read_receipts()[0]
        legacy = {
            key: value
            for key, value in v2.items()
            if key in native_entry.RECEIPT_V1_KEYS
        }
        legacy["schema"] = native_entry.SCHEMA_V1
        path = native_entry.receipt_path(str(root), "legacy-success")
        path.write_text(
            json.dumps(legacy, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)

        observed = native_entry.read_receipts()
        self.assertEqual(observed, [legacy])
        self.assertEqual(native_entry.evidence_state(), "legacy")
        for key in (
            "source_event",
            "conversation_id",
            "source_generation_id",
        ):
            self.assertNotIn(key, observed[0])

    def test_v2_success_replay_cannot_survive_live_identity_drift(self) -> None:
        root = self._worktree("feat/replay-drift")
        result = native_entry.register_event(
            self._payload(root, conversation="replay-drift")
        )
        self.assertEqual(result.result, "success")
        path = native_entry.receipt_path(str(root), "replay-drift")
        original = path.read_bytes()
        receipt = json.loads(original)
        self.assertEqual(native_entry.evidence_state(), "recovered")

        lease_drift = dict(receipt)
        lease_drift["lease_id"] = "different-lease"
        path.write_text(
            json.dumps(lease_drift, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        path.chmod(0o600)
        self.assertEqual(native_entry.evidence_state(), "stale")

        path.write_bytes(original)
        path.chmod(0o600)
        current, status = awa_roots.read_current_session(str(root))
        self.assertEqual(status, "ok")
        replacement = awa_roots.write_current_session(
            str(root),
            session_id="replacement-session",
            conversation_id="replacement-session",
            branch=current["branch"],
            common_dir=current["common_dir"],
        )
        self.assertEqual(replacement["session_id"], "replacement-session")
        self.assertEqual(native_entry.evidence_state(), "stale")

    def test_current_session_bind_refusal_prevents_lifecycle_mutation(self) -> None:
        root = self._worktree("feat/bind-refusal")
        with mock.patch.object(
            awa_roots,
            "heartbeat_and_bind_current_session",
            return_value={"ok": False, "reason": "current_session_lock_busy"},
        ):
            result = native_entry.register_event(self._payload(root))
        self.assertEqual(result.result, "failed")
        self.assertEqual(result.reason, "current_session_invalid")
        self.assertIsNone(lease_mod.read_lease(str(root)))
        with state_mod.State() as state:
            self.assertEqual(state.list_leases("active"), [])

    def test_ignored_hidden_index_and_malformed_current_session_refuse(self) -> None:
        ignored = self._worktree("feat/ignored-state")
        common = Path(
            git(
                str(ignored),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ).stdout.strip()
        )
        (common / "info" / "exclude").write_text(
            "private.local\n",
            encoding="utf-8",
        )
        (ignored / "private.local").write_text("private\n", encoding="utf-8")
        ignored_result = native_entry.register_event(self._payload(ignored))
        self.assertEqual(
            (ignored_result.result, ignored_result.reason),
            ("failed", "worktree_ignored_state"),
        )
        self.assertIsNone(lease_mod.read_lease(str(ignored)))

        hidden = self._worktree("feat/hidden-index")
        git(str(hidden), "update-index", "--skip-worktree", "README.md")
        hidden_result = native_entry.register_event(
            self._payload(hidden, conversation="hidden-index")
        )
        self.assertEqual(
            (hidden_result.result, hidden_result.reason),
            ("failed", "index_hidden_state"),
        )
        self.assertIsNone(lease_mod.read_lease(str(hidden)))

        malformed = self._worktree("feat/malformed-current")
        current_path = Path(awa_roots.current_session_path(str(malformed)))
        current_path.parent.mkdir(parents=True, mode=0o700)
        current_path.parent.parent.chmod(0o700)
        current_path.write_text('{"schema":', encoding="utf-8")
        current_path.chmod(0o600)
        before = current_path.read_bytes()
        malformed_result = native_entry.register_event(
            self._payload(malformed, conversation="malformed-current")
        )
        self.assertEqual(
            (malformed_result.result, malformed_result.reason),
            ("failed", "current_session_invalid"),
        )
        self.assertEqual(current_path.read_bytes(), before)
        self.assertIsNone(lease_mod.read_lease(str(malformed)))

    def test_exact_success_with_sqlite_drift_starts_new_monotonic_attempt(self) -> None:
        root = self._worktree("feat/sqlite-drift")
        first = native_entry.register_event(self._payload(root))
        self.assertEqual((first.result, first.action), ("success", "adopted"))
        initial = native_entry.read_receipts()[0]
        lease = lease_mod.read_lease(str(root))
        with state_mod.State() as state:
            state.conn.execute(
                "DELETE FROM leases WHERE lease_id=?",
                (lease["lease_id"],),
            )

        repaired = native_entry.register_event(
            self._payload(root, generation="generation-after-drift")
        )
        self.assertEqual((repaired.result, repaired.action), ("success", "repaired"))
        current = native_entry.read_receipts()[0]
        self.assertGreater(current["generation"], initial["generation"])
        self.assertEqual(
            current["source_generation_id"],
            "generation-after-drift",
        )
        self.assertEqual(current["source_event"], "beforeSubmitPrompt")

    def test_workspace_open_and_malformed_or_oversized_cli_input_are_quiet(self) -> None:
        root = self._worktree("feat/cli-refusal")
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        }
        cases = (
            b"{not-json",
            b"x" * (native_entry._MAX_PAYLOAD_BYTES + 1),
            (
                b'{"hook_event_name":"beforeSubmitPrompt",'
                b'"workspace_roots":["'
                + str(root).encode()
                + b'"],"conversation_id":"one","conversation_id":"two",'
                b'"generation_id":"generation"}'
            ),
            json.dumps(
                {
                    **self._payload(root),
                    "hook_event_name": "workspaceOpen",
                }
            ).encode(),
        )
        for payload in cases:
            with self.subTest(size=len(payload)):
                result = subprocess.run(
                    [os.sys.executable, "-B", "-m", "engine.native_entry"],
                    input=payload,
                    capture_output=True,
                    env=env,
                    timeout=10,
                )
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr),
                    (0, b"", b""),
                )
        self.assertIsNone(lease_mod.read_lease(str(root)))
        self.assertEqual(native_entry.read_receipts(), [])


if __name__ == "__main__":
    unittest.main()
