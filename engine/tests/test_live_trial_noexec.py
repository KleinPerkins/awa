"""Noexec contracts for the comprehensive live-verification trial harness."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_TRIAL_ROOT = _ROOT / "live-verify" / "trial-runner"
sys.path.insert(0, str(_TRIAL_ROOT))
import _trial_lib as trial_lib  # noqa: E402


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} in {path}, found {len(matches)}")
    return matches[0]


class TestLiveTrialNoexec(unittest.TestCase):
    def test_runtime_shell_helpers_do_not_rely_on_script_shebangs(self) -> None:
        with trial_lib.Sandbox() as sandbox:
            hook = sandbox.tmp / "hook.sh"
            hook.write_text(
                "#!/definitely/missing\n"
                "input=\"$(cat)\"\n"
                "printf 'hook:%s\\n' \"$input\"\n",
                encoding="utf-8",
            )
            hook.chmod(0o700)
            hooked = sandbox.run_hook(hook, "payload")
            self.assertEqual(hooked.returncode, 0, hooked.stderr)
            self.assertEqual(hooked.stdout, "hook:payload\n")

            dev_worktree = sandbox.tmp / "dev-worktree.sh"
            dev_worktree.write_text(
                "#!/definitely/missing\nprintf '%s\\n' \"$*\"\n",
                encoding="utf-8",
            )
            dev_worktree.chmod(0o700)
            original = trial_lib.DEV_WORKTREE
            trial_lib.DEV_WORKTREE = dev_worktree
            try:
                finished = sandbox.run_dev_finish(
                    "--preview",
                    cwd=str(sandbox.tmp),
                )
            finally:
                trial_lib.DEV_WORKTREE = original
            self.assertEqual(finished.returncode, 0, finished.stderr)
            self.assertEqual(
                finished.stdout,
                "clean --finish-current --preview\n",
            )

    def test_phase_install_and_uninstall_calls_are_bash_prefixed(self) -> None:
        expectations = (
            ("_trial_phase2.py", "hook_install", "INSTALL_HOOKS", 3),
            ("_trial_phase2.py", "hook_install", "install.sh", 4),
            ("_trial_phase3.py", "uninstall_survival", "INSTALL_SH", 2),
        )
        for filename, function_name, target, expected_count in expectations:
            with self.subTest(
                filename=filename,
                function=function_name,
                target=target,
            ):
                function = _function(_TRIAL_ROOT / filename, function_name)
                matches: list[ast.List | ast.Tuple] = []
                for call in ast.walk(function):
                    if not isinstance(call, ast.Call) or not call.args:
                        continue
                    argv = call.args[0]
                    if not isinstance(argv, (ast.List, ast.Tuple)):
                        continue
                    if target in ast.unparse(argv):
                        matches.append(argv)
                self.assertEqual(len(matches), expected_count)
                for argv in matches:
                    first = argv.elts[0]
                    self.assertIsInstance(first, ast.Constant)
                    self.assertEqual(first.value, "bash")


if __name__ == "__main__":
    unittest.main()
