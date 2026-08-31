#!/usr/bin/env python3
"""Focused tests for fast-by-default dashboard publication."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_DASHBOARD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DASHBOARD_DIR))
import render  # noqa: E402


_VALID_DOC = {
    "schema": "awa-worktree/v1",
    "generated_at": "2026-08-31T00:00:00+00:00",
    "root": "/fixture",
    "default_base": "main",
    "detail": "fast",
    "summary": {
        "repos": 1,
        "included": 1,
        "excluded": 0,
        "advisory": 0,
        "worktrees": 1,
        "linked": 0,
        "dirty": 0,
        "ahead_of_main": 0,
        "behind_main": 0,
        "diverged": 0,
        "no_base": 0,
        "orphan_branches": 0,
    },
    "repos": [{
        "path": "/fixture/repo",
        "rel": "repo",
        "name": "repo",
        "classification": "include",
        "reason": "fixture",
        "mode": "",
        "mode_error": "",
        "owner_repo": "example/repo",
        "has_base": True,
        "base_ref": "refs/heads/main",
        "default_base": "main",
        "branches": ["main"],
        "orphan_branches": [],
        "worktrees": [{
            "path": "/fixture/repo",
            "branch": "main",
            "detached": False,
            "is_primary": True,
            "is_linked": False,
            "locked": False,
            "prunable": False,
            "head": "0123456",
            "dirty": False,
            "dirty_count": 0,
            "size_bytes": None,
            "ahead": 0,
            "behind": 0,
            "ab_status": "even",
            "is_base_branch": True,
            "last_commit_ts": None,
            "last_commit_subject": None,
            "enrichment_state": "not_checked",
            "plain_size": "not checked",
        }],
    }],
    "environment": {},
}


class TestRenderDetailProfile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-render-test.")
        self.root = Path(self._tmp.name) / "root"
        self.root.mkdir()
        self.canvas_dir = Path(self._tmp.name) / "canvases"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_publish_requests_fast_by_default_and_renders_not_checked(self) -> None:
        with mock.patch.object(
            render.emitter, "build", return_value=copy.deepcopy(_VALID_DOC),
        ) as build:
            result = render.publish(self.root, canvas_dir=self.canvas_dir)
        build.assert_called_once_with(self.root.resolve(), 4.0, detail="fast")
        rendered = Path(result["canvas"]).read_text(encoding="utf-8")
        self.assertIn('"detail": "fast"', rendered)
        self.assertIn('"enrichment_state": "not_checked"', rendered)
        self.assertIn('"plain_size": "not checked"', rendered)

    def test_seed_renders_unqueried_history_as_not_checked(self) -> None:
        source = (_DASHBOARD_DIR / "seed.canvas.tsx").read_text(encoding="utf-8")
        self.assertIn('enrichmentNotChecked: "not checked"', source)
        self.assertIn(
            'item.enrichment_state === "not_checked"',
            source,
        )
        self.assertIn("{lastWorkLabel(wt)}", source)
        self.assertIn("{lastSavedLabel(wt)}", source)
        self.assertIn("{lastSavedLabel(branch)}", source)

    def test_publish_allows_explicit_deep(self) -> None:
        payload = copy.deepcopy(_VALID_DOC)
        payload["detail"] = "deep"
        payload["repos"][0]["worktrees"][0]["enrichment_state"] = "checked"
        with mock.patch.object(render.emitter, "build", return_value=payload) as build:
            render.publish(self.root, detail="deep", canvas_dir=self.canvas_dir)
        build.assert_called_once_with(self.root.resolve(), 4.0, detail="deep")

    def test_cli_exposes_internal_deep_override(self) -> None:
        result = {
            "schema": "awa-dashboard-render/v1",
            "generated_at": "fixture",
            "canvas": "/tmp/fixture",
            "bridge_alias": "/tmp/alias",
            "repos": 0,
        }
        argv = [
            "render.py", "--root", str(self.root), "--detail", "deep",
            "--canvas-dir", str(self.canvas_dir),
        ]
        output = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(render, "publish", return_value=result) as publish, \
                contextlib.redirect_stdout(output):
            self.assertEqual(render.main(), 0)
        self.assertEqual(publish.call_args.kwargs["detail"], "deep")
        json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
