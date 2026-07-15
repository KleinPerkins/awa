#!/usr/bin/env python3
"""test_emitter.py — focused tests for the AWA dashboard emitter's per-repo MODE surface.

Self-contained (builds scratch git repos in the SYSTEM temp dir, outside any governed repo,
so their commits carry NO governed hooks) and stdlib-only. Runnable directly:

    python3 dashboard/test_emitter.py

or via unittest discovery. Covers the per-repo MODE surface after the ASK_ON removal:
  * the summary map counts only include|exclude|advisory (no ``ask_on`` key ever),
  * a repo configured ONLY via a ``modes:`` entry (outside include globs) is enumerated,
  * per-repo ``repo.mode`` / ``repo.mode_error`` populate correctly: "" (none), a valid
    ``on``/``off``, or ``invalid`` for a removed-legacy/unknown value — which still classifies
    ``include`` via the fail-safe rule (only ``off`` disables),
  * existing emitter shape (schema, required summary keys, repo fields) stays intact.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_DASHBOARD_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DASHBOARD_DIR))
import emitter  # noqa: E402
import render as dashboard_render  # noqa: E402

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
        # Hermetic + side-effect-free: point XDG_STATE_HOME at an EMPTY temp so the additive
        # environment.recovery probe finds no engine state db and returns available:false WITHOUT
        # spawning the engine or touching the operator's real recovery state during the test.
        self._saved_state_home = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = str(Path(self._tmp.name) / "state")

    def tearDown(self) -> None:
        if self._saved_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = self._saved_policy
        if self._saved_state_home is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = self._saved_state_home
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
        # included/inval: matching modes entry with a removed-legacy/unknown value -> mode
        # "invalid", but fail-safe classification include (only `off` disables)
        _make_repo(self.root, "included/inval")
        # included/beta: explicit off -> exclude
        _make_repo(self.root, "included/beta")
        # modeonly/repo: NOT under any include glob; only reachable via its explicit `on` entry
        _make_repo(self.root, "modeonly/repo")
        self._write_policy(
            "version: 1\n"
            "default: advisory\n"
            "default_mode: on\n"
            "include:\n"
            "  - included/*\n"
            "modes:\n"
            "  modeonly/repo: on\n"
            "  included/inval: ask_on\n"   # a removed legacy value -> mode invalid, class include
            "  included/beta: off\n"
        )

    def _build(self) -> dict:
        # A generous timeout keeps CI-slow git probes from degrading rows under test.
        return emitter.build(self.root, timeout=30.0)

    def test_build_does_not_throw(self) -> None:
        doc = self._build()  # must not raise (summary map counts only include/exclude/advisory)
        self.assertEqual(doc["schema"], "awa-worktree/v1")

    def test_summary_counts_include_exclude_advisory(self) -> None:
        doc = self._build()
        summary = doc["summary"]
        # ASK_ON is removed: the summary NEVER carries an ask_on key.
        self.assertNotIn("ask_on", summary)
        # included = alpha (glob) + inval (legacy value fail-safe -> include) + modeonly (on)
        self.assertEqual(summary["included"], 3)
        self.assertEqual(summary["excluded"], 1)   # included/beta (explicit off)
        self.assertEqual(summary["advisory"], 0)
        self.assertEqual(summary["repos"], 4)
        self.assertEqual(
            summary["included"] + summary["excluded"] + summary["advisory"],
            summary["repos"],
        )

    def test_mode_only_root_enumerated(self) -> None:
        doc = self._build()
        by_rel = self._by_rel(doc)
        self.assertIn("modeonly/repo", by_rel,
                      "a repo configured only via a modes entry must be enumerated")
        # explicit `on` outside the include globs -> include
        self.assertEqual(by_rel["modeonly/repo"]["classification"], "include")

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
        self.assertEqual(modeonly["mode"], "on")       # valid explicit on
        self.assertEqual(modeonly["mode_error"], "")
        self.assertEqual(modeonly["classification"], "include")

        # A removed-legacy/unknown value surfaces as mode "invalid" (+ mode_error) but the repo
        # still classifies include via the fail-safe rule (only `off` disables).
        inval = by_rel["included/inval"]
        self.assertEqual(inval["mode"], "invalid")
        self.assertTrue(inval["mode_error"], "invalid mode must set mode_error")
        self.assertEqual(inval["classification"], "include")

    def test_existing_repo_shape_intact(self) -> None:
        doc = self._build()
        for key in ("schema", "generated_at", "root", "default_base", "summary",
                    "repos", "environment"):
            self.assertIn(key, doc)
        # Additive recovery-retention visibility block is always present; with no engine state db
        # (isolated empty XDG_STATE_HOME) it reports available:false WITHOUT spawning the engine.
        self.assertIn("recovery", doc["environment"])
        self.assertFalse(doc["environment"]["recovery"]["available"])
        for key in ("repos", "included", "excluded", "advisory", "worktrees", "linked",
                    "dirty", "ahead_of_main", "behind_main", "diverged", "no_base",
                    "orphan_branches"):
            self.assertIn(key, doc["summary"])
        for repo in doc["repos"]:
            for key in ("path", "rel", "name", "classification", "reason", "mode",
                        "mode_error", "owner_repo", "has_base", "worktrees"):
                self.assertIn(key, repo)
            for worktree in repo["worktrees"]:
                self.assertIn("size_bytes", worktree)
                self.assertIn("plain_size", worktree)


class TestEmitterModeFreeBackCompat(_EmitterModeTestBase):
    def test_no_modes_clean_summary_and_empty_mode_fields(self) -> None:
        _make_repo(self.root, "included/alpha")
        self._write_policy(
            "version: 1\n"
            "default: advisory\n"
            "default_mode: on\n"
            "include:\n"
            "  - included/*\n"
        )
        doc = emitter.build(self.root, timeout=30.0)
        # No ask_on key (removed); advisory bucket still present in the summary map.
        self.assertNotIn("ask_on", doc["summary"])
        self.assertIn("advisory", doc["summary"])
        # Every repo still carries the additive (empty) mode fields.
        for repo in doc["repos"]:
            self.assertEqual(repo["mode"], "")
            self.assertEqual(repo["mode_error"], "")


class TestCanvasRefreshBridge(_EmitterModeTestBase):
    def setUp(self) -> None:
        super().setUp()
        _make_repo(self.root, "included/alpha")
        self._write_policy(
            "version: 1\n"
            "default: advisory\n"
            "default_mode: on\n"
            "include:\n"
            "  - included/*\n"
        )

    def test_seed_uses_background_request_and_never_opens_chat(self) -> None:
        source = (_DASHBOARD_DIR / "seed.canvas.tsx").read_text(encoding="utf-8")
        self.assertIn('"dash.runRequest"', source)
        self.assertIn('const REFRESH_JOB_ID = "awa-dashboard-refresh"', source)
        for field in ("jobId:", "nonce:", "at:", "snapshotGeneratedAt:"):
            self.assertIn(field, source)
        self.assertNotIn("newComposerChat", source)
        self.assertNotIn("useCanvasAction", source)

    def test_renderer_publishes_owned_bridge_alias(self) -> None:
        canvas_dir = Path(self._tmp.name) / "canvases"
        result = dashboard_render.publish(
            self.root,
            policy=Path(os.environ["AWA_POLICY"]),
            timeout=30.0,
            canvas_dir=canvas_dir,
        )
        canvas = Path(result["canvas"])
        alias = Path(result["bridge_alias"])
        self.assertTrue(canvas.is_file())
        self.assertTrue(alias.is_symlink())
        self.assertEqual(
            os.readlink(alias),
            "awa-worktree-dashboard.canvas.data.json",
        )
        rendered = canvas.read_text(encoding="utf-8")
        self.assertIn('"schema": "awa-worktree/v1"', rendered)
        self.assertIn('"rel": "included/alpha"', rendered)
        self.assertNotIn("/Users/", rendered)

    def test_renderer_refuses_unowned_bridge_alias(self) -> None:
        canvas = Path(self._tmp.name) / "canvases" / dashboard_render.CANVAS_NAME
        canvas.parent.mkdir(parents=True)
        alias = canvas.parent / dashboard_render.BRIDGE_ALIAS_NAME
        alias.write_text("operator data\n", encoding="utf-8")
        with self.assertRaises(dashboard_render.RenderError):
            dashboard_render.ensure_bridge_alias(canvas)
        self.assertEqual(alias.read_text(encoding="utf-8"), "operator data\n")

    def _fake_local_jobs(self, bridge_enabled: bool) -> tuple[Path, Path]:
        fake = Path(self._tmp.name) / "local-jobs.sh"
        log = Path(self._tmp.name) / "local-jobs.log"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_LOCAL_JOBS_LOG\"\n"
            "if [[ \"${1:-}\" == dashboard ]]; then\n"
            f"  printf '%s\\n' '{{\"run_bridge_enabled\":{str(bridge_enabled).lower()}}}'\n"
            "elif [[ \"${1:-}\" == explain-job ]]; then\n"
            "  [[ \"${FAKE_JOB_EXISTS:-0}\" == 1 ]] || exit 1\n"
            "elif [[ \"${1:-}\" == view-jobs ]]; then\n"
            "  owner=\"\"\n"
            "  if [[ \"${FAKE_JOB_OWNED:-1}\" == 1 ]]; then\n"
            "    owner='\"AWA_DASHBOARD_REFRESH_OWNER\":\"awa-dashboard-refresh/v1\"'\n"
            "  fi\n"
            "  printf '%s\\n' \"{\\\"instances\\\":[{\\\"id\\\":\\\"awa-dashboard-refresh\\\","
            "\\\"type\\\":\\\"command\\\",\\\"role\\\":\\\"instance\\\",\\\"env\\\":{${owner}}}]}\"\n"
            "fi\n",
            encoding="utf-8",
        )
        fake.chmod(0o700)
        return fake, log

    def test_action_installer_registers_fixed_disabled_job(self) -> None:
        fake, log = self._fake_local_jobs(True)
        env = {
            **os.environ,
            "AWA_HOME": str(_DASHBOARD_DIR.parent),
            "AWA_LOCAL_JOBS_CLI": str(fake),
            "FAKE_LOCAL_JOBS_LOG": str(log),
        }
        proc = subprocess.run(
            [
                "bash",
                str(_DASHBOARD_DIR / "install_actions.sh"),
                "--root",
                str(self.root),
                "--policy",
                os.environ["AWA_POLICY"],
            ],
            text=True,
            capture_output=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        calls = log.read_text(encoding="utf-8")
        self.assertIn("add-job --type command --id awa-dashboard-refresh", calls)
        self.assertIn("--interval-seconds 2147483647", calls)
        self.assertIn("--enabled false", calls)
        self.assertIn(
            "--env AWA_DASHBOARD_REFRESH_OWNER=awa-dashboard-refresh/v1",
            calls,
        )
        self.assertIn("run-job --id awa-dashboard-refresh", calls)
        self.assertNotIn("enable-canvas-runs", calls)

    def test_action_installer_preserves_existing_schedule_and_enabled_state(self) -> None:
        fake, log = self._fake_local_jobs(True)
        proc = subprocess.run(
            [
                "bash",
                str(_DASHBOARD_DIR / "install_actions.sh"),
                "--root",
                str(self.root),
                "--policy",
                os.environ["AWA_POLICY"],
            ],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AWA_HOME": str(_DASHBOARD_DIR.parent),
                "AWA_LOCAL_JOBS_CLI": str(fake),
                "FAKE_LOCAL_JOBS_LOG": str(log),
                "FAKE_JOB_EXISTS": "1",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        update = next(
            line for line in log.read_text(encoding="utf-8").splitlines()
            if line.startswith("update-job ")
        )
        self.assertNotIn("--interval-seconds", update)
        self.assertNotIn("--enabled", update)

    def test_action_installer_refuses_existing_unowned_job(self) -> None:
        fake, log = self._fake_local_jobs(True)
        proc = subprocess.run(
            [
                "bash",
                str(_DASHBOARD_DIR / "install_actions.sh"),
                "--root",
                str(self.root),
                "--policy",
                os.environ["AWA_POLICY"],
            ],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AWA_HOME": str(_DASHBOARD_DIR.parent),
                "AWA_LOCAL_JOBS_CLI": str(fake),
                "FAKE_LOCAL_JOBS_LOG": str(log),
                "FAKE_JOB_EXISTS": "1",
                "FAKE_JOB_OWNED": "0",
            },
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("not AWA-owned", proc.stderr)
        self.assertNotIn("update-job", log.read_text(encoding="utf-8"))

    def test_action_installer_removes_only_owned_job(self) -> None:
        fake, log = self._fake_local_jobs(True)
        base_env = {
            **os.environ,
            "AWA_HOME": str(_DASHBOARD_DIR.parent),
            "AWA_LOCAL_JOBS_CLI": str(fake),
            "FAKE_LOCAL_JOBS_LOG": str(log),
            "FAKE_JOB_EXISTS": "1",
        }
        owned = subprocess.run(
            ["bash", str(_DASHBOARD_DIR / "install_actions.sh"), "--remove"],
            text=True,
            capture_output=True,
            env=base_env,
        )
        self.assertEqual(owned.returncode, 0, owned.stderr)
        self.assertIn(
            "delete-job --type command --id awa-dashboard-refresh --confirm",
            log.read_text(encoding="utf-8"),
        )

        log.write_text("", encoding="utf-8")
        unowned = subprocess.run(
            ["bash", str(_DASHBOARD_DIR / "install_actions.sh"), "--remove"],
            text=True,
            capture_output=True,
            env={**base_env, "FAKE_JOB_OWNED": "0"},
        )
        self.assertEqual(unowned.returncode, 1, unowned.stderr)
        self.assertNotIn("delete-job", log.read_text(encoding="utf-8"))

    def test_action_installer_does_not_adopt_shared_bridge(self) -> None:
        fake, log = self._fake_local_jobs(False)
        proc = subprocess.run(
            [
                "bash",
                str(_DASHBOARD_DIR / "install_actions.sh"),
                "--root",
                str(self.root),
                "--policy",
                os.environ["AWA_POLICY"],
            ],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AWA_HOME": str(_DASHBOARD_DIR.parent),
                "AWA_LOCAL_JOBS_CLI": str(fake),
                "FAKE_LOCAL_JOBS_LOG": str(log),
            },
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        calls = log.read_text(encoding="utf-8")
        self.assertNotIn("add-job", calls)
        self.assertNotIn("enable-canvas-runs", calls)


class TestWorktreeDiskSize(unittest.TestCase):
    def test_adaptive_size_labels(self) -> None:
        cases = (
            (None, "not available"),
            (0, "0 KB"),
            (512 * 1024, "512 KB"),
            (1024 ** 2, "1 MB"),
            (1536 * 1024, "1.5 MB"),
            (1536 * 1024 ** 2, "1.5 GB"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(emitter.format_disk_size(value), expected)

    def test_measurement_is_bounded_and_parses_du_kib(self) -> None:
        completed = subprocess.CompletedProcess(
            ["du", "-sk", "/tmp/worktree"],
            0,
            stdout="1536\t/tmp/worktree\n",
            stderr="",
        )
        with mock.patch.object(emitter.subprocess, "run", return_value=completed) as run:
            self.assertEqual(
                emitter.disk_usage_bytes("/tmp/worktree", timeout=1.25),
                1536 * 1024,
            )
        self.assertEqual(run.call_args.kwargs["timeout"], 1.25)

        with mock.patch.object(
            emitter.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["du"], 0.1),
        ):
            self.assertIsNone(emitter.disk_usage_bytes("/tmp/worktree", timeout=0.1))

    def test_seed_displays_size_on_every_worktree_row(self) -> None:
        source = (_DASHBOARD_DIR / "seed.canvas.tsx").read_text(encoding="utf-8")
        self.assertIn('"Size on disk"', source)
        self.assertIn("wt.plain_size || PM_COPY.sizeUnavailable", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
