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


if __name__ == "__main__":
    unittest.main()
