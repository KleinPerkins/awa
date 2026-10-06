"""Body C A25/A27/A28/A29/A32 provider and authority independence."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from engine.tests import registration_body_c_fixtures as fixtures


ROOT = Path(__file__).resolve().parents[2]


class BodyCFixtureCatalogTest(unittest.TestCase):
    def test_a25_serializer_fixture_covers_every_receiving_seam(self) -> None:
        self.assertEqual(
            {row.event for row in fixtures.A25_SERIALIZERS},
            {
                "preToolUse",
                "beforeShellExecution",
                "beforeReadFile",
                "beforeMCPExecution",
                "subagentStart",
            },
        )
        self.assertTrue(
            any(
                row.reason == "TASK_SUBAGENT_DENIED"
                for row in fixtures.A25_SERIALIZERS
            )
        )

    def test_a27_control_fixture_is_exact_c0_c7(self) -> None:
        self.assertEqual(
            [row.cut for row in fixtures.A27_CONTROL_SEQUENCE],
            [f"C{value}" for value in range(8)],
        )
        self.assertEqual(
            [row.expected_action for row in fixtures.A27_CONTROL_SEQUENCE],
            [
                "INSTALL_BUNDLE",
                "DRAIN_STAGE_PROVE",
                "SWITCH_POINTER",
                "PROVE_DISABLE_OLD",
                "RECONCILE_CUSTODY",
                "ADVANCE",
                "CLEAN_OLD",
                "VERIFY",
            ],
        )

    def test_a28_resolver_fixture_covers_fault_classes(self) -> None:
        by_resolver = {}
        for row in fixtures.A28_RESOLVERS:
            by_resolver.setdefault(row.resolver, set()).add(row.fault)
        self.assertEqual(set(by_resolver), {"close", "successor", "reacquire"})
        for faults in by_resolver.values():
            self.assertTrue(
                {"busy", "ioerr", "enospc", "lock", "reboot", "concurrency"}
                <= faults
            )

    def test_a32_storage_fixture_never_manufactures_durable_claim(self) -> None:
        unavailable = [
            row
            for row in fixtures.A32_STORAGE_CALL_SITES
            if row.expected == "CONTAINMENT_UNAVAILABLE"
        ]
        self.assertEqual(len(unavailable), 1)
        self.assertFalse(unavailable[0].durable_claim)
        self.assertTrue(
            any(
                row.expected == "ZERO_WRITE"
                for row in fixtures.A32_STORAGE_CALL_SITES
            )
        )


class BodyCAuthorityIndependenceTest(unittest.TestCase):
    def test_body_c_runtime_does_not_import_alert_guard_finish_or_cleanup(
        self,
    ) -> None:
        forbidden = {
            "integrity_alert",
            "guard",
            "finish_current",
            "cleanup",
            "active_root",
        }
        for relative in (
            "engine/registration_projection.py",
            "engine/registration_hook_runtime.py",
            "engine/registration_installer.py",
            "engine/registration_host.py",
            "engine/registration_receiver.py",
        ):
            with self.subTest(relative=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(
                            name.name.rsplit(".", 1)[-1]
                            for name in node.names
                        )
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imported.add(node.module.rsplit(".", 1)[-1])
                        imported.update(name.name for name in node.names)
                self.assertTrue(forbidden.isdisjoint(imported), imported)

    def test_adr0020_outbox_and_independent_kernel_files_are_unreferenced(
        self,
    ) -> None:
        combined = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in (
                "engine/registration_projection.py",
                "engine/registration_hook_runtime.py",
                "engine/registration_installer.py",
                "engine/registration_host.py",
                "engine/registration_receiver.py",
            )
        )
        for forbidden in (
            "outbox/",
            "commit_alert_receipt",
            "worktree-guard.sh",
            "finish_current.py",
            "clean --path",
            "active_root",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
