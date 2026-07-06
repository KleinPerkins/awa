"""Phase 2: generic policy resolver (mini-YAML parse + zero-link classification)."""

from __future__ import annotations

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
    """Per-repo explicit modes (on|ask_on|off) resolved through classify()."""

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

    def test_explicit_ask_on(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "ask_on"}))
        self.assertEqual(c.classification, policy.ASK_ON)
        self.assertEqual(c.reason, "explicit mode: ask_on")

    def test_invalid_mode_falls_back_to_ask_on(self):
        c = policy.classify("proj", self.top, self._cfg(modes={"proj": "bogus"}))
        self.assertEqual(c.classification, policy.ASK_ON)
        self.assertEqual(c.reason, "invalid explicit mode; safe fallback")

    def test_safety_marker_beats_explicit_on(self):
        c = policy.classify("proj", self.gov,
                            self._cfg(modes={"proj": "on"}, governed_markers=["_ops/POLICY.md"]))
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertIn("self-governed", c.reason)

    def test_safety_marker_beats_explicit_ask_on(self):
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
        cfg = self._cfg(modes={"a": "on", "b/*": "ask_on"})
        self.assertEqual(policy.mode_for("a", cfg), "on")
        self.assertEqual(policy.mode_for("b/x", cfg), "ask_on")
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

    def test_default_mode_ask_on(self):
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="ask_on")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.ASK_ON)
        self.assertEqual(c.reason, "policy default_mode: ask_on")

    def test_default_mode_off(self):
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="off")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertEqual(c.reason, "policy default_mode: off")

    def test_invalid_default_mode_honest_reason(self):
        # An invalid default_mode falls back to safe ask_on but is HONESTLY labeled — not
        # mislabeled as the reason for a validly-configured ask_on.
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="bogus")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.ASK_ON)
        self.assertEqual(c.reason, "invalid default_mode; safe fallback ask_on")

    def test_include_glob_maps_through_default_mode(self):
        cfg = policy.PolicyConfig(include=["proj"], default_mode="ask_on")
        c = policy.classify("proj", self.top, cfg)
        self.assertEqual(c.classification, policy.ASK_ON)

    def test_no_origin_stays_advisory_regardless_of_default_mode(self):
        cfg = policy.PolicyConfig(default=policy.INCLUDE, default_mode="ask_on")
        c = policy.classify("proj", self.top, cfg, has_origin=False)
        self.assertEqual(c.classification, policy.ADVISORY)
        self.assertEqual(c.reason, "no origin remote")

    def test_outside_include_stays_advisory(self):
        cfg = policy.PolicyConfig(default=policy.ADVISORY, default_mode="ask_on")
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


if __name__ == "__main__":
    unittest.main()
