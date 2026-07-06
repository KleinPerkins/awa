"""Parity: the kernel classifier (kernel/lib/awa_policy.py) must AGREE with the engine
classifier (engine/policy.py) on every case.

AWA ships two mirror implementations of the SAME generic policy classifier: the shell kernel
calls `kernel/lib/awa_policy.py` (so the safety guarantee holds with the engine OFF), and the
engine core uses `engine/policy.py`. This test is the anti-drift guard between the two mirrors —
if either changes classification order, a reason string, or a detector, this fails.

Both implementations decide the governed-marker case from the real filesystem, so cases that
exercise it use real temp dirs (one with `_ops/POLICY.md`, one without).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "kernel" / "lib"))

import awa_policy  # noqa: E402  (kernel mirror)
from engine import policy as engine_policy  # noqa: E402  (engine mirror)


def _make_cfgs(**kw):
    """Build the SAME PolicyConfig for each mirror (identical field set)."""
    return engine_policy.PolicyConfig(**kw), awa_policy.PolicyConfig(**kw)


class TestKernelPolicyParity(unittest.TestCase):
    def setUp(self):
        self._plain = tempfile.TemporaryDirectory()
        self._gov = tempfile.TemporaryDirectory()
        self.plain = self._plain.name  # no governance marker
        self.gov = self._gov.name
        marker = Path(self.gov) / "_ops"
        marker.mkdir(parents=True, exist_ok=True)
        (marker / "POLICY.md").write_text("# governed\n", encoding="utf-8")

    def tearDown(self):
        self._plain.cleanup()
        self._gov.cleanup()

    def _assert_agree(self, rel, toplevel, cfg_kw, *, hooks_path="", has_origin=True, is_root=False):
        e_cfg, k_cfg = _make_cfgs(**cfg_kw)
        e = engine_policy.classify(rel, toplevel, e_cfg, hooks_path=hooks_path,
                                   has_origin=has_origin, is_root=is_root)
        k_cls, k_reason = awa_policy.classify(rel, toplevel, k_cfg, hooks_path=hooks_path,
                                              has_origin=has_origin, is_root=is_root)
        label = f"rel={rel!r} hooks={hooks_path!r} origin={has_origin} root={is_root} cfg={cfg_kw}"
        self.assertEqual(e.classification, k_cls, f"class mismatch: {label}")
        self.assertEqual(e.reason, k_reason, f"reason mismatch: {label}")
        return k_cls

    def test_matrix_agrees(self):
        gm = {"governed_markers": ["_ops/POLICY.md"]}
        cases = [
            # (rel, toplevel, cfg_kw, kwargs, expected_class)
            ("foo", self.plain, {"overrides_exclude": ["foo"]}, {}, "exclude"),
            ("foo", self.plain, {"overrides_include": ["foo"], "default": "advisory"}, {}, "include"),
            ("anything", self.plain, {}, {"is_root": True}, "exclude"),
            (".", self.plain, {}, {}, "exclude"),
            ("proj", self.gov, gm, {}, "exclude"),               # self-governed marker
            ("proj", self.plain, {"foreign_hook_frameworks": ["husky"]}, {"hooks_path": "/x/.husky/_"}, "exclude"),
            ("vendor/x", self.plain, {"read_only_paths": ["vendor/*"]}, {}, "exclude"),
            ("skip", self.plain, {"exclude": ["skip"]}, {}, "exclude"),
            ("proj", self.plain, {}, {"has_origin": False}, "advisory"),
            ("proj", self.plain, {"include": ["proj"]}, {}, "include"),
            ("whatever", self.plain, {"default": "include"}, {}, "include"),
            ("whatever", self.plain, {"default": "advisory"}, {}, "advisory"),
            (None, None, {}, {}, "not-git"),
            # precedence: governed marker beats a matching include glob
            ("proj", self.gov, {"governed_markers": ["_ops/POLICY.md"], "include": ["proj"]}, {}, "exclude"),
            # precedence: foreign hook beats include glob (no marker)
            ("proj", self.plain, {"foreign_hook_frameworks": ["lefthook"], "include": ["proj"]},
             {"hooks_path": "/x/lefthook"}, "exclude"),
        ]
        for rel, toplevel, cfg_kw, kwargs, expected in cases:
            got = self._assert_agree(rel, toplevel, cfg_kw, **kwargs)
            self.assertEqual(got, expected, f"unexpected class for rel={rel!r} cfg={cfg_kw}: {got}")

    def test_parse_mini_yaml_agrees(self):
        """Both mirrors parse the same policy YAML subset identically."""
        sample = (
            "version: 1\n"
            "governed_roots:\n  - ~/a\n  - ~/b\n"
            "default: include\n"
            "include:\n  - proj/*\n"
            "detectors:\n  governed_markers:\n    - _ops/POLICY.md\n"
            "  foreign_hook_frameworks:\n    - husky\n"
            "overrides:\n  exclude:\n    - skip/*\n"
        )
        e = engine_policy._parse_mini_yaml(sample)
        k = awa_policy.parse_mini_yaml(sample)
        self.assertEqual(e, k)


if __name__ == "__main__":
    unittest.main()
