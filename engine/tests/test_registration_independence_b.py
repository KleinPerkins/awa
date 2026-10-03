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

    def test_body_b_uses_only_public_typed_store_boundaries(self) -> None:
        basis_changing = {
            "install_member",
            "bind_episode",
            "invalidate_requested",
            "set_pending",
            "replace_pending",
            "handoff_resolved",
            "mark_dead_executor_unavailable",
        }
        for path in BODY_B_MODULES:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            private_access = {
                node.attr
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute)
                and node.attr in {"_locks", "_connection"}
            }
            private_keywords = {
                keyword.arg
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                for keyword in node.keywords
                if keyword.arg == "_member_lock"
            }
            direct_store_calls = set()
            for node in ast.walk(tree):
                if (
                    not isinstance(node, ast.Call)
                    or not isinstance(node.func, ast.Attribute)
                    or node.func.attr not in basis_changing
                ):
                    continue
                receiver = node.func.value
                if (
                    isinstance(receiver, ast.Attribute)
                    and receiver.attr == "store"
                ):
                    direct_store_calls.add(node.func.attr)
            with self.subTest(path=path.name):
                self.assertEqual(private_access, set())
                self.assertEqual(private_keywords, set())
                self.assertEqual(direct_store_calls, set())
                self.assertNotIn("SELECT ", source)
                self.assertNotIn("INSERT ", source)
                self.assertNotIn("UPDATE ", source)
                self.assertNotIn("DELETE ", source)


if __name__ == "__main__":
    unittest.main()
