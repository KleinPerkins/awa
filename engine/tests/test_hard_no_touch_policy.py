"""ADR 0027 hard-no-touch host-policy schema, matching, and parity tests."""

from __future__ import annotations

import builtins
import dataclasses
import glob
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "kernel" / "lib"))

import awa_policy as kernel_policy  # noqa: E402
from engine import policy as engine_policy  # noqa: E402


_HOME = "/synthetic/home"
_EXACT = "/synthetic/protected/root"
_MANAGED = "/synthetic/managed/namespace"


def _data(
    *,
    exact: object = None,
    managed: object = None,
) -> dict:
    value = {}
    if exact is not None:
        value["exact_roots"] = exact
    if managed is not None:
        value["managed_namespace_prefixes"] = managed
    return {"version": "1", "hard_no_touch_paths": value}


def _decision_tuple(decision: object) -> tuple[object, object, object]:
    return decision.matched, decision.kind, decision.policy_valid


class TestHardNoTouchMatching(unittest.TestCase):
    def _matchers(self, data: dict) -> tuple[object, object]:
        return (
            engine_policy.hard_no_touch_matcher_from_data(data, home=_HOME),
            kernel_policy.hard_no_touch_matcher_from_data(data, home=_HOME),
        )

    def test_exact_root_descendant_and_component_sibling(self):
        for matcher in self._matchers(_data(exact=[_EXACT])):
            with self.subTest(module=matcher.__class__.__module__):
                self.assertEqual(matcher.classify(_EXACT).kind, "exact_root")
                self.assertEqual(
                    matcher.classify(_EXACT + "/child/deep").kind,
                    "exact_root",
                )
                sibling = matcher.classify(_EXACT + "-sibling")
                self.assertFalse(sibling.matched)
                self.assertEqual(sibling.kind, "none")

    def test_managed_namespace_root_and_recursive_descendants(self):
        for matcher in self._matchers(_data(managed=[_MANAGED])):
            with self.subTest(module=matcher.__class__.__module__):
                self.assertEqual(
                    matcher.classify(_MANAGED).kind,
                    "managed_namespace",
                )
                self.assertEqual(
                    matcher.classify(_MANAGED + "/repo/worktree/child").kind,
                    "managed_namespace",
                )
                self.assertFalse(matcher.matches(_MANAGED + "-other/child"))

    def test_tilde_dot_dot_repeated_and_trailing_separator_normalization(self):
        data = _data(
            exact=["~/alpha/./beta/../protected///"],
            managed=["//synthetic//managed/./namespace/"],
        )
        for matcher in self._matchers(data):
            with self.subTest(module=matcher.__class__.__module__):
                self.assertEqual(
                    matcher.exact_roots,
                    ("/synthetic/home/alpha/protected",),
                )
                self.assertEqual(
                    matcher.managed_namespace_prefixes,
                    (_MANAGED,),
                )
                self.assertEqual(
                    matcher.classify(
                        "/synthetic/home/alpha/x/../protected/./child"
                    ).kind,
                    "exact_root",
                )
                self.assertEqual(
                    matcher.classify("//synthetic/managed/namespace/deep").kind,
                    "managed_namespace",
                )

    def test_bare_tilde_expands_from_trusted_home(self):
        for matcher in self._matchers(_data(exact=["~"])):
            self.assertEqual(matcher.exact_roots, (_HOME,))
            self.assertEqual(
                matcher.classify(_HOME + "/child").kind,
                "exact_root",
            )

    def test_exact_kind_wins_deterministically_when_entries_overlap(self):
        data = _data(exact=[_EXACT], managed=[_EXACT])
        for matcher in self._matchers(data):
            self.assertEqual(
                matcher.classify(_EXACT + "/child").kind,
                "exact_root",
            )

    def test_root_entry_matches_every_absolute_candidate(self):
        for matcher in self._matchers(_data(exact=["/"])):
            self.assertEqual(
                matcher.classify("/synthetic/anything").kind,
                "exact_root",
            )

    def test_matcher_and_decision_are_immutable(self):
        matcher = engine_policy.hard_no_touch_matcher_from_data(
            _data(exact=[_EXACT]),
            home=_HOME,
        )
        decision = matcher.classify(_EXACT)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            matcher.valid = False
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.matched = False

    def test_typed_values_copy_inputs_and_enforce_closed_invariants(self):
        for module in (engine_policy, kernel_policy):
            roots = [_EXACT]
            matcher = module.HardNoTouchMatcher(
                exact_roots=roots,
                home=_HOME,
            )
            roots.append("/synthetic/later-mutation")
            self.assertEqual(matcher.exact_roots, (_EXACT,))
            with self.assertRaises(ValueError):
                module.HardNoTouchMatcher(
                    exact_roots=("relative/path",),
                    home=_HOME,
                )
            with self.assertRaises(ValueError):
                module.HardNoTouchDecision(False, "exact_root", True)
            invalid = module.HardNoTouchMatcher.invalid(
                "synthetic_error",
                home=_HOME,
            )
            with self.assertRaises(ValueError):
                invalid.to_policy_value()


