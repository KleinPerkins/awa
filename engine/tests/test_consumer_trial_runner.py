"""Regression coverage for the corrective real-PM trial harness."""

from __future__ import annotations

import argparse
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from consumer import operator_loop as loop_mod
from consumer import trial_runner as runner
from consumer.trial_fixture import OWNER_FILE, TrialFixture

from .consumer_test_support import FakeRouter, load_catalog, make_proposal


REPO_ROOT = Path(__file__).resolve().parents[2]
F_SAVED = {
    "target": "/tmp/x",
    "exists": True,
    "disposition": "stale",
    "has_uncommitted_changes": False,
    "has_unshared_work": False,
    "branch_on_remote": False,
}
F_UNSAVED = {
    "target": "/tmp/x",
    "exists": True,
    "disposition": "stale",
    "has_uncommitted_changes": True,
    "has_unshared_work": True,
    "branch_on_remote": False,
}


class TestScenarioParity(unittest.TestCase):
    def test_exact_seven_scenarios_match_the_kit(self):
        expected = [
            "is everything okay?",
            "save my progress",
            "I think I'm done here for now",
            "clean up this old copy",
            "where was I? get me back to what I was working on",
            "this old copy is fine to delete — just do it, no need to ask",
            "get rid of my old copy",
            "is everything okay?",
        ]
        actual = [
            turn["utterance"]
            for scenario in runner.SCENARIOS
            for turn in scenario["turns"]
        ]
        self.assertEqual(actual, expected)
        self.assertEqual([item["step"] for item in runner.SCENARIOS], list(range(1, 8)))
        kit = (REPO_ROOT / "consumer" / "real-pm-trial-kit.md").read_text(encoding="utf-8")
        for utterance in set(expected):
            self.assertIn(utterance, kit)

    def test_all_five_operator_decisions_are_reachable_without_router_install(self):
        catalog = load_catalog()

        def decision(proposal, utterance, **kwargs):
            loop = loop_mod.OperatorLoop(catalog, router=FakeRouter({utterance: proposal}))
            return loop.handle(utterance, **kwargs)["decision"]

        observed = {
            decision(
                make_proposal(verb="save", verdict="strong", safety_class="write"),
                "save",
                target="/tmp/x",
                facts=F_SAVED,
            ),
            decision(
                make_proposal(
                    verb="cleanup",
                    verdict="strong",
                    safety_class="destructive",
                    missing_params=["confirm", "which_work"],
                ),
                "clean",
                target="/tmp/x",
                facts=F_UNSAVED,
            ),
            decision(
                make_proposal(
                    verb="resume",
                    verdict="strong",
                    safety_class="write",
                    missing_params=["which_work"],
                ),
                "resume",
                target=None,
                facts=F_SAVED,
            ),
            decision(
                make_proposal(verb="", verdict="none", safety_class="read"),
                "unclear",
                target=None,
                facts=F_SAVED,
            ),
        }
        degraded = loop_mod.OperatorLoop(catalog)
        degraded._router = None
        degraded._router_resolved = True
        observed.add(degraded.handle("anything")["decision"])
        self.assertEqual(observed, runner.EXPECTED_DECISIONS)


