"""Phase 2: generic policy resolver (mini-YAML parse + zero-link classification)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from engine import policy

# Generic fixture (zero-link: no org-specific literals — those live only in the real
# machine-local policy file, never in shelf-bound engine code/tests). The mechanism
# under test is generic: include/exclude globs + the governed-marker detector.
_POLICY_YAML = """\
version: 1
governed_roots:
  - ~/dev
managed_location: ~/.cursor/worktrees
default: include
include:
  - personal/*
  - capabilities/*
  - work/src/*
exclude:
  - work/src/self-governed-sibling
  - vendorroot/*
  - .
detectors:
  governed_markers:
    - _ops/POLICY.md
  foreign_hook_frameworks:
    - husky
    - lefthook
    - pre-commit
  read_only_paths:
    - vendorroot/*
overrides:
  include: []
  exclude: []
"""


class TestMiniYaml(unittest.TestCase):
    def test_parses_scalars_lists_and_nested_maps(self):
        cfg = self._load()
        self.assertEqual(cfg.version, 1)
        self.assertEqual(cfg.default, "include")
        self.assertIn("personal/*", cfg.include)
        self.assertIn("vendorroot/*", cfg.exclude)
        self.assertIn("_ops/POLICY.md", cfg.governed_markers)
        self.assertIn("husky", cfg.foreign_hook_frameworks)
        self.assertIn("vendorroot/*", cfg.read_only_paths)

    def _load(self) -> policy.PolicyConfig:
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
            fh.write(_POLICY_YAML)
            path = fh.name
        return policy.PolicyConfig.load(path)


class TestClassify(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as fh:
            fh.write(_POLICY_YAML)
            self.path = fh.name
        self.cfg = policy.PolicyConfig.load(self.path)
        self._tmp = tempfile.TemporaryDirectory()
        self.top = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_include_glob(self):
        c = policy.classify("personal/foo", self.top, self.cfg, has_origin=True)
        self.assertEqual(c.classification, policy.INCLUDE)

    def test_exclude_glob(self):
        c = policy.classify("vendorroot/x", self.top, self.cfg, has_origin=True)
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_umbrella_root_excluded(self):
        c = policy.classify(".", self.top, self.cfg, is_root=True)
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_governed_marker_excludes_generically(self):
        # A repo carrying its OWN governance marker is self-governed -> exclude, WITHOUT
        # naming it. This is the zero-link self-governed exclusion mechanism (§D3).
        Path(self.top, "_ops").mkdir()
        Path(self.top, "_ops", "POLICY.md").write_text("policy")
        c = policy.classify("personal/self-governed", self.top, self.cfg, has_origin=True)
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertIn("self-governed", c.reason)

    def test_foreign_hook_excludes(self):
        c = policy.classify("personal/withhusky", self.top, self.cfg,
                            hooks_path="/x/.husky", has_origin=True)
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_no_origin_advisory(self):
        c = policy.classify("personal/noremote", self.top, self.cfg, has_origin=False)
        self.assertEqual(c.classification, policy.ADVISORY)

    def test_outside_include_defaults(self):
        cfg = policy.PolicyConfig.load(self.path)
        cfg.default = policy.ADVISORY
        c = policy.classify("random/path", self.top, cfg, has_origin=True)
        self.assertEqual(c.classification, policy.ADVISORY)


class TestExplicitModes(unittest.TestCase):
    """Per-repo explicit modes (on|off) resolved through classify(). One fail-safe rule: only
    `off` disables; ANY other value (a removed legacy value, a typo) resolves to include."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.top = self._tmp.name  # plain toplevel (no governance marker)
        self._gov = tempfile.TemporaryDirectory()
        self.gov = self._gov.name
        Path(self.gov, "_ops").mkdir()
        Path(self.gov, "_ops", "POLICY.md").write_text("policy")

    def tearDown(self):
        self._tmp.cleanup()
        self._gov.cleanup()

    def _cfg(self, **kw) -> policy.PolicyConfig:
        return policy.PolicyConfig(**kw)

    def test_explicit_on(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "on"}))
        self.assertEqual(c.classification, policy.INCLUDE)
        self.assertEqual(c.reason, "explicit mode: on")

    def test_explicit_off(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "off"}))
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertEqual(c.reason, "explicit mode: off")

    def test_legacy_value_maps_to_include(self):
        # A removed legacy value (e.g. the retired ask_on) is not `off`, so it fails safe to
        # include/ON (protected) — no legacy-specific branch, the generic non-off rule.
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "ask_on"}))
        self.assertEqual(c.classification, policy.INCLUDE)
        self.assertEqual(c.reason, "explicit mode: on")

    def test_invalid_mode_maps_to_include(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "bogus"}))
        self.assertEqual(c.classification, policy.INCLUDE)
        self.assertEqual(c.reason, "explicit mode: on")

    def test_safety_marker_beats_explicit_on(self):
        c = policy.classify("proj", self.gov,
                            self._cfg(modes={"proj": "on"}, governed_markers=["_ops/POLICY.md"]))
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertIn("self-governed", c.reason)

    def test_safety_marker_beats_legacy_value(self):
        # A safety exclude (self-governed marker) still wins over a non-off explicit value.
        c = policy.classify("proj", self.gov,
                            self._cfg(modes={"proj": "ask_on"}, governed_markers=["_ops/POLICY.md"]))
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_safety_marker_beats_invalid_mode(self):
        c = policy.classify("proj", self.gov,
                            self._cfg(modes={"proj": "bogus"}, governed_markers=["_ops/POLICY.md"]))
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_umbrella_beats_explicit_on(self):
        c = policy.classify(".", self.top, self._cfg(modes={".": "on"}), is_root=True)
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_foreign_hook_beats_explicit_on(self):
        c = policy.classify("proj", self.top,
                            self._cfg(modes={"proj": "on"}, foreign_hook_frameworks=["husky"]),
                            hooks_path="/x/.husky/_")
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_readonly_beats_explicit_on(self):
        c = policy.classify("vendor/x", self.top,
                            self._cfg(modes={"vendor/*": "on"}, read_only_paths=["vendor/*"]))
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_off_beats_legacy_override_include(self):
        c = policy.classify("proj", self.gov,
                            self._cfg(modes={"proj": "off"}, overrides_include=["proj"],
                                      governed_markers=["_ops/POLICY.md"]))
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertEqual(c.reason, "explicit mode: off")  # OFF wins even over safety + legacy

    def test_off_beats_include_glob(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "off"}, include=["proj"]))
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertEqual(c.reason, "explicit mode: off")

    def test_off_beats_default_include(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "off"}, default=policy.INCLUDE))
        self.assertEqual(c.classification, policy.EXCLUDE)

    def test_exact_beats_glob_first_match(self):
        cfg = self._cfg(modes={"personal/foo": "off", "personal/*": "on"})
        self.assertEqual(policy.classify("personal/foo", self.top, cfg).classification, policy.EXCLUDE)
        self.assertEqual(policy.classify("personal/bar", self.top, cfg).classification, policy.INCLUDE)

    def test_exact_beats_glob_when_glob_listed_first(self):
        # Reversed insertion order: the glob precedes the exact key, but the EXACT key must
        # still win (docs promise "exact keys preferred", not pure first-match).
        cfg = self._cfg(modes={"personal/*": "on", "personal/foo": "off"})
        self.assertEqual(policy.classify("personal/foo", self.top, cfg).classification, policy.EXCLUDE)
        self.assertEqual(policy.classify("personal/bar", self.top, cfg).classification, policy.INCLUDE)
        self.assertEqual(policy.mode_for("personal/foo", cfg), "off")
        self.assertEqual(policy.mode_for("personal/bar", cfg), "on")

    def test_mode_for_helper(self):
        # mode_for returns the RAW configured value verbatim (the dashboard uses it to render an
        # "invalid" badge); classification is what applies the fail-safe.
        cfg = self._cfg(modes={"a": "on", "b/*": "off", "c": "bogus"})
        self.assertEqual(policy.mode_for("a", cfg), "on")
        self.assertEqual(policy.mode_for("b/x", cfg), "off")
        self.assertEqual(policy.mode_for("c", cfg), "bogus")   # raw passthrough (unknown)
        self.assertEqual(policy.mode_for("nope", cfg), "")


class TestDefaultMode(unittest.TestCase):
    """default_mode maps eligible (would-be-include) repos with no explicit entry."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.top = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_default_mode_on_is_backcompat(self):
        # default_mode="on" (the default) reproduces today's classification AND reason.
        cfg = policy.PolicyConfig(default=policy.INCLUDE, include=["proj"])
        self.assertEqual(cfg.default_mode, "on")
        inc = policy.classify("proj", self.top, cfg)
        self.assertEqual((inc.classification, inc.reason), (policy.INCLUDE, "included by workspace policy"))
        dfl = policy.classify("other", self.top, cfg)
        self.assertEqual((dfl.classification, dfl.reason), (policy.INCLUDE, "policy default: include"))

    def test_legacy_default_mode_maps_to_include(self):
        # A removed legacy default_mode (ask_on) is not `off`, so eligible repos fail safe to
        # include/ON. The reason is the ordinary eligibility reason (no legacy-specific label).
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="ask_on")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.INCLUDE)
        self.assertEqual(c.reason, "policy default: include")

    def test_default_mode_off(self):
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="off")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertEqual(c.reason, "policy default_mode: off")

    def test_invalid_default_mode_maps_to_include(self):
        # An invalid default_mode is not `off`, so it fails safe to include/ON (protected).
        # (policy-check separately WARNs on an unknown default_mode; classification stays safe.)
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="bogus")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.INCLUDE)
        self.assertEqual(c.reason, "policy default: include")

    def test_include_glob_maps_through_default_mode(self):
        # An include-glob hit with a non-off default_mode is include (reason from the glob).
        cfg = policy.PolicyConfig(include=["proj"], default_mode="ask_on")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.INCLUDE)
        self.assertEqual(c.reason, "included by workspace policy")

    def test_no_origin_stays_advisory_regardless_of_default_mode(self):
        # No-origin short-circuits to advisory BEFORE eligibility, so even default_mode=off cannot
        # make it exclude — advisory is a separate classification, never conflated with mode.
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="off")
        c = policy.classify("proj", self.top, cfg, has_origin=False)
        self.assertEqual(c.classification, policy.ADVISORY)
        self.assertEqual(c.reason, "no origin remote")

    def test_outside_include_stays_advisory(self):
        cfg = policy.PolicyConfig(default=policy.ADVISORY, default_mode="on")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.ADVISORY)


class TestModesFile(unittest.TestCase):
    """modes_file pointer: read referenced file, merge over inline (file wins)."""

    def _write(self, dirpath: str, name: str, text: str) -> str:
        p = Path(dirpath) / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_modes_file_load_and_inline_merge(self):
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "worktree-modes.yml",
                        "schema: awa-modes/v1\n"
                        "default_mode: ask_on\n"
                        "modes:\n"
                        "  proj: ask_on\n"
                        "  extra: on\n")
            pol = self._write(d, "worktree-policy.yml",
                              "version: 1\n"
                              "default: include\n"
                              "default_mode: on\n"
                              "modes_file: worktree-modes.yml\n"
                              "modes:\n"
                              "  proj: on\n"
                              "  other: off\n")
            cfg = policy.PolicyConfig.load(pol)
            # modes_file wins on key collision; loader preserves stored bytes verbatim
            # (classify/mode-for apply the fail-safe rule at read time).
            self.assertEqual(cfg.modes["proj"], "ask_on")   # file wins on collision
            self.assertEqual(cfg.modes["other"], "off")     # inline preserved
            self.assertEqual(cfg.modes["extra"], "on")      # file-only preserved
            self.assertEqual(cfg.default_mode, "ask_on")    # file default_mode wins

    def test_default_mode_defaults_to_on_when_unset(self):
        with tempfile.TemporaryDirectory() as d:
            pol = self._write(d, "worktree-policy.yml", "version: 1\ndefault: include\n")
            cfg = policy.PolicyConfig.load(pol)
            self.assertEqual(cfg.default_mode, "on")
            self.assertEqual(cfg.modes, {})

    def test_inline_modes_only(self):
        with tempfile.TemporaryDirectory() as d:
            pol = self._write(d, "worktree-policy.yml",
                              "version: 1\ndefault_mode: ask_on\nmodes:\n  proj: off\n")
            cfg = policy.PolicyConfig.load(pol)
            self.assertEqual(cfg.modes, {"proj": "off"})
            self.assertEqual(cfg.default_mode, "ask_on")


class TestUnreadableModesFile(unittest.TestCase):
    """Unreadable/non-regular referenced modes files force a protected posture."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.top = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _policy_with_modes_file(self, d: str, modes_name: str) -> str:
        pol = Path(d) / "worktree-policy.yml"
        pol.write_text(
            "version: 1\n"
            "default: include\n"
            f"modes_file: {modes_name}\n",
            encoding="utf-8",
        )
        return str(pol)

    def test_modes_file_is_a_directory_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "worktree-modes.yml").mkdir()  # a DIRECTORY where a file is expected
            pol = self._policy_with_modes_file(d, "worktree-modes.yml")
            cfg = policy.PolicyConfig.load(pol)   # must NOT raise
            self.assertEqual(cfg.modes, {})
            self.assertEqual(cfg.default_mode, "on")  # back-compat default preserved
            c = policy.classify("proj", self.top, cfg, has_origin=True)
            self.assertNotEqual(c.classification, policy.ADVISORY)
            self.assertEqual(c.classification, policy.INCLUDE)  # protective (guard asks)

    def test_directory_forces_on_over_inline_off(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "worktree-modes.yml").mkdir()
            pol = Path(d) / "worktree-policy.yml"
            pol.write_text(
                "version: 1\n"
                "default: include\n"
                "default_mode: off\n"
                "modes_file: worktree-modes.yml\n"
                "modes:\n"
                "  proj: off\n",
                encoding="utf-8",
            )
            cfg = policy.PolicyConfig.load(pol)
            self.assertEqual(cfg.default_mode, "on")
            self.assertEqual(cfg.modes, {"proj": "on"})
            self.assertEqual(
                policy.classify("proj", self.top, cfg, has_origin=True).classification,
                policy.INCLUDE,
            )

    def test_fifo_is_rejected_without_blocking_and_forces_on(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO support unavailable")
        with tempfile.TemporaryDirectory() as d:
            os.mkfifo(Path(d) / "worktree-modes.yml")
            pol = Path(d) / "worktree-policy.yml"
            pol.write_text(
                "version: 1\n"
                "default: include\n"
                "default_mode: off\n"
                "modes_file: worktree-modes.yml\n",
                encoding="utf-8",
            )
            cfg = policy.PolicyConfig.load(pol)
            self.assertEqual(cfg.default_mode, "on")
            self.assertEqual(cfg.modes, {})

    def test_modes_file_chmod_000_forces_on(self):
        with tempfile.TemporaryDirectory() as d:
            mf = Path(d) / "worktree-modes.yml"
            mf.write_text("schema: awa-modes/v1\ndefault_mode: off\n", encoding="utf-8")
            os.chmod(mf, 0o000)
            try:
                pol = self._policy_with_modes_file(d, "worktree-modes.yml")
                cfg = policy.PolicyConfig.load(pol)   # must NOT raise
                # Unreadable -> forced ON: the `off` default inside is not honored.
                self.assertEqual(cfg.default_mode, "on")
                c = policy.classify("proj", self.top, cfg, has_origin=True)
                self.assertNotEqual(c.classification, policy.ADVISORY)
                self.assertEqual(c.classification, policy.INCLUDE)
            finally:
                os.chmod(mf, 0o600)  # restore so TemporaryDirectory cleanup succeeds


class TestMissingPolicy(unittest.TestCase):
    """#9: a missing policy path returns safe defaults (parity with the kernel mirror)."""

    def test_missing_policy_returns_defaults(self):
        cfg = policy.PolicyConfig.load("/nonexistent/worktree-policy.yml")
        self.assertEqual(cfg.default, policy.INCLUDE)
        self.assertEqual(cfg.default_mode, "on")
        self.assertEqual(cfg.modes, {})


if __name__ == "__main__":
    unittest.main()
