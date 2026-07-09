"""Regression coverage for the corrective real-PM trial harness."""

from __future__ import annotations

import argparse
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from consumer import operator_loop as loop_mod
from consumer import trial_runner as runner
from consumer.trial_fixture import NOTES_FILE, OWNER_FILE, FixtureError, TrialFixture

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
                    confirmation_fingerprint="abc123",
                )
            sent = json.loads(call.call_args.kwargs["input"])
            self.assertEqual(sent["utterance"], "clean up this old copy")
            self.assertIs(sent["confirm"], True)
            self.assertEqual(sent["confirmation_fingerprint"], "abc123")
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
        _, value_leaks = runner._scan_assistant_lines(
            ["The hidden route was __private_route_91__."],
            ["__private_route_91__"],
        )
        self.assertEqual(value_leaks, ["value:__private_route_91__"])

    def test_scripted_request_is_actual_input_and_singleton_answer_is_resolved(self):
        scenario = runner.SCENARIOS[4]
        with mock.patch("sys.stdin", io.StringIO("my exact entered wording\n")):
            actual = runner._scripted_request(
                scenario, scenario["turns"][0], auto=False
            )
        self.assertEqual(actual, "my exact entered wording")
        fixture = mock.Mock()
        fixture.worktree = Path("/tmp/practice-safe-copy")
        target, evidence = runner._resolve_singleton_target("that practice copy", fixture)
        self.assertEqual(target, "/tmp/practice-safe-copy")
        self.assertEqual(
            evidence, "that practice copy -> the practice safe copy"
        )

    def test_warning_fidelity_includes_exact_confirmation_question(self):
        run = runner._new_run(runner.SCENARIOS[3])
        confirmation = {
            "needs_confirmation": True,
            "plain": runner.EXACT_RISK,
            "undo": runner.EXACT_UNDO,
            "point_of_no_return": runner.EXACT_POINT,
            "ask": "different question",
        }
        payload = {
            "pm": {"decision": "awaiting_confirmation", "confirmation": confirmation},
            "internal": {
                "decision": "awaiting_confirmation",
                "leak_markers": [],
            },
        }
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            runner._record_turn(run, payload)
        self.assertFalse(run["warning_exact"])
        confirmation["ask"] = runner.EXACT_ASK
        run = runner._new_run(runner.SCENARIOS[3])
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            runner._record_turn(run, payload)
        self.assertTrue(run["warning_exact"])

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
            result.close()

    def test_results_retained_descriptor_rejects_path_swap_without_touching_victim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "result.md"
            victim = root / "victim.txt"
            victim.write_text("untouched\n", encoding="utf-8")
            result = runner.ResultsLog(str(path), auto=True)
            reserved = root / "reserved-inode"
            path.rename(reserved)
            path.symlink_to(victim)
            with self.assertRaises(runner.TrialFailure):
                result.write()
            self.assertEqual(victim.read_text(encoding="utf-8"), "untouched\n")
            result.close()

    def test_human_failure_is_nonzero_and_auto_is_never_pass(self):
        self.assertEqual(runner.trial_exit_code("PASS"), 0)
        self.assertEqual(runner.trial_exit_code("FAIL"), 1)
        self.assertEqual(runner.trial_exit_code("NOT SCORED"), 0)
        with tempfile.TemporaryDirectory() as td:
            result = runner.ResultsLog(str(Path(td) / "auto.md"), auto=True)
            runner._score_final(result, auto=True)
            self.assertEqual(result.status, "NOT SCORED")
            self.assertNotIn("proven", result.status.lower())
            result.write()
            text = result.path.read_text(encoding="utf-8")
            self.assertIn('"human_gate_passed": false', text)
            self.assertIn('"status": "not_scored"', text)
            result.close()

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
            sandbox.close_if_restored.return_value = None

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
            self.assertIn('"status": "aborted"', text)
            self.assertIn("### Step 1 — Is everything okay?", text)

    def test_results_persist_wording_every_check_answer_and_observed_question_total(self):
        with tempfile.TemporaryDirectory() as td:
            result = runner.ResultsLog(str(Path(td) / "human.md"), auto=False)
            run = runner._new_run(runner.SCENARIOS[2])
            run["actual_requests"] = ["my exact request"]
            run["assistant_lines"] = ["Exact safe assistant wording."]
            run["clarification_questions"] = 1
            run["checklist"] = {
                "plain_english": True,
                "honest_confidence": True,
                "understood_without_help": True,
                "one_question": False,
                "never_guessed": True,
            }
            result.runs = [run]
            result.final_checks = {"zero_technical": True}
            result.status = "FAIL"
            result.write()
            text = result.path.read_text(encoding="utf-8")
            self.assertIn("Exact safe assistant wording.", text)
            self.assertIn("one_question: N", text)
            self.assertIn("zero_technical: Y", text)
            self.assertIn(
                "Times an unclear request cost more than one question (should be 0):** 1",
                text,
            )
            result.close()

    def test_worker_timeout_is_translated(self):
        sandbox = mock.Mock()
        sandbox.worker_env.return_value = {}
        with mock.patch(
            "consumer.trial_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["python"], 30),
        ):
            with self.assertRaisesRegex(runner.TrialFailure, "timed out"):
                runner.WorkerClient(sandbox).turn(
                    on=True, utterance="save my progress", target="/tmp/x"
                )

    def test_sandbox_cleanup_failure_overrides_aborted_status(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = mock.Mock()
            fixture.created_paths = []
            fixture.commands = []
            fixture.worktree = Path(td) / "worktree"
            fixture.facts = {"exists": True}
            fixture.create.return_value = fixture
            fixture.teardown.return_value = True
            sandbox = mock.Mock()
            sandbox.root = Path(td) / "sandbox"
            sandbox.state_preserved = True
            sandbox.restored = True
            sandbox.close_if_restored.return_value = "sandbox cleanup failed: injected"
            worker = mock.Mock()
            worker.turn.side_effect = KeyboardInterrupt
            args = argparse.Namespace(
                auto=True,
                out=str(Path(td) / "cleanup-error.md"),
                router_source=str(Path(td) / "router"),
                governed_root=None,
                personal_root=None,
                awa_cli=None,
                managed_root=None,
            )
            with mock.patch("consumer.trial_runner.HostRouterGuard"), mock.patch(
                "consumer.trial_runner.TrialFixture", return_value=fixture
            ), mock.patch(
                "consumer.trial_runner.RouterSandbox", return_value=sandbox
            ), mock.patch(
                "consumer.trial_runner.WorkerClient", return_value=worker
            ):
                rc = runner._run_trial(args)
            self.assertEqual(rc, 2)
            text = Path(args.out).read_text(encoding="utf-8")
            self.assertIn('"status": "error"', text)
            self.assertIn("sandbox cleanup failed: injected", text)


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
            hostile_hooks = root / "hostile-hooks"
            hostile_hooks.mkdir()
            pre_commit = hostile_hooks / "pre-commit"
            pre_commit.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            pre_commit.chmod(0o755)
            hostile_global = root / "hostile-gitconfig"
            origin = personal / ".awa-trial-origin-bounded-fixture.git"
            hostile_global.write_text(
                "[core]\n\thooksPath = {0}\n"
                "[commit]\n\tgpgSign = true\n"
                '[url "file:///definitely-missing/"]\n\tinsteadOf = {1}\n'.format(
                    hostile_hooks, origin
                ),
                encoding="utf-8",
            )
            env = self._env(root)
            env["GIT_CONFIG_GLOBAL"] = str(hostile_global)
            fixture = TrialFixture(
                awa_repo_root=REPO_ROOT,
                governed_root=root,
                personal_root=personal,
                awa_cli=REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh",
                managed_root=root / "managed",
                nonce="bounded-fixture",
                env=env,
            ).create()
            self.assertTrue(fixture.facts["has_uncommitted_changes"])
            self.assertTrue(fixture.consequence["destroys_unshared_work"])
            self.assertIn("linked-worktree: yes", fixture.status_output)
            self.assertEqual(fixture.env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(fixture.env["GIT_CONFIG_VALUE_0"], os.devnull)
            self.assertEqual(fixture.env["GIT_CONFIG_VALUE_1"], "false")
            self.assertEqual(
                set(fixture.directory_identities),
                {
                    str(fixture.origin),
                    str(fixture.primary),
                    str(fixture.fixture_root),
                    str(fixture.worktree),
                },
            )

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

    def test_supplied_env_drives_defaults_and_command_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env = self._env(root)
            personal = root / "personal"
            personal.mkdir()
            fixture = TrialFixture(
                awa_repo_root=REPO_ROOT,
                governed_root=root,
                personal_root=personal,
                awa_cli=REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh",
                nonce="env-defaults",
                env=env,
            )
            self.assertEqual(
                fixture.managed_root, (root / "data" / "awa" / "trial-fixtures").resolve()
            )
            with mock.patch(
                "consumer.trial_fixture.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["git"], 60),
            ):
                with self.assertRaisesRegex(FixtureError, "timed out"):
                    fixture._run(["git", "--version"])

    def test_notes_symlink_swap_fails_closed_and_preserves_victim(self):
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
                nonce="notes-symlink",
                env=self._env(root),
            ).create()
            victim = root / "victim.txt"
            victim.write_text("do not touch\n", encoding="utf-8")
            notes = fixture.worktree / NOTES_FILE
            notes.unlink()
            notes.symlink_to(victim)
            self.assertFalse(fixture.teardown())
            self.assertIn("read-only command:", fixture.recovery_guidance)
            self.assertIn(str(fixture.worktree), fixture.recovery_guidance)
            self.assertEqual(victim.read_text(encoding="utf-8"), "do not touch\n")

    def test_active_root_blocks_teardown_before_known_edit_is_restored(self):
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
                nonce="active-root",
                env=self._env(root),
            ).create()
            subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(REPO_ROOT / "kernel" / "lib" / "awa_roots.py"),
                    "heartbeat",
                    "--root",
                    str(fixture.worktree),
                    "--pid",
                    str(os.getpid()),
                ],
                env=fixture.env,
                check=True,
                capture_output=True,
                text=True,
            )
            before = (fixture.worktree / NOTES_FILE).read_text(encoding="utf-8")
            self.assertFalse(fixture.teardown())
            after = (fixture.worktree / NOTES_FILE).read_text(encoding="utf-8")
            self.assertEqual(after, before, "active-root refusal must happen before teardown writes")
            self.assertIn("active", fixture.preserved_reason)


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

    def test_real_post_uninstall_failure_and_interrupt_restore(self):
        source = Path(os.environ["AWA_TRIAL_ROUTER_SOURCE"])
        for raised in (runner.TrialFailure("post-uninstall failure"), KeyboardInterrupt()):
            with self.subTest(raised=type(raised).__name__):
                sandbox = runner.RouterSandbox(source)
                observed = None
                try:
                    sandbox.install_and_doctor()
                    sandbox.uninstall_keep_state()
                    try:
                        raise raised
                    except (runner.TrialFailure, KeyboardInterrupt) as exc:
                        observed = type(exc)
                    finally:
                        sandbox.restore()
                    self.assertIs(observed, type(raised))
                    self.assertTrue(sandbox.state_preserved)
                    self.assertTrue(sandbox.restored)
                finally:
                    if not sandbox.restored and sandbox.state_marker.is_file():
                        sandbox.restore()
                    self.assertIsNone(sandbox.close_if_restored())


class TestCIConfiguration(unittest.TestCase):
    def test_router_seam_fails_closed_without_credentials(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ROUTER_SEAM_TOKEN is required", workflow)
        self.assertIn("exit 1", workflow)
        self.assertNotIn("Skipping (green)", workflow)


if __name__ == "__main__":
    unittest.main()