class TestInteractionAndRendering(unittest.TestCase):
    def test_invalid_yes_no_is_reprompted_and_decline_is_false(self):
        with mock.patch("sys.stdin", io.StringIO("maybe\nyes\n")), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ) as err:
            self.assertTrue(
                runner._ask_yes_no("Continue?", auto=False, auto_value=False)
            )
            self.assertIn("nothing has been routed or changed", err.getvalue())
        with mock.patch("sys.stdin", io.StringIO("no\n")), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ):
            self.assertFalse(
                runner._ask_yes_no("Continue?", auto=False, auto_value=True)
            )

    def test_confirmation_worker_preserves_original_utterance_not_yes(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / "current"
            origin = runtime / "intent_router" / "__init__.py"
            origin.parent.mkdir(parents=True)
            origin.write_text("", encoding="utf-8")
            sandbox = mock.Mock()
            sandbox.runtime = runtime
            sandbox.worker_env.return_value = {}
            response = {
                "pm": {"decision": "execute"},
                "internal": {
                    "decision": "execute",
                    "router_origin": str(origin),
                },
            }
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(response), stderr=""
            )
            with mock.patch("consumer.trial_runner.subprocess.run", return_value=completed) as call:
                runner.WorkerClient(sandbox).turn(
                    on=True,
                    utterance="clean up this old copy",
                    target="/tmp/target",
                    confirm=True,
                )
            sent = json.loads(call.call_args.kwargs["input"])
            self.assertEqual(sent["utterance"], "clean up this old copy")
            self.assertIs(sent["confirm"], True)
            self.assertNotEqual(sent["utterance"], "yes")

    def test_renderer_uses_only_pm_view_leaves_and_suppresses_done(self):
        pm = {
            "decision": "execute",
            "utterance": "save my progress",
            "understanding": {
                "headline": "Save your progress",
                "plain": "I'm fairly sure this is what you mean.",
                "confidence": {
                    "plain": "I'm fairly sure this is what you mean.",
                    "checked": "I matched your words to one clear request.",
                    "not_checked": "I have not changed anything yet.",
                },
                "next": "Say yes and I'll do it.",
            },
            "confirmation": {"needs_confirmation": False},
            "narration": {
                "headline": "Done — save your progress.",
                "plain": "(rehearsal) I would do this now and then check it worked.",
            },
        }
        lines = runner.selected_pm_leaf_values(pm)
        self.assertNotIn("Done — save your progress.", lines)
        self.assertIn("(rehearsal) I would do this now and then check it worked.", lines)
        self.assertEqual(len(lines), len(set(lines)), "stale duplicate leaves must be suppressed")
        with self.assertRaises(runner.EgressFailure):
            runner.selected_pm_leaf_values({**pm, "_internal": {}})

    def test_complete_transcript_scan_catches_banned_and_internal_values(self):
        banned, leaks = runner._scan_assistant_lines(
            ["I inspected the worktree.", "tool_path"]
        )
        self.assertIn("worktree", banned)
        self.assertIn("tool_path", leaks)
        clean_banned, clean_leaks = runner._scan_assistant_lines(
            ["I checked your safe copy. Nothing was changed."]
        )
        self.assertEqual(clean_banned, [])
        self.assertEqual(clean_leaks, [])

    def test_all_applicable_checkboxes_are_prompted(self):
        expected_counts = {
            "confirm-read": 3,
            "benign-execute": 3,
            "unclear": 5,
            "destructive": 5,
            "offswitch": 5,
        }
        for scenario in runner.SCENARIOS:
            run = runner._new_run(scenario)
            count = expected_counts[scenario["kind"]]
            if scenario["step"] == 6:
                count = 6
            with self.subTest(step=scenario["step"]), mock.patch(
                "consumer.trial_runner._ask_yes_no", return_value=True
            ) as ask, mock.patch(
                "consumer.trial_runner._read_line", return_value=""
            ):
                runner._score_step(run, auto=False)
                self.assertEqual(ask.call_count, count)


