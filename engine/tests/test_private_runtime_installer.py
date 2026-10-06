"""V7 root-private runtime installer tests over a synthetic filesystem."""

from __future__ import annotations

import hashlib
import unittest

from engine import registration_privileged_installer as privileged


RUNTIME_DIGEST = "1" * 64
MANIFEST_DIGEST = "2" * 64
Q2_MANIFEST_DIGEST = "9" * 64
SOURCE_LOCK_DIGEST = (
    "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
)
EXACT_HEAD = "03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d"


def _request(
    operation: str,
    *,
    current: privileged.CurrentRecord | None = None,
    request_id: str = "a" * 64,
) -> privileged.PrivilegedRequest:
    return privileged.PrivilegedRequest.synthetic_qualification(
        operation=operation,
        requested_uid="501",
        request_id=request_id,
        qualification_nonce="b" * 64,
        packet_root_digest="3" * 64,
        qualification_context_digest="4" * 64,
        qualification_allowed_signers_digest="5" * 64,
        current=current,
        q1_envelope_digest="6" * 64,
        q1_manifest_sha256=MANIFEST_DIGEST,
        q2_envelope_digest="7" * 64,
        q2_manifest_sha256=Q2_MANIFEST_DIGEST,
        created_wall_ns="1000000000",
    )


class InstallerStateMachineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = privileged.MemoryAdminBackend()
        self.installer = privileged.PrivateRuntimeInstaller(self.backend)

    def test_install_publishes_current_only_after_durable_payload(self) -> None:
        receipt = self.installer.apply(_request("INSTALL"))
        self.assertEqual(receipt.outcome, "SUCCESS")
        self.assertEqual(receipt.reason_code, "OK")
        self.assertEqual(
            self.backend.current.active_manifest_sha256,
            MANIFEST_DIGEST,
        )
        self.assertEqual(
            self.backend.current.version_root,
            f"/Library/Application Support/AWA/runtime/versions/{MANIFEST_DIGEST}",
        )
        events = self.backend.events
        self.assertLess(events.index("payload:sync"), events.index("current:replace"))
        self.assertLess(events.index("current:replace"), events.index("parent:sync"))
        self.assertEqual(events[-1], "audit:append")

    def test_v12_runtime_and_product_currents_publish_as_one_commit(self) -> None:
        receipt = self.installer.apply(_request("INSTALL"))
        self.assertEqual(receipt.outcome, "SUCCESS")
        self.assertTrue(
            hasattr(self.backend, "product_current"),
            "installer did not publish product-current authority",
        )
        self.assertIsNotNone(self.backend.current)
        self.assertIsNotNone(self.backend.product_current)
        self.assertEqual(
            self.backend.product_current.runtime_current_digest,
            self.backend.current.current_digest,
        )
        before = self.backend.snapshot()
        self.backend.fail_at = "currents:parent-sync"
        failed = self.installer.apply(
            _request(
                "UPDATE",
                current=self.backend.current,
                request_id="d" * 64,
            )
        )
        self.assertEqual(failed.outcome, "FAILED")
        after = self.backend.snapshot()
        self.assertEqual(after.current, before.current)
        self.assertEqual(after.product_current, before.product_current)

    def test_update_rejects_stale_current_and_preserves_prior(self) -> None:
        self.installer.apply(_request("INSTALL", request_id="a" * 64))
        before = self.backend.snapshot()
        stale = _request(
            "UPDATE",
            current=self.backend.current,
            request_id="c" * 64,
        )
        stale = stale.replace(pre_current_digest="8" * 64)
        receipt = self.installer.apply(stale)
        self.assertEqual(receipt.outcome, "REFUSED")
        self.assertEqual(receipt.reason_code, "CONTEXT_MISMATCH")
        self.assertEqual(self.backend.current, before.current)
        self.assertEqual(self.backend.runtime_roots, before.runtime_roots)

    def test_remove_deletes_only_exact_selected_digest(self) -> None:
        self.installer.apply(_request("INSTALL", request_id="a" * 64))
        self.backend.runtime_roots["8" * 64] = b"unrelated"
        remove = _request(
            "REMOVE",
            current=self.backend.current,
            request_id="c" * 64,
        )
        receipt = self.installer.apply(remove)
        self.assertEqual(receipt.outcome, "SUCCESS")
        self.assertEqual(receipt.reason_code, "OK")
        self.assertIsNone(self.backend.current)
        self.assertNotIn(MANIFEST_DIGEST, self.backend.runtime_roots)
        self.assertEqual(self.backend.runtime_roots["8" * 64], b"unrelated")

    def test_fault_matrix_never_publishes_partial_current(self) -> None:
        operations = ("INSTALL", "UPDATE", "ROLLBACK", "REMOVE")
        fault_points = privileged.MemoryAdminBackend.FAULT_POINTS
        for operation in operations:
            for fault in fault_points:
                with self.subTest(operation=operation, fault=fault):
                    backend = privileged.MemoryAdminBackend()
                    installer = privileged.PrivateRuntimeInstaller(backend)
                    if operation != "INSTALL":
                        installer.apply(
                            _request("INSTALL", request_id="a" * 64)
                        )
                    if operation in {"ROLLBACK", "REMOVE"}:
                        installer.apply(
                            _request(
                                "UPDATE",
                                current=backend.current,
                                request_id="c" * 64,
                            )
                        )
                    before = backend.snapshot()
                    request = _request(
                        operation,
                        current=backend.current,
                        request_id=hashlib.sha256(
                            f"{operation}:{fault}".encode()
                        ).hexdigest(),
                    )
                    backend.fail_at = fault
                    receipt = installer.apply(request)
                    self.assertIn(receipt.outcome, {"FAILED", "SUCCESS"})
                    if receipt.outcome == "FAILED":
                        self.assertEqual(
                            backend.current,
                            before.current,
                            msg=f"{operation}:{fault}",
                        )
                        self.assertFalse(
                            any(
                                event == "current:partial"
                                for event in backend.events
                            )
                        )

    def test_duplicate_nonce_is_idempotent_and_conflicting_reuse_refuses(self) -> None:
        request = _request("INSTALL")
        first = self.installer.apply(request)
        events = tuple(self.backend.events)
        replay = self.installer.apply(request)
        self.assertEqual(replay, first)
        self.assertEqual(tuple(self.backend.events), events)
        conflict = request.replace(target_manifest_sha256="8" * 64)
        refused = self.installer.apply(conflict)
        self.assertEqual(refused.outcome, "REFUSED")
        self.assertEqual(refused.reason_code, "NONCE_REPLAY")

    def test_root_tree_and_qualification_trust_are_structurally_isolated(
        self,
    ) -> None:
        self.installer.apply(_request("INSTALL"))
        snapshot = self.backend.snapshot()
        self.assertEqual(
            snapshot.directories,
            privileged.EXACT_ROOT_DIRECTORIES,
        )
        for path, metadata in snapshot.metadata.items():
            with self.subTest(path=path):
                self.assertEqual(metadata.owner, "root")
                self.assertEqual(metadata.group, "wheel")
                self.assertFalse(metadata.symlink)
                self.assertEqual(metadata.link_count, 1)
        self.assertNotIn("qualification", "\n".join(snapshot.directories).lower())
        self.assertFalse(
            any("private" in key.lower() for key in snapshot.trust_material)
        )

    def test_artifact_hashes_are_computed_not_caller_supplied(self) -> None:
        receipt = self.installer.apply(_request("INSTALL"))
        expected = hashlib.sha256(self.backend.current.to_bytes()).hexdigest()
        self.assertEqual(self.backend.current.file_sha256, expected)
        self.assertEqual(
            receipt.current_manifest_sha256,
            self.backend.current.active_manifest_sha256,
        )

    def test_exact_q1_q2_orchestration_ends_removed_at_epoch_four(self) -> None:
        planner_backend = privileged.MemoryAdminBackend()
        planner = privileged.PrivateRuntimeInstaller(planner_backend)
        planned = []
        for operation, request_id in (
            ("INSTALL", "1" * 64),
            ("UPDATE", "2" * 64),
            ("ROLLBACK", "3" * 64),
            ("REMOVE", "4" * 64),
        ):
            request = _request(
                operation,
                current=planner_backend.current,
                request_id=request_id,
            )
            planned.append(request)
            self.assertEqual(planner.apply(request).outcome, "SUCCESS")
        parent = _request("QUALIFY", request_id="5" * 64)
        backend = privileged.MemoryAdminBackend()
        lifecycle = privileged.QualificationLifecycle(
            privileged.PrivateRuntimeInstaller(backend)
        )
        receipt, children = lifecycle.run(parent, planned)
        self.assertEqual(receipt.outcome, "SUCCESS")
        self.assertEqual(receipt.post_epoch, "4")
        self.assertEqual(
            tuple(child.operation for child in children),
            ("INSTALL", "UPDATE", "ROLLBACK", "REMOVE"),
        )
        self.assertIsNone(backend.current)


class OperationOutcomeMatrixTest(unittest.TestCase):
    def test_exact_operation_outcome_reason_null_matrix(self) -> None:
        matrix = privileged.ADMIN_AUDIT_MATRIX
        expected = {
            (operation, outcome)
            for operation in (
                "INSTALL",
                "UPDATE",
                "ROLLBACK",
                "REMOVE",
                "QUALIFY",
            )
            for outcome in ("SUCCESS", "REFUSED", "FAILED", "CANCELLED")
        }
        self.assertEqual(set(matrix), expected)
        for row in matrix:
            with self.subTest(row=row):
                receipt = privileged.AdminAuditReceipt.synthetic_for_matrix(row)
                receipt.validate()
                self.assertEqual(
                    receipt.null_fields(),
                    privileged.ADMIN_AUDIT_MATRIX[row],
                )


if __name__ == "__main__":
    unittest.main()
