from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from engine.tests.helpers import EngineTestCase


class TestGitRemoteDryRunBehavior(EngineTestCase):
    @classmethod
    def setUpClass(cls):
        cls.git_version = subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        })
        return env

    def _git(self, cwd: Path, *args: str, check: bool = True):
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=check,
            capture_output=True,
            text=True,
            env=self._env(),
        )

    def _fixture(self) -> tuple[Path, Path, Path]:
        root = Path(self._tmp.name)
        remote = root / "remote.git"
        source = root / "source"
        client = root / "client"
        self._git(root, "init", "-q", "--bare", str(remote))
        source.mkdir()
        self._git(source, "init", "-q", ".")
        (source / "tracked.txt").write_text("one\n", encoding="utf-8")
        self._git(source, "add", "tracked.txt")
        self._git(
            source,
            "-c", "user.email=awa-test@example.invalid",
            "-c", "user.name=AWA Test",
            "commit", "-qm", "initial",
        )
        self._git(source, "branch", "-M", "main")
        self._git(source, "remote", "add", "origin", remote.as_uri())
        self._git(source, "push", "-q", "-u", "origin", "main")
        self._git(root, "clone", "-q", "--branch", "main", remote.as_uri(), str(client))
        return remote, source, client

    def test_fetch_dry_run_writes_objects_without_updating_refs_or_fetch_head(self):
        _remote, source, client = self._fixture()
        (source / "tracked.txt").write_text("two\n", encoding="utf-8")
        self._git(source, "add", "tracked.txt")
        self._git(
            source,
            "-c", "user.email=awa-test@example.invalid",
            "-c", "user.name=AWA Test",
            "commit", "-qm", "remote advance",
        )
        self._git(source, "push", "-q", "origin", "main")
        new_oid = self._git(source, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(
            self._git(client, "cat-file", "-e", new_oid, check=False).returncode,
            0,
            self.git_version,
        )
        refs_before = self._git(
            client, "for-each-ref", "--format=%(refname):%(objectname)"
        ).stdout
        fetch_head = client / ".git" / "FETCH_HEAD"
        fetch_head_before = fetch_head.read_bytes() if fetch_head.exists() else None

        self._git(
            client,
            "-c", "gc.auto=0",
            "-c", "fetch.writeCommitGraph=false",
            "fetch", "--dry-run", "--no-recurse-submodules", "origin",
        )

        self.assertEqual(
            self._git(client, "cat-file", "-e", new_oid).returncode,
            0,
            self.git_version,
        )
        self.assertEqual(
            self._git(client, "for-each-ref", "--format=%(refname):%(objectname)").stdout,
            refs_before,
        )
        fetch_head_after = fetch_head.read_bytes() if fetch_head.exists() else None
        self.assertEqual(fetch_head_after, fetch_head_before, self.git_version)

    def test_push_dry_run_runs_pre_push_without_updating_remote_refs(self):
        remote, _source, client = self._fixture()
        (client / "local.txt").write_text("local\n", encoding="utf-8")
        self._git(client, "add", "local.txt")
        self._git(
            client,
            "-c", "user.email=awa-test@example.invalid",
            "-c", "user.name=AWA Test",
            "commit", "-qm", "local advance",
        )
        sentinel = Path(self._tmp.name) / "pre-push-ran"
        hook = client / ".git" / "hooks" / "pre-push"
        hook.write_text(
            "#!/bin/sh\n: > \"$AWA_DRY_RUN_SENTINEL\"\n",
            encoding="utf-8",
        )
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        env = self._env()
        env["AWA_DRY_RUN_SENTINEL"] = str(sentinel)

        proc = subprocess.run(
            [
                "git", "-C", str(client), "push", "--dry-run",
                "origin", "HEAD:refs/heads/dry-run-proof",
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(sentinel.exists(), self.git_version)
        self.assertNotEqual(
            self._git(
                remote,
                "rev-parse", "--verify", "refs/heads/dry-run-proof",
                check=False,
            ).returncode,
            0,
            self.git_version,
        )
