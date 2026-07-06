#!/usr/bin/env python3
"""test_emitter.py — focused tests for the AWA dashboard emitter's per-repo MODE surface.

Self-contained (builds scratch git repos in the SYSTEM temp dir, outside any governed repo,
so their commits carry NO governed hooks) and stdlib-only. Runnable directly:

    python3 dashboard/test_emitter.py

or via unittest discovery. Covers the Wave-1 SURFACE contract:
  * classification ``ask_on`` no longer throws in the summary counter (the old KeyError),
  * ``summary.ask_on`` is present and correctly counted when modes are configured,
  * a repo configured ONLY via a ``modes:`` entry (outside include globs) is enumerated,
  * per-repo ``repo.mode`` / ``repo.mode_error`` populate correctly (valid / off / invalid),
  * existing emitter shape (schema, required summary keys, repo fields) stays intact,
  * mode-free policy output omits the optional ``summary.ask_on`` key (byte-stable).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_DASHBOARD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DASHBOARD_DIR))
import emitter  # noqa: E402

_IDENT = (
    "-c", "user.email=awa-test@example.invalid",
    "-c", "user.name=awa-test",
)


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True)


def _make_repo(root: Path, rel: str, *, origin: bool = True) -> str:
    repo = root / rel
    repo.mkdir(parents=True, exist_ok=True)
    _git(str(repo), "init", "-q", ".")
    (repo / "README.md").write_text("# scratch\n", encoding="utf-8")
    _git(str(repo), "add", "-A")
    subprocess.run(["git", "-C", str(repo), *_IDENT, "commit", "-qm", "init"],
                   capture_output=True, text=True, check=True)
    _git(str(repo), "branch", "-M", "main")
    if origin:
        _git(str(repo), "remote", "add", "origin",
             "git@github.com:example/awa-test.git")
    return str(repo)


class _EmitterModeTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-emitter-test.")
        self.root = Path(self._tmp.name) / "gov"
        self.root.mkdir(parents=True, exist_ok=True)
        self._saved_policy = os.environ.get("AWA_POLICY")

    def tearDown(self) -> None:
        if self._saved_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = self._saved_policy
        self._tmp.cleanup()

    def _write_policy(self, text: str) -> None:
        policy = Path(self._tmp.name) / "policy.yml"
        policy.write_text(text, encoding="utf-8")
        os.environ["AWA_POLICY"] = str(policy)

    def _by_rel(self, doc: dict) -> dict:
        return {r["rel"]: r for r in doc["repos"]}


class TestEmitterModeSurface(_EmitterModeTestBase):
    def setUp(self) -> None:
        super().setUp()
        # included/alpha: under include glob, no explicit mode -> default_mode(on) -> include
        _make_repo(self.root, "included/alpha")
        # included/inval: matching modes entry with a bogus value -> invalid -> ask_on fallback
        _make_repo(self.root, "included/inval")
        # included/beta: explicit off -> exclude
        _make_repo(self.root, "included/beta")
        # modeonly/repo: NOT under any include glob; only reachable via its modes entry
        _make_repo(self.root, "modeonly/repo")
        self._write_policy(
            "version: 1\n"
            "default: advisory\n"
            "default_mode: on\n"
            "include:\n"
            "  - included/*\n"
            "modes:\n"
            "  modeonly/repo: ask_on\n"
            "  included/inval: bogus\n"
            "  included/beta: off\n"
        )

    def _build(self) -> dict:
        # A generous timeout keeps CI-slow git probes from degrading rows under test.
        return emitter.build(self.root, timeout=30.0)

    def test_ask_on_does_not_throw(self) -> None:
        # Regression: the old summary map `{...}[cls]` raised KeyError on `ask_on`.
        doc = self._build()  # must not raise
        self.assertEqual(doc["schema"], "awa-worktree/v1")

    def test_summary_ask_on_present_and_counted(self) -> None:
        doc = self._build()
        summary = doc["summary"]
        self.assertIn("ask_on", summary)
        # ask_on repos = modeonly/repo (explicit ask_on) + included/inval (invalid->ask_on)
        self.assertEqual(summary["ask_on"], 2)
        # existing buckets stay correct and mutually exclusive with ask_on
        self.assertEqual(summary["included"], 1)   # included/alpha
        self.assertEqual(summary["excluded"], 1)   # included/beta (explicit off)
        self.assertEqual(summary["advisory"], 0)
        self.assertEqual(summary["repos"], 4)
        self.assertEqual(
            summary["included"] + summary["excluded"] + summary["advisory"] + summary["ask_on"],
            summary["repos"],
        )

    def test_mode_only_root_enumerated(self) -> None:
        doc = self._build()
        by_rel = self._by_rel(doc)
        self.assertIn("modeonly/repo", by_rel,
                      "a repo configured only via a modes entry must be enumerated")
        self.assertEqual(by_rel["modeonly/repo"]["classification"], "ask_on")

    def test_repo_mode_and_mode_error_populate(self) -> None:
        doc = self._build()
        by_rel = self._by_rel(doc)

        alpha = by_rel["included/alpha"]
        self.assertEqual(alpha["mode"], "")            # no matching modes entry
        self.assertEqual(alpha["mode_error"], "")
        self.assertEqual(alpha["classification"], "include")

        beta = by_rel["included/beta"]
        self.assertEqual(beta["mode"], "off")
        self.assertEqual(beta["mode_error"], "")
        self.assertEqual(beta["classification"], "exclude")

        modeonly = by_rel["modeonly/repo"]
        self.assertEqual(modeonly["mode"], "ask_on")
        self.assertEqual(modeonly["mode_error"], "")

        inval = by_rel["included/inval"]
        self.assertEqual(inval["mode"], "invalid")
        self.assertTrue(inval["mode_error"], "invalid mode must set mode_error")
        self.assertEqual(inval["classification"], "ask_on")  # safe fallback

    def test_existing_repo_shape_intact(self) -> None:
        doc = self._build()
        for key in ("schema", "generated_at", "root", "default_base", "summary",
                    "repos", "environment"):
            self.assertIn(key, doc)
        for key in ("repos", "included", "excluded", "advisory", "worktrees", "linked",
                    "dirty", "ahead_of_main", "behind_main", "diverged", "no_base",
                    "orphan_branches"):
            self.assertIn(key, doc["summary"])
        for repo in doc["repos"]:
            for key in ("path", "rel", "name", "classification", "reason", "mode",
                        "mode_error", "owner_repo", "has_base", "worktrees"):
                self.assertIn(key, repo)


class TestEmitterModeFreeBackCompat(_EmitterModeTestBase):
    def test_no_modes_omits_ask_on_key(self) -> None:
        _make_repo(self.root, "included/alpha")
        self._write_policy(
            "version: 1\n"
            "default: advisory\n"
            "default_mode: on\n"
            "include:\n"
            "  - included/*\n"
        )
        doc = emitter.build(self.root, timeout=30.0)
        # No modes configured and no ask_on repos -> optional key absent (byte-stable).
        self.assertNotIn("ask_on", doc["summary"])
        # Every repo still carries the additive (empty) mode fields.
        for repo in doc["repos"]:
            self.assertEqual(repo["mode"], "")
            self.assertEqual(repo["mode_error"], "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
