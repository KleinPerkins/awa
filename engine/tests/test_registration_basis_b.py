from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock

from engine import registration_admission, registration_basis, registration_store
from engine.tests import helpers


class RegistrationBasisCollectorTest(helpers.EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.make_seeded_repo("basis-repo")
        self.root = self.add_worktree(self.repo, "feature")
        self._old_governed = os.environ.get("AWA_GOVERNED_ROOT")
        os.environ["AWA_GOVERNED_ROOT"] = self._tmp.name
        self.proof = self.state_home / "proof"
        self.projection = self.state_home / "projection"
        self.legacy = self.state_home / "legacy"
        for path in (self.proof, self.projection, self.legacy):
            path.mkdir(mode=0o700)
        self.proof = self.proof.resolve()
        self.projection = self.projection.resolve()
        self.legacy = self.legacy.resolve()

    def tearDown(self) -> None:
        if self._old_governed is None:
            os.environ.pop("AWA_GOVERNED_ROOT", None)
        else:
            os.environ["AWA_GOVERNED_ROOT"] = self._old_governed
        super().tearDown()

    def _event(self):
        return registration_admission.RegistrationEvent(
            workspace_roots=(self.root,),
            conversation_id="conversation-1",
            generation_id="generation-1",
            source_contract="cursor-hook/v1",
            source_event="beforeShellExecution",
        )

    def _collector(self):
        return registration_basis.GitBasisCollector(
            proof_parent=self.proof,
            projection_parent=self.projection,
            legacy_parent=self.legacy,
        )

    def test_clean_linked_root_returns_closed_basis(self) -> None:
        observation = self._collector().collect_observation(self._event())
        self.assertEqual(observation.request_kind, "CLEAN_ELIGIBLE")
        self.assertEqual(observation.identity.canonical_root, self.root)
        self.assertIsNone(observation.blocked_basis_fingerprint)
        sample = observation.basis_sample
        self.assertEqual(sample.canonical_root, self.root)
        self.assertNotIn(self.root, sample.current_basis_hash)

    def test_fresh_provider_returns_only_closed_store_value(self) -> None:
        value = self._collector().collect_fresh_basis(self._event())
        self.assertIsInstance(value, registration_store.FreshMemberBasis)
        self.assertEqual(value.identity.canonical_root, self.root)
        self.assertEqual(
            value.identity.current_basis_hash,
            value.intent.request_basis_hash,
        )
        self.assertEqual(len(value.workspace_roots_hash), 64)

    def test_dirty_root_is_redacted_and_source_index_refs_unchanged(self) -> None:
        dirty = Path(self.root) / "dirty.txt"
        dirty.write_text("private local work\n", encoding="utf-8")
        before_source = dirty.read_bytes()
        before_head = helpers.git(self.root, "rev-parse", "HEAD").stdout
        before_status = helpers.git(
            self.root, "status", "--porcelain=v2", "-z"
        ).stdout
        observation = self._collector().collect_observation(self._event())
        self.assertEqual(observation.request_kind, "BLOCKED_DIRTY")
        self.assertIsNotNone(observation.blocked_basis_fingerprint)
        self.assertEqual(dirty.read_bytes(), before_source)
        self.assertEqual(
            helpers.git(self.root, "rev-parse", "HEAD").stdout, before_head
        )
        self.assertEqual(
            helpers.git(self.root, "status", "--porcelain=v2", "-z").stdout,
            before_status,
        )

    def test_in_progress_git_operation_is_blocked_without_mutation(self) -> None:
        git_dir = Path(
            helpers.git(self.root, "rev-parse", "--git-dir").stdout.strip()
        )
        marker = git_dir / "MERGE_HEAD"
        marker.write_text("0" * 40 + "\n", encoding="ascii")
        before = marker.read_bytes()
        observation = self._collector().collect_observation(self._event())
        self.assertEqual(observation.request_kind, "BLOCKED_OPERATION")
        self.assertEqual(marker.read_bytes(), before)

    def test_symlink_alias_root_refuses(self) -> None:
        alias = Path(self._tmp.name).resolve() / "root-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        event = registration_admission.RegistrationEvent(
            **{
                **self._event().__dict__,
                "workspace_roots": (str(alias),),
            }
        )
        with self.assertRaises(registration_admission.BasisUnavailable):
            self._collector().collect_observation(event)

    def test_identity_timeout_maps_basis_timeout_not_root_unsupported(self) -> None:
        with mock.patch.object(
            registration_basis.native_entry,
            "_observe_identity",
            side_effect=subprocess.TimeoutExpired("git", 1),
        ):
            with self.assertRaises(
                registration_admission.BasisUnavailable
            ) as captured:
                self._collector().collect_observation(self._event())
        self.assertEqual(captured.exception.reason, "BASIS_TIMEOUT")

    def test_validation_and_policy_timeouts_also_map_basis_timeout(self) -> None:
        with mock.patch.object(
            registration_basis.native_entry,
            "_validated_registration_identity",
            side_effect=subprocess.TimeoutExpired("git", 1),
        ):
            with self.assertRaises(
                registration_admission.BasisUnavailable
            ) as captured:
                self._collector().collect_observation(self._event())
        self.assertEqual(captured.exception.reason, "BASIS_TIMEOUT")

        with (
            mock.patch.object(
                registration_basis.native_entry,
                "_validated_registration_identity",
                side_effect=registration_basis.native_entry.EntryUnavailable(
                    "worktree_dirty"
                ),
            ),
            mock.patch.object(
                registration_basis.native_entry,
                "_git",
                side_effect=subprocess.TimeoutExpired("git", 1),
            ),
        ):
            with self.assertRaises(
                registration_admission.BasisUnavailable
            ) as captured:
                self._collector().collect_observation(self._event())
        self.assertEqual(captured.exception.reason, "BASIS_TIMEOUT")


if __name__ == "__main__":
    import unittest

    unittest.main()