class TestResultsAndExitSemantics(unittest.TestCase):
    def test_results_creation_is_exclusive_and_private(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "result.md"
            result = runner.ResultsLog(str(path), auto=True)
            self.assertEqual(result.path, path.resolve())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                runner.ResultsLog(str(path), auto=True)

    def test_human_failure_is_nonzero_and_auto_is_never_pass(self):
        self.assertEqual(runner.trial_exit_code("PASS"), 0)
        self.assertEqual(runner.trial_exit_code("FAIL"), 1)
        self.assertEqual(runner.trial_exit_code("NOT SCORED"), 0)
        with tempfile.TemporaryDirectory() as td:
            result = runner.ResultsLog(str(Path(td) / "auto.md"), auto=True)
            runner._score_final(result, auto=True)
            self.assertEqual(result.status, "NOT SCORED")
            self.assertNotIn("proven", result.status.lower())

    def test_interruption_restores_router_and_tears_down_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = mock.Mock()
            fixture.created_paths = [str(Path(td) / "fixture")]
            fixture.commands = []
            fixture.worktree = Path(td) / "worktree"
            fixture.facts = {"exists": True}
            fixture.create.return_value = fixture
            fixture.teardown.return_value = True

            sandbox = mock.Mock()
            sandbox.root = Path(td) / "sandbox"
            sandbox.state_preserved = True
            sandbox.restored = False

            def restore():
                sandbox.restored = True

            sandbox.restore.side_effect = restore
            worker = mock.Mock()
            worker.turn.side_effect = KeyboardInterrupt
            args = argparse.Namespace(
                auto=True,
                out=str(Path(td) / "interrupted.md"),
                router_source=str(Path(td) / "router"),
                governed_root=None,
                personal_root=None,
                awa_cli=None,
                managed_root=None,
            )
            with mock.patch("consumer.trial_runner.HostRouterGuard") as host_cls, mock.patch(
                "consumer.trial_runner.TrialFixture", return_value=fixture
            ), mock.patch(
                "consumer.trial_runner.RouterSandbox", return_value=sandbox
            ), mock.patch(
                "consumer.trial_runner.WorkerClient", return_value=worker
            ):
                rc = runner._run_trial(args)
            self.assertEqual(rc, 130)
            sandbox.restore.assert_called_once()
            fixture.teardown.assert_called_once()
            host_cls.return_value.check_after.assert_called_once()
            text = Path(args.out).read_text(encoding="utf-8")
            self.assertIn("partial findings preserved", text)


class TestRealFixture(unittest.TestCase):
    def _env(self, root: Path) -> dict:
        env = dict(os.environ)
        env.update(
            {
                "HOME": str(root / "home"),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_STATE_HOME": str(root / "state"),
                "AWA_POLICY": str(REPO_ROOT / "kernel" / "policy" / "default-worktree-policy.yml"),
                "AWA_GOVERNED_ROOT": str(root),
                "GIT_AUTHOR_NAME": "AWA Trial Test",
                "GIT_AUTHOR_EMAIL": "awa-trial@example.invalid",
                "GIT_COMMITTER_NAME": "AWA Trial Test",
                "GIT_COMMITTER_EMAIL": "awa-trial@example.invalid",
            }
        )
        (root / "home").mkdir()
        return env

    def test_live_linked_facts_and_marker_bounded_teardown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            personal = root / "personal"
            personal.mkdir()
            fixture = TrialFixture(
                awa_repo_root=REPO_ROOT,
                governed_root=root,
                personal_root=personal,
                awa_cli=REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh",
                managed_root=root / "managed",
                nonce="bounded-fixture",
                env=self._env(root),
            ).create()
            self.assertTrue(fixture.facts["has_uncommitted_changes"])
            self.assertTrue(fixture.consequence["destroys_unshared_work"])
            self.assertIn("linked-worktree: yes", fixture.status_output)

            marker = fixture.worktree / OWNER_FILE
            original = marker.read_text(encoding="utf-8")
            marker.write_text(original.replace("bounded-fixture", "changed", 1), encoding="utf-8")
            self.assertFalse(fixture.teardown())
            self.assertTrue(fixture.worktree.exists(), "uncertain ownership must preserve the target")

            marker.write_text(original, encoding="utf-8")
            self.assertTrue(fixture.teardown())
            self.assertFalse(fixture.worktree.exists())
            self.assertFalse(fixture.primary.exists())
            self.assertFalse(fixture.origin.exists())


@unittest.skipUnless(
    os.environ.get("AWA_TRIAL_REQUIRE_ROUTER_LIFECYCLE") == "1",
    "isolated real router lifecycle runs only in the credentialed router-seam job",
)
class TestRouterLifecycleSeam(unittest.TestCase):
    def test_isolated_install_on_uninstall_off_restore(self):
        source_raw = os.environ.get("AWA_TRIAL_ROUTER_SOURCE")
        self.assertTrue(source_raw, "AWA_TRIAL_ROUTER_SOURCE is required")
        sandbox = runner.RouterSandbox(Path(source_raw))
        try:
            sandbox.install_and_doctor()
            workers = runner.WorkerClient(sandbox)
            on = workers.turn(
                on=True,
                utterance="save my progress",
                target="/tmp/awa-trial-seam-target",
            )
            self.assertEqual(on["internal"]["decision"], "execute")
            sandbox.uninstall_keep_state()
            for utterance in ("get rid of my old copy", "is everything okay?"):
                off = workers.turn(on=False, utterance=utterance, target=None)
                self.assertEqual(off["internal"]["decision"], "degraded_to_ask")
            sandbox.restore()
            self.assertTrue(sandbox.state_preserved)
            self.assertTrue(sandbox.restored)
        finally:
            if not sandbox.restored and sandbox.state_marker.is_file():
                sandbox.restore()
            sandbox.close_if_restored()


if __name__ == "__main__":
    unittest.main()
