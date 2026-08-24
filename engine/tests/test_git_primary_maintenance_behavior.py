from __future__ import annotations

import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

from engine.tests.helpers import EngineTestCase


@dataclass(frozen=True)
class MaintenanceFixture:
    root: Path
    remote: Path
    source: Path
    primary: Path
    linked: Path
    base_oid: str


class TestGitPrimaryMaintenanceBehavior(EngineTestCase):
    """Offline evidence for the exact Git effects accepted by the maintenance lane."""

    _RISKY_GIT_ENV = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG",
        "GIT_EXEC_PATH",
        "GIT_NAMESPACE",
        "GIT_SHALLOW_FILE",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.git_version = subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        print(
            "git_primary_maintenance_behavior: {0}".format(cls.git_version),
            file=sys.stderr,
        )

    def _env(
        self,
        extra: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, str]:
        env = dict(os.environ)
        for key in list(env):
            if key in self._RISKY_GIT_ENV or key.startswith("GIT_CONFIG_"):
                env.pop(key, None)
        env.update(
            {
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "LC_ALL": "C",
            }
        )
        if extra:
            env.update({key: str(value) for key, value in extra.items()})
        return env

    def _git(
        self,
        cwd: Path,
        *args: str,
        check: bool = True,
        extra_env: Optional[Mapping[str, str]] = None,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=check,
            capture_output=True,
            text=True,
            env=self._env(extra_env),
        )

    def _commit(
        self,
        cwd: Path,
        message: str,
        *,
        force_paths: tuple[str, ...] = (),
    ) -> str:
        self._git(cwd, "add", "-A")
        for path in force_paths:
            self._git(cwd, "add", "-f", "--", path)
        self._git(
            cwd,
            "-c",
            "user.email=awa-test@example.invalid",
            "-c",
            "user.name=AWA Test",
            "commit",
            "-qm",
            message,
        )
        return self._oid(cwd, "HEAD")

    def _fixture(self, name: str = "maintenance") -> MaintenanceFixture:
        root = Path(self._tmp.name) / name
        remote = root / "remote.git"
        source = root / "source"
        primary = root / "primary"
        linked = root / "linked"
        root.mkdir()

        self._git(root, "init", "-q", "--bare", str(remote))
        source.mkdir()
        self._git(source, "init", "-q", ".")
        (source / ".gitignore").write_text("ignored-target.txt\n", encoding="utf-8")
        (source / "tracked.txt").write_text("base\n", encoding="utf-8")
        base_oid = self._commit(source, "base")
        self._git(source, "branch", "-M", "main")
        self._git(source, "remote", "add", "origin", remote.as_uri())
        self._git(source, "push", "-q", "-u", "origin", "main")
        self._git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

        self._git(
            root,
            "clone",
            "-q",
            "--branch",
            "main",
            remote.as_uri(),
            str(primary),
        )
        self._git(primary, "config", "user.email", "awa-test@example.invalid")
        self._git(primary, "config", "user.name", "AWA Test")
        self._git(primary, "update-ref", "refs/heads/unrelated", base_oid)
        self._git(
            primary,
            "worktree",
            "add",
            "-q",
            "-b",
            "linked-proof",
            str(linked),
            "main",
        )
        return MaintenanceFixture(
            root=root,
            remote=remote,
            source=source,
            primary=primary,
            linked=linked,
            base_oid=base_oid,
        )

    def _advance(
        self,
        fixture: MaintenanceFixture,
        message: str,
        changes: Mapping[str, str],
        *,
        force_paths: tuple[str, ...] = (),
    ) -> str:
        for relative, content in changes.items():
            path = fixture.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        oid = self._commit(
            fixture.source,
            message,
            force_paths=force_paths,
        )
        self._git(fixture.source, "push", "-q", "origin", "main")
        return oid

    def _oid(self, cwd: Path, ref: str) -> str:
        return self._git(cwd, "rev-parse", "--verify", ref).stdout.strip()

    def _git_path(self, cwd: Path, name: str) -> Path:
        value = self._git(
            cwd,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            name,
        ).stdout.strip()
        return Path(value).resolve()

    def _common_dir(self, cwd: Path) -> Path:
        value = self._git(
            cwd,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
        return Path(value).resolve()

    def _refs(self, cwd: Path) -> Dict[str, str]:
        output = self._git(
            cwd,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
        ).stdout
        return dict(line.split(" ", 1) for line in output.splitlines() if line)

    def _worktree_files(self, cwd: Path) -> Dict[str, bytes]:
        files: Dict[str, bytes] = {}
        for path in cwd.rglob("*"):
            relative = path.relative_to(cwd)
            if relative.parts and relative.parts[0] == ".git":
                continue
            if path.is_file():
                files[str(relative)] = path.read_bytes()
        return files

    def _status(self, cwd: Path) -> str:
        return self._git(
            cwd,
            "status",
            "--porcelain",
            "--untracked-files=all",
        ).stdout

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def test_primary_and_linked_worktree_share_common_git_state(self):
        fixture = self._fixture()
        self.assertEqual(
            self._common_dir(fixture.primary),
            self._common_dir(fixture.linked),
            self.git_version,
        )
        primary_tracking = self._git_path(
            fixture.primary,
            "refs/remotes/origin/main",
        )
        linked_tracking = self._git_path(
            fixture.linked,
            "refs/remotes/origin/main",
        )
        self.assertEqual(primary_tracking, linked_tracking, self.git_version)
        self.assertEqual(
            self._oid(fixture.primary, "refs/remotes/origin/main"),
            fixture.base_oid,
        )
        self.assertEqual(
            self._oid(fixture.linked, "refs/remotes/origin/main"),
            fixture.base_oid,
        )

    def test_canonical_fetch_updates_only_expected_shared_git_state(self):
        fixture = self._fixture()
        linked_head_before = self._oid(fixture.linked, "HEAD")
        linked_branch_before = self._oid(fixture.linked, "refs/heads/linked-proof")
        linked_index_before = self._git(fixture.linked, "write-tree").stdout.strip()
        linked_files_before = self._worktree_files(fixture.linked)
        primary_head_before = self._oid(fixture.primary, "HEAD")
        primary_branch_before = self._oid(fixture.primary, "refs/heads/main")
        primary_index_before = self._git(fixture.primary, "write-tree").stdout.strip()
        primary_files_before = self._worktree_files(fixture.primary)
        unrelated_before = self._oid(fixture.primary, "refs/heads/unrelated")

        target_oid = self._advance(
            fixture,
            "remote advance",
            {"tracked.txt": "remote advance\n", "remote-only.txt": "new\n"},
        )
        remote_refs_before = self._refs(fixture.remote)
        self.assertNotEqual(
            self._git(
                fixture.primary,
                "cat-file",
                "-e",
                target_oid,
                check=False,
            ).returncode,
            0,
            self.git_version,
        )

        self._git(fixture.primary, "fetch")

        self.assertEqual(self._oid(fixture.primary, "origin/main"), target_oid)
        self.assertEqual(self._oid(fixture.linked, "origin/main"), target_oid)
        self.assertEqual(
            self._git(fixture.primary, "cat-file", "-e", target_oid).returncode,
            0,
        )
        fetch_head = self._git_path(fixture.primary, "FETCH_HEAD").read_text(
            encoding="utf-8"
        )
        self.assertIn(target_oid, fetch_head)
        self.assertEqual(self._oid(fixture.primary, "HEAD"), primary_head_before)
        self.assertEqual(
            self._oid(fixture.primary, "refs/heads/main"),
            primary_branch_before,
        )
        self.assertEqual(
            self._git(fixture.primary, "write-tree").stdout.strip(),
            primary_index_before,
        )
        self.assertEqual(self._worktree_files(fixture.primary), primary_files_before)
        self.assertEqual(
            self._oid(fixture.primary, "refs/heads/unrelated"),
            unrelated_before,
        )
        self.assertEqual(self._refs(fixture.remote), remote_refs_before)
        self.assertEqual(self._oid(fixture.linked, "HEAD"), linked_head_before)
        self.assertEqual(
            self._oid(fixture.linked, "refs/heads/linked-proof"),
            linked_branch_before,
        )
        self.assertEqual(
            self._git(fixture.linked, "write-tree").stdout.strip(),
            linked_index_before,
        )
        self.assertEqual(self._worktree_files(fixture.linked), linked_files_before)
        self.assertEqual(self._status(fixture.primary), "")
        self.assertEqual(self._status(fixture.linked), "")

    def test_canonical_fast_forward_runs_configured_hook_and_filter(self):
        fixture = self._fixture()
        hooks = fixture.root / "hooks"
        hooks.mkdir()
        post_merge_sentinel = fixture.root / "post-merge-ran"
        filter_sentinel = fixture.root / "filter-ran"
        post_merge = hooks / "post-merge"
        self._write_executable(
            post_merge,
            "#!/bin/sh\nprintf post-merge > \"$AWA_POST_MERGE_SENTINEL\"\n",
        )
        filter_driver = fixture.root / "smudge-filter.sh"
        self._write_executable(
            filter_driver,
            "#!/bin/sh\ncat\nprintf smudge > \"$AWA_FILTER_SENTINEL\"\n",
        )
        self._git(fixture.primary, "config", "core.hooksPath", str(hooks))
        self._git(
            fixture.primary,
            "config",
            "filter.awa-proof.smudge",
            str(filter_driver),
        )
        self._git(fixture.primary, "config", "filter.awa-proof.clean", "cat")
        self._git(fixture.primary, "config", "filter.awa-proof.required", "true")

        linked_head_before = self._oid(fixture.linked, "HEAD")
        linked_index_before = self._git(fixture.linked, "write-tree").stdout.strip()
        linked_files_before = self._worktree_files(fixture.linked)
        target_oid = self._advance(
            fixture,
            "filter target",
            {
                ".gitattributes": "filtered.txt filter=awa-proof\n",
                "filtered.txt": "filtered payload\n",
                "tracked.txt": "fast-forwarded\n",
            },
        )
        self._git(fixture.primary, "fetch")

        self._git(
            fixture.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
            extra_env={
                "AWA_POST_MERGE_SENTINEL": str(post_merge_sentinel),
                "AWA_FILTER_SENTINEL": str(filter_sentinel),
            },
        )

        self.assertEqual(self._oid(fixture.primary, "HEAD"), target_oid)
        parents = self._git(
            fixture.primary,
            "show",
            "-s",
            "--format=%P",
            "HEAD",
        ).stdout.split()
        self.assertEqual(parents, [fixture.base_oid], self.git_version)
        self.assertEqual(
            self._git(fixture.primary, "write-tree").stdout.strip(),
            self._oid(fixture.primary, "HEAD^{tree}"),
        )
        self.assertEqual(
            (fixture.primary / "filtered.txt").read_text(encoding="utf-8"),
            "filtered payload\n",
        )
        self.assertTrue(post_merge_sentinel.exists(), self.git_version)
        self.assertTrue(filter_sentinel.exists(), self.git_version)
        self.assertEqual(self._status(fixture.primary), "")
        self.assertEqual(self._oid(fixture.linked, "HEAD"), linked_head_before)
        self.assertEqual(
            self._git(fixture.linked, "write-tree").stdout.strip(),
            linked_index_before,
        )
        self.assertEqual(self._worktree_files(fixture.linked), linked_files_before)

    def test_no_overwrite_ignore_refuses_ignored_untracked_collision(self):
        fixture = self._fixture()
        target_oid = self._advance(
            fixture,
            "track ignored target",
            {"ignored-target.txt": "remote tracked value\n"},
            force_paths=("ignored-target.txt",),
        )
        self._git(fixture.primary, "fetch")
        collision = fixture.primary / "ignored-target.txt"
        collision.write_text("local ignored value\n", encoding="utf-8")
        head_before = self._oid(fixture.primary, "HEAD")

        proc = self._git(
            fixture.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
            check=False,
        )

        self.assertNotEqual(proc.returncode, 0, self.git_version)
        self.assertEqual(self._oid(fixture.primary, "HEAD"), head_before)
        self.assertEqual(
            collision.read_text(encoding="utf-8"),
            "local ignored value\n",
        )
        self.assertEqual(self._oid(fixture.primary, "origin/main"), target_oid)

    def test_moving_upstream_yields_descendant_noop_or_refusal(self):
        descendant = self._fixture("moving-descendant")
        first_oid = self._advance(
            descendant,
            "first upstream move",
            {"tracked.txt": "first\n"},
        )
        self._git(descendant.primary, "fetch")
        self.assertEqual(
            self._git(
                descendant.primary,
                "merge-base",
                "--is-ancestor",
                "HEAD",
                "@{upstream}",
                check=False,
            ).returncode,
            0,
        )
        second_oid = self._advance(
            descendant,
            "second upstream move",
            {"tracked.txt": "second\n"},
        )
        self._git(descendant.primary, "fetch")
        self._git(
            descendant.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
        )
        self.assertNotEqual(first_oid, second_oid)
        self.assertEqual(self._oid(descendant.primary, "HEAD"), second_oid)
        self.assertEqual(
            self._git(
                descendant.primary,
                "merge-base",
                "--is-ancestor",
                descendant.base_oid,
                "HEAD",
                check=False,
            ).returncode,
            0,
        )

        noop = self._fixture("moving-noop")
        self._advance(noop, "preflight target", {"tracked.txt": "ahead\n"})
        self._git(noop.primary, "fetch")
        self.assertEqual(
            self._git(
                noop.primary,
                "merge-base",
                "--is-ancestor",
                "HEAD",
                "@{upstream}",
                check=False,
            ).returncode,
            0,
        )
        self._git(
            noop.primary,
            "update-ref",
            "refs/remotes/origin/main",
            noop.base_oid,
        )
        self._git(
            noop.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
        )
        self.assertEqual(self._oid(noop.primary, "HEAD"), noop.base_oid)
        self.assertEqual(self._status(noop.primary), "")

        refused = self._fixture("moving-refusal")
        self._advance(refused, "preflight target", {"tracked.txt": "ahead\n"})
        self._git(refused.primary, "fetch")
        self.assertEqual(
            self._git(
                refused.primary,
                "merge-base",
                "--is-ancestor",
                "HEAD",
                "@{upstream}",
                check=False,
            ).returncode,
            0,
        )
        tree_oid = self._oid(refused.source, "HEAD^{tree}")
        side_oid = self._git(
            refused.source,
            "-c",
            "user.email=awa-test@example.invalid",
            "-c",
            "user.name=AWA Test",
            "commit-tree",
            tree_oid,
            "-m",
            "unrelated root",
        ).stdout.strip()
        self._git(
            refused.source,
            "push",
            "-q",
            "origin",
            "{0}:refs/heads/unrelated-root".format(side_oid),
        )
        self._git(refused.primary, "fetch")
        self._git(
            refused.primary,
            "update-ref",
            "refs/remotes/origin/main",
            side_oid,
        )
        head_before = self._oid(refused.primary, "HEAD")
        proc = self._git(
            refused.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0, self.git_version)
        self.assertEqual(self._oid(refused.primary, "HEAD"), head_before)
        self.assertEqual(self._status(refused.primary), "")

    def test_equal_upstream_is_noop_and_divergence_refuses(self):
        equal = self._fixture("equal")
        head_before = self._oid(equal.primary, "HEAD")
        self._git(
            equal.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
        )
        self.assertEqual(self._oid(equal.primary, "HEAD"), head_before)
        self.assertEqual(self._status(equal.primary), "")

        divergent = self._fixture("divergent")
        (divergent.primary / "local.txt").write_text("local\n", encoding="utf-8")
        local_oid = self._commit(divergent.primary, "local-only")
        self._advance(
            divergent,
            "remote-only",
            {"remote.txt": "remote\n"},
        )
        self._git(divergent.primary, "fetch")
        proc = self._git(
            divergent.primary,
            "merge",
            "--ff-only",
            "--no-overwrite-ignore",
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0, self.git_version)
        self.assertEqual(self._oid(divergent.primary, "HEAD"), local_oid)
        self.assertEqual(self._status(divergent.primary), "")

    def test_fetch_hook_residue_stops_flow_without_merge_or_cleanup(self):
        fixture = self._fixture()
        hooks = fixture.root / "residue-hooks"
        hooks.mkdir()
        residue = fixture.primary / "maintenance-residue.txt"
        merge_sentinel = fixture.root / "merge-should-not-run"
        self._write_executable(
            hooks / "reference-transaction",
            (
                "#!/bin/sh\n"
                "while IFS= read -r line; do :; done\n"
                "if [ \"$1\" = committed ]; then\n"
                "  printf residue > \"$AWA_RESIDUE_PATH\"\n"
                "fi\n"
            ),
        )
        self._write_executable(
            hooks / "post-merge",
            "#!/bin/sh\nprintf merged > \"$AWA_MERGE_SENTINEL\"\n",
        )
        self._git(fixture.primary, "config", "core.hooksPath", str(hooks))
        target_oid = self._advance(
            fixture,
            "hook residue target",
            {"tracked.txt": "hook target\n"},
        )
        head_before = self._oid(fixture.primary, "HEAD")

        self._git(
            fixture.primary,
            "fetch",
            extra_env={
                "AWA_RESIDUE_PATH": str(residue),
                "AWA_MERGE_SENTINEL": str(merge_sentinel),
            },
        )
        status_after_fetch = self._status(fixture.primary)
        if not status_after_fetch:
            self._git(
                fixture.primary,
                "merge",
                "--ff-only",
                "--no-overwrite-ignore",
                extra_env={"AWA_MERGE_SENTINEL": str(merge_sentinel)},
            )

        self.assertTrue(residue.exists(), self.git_version)
        self.assertIn("maintenance-residue.txt", status_after_fetch)
        self.assertFalse(merge_sentinel.exists(), self.git_version)
        self.assertEqual(self._oid(fixture.primary, "HEAD"), head_before)
        self.assertEqual(self._oid(fixture.primary, "origin/main"), target_oid)
