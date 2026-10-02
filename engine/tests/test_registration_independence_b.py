from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BODY_B_MODULES = (
    ROOT / "engine" / "registration_admission.py",
    ROOT / "engine" / "registration_basis.py",
    ROOT / "engine" / "registration_runtime.py",
    ROOT / "engine" / "registration_view.py",
)


class RegistrationIndependenceTest(unittest.TestCase):
    def test_body_b_does_not_import_guard_finish_cleanup_or_alert_authority(self) -> None:
        forbidden = {
            "consumer",
            "engine.guard",
            "engine.finish_kernel",
            "engine.integrity_alert",
            "kernel",
        }
        for path in BODY_B_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.add(node.module or "")
            with self.subTest(path=path.name):
                for name in imports:
                    self.assertFalse(
                        any(
                            name == item or name.startswith(item + ".")
                            for item in forbidden
                        ),
                        name,
                    )

    def test_no_body_b_module_defines_alert_outbox_or_cleanup_verbs(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in BODY_B_MODULES
        )
        for forbidden in (
            "registration_alert",
            "registration_outbox",
            "remove-worktree",
            "retire-bookkeeping",
            "finish_current",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_runtime_and_actor_surfaces_cannot_construct_control(self) -> None:
        forbidden = {
            "ControlCapability",
            "_CONTROL_SEAL",
            "authenticate_control",
            "bootstrap",
            "activate",
            "begin_drain",
            "stage_next",
            "cancel_drain",
            "advance_generation",
            "pre_effect_dormant",
            "enter_containment",
            "begin_repair",
            "adopt_effect",
        }
        for path in BODY_B_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            referenced = {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name)
            } | {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
            }
            with self.subTest(path=path.name):
                self.assertEqual(referenced & forbidden, set())


if __name__ == "__main__":
    unittest.main()