class TestHardNoTouchValidation(unittest.TestCase):
    def _assert_invalid(self, data: object) -> None:
        engine = engine_policy.hard_no_touch_matcher_from_data(data, home=_HOME)
        kernel = kernel_policy.hard_no_touch_matcher_from_data(data, home=_HOME)
        for matcher in (engine, kernel):
            with self.subTest(module=matcher.__class__.__module__, data=data):
                self.assertFalse(matcher.valid)
                decision = matcher.classify("/synthetic/ordinary")
                self.assertEqual(
                    _decision_tuple(decision),
                    (True, "invalid_policy", False),
                )
        self.assertEqual(engine.errors, kernel.errors)

    def test_malformed_field_shapes_and_entries_fail_closed(self):
        cases = [
            [],
            {"hard_no_touch_paths": []},
            {"hard_no_touch_paths": "scalar"},
            {"hard_no_touch_paths": {"unknown": []}},
            _data(exact="not-a-list"),
            _data(managed="not-a-list"),
            _data(exact=[""]),
            _data(exact=["relative/path"]),
            _data(exact=["~other/path"]),
            _data(exact=["/synthetic/bad\0path"]),
            _data(exact=["/synthetic/*"]),
            _data(exact=["/synthetic/?"]),
            _data(exact=["/synthetic/[bad]"]),
            _data(exact=["/synthetic/bad]"]),
            _data(exact=[7]),
        ]
        for data in cases:
            self._assert_invalid(data)

    def test_strict_text_ingestion_rejects_fail_open_syntax(self):
        cases = [
            (
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/protected\n"
                "hard_no_touch_paths: {}\n"
            ),
            (
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                '    - "/synthetic/unclosed\n'
            ),
            (
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    ignored-value\n"
            ),
            (
                "hard_no_touch_paths:\n"
                "exact_roots:\n"
                "  - /synthetic/dedented\n"
            ),
            (
                "hard_no_touch_paths:\n"
                "\texact_roots:\n"
                "\t  - /synthetic/tabbed\n"
            ),
            (
                "version: 2\n"
                "hard_no_touch_paths:\n"
                "  exact_roots: []\n"
            ),
            (
                '"hard_no_touch_paths":\n'
                "  exact_roots:\n"
                "    - /synthetic/quoted-key\n"
            ),
            (
                "\ufeffhard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/bom-key\n"
            ),
            (
                '"version": 2\n'
                "hard_no_touch_paths:\n"
                "  exact_roots: []\n"
            ),
            (
                "version: 1\n"
                "version: 2\n"
                "hard_no_touch_paths:\n"
                "  exact_roots: []\n"
            ),
            (
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                '    - "/synthetic/protected\\\\root"\n'
            ),
            (
                "hard_no_touch_paths: {}\n"
                "  exact_roots:\n"
                "    - /synthetic/ignored-child\n"
            ),
            (
                "!!str hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/tagged-key\n"
            ),
            (
                "!<tag:synthetic.example,2026:str> hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/tagged-uri-key\n"
            ),
            (
                "&field hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/anchored-key\n"
            ),
            (
                "? hard_no_touch_paths\n"
                "  exact_roots:\n"
                "    - /synthetic/explicit-key\n"
            ),
            (
                "!!str version: 2\n"
                "hard_no_touch_paths:\n"
                "  exact_roots: []\n"
            ),
            (
                '"hard_no_touch_\\u0070aths":\n'
                "  exact_roots:\n"
                "    - /synthetic/escaped-key\n"
            ),
            (
                "version: 1\n"
                '"vers\\u0069on": 2\n'
                "hard_no_touch_paths:\n"
                "  exact_roots: []\n"
            ),
            (
                "version: 1\n"
                '? "hard_no_touch_pa\\\n'
                '  ths"\n'
                ":\n"
                "  exact_roots:\n"
                "    - /synthetic/multiline-key\n"
            ),
        ]
        for module in (engine_policy, kernel_policy):
            for text in cases:
                with self.subTest(module=module.__name__, text=text):
                    matcher = module.hard_no_touch_matcher_from_text(
                        text,
                        home=_HOME,
                    )
                    self.assertFalse(matcher.valid)
                    self.assertEqual(
                        _decision_tuple(
                            matcher.classify("/synthetic/ordinary")
                        ),
                        (True, "invalid_policy", False),
                    )

    def test_strict_text_ingestion_preserves_quoted_comment_marker(self):
        text = (
            "version: 1\n"
            "hard_no_touch_paths:\n"
            "  exact_roots:\n"
            '    - "/synthetic/protected # literal"\n'
            "  managed_namespace_prefixes: []\n"
        )
        for module in (engine_policy, kernel_policy):
            matcher = module.hard_no_touch_matcher_from_text(text, home=_HOME)
            self.assertTrue(matcher.valid)
            self.assertEqual(
                matcher.exact_roots,
                ("/synthetic/protected # literal",),
            )
            self.assertEqual(
                matcher.classify(
                    "/synthetic/protected # literal/child"
                ).kind,
                "exact_root",
            )

    def test_strict_text_ingestion_accepts_plain_apostrophe_and_ignores_unrelated_children(self):
        text = (
            "version: 1\n"
            "legacy_metadata:\n"
            "  exact_roots:\n"
            "    - /synthetic/unrelated\n"
            "hard_no_touch_paths:\n"
            "  exact_roots:\n"
            "    - /synthetic/operator's/protected\n"
            "  managed_namespace_prefixes: []\n"
            "other_metadata:\n"
            "  managed_namespace_prefixes: []\n"
        )
        for module in (engine_policy, kernel_policy):
            matcher = module.hard_no_touch_matcher_from_text(text, home=_HOME)
            self.assertTrue(matcher.valid)
            self.assertEqual(
                matcher.exact_roots,
                ("/synthetic/operator's/protected",),
            )
            self.assertEqual(
                matcher.classify(
                    "/synthetic/operator's/protected/child"
                ).kind,
                "exact_root",
            )

    def test_missing_trusted_home_fails_closed_only_for_tilde_entries(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            tilde = engine_policy.hard_no_touch_matcher_from_data(
                _data(exact=["~/protected"])
            )
            absolute = engine_policy.hard_no_touch_matcher_from_data(
                _data(exact=[_EXACT])
            )
        self.assertFalse(tilde.valid)
        self.assertTrue(absolute.valid)

    def test_invalid_candidates_fail_closed(self):
        cases = ["", "relative/path", "~other/path", "bad\0path", None, 7]
        for matcher in (
            engine_policy.HardNoTouchMatcher.empty(home=_HOME),
            kernel_policy.HardNoTouchMatcher.empty(home=_HOME),
        ):
            for candidate in cases:
                with self.subTest(
                    module=matcher.__class__.__module__,
                    candidate=candidate,
                ):
                    decision = matcher.classify(candidate)
                    self.assertEqual(
                        _decision_tuple(decision),
                        (True, "invalid_candidate", True),
                    )

    def test_unreadable_or_missing_policy_loader_fails_closed(self):
        missing = "/synthetic/policy/does-not-exist.yml"
        for module in (engine_policy, kernel_policy):
            matcher = module.load_hard_no_touch_matcher(missing, home=_HOME)
            self.assertFalse(matcher.valid)
            self.assertTrue(matcher.matches("/synthetic/ordinary"))
            cfg = module.PolicyConfig.load(missing, home=_HOME)
            self.assertFalse(cfg.hard_no_touch_paths.valid)
            self.assertTrue(
                cfg.hard_no_touch_paths.matches("/synthetic/ordinary")
            )

    def test_config_and_policy_only_loaders_use_strict_text_ingestion(self):
        text = (
            "version: 1\n"
            "hard_no_touch_paths:\n"
            "  exact_roots:\n"
            "    - /synthetic/protected\n"
            "hard_no_touch_paths: {}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yml"
            policy_path.write_text(text, encoding="utf-8")
            for module in (engine_policy, kernel_policy):
                matcher = module.load_hard_no_touch_matcher(
                    policy_path,
                    home=_HOME,
                )
                cfg = module.PolicyConfig.load(policy_path, home=_HOME)
                self.assertFalse(matcher.valid)
                self.assertFalse(cfg.hard_no_touch_paths.valid)
                self.assertTrue(matcher.matches("/synthetic/ordinary"))
                self.assertTrue(
                    cfg.hard_no_touch_paths.matches("/synthetic/ordinary")
                )

    def test_present_old_policy_without_field_is_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yml"
            policy_path.write_text(
                "version: 1\n"
                "default: include\n"
                "include: []\n"
                "exclude: []\n",
                encoding="utf-8",
            )
            for module in (engine_policy, kernel_policy):
                cfg = module.PolicyConfig.load(policy_path, home=_HOME)
                self.assertTrue(cfg.hard_no_touch_paths.valid)
                self.assertEqual(
                    cfg.hard_no_touch_paths.to_policy_value(),
                    {
                        "exact_roots": [],
                        "managed_namespace_prefixes": [],
                    },
                )
                self.assertFalse(
                    cfg.hard_no_touch_paths.matches("/synthetic/ordinary")
                )

    def test_typed_projection_round_trip_preserves_semantics(self):
        original_data = _data(
            exact=["~/alpha/../protected/"],
            managed=[_MANAGED + "/./"],
        )
        for module in (engine_policy, kernel_policy):
            first = module.hard_no_touch_matcher_from_data(
                original_data,
                home=_HOME,
            )
            projected = first.to_policy_value()
            second = module.hard_no_touch_matcher_from_data(
                {"hard_no_touch_paths": projected},
                home=_HOME,
            )
            self.assertTrue(first.valid)
            self.assertEqual(first.to_policy_value(), second.to_policy_value())
            for candidate in (
                "/synthetic/home/protected",
                "/synthetic/home/protected/child",
                _MANAGED,
                _MANAGED + "/child",
                "/synthetic/ordinary",
            ):
                self.assertEqual(
                    _decision_tuple(first.classify(candidate)),
                    _decision_tuple(second.classify(candidate)),
                )


class TestHardNoTouchZeroAccess(unittest.TestCase):
    def test_candidate_classification_performs_zero_target_access(self):
        matchers = (
            engine_policy.hard_no_touch_matcher_from_data(
                _data(exact=[_EXACT], managed=[_MANAGED]),
                home=_HOME,
            ),
            kernel_policy.hard_no_touch_matcher_from_data(
                _data(exact=[_EXACT], managed=[_MANAGED]),
                home=_HOME,
            ),
        )
        forbidden = AssertionError("candidate access is forbidden")
        patches = (
            mock.patch.object(os.path, "realpath", side_effect=forbidden),
            mock.patch.object(os, "stat", side_effect=forbidden),
            mock.patch.object(os, "lstat", side_effect=forbidden),
            mock.patch.object(os, "open", side_effect=forbidden),
            mock.patch.object(os, "read", side_effect=forbidden),
            mock.patch.object(os, "listdir", side_effect=forbidden),
            mock.patch.object(os, "scandir", side_effect=forbidden),
            mock.patch.object(Path, "resolve", side_effect=forbidden),
            mock.patch.object(Path, "stat", side_effect=forbidden),
            mock.patch.object(Path, "lstat", side_effect=forbidden),
            mock.patch.object(Path, "open", side_effect=forbidden),
            mock.patch.object(Path, "read_text", side_effect=forbidden),
            mock.patch.object(builtins, "open", side_effect=forbidden),
            mock.patch.object(glob, "glob", side_effect=forbidden),
            mock.patch.object(subprocess, "run", side_effect=forbidden),
            mock.patch.object(subprocess, "Popen", side_effect=forbidden),
            mock.patch.object(subprocess, "check_output", side_effect=forbidden),
        )
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            for matcher in matchers:
                self.assertEqual(
                    matcher.classify(_EXACT + "/child").kind,
                    "exact_root",
                )
                self.assertEqual(
                    matcher.classify(_MANAGED + "/child").kind,
                    "managed_namespace",
                )
                self.assertFalse(matcher.matches("/synthetic/ordinary"))


class TestHardNoTouchKernelEngineParity(unittest.TestCase):
    def test_schema_projection_decision_and_errors_agree(self):
        cases = [
            {},
            _data(exact=[_EXACT], managed=[_MANAGED]),
            _data(exact=["~/a/../protected/"]),
            _data(exact=["relative"]),
            {"hard_no_touch_paths": {"unexpected": []}},
        ]
        candidates = [
            _EXACT,
            _EXACT + "/child",
            _EXACT + "-sibling",
            _MANAGED,
            _MANAGED + "/child",
            "/synthetic/ordinary",
            "relative",
        ]
        for data in cases:
            engine = engine_policy.hard_no_touch_matcher_from_data(
                data,
                home=_HOME,
            )
            kernel = kernel_policy.hard_no_touch_matcher_from_data(
                data,
                home=_HOME,
            )
            with self.subTest(data=data):
                self.assertEqual(
                    engine_policy.HARD_NO_TOUCH_SCHEMA,
                    "awa-hard-no-touch/v1",
                )
                self.assertEqual(
                    engine_policy.HARD_NO_TOUCH_SCHEMA,
                    kernel_policy.HARD_NO_TOUCH_SCHEMA,
                )
                self.assertEqual(engine.valid, kernel.valid)
                self.assertEqual(engine.errors, kernel.errors)
                if engine.valid:
                    self.assertEqual(
                        engine.to_policy_value(),
                        kernel.to_policy_value(),
                    )
                else:
                    with self.assertRaises(ValueError):
                        engine.to_policy_value()
                    with self.assertRaises(ValueError):
                        kernel.to_policy_value()
                for candidate in candidates:
                    self.assertEqual(
                        _decision_tuple(engine.classify(candidate)),
                        _decision_tuple(kernel.classify(candidate)),
                    )

    def test_nested_mini_yaml_parsing_and_policy_load_agree(self):
        text = (
            "version: 1\n"
            "hard_no_touch_paths:\n"
            "  exact_roots:\n"
            "    - /synthetic/protected/./root/\n"
            "  managed_namespace_prefixes:\n"
            "    - ~/managed/../namespace\n"
        )
        engine_data = engine_policy._parse_mini_yaml(text)
        kernel_data = kernel_policy.parse_mini_yaml(text)
        self.assertEqual(engine_data, kernel_data)
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yml"
            policy_path.write_text(text, encoding="utf-8")
            engine = engine_policy.PolicyConfig.load(
                policy_path,
                home=_HOME,
            ).hard_no_touch_paths
            kernel = kernel_policy.PolicyConfig.load(
                policy_path,
                home=_HOME,
            ).hard_no_touch_paths
        self.assertEqual(engine.to_policy_value(), kernel.to_policy_value())

    def test_strict_text_parity_for_valid_and_malformed_documents(self):
        texts = [
            (
                "version: 1\n"
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/protected/root\n"
                "  managed_namespace_prefixes: []\n"
            ),
            (
                "hard_no_touch_paths:\n"
                "  exact_roots: []\n"
                "hard_no_touch_paths: {}\n"
            ),
            (
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                '    - "/synthetic/unclosed\n'
            ),
        ]
        for text in texts:
            engine = engine_policy.hard_no_touch_matcher_from_text(
                text,
                home=_HOME,
            )
            kernel = kernel_policy.hard_no_touch_matcher_from_text(
                text,
                home=_HOME,
            )
            self.assertEqual(engine.valid, kernel.valid)
            self.assertEqual(engine.errors, kernel.errors)
            if engine.valid:
                self.assertEqual(
                    engine.to_policy_value(),
                    kernel.to_policy_value(),
                )
            self.assertEqual(
                _decision_tuple(engine.classify("/synthetic/protected/root")),
                _decision_tuple(kernel.classify("/synthetic/protected/root")),
            )

    def test_repository_and_lifecycle_policy_meanings_stay_distinct(self):
        data = {
            "version": "1",
            "default": "include",
            "hard_no_touch_paths": {
                "exact_roots": [_EXACT],
                "managed_namespace_prefixes": [],
            },
            "lifecycle_no_touch": ["/synthetic/lifecycle/**"],
            "detectors": {"read_only_paths": ["reference/*"]},
        }
        cfg = engine_policy.PolicyConfig._from_data(
            data,
            "/synthetic/policy.yml",
            home=_HOME,
        )
        self.assertTrue(cfg.hard_no_touch_paths.matches(_EXACT + "/child"))
        self.assertFalse(
            cfg.hard_no_touch_paths.matches("/synthetic/lifecycle/child")
        )
        self.assertEqual(cfg.lifecycle_no_touch, ["/synthetic/lifecycle/**"])
        self.assertEqual(
            engine_policy.classify(
                "project",
                "/synthetic/repository",
                cfg,
            ).classification,
            engine_policy.INCLUDE,
        )
        self.assertEqual(
            engine_policy.classify(
                "reference/repository",
                "/synthetic/repository",
                cfg,
            ).classification,
            engine_policy.EXCLUDE,
        )
        self.assertFalse(
            cfg.hard_no_touch_paths.matches("/synthetic/reference/repository")
        )

    def test_kernel_has_no_engine_router_or_consumer_import(self):
        source = Path(kernel_policy.__file__).read_text(encoding="utf-8")
        tree = compile(source, str(Path(kernel_policy.__file__)), "exec")
        self.assertIsNotNone(tree)
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.lstrip().startswith(("import ", "from "))
        ]
        for forbidden in ("engine", "router", "consumer"):
            self.assertFalse(
                any(
                    line == f"import {forbidden}"
                    or line.startswith(f"from {forbidden}")
                    for line in import_lines
                )
            )


class TestHardNoTouchPolicyCheck(unittest.TestCase):
    def _policy_text(self, hard_no_touch: str = "") -> str:
        return (
            "version: 1\n"
            "governed_roots: []\n"
            "managed_location: ~/.cursor/worktrees\n"
            "default: include\n"
            "include: []\n"
            "exclude: []\n"
            f"{hard_no_touch}"
            "detectors: {}\n"
            "overrides: {}\n"
        )

    def _run_policy_check(self, text: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yml"
            policy_path.write_text(text, encoding="utf-8")
            env = os.environ.copy()
            env["AWA_POLICY"] = str(policy_path)
            return subprocess.run(
                [
                    "bash",
                    str(_REPO / "kernel" / "bin" / "dev-worktree.sh"),
                    "policy-check",
                ],
                cwd=_REPO,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_old_policy_without_field_passes(self):
        result = self._run_policy_check(self._policy_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("policy-check: OK", result.stdout)

    def test_valid_present_field_passes(self):
        result = self._run_policy_check(
            self._policy_text(
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/protected/root\n"
                "  managed_namespace_prefixes:\n"
                "    - ~/synthetic-managed/protected\n"
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("policy-check: OK", result.stdout)

    def test_malformed_present_field_is_rejected(self):
        result = self._run_policy_check(
            self._policy_text(
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - relative/path\n"
                "  managed_namespace_prefixes: []\n"
            )
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "policy-check: FAIL hard_no_touch_paths is malformed",
            result.stderr,
        )

    def test_duplicate_present_field_is_rejected(self):
        result = self._run_policy_check(
            self._policy_text(
                "hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/protected/root\n"
                "  managed_namespace_prefixes: []\n"
                "hard_no_touch_paths: {}\n"
            )
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "policy-check: FAIL hard_no_touch_paths is malformed",
            result.stderr,
        )

    def test_quoted_present_field_is_rejected(self):
        result = self._run_policy_check(
            self._policy_text(
                '"hard_no_touch_paths":\n'
                "  exact_roots:\n"
                "    - /synthetic/protected/root\n"
            )
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "policy-check: FAIL hard_no_touch_paths is malformed",
            result.stderr,
        )

    def test_unsupported_present_field_syntax_is_rejected(self):
        values = [
            (
                "hard_no_touch_paths: {}\n"
                "  exact_roots:\n"
                "    - /synthetic/ignored-child\n"
            ),
            (
                "!!str hard_no_touch_paths:\n"
                "  exact_roots:\n"
                "    - /synthetic/tagged-key\n"
            ),
            (
                '"hard_no_touch_\\u0070aths":\n'
                "  exact_roots:\n"
                "    - /synthetic/escaped-key\n"
            ),
            (
                '? "hard_no_touch_pa\\\n'
                '  ths"\n'
                ":\n"
                "  exact_roots:\n"
                "    - /synthetic/multiline-key\n"
            ),
        ]
        for value in values:
            with self.subTest(value=value):
                result = self._run_policy_check(self._policy_text(value))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "policy-check: FAIL hard_no_touch_paths is malformed",
                    result.stderr,
                )


class TestHardNoTouchGlobalContamination(unittest.TestCase):
    def test_changed_global_bytes_have_no_host_instance_or_consumer_ux(self):
        changed_global_files = [
            "engine/policy.py",
            "engine/tests/test_hard_no_touch_policy.py",
            "kernel/lib/awa_policy.py",
            "kernel/bin/dev-worktree.sh",
            "kernel/policy/default-worktree-policy.yml",
            "README.md",
            "ARCHITECTURE.md",
            "SECURITY.md",
            "docs/adr/0027-hard-no-touch-host-policy.md",
            "docs/plans/hard-no-touch-host-policy-v1.md",
        ]
        forbidden = (
            "chaos" + "-scheduler",
            "/" + "Users/",
            ("shadow" + "sync").lower(),
        )
        for relative in changed_global_files:
            text = (_REPO / relative).read_text(encoding="utf-8").lower()
            for literal in forbidden:
                with self.subTest(path=relative, literal=literal):
                    self.assertNotIn(literal.lower(), text)


if __name__ == "__main__":
    unittest.main()
