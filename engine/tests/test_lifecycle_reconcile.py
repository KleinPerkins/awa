"""M2.1: read-only lifecycle reconciliation and CLI reporting."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from engine import (
    cli,
    integrity,
    lease as lease_mod,
    lifecycle_reconcile,
    native_entry,
    state as state_mod,
)
from engine.tests.helpers import EngineTestCase, git
from kernel.lib import awa_roots


def _observation(
    path: str = "/missing/worktree",
    *,
    leased: bool = True,
    root_exists: bool | None = False,
    registered: bool | None = False,
    linked: bool | None = True,
    disposition: str | None = "dead",
    live_session: bool | None = False,
    lease_on_disk: bool | None = False,
    dirty: bool | None = None,
    cached_remote: bool | None = None,
    ambiguous: bool | None = False,
    pid: int | None = 999_999,
    boot_id: str = "old-boot",
) -> lifecycle_reconcile._Observation:
    lease = None
    if leased:
        lease = {
            "lease_id": "awa1-test",
            "worktree_path": path,
            "branch": "feat/test",
            "git_common_dir": "/repo/.git",
            "boot_id": boot_id,
            "pid": pid,
            "status": "active",
        }
    registration = None
    if registered is True:
        registration = lifecycle_reconcile.GitRegistration(
            path=path,
            git_common_dir="/repo/.git",
            linked=linked,
            dirty=dirty,
            cached_remote=cached_remote,
        )
    return lifecycle_reconcile._Observation(
        path=path,
        lease=lease,
        registration=registration,
        registration_known=registered is not None,
        root_exists=root_exists,
        lease_on_disk=lease_on_disk,
        disposition=disposition,
        live_session=live_session,
        journal_or_recovery_ambiguous=ambiguous,
    )


def _classify_one(
    observation: lifecycle_reconcile._Observation,
) -> lifecycle_reconcile.Row:
    with mock.patch.object(
        lifecycle_reconcile,
        "_observations",
        return_value=[observation],
    ):
        rows = lifecycle_reconcile.classify()
    if len(rows) != 1:
        raise AssertionError(f"expected one lifecycle row, got {rows!r}")
    return rows[0]


class TestLifecycleReconcile(EngineTestCase):
    def test_dead_pid_old_boot_absent_root_is_not_retire_candidate_unless_full_conjunction(
        self,
    ):
        complete = _observation()
        self.assertEqual(
            _classify_one(complete).classification,
            "retire_candidate",
        )

        incomplete = {
            "root-present": replace(complete, root_exists=True),
            "git-registered": replace(
                complete,
                registration=lifecycle_reconcile.GitRegistration(
                    path=complete.path,
                    git_common_dir="/repo/.git",
                    linked=True,
                    dirty=False,
                    cached_remote=True,
                ),
            ),
            "active-disposition": replace(
                complete,
                disposition="active",
            ),
            "live-session": replace(complete, live_session=True),
            "lease-on-disk": replace(complete, lease_on_disk=True),
            "journal-or-recovery-ambiguity": replace(
                complete,
                journal_or_recovery_ambiguous=True,
            ),
        }
        for name, observation in incomplete.items():
            with self.subTest(name=name):
                self.assertNotEqual(
                    _classify_one(observation).classification,
                    "retire_candidate",
                )

    def test_canonical_dead_retained_record_can_retire_only_with_full_conjunction(
        self,
    ):
        root = self.state_home.parent / "removed-worktree"
        roots = integrity._roots_module(integrity._source_root())
        Path(roots.roots_dir()).mkdir(parents=True)
        retained_record = {"historical": "heartbeat"}
        Path(roots.record_path(str(root))).write_text(
            json.dumps(retained_record),
            encoding="utf-8",
        )
        canonical = roots.disposition(str(root))
        self.assertEqual(canonical["disposition"], "dead")
        self.assertIs(canonical["exists"], False)
        self.assertEqual(canonical["record"], retained_record)

        common_dir = str(self.state_home.parent / "repo" / ".git")
        lease = _observation(path=str(root)).lease
        lease["git_common_dir"] = common_dir
        git_snapshot = lifecycle_reconcile._GitSnapshot(
            registrations=(),
            known_common_dirs=frozenset(
                {lifecycle_reconcile._common_key(common_dir)}
            ),
        )
        observation = lifecycle_reconcile._observation_for(
            str(root),
            lease=lease,
            lease_snapshot_known=True,
            lease_ambiguous=False,
            registrations=[],
            git_snapshot=git_snapshot,
        )
        self.assertEqual(
            lifecycle_reconcile._classify_observation(
                observation
            ).classification,
            "retire_candidate",
        )
        self.assertIs(observation.live_session, False)

        stale = replace(
            observation,
            root_exists=True,
            disposition="stale",
            live_session=lifecycle_reconcile._live_session(
                {"disposition": "stale", "record": retained_record}
            ),
        )
        self.assertNotEqual(
            lifecycle_reconcile._classify_observation(stale).classification,
            "retire_candidate",
        )
        self.assertEqual(
            lifecycle_reconcile._classify_observation(
                replace(
                    observation,
                    journal_or_recovery_ambiguous=True,
                )
            ).classification,
            "preserve",
        )

    def test_fresh_heartbeat_row_preserved(self):
        row = _classify_one(
            _observation(
                path="/repo/worktree",
                root_exists=True,
                registered=True,
                disposition="active",
                live_session=True,
                lease_on_disk=True,
                dirty=False,
                cached_remote=True,
            )
        )
        self.assertEqual(row.classification, "preserve")
        self.assertEqual(row.activity, "active")

    def test_local_only_dirty_husk_preserved(self):
        local_only = _classify_one(
            _observation(
                path="/repo/local-only",
                root_exists=True,
                registered=True,
                disposition="untracked",
                lease_on_disk=True,
                dirty=False,
                cached_remote=False,
            )
        )
        dirty_husk = _classify_one(
            _observation(
                path="/repo/dirty-husk",
                root_exists=True,
                registered=False,
                disposition="untracked",
                lease_on_disk=True,
                dirty=True,
                cached_remote=False,
            )
        )
        self.assertEqual(local_only.classification, "preserve")
        self.assertEqual(local_only.cached_remote, "local_only")
        self.assertEqual(dirty_husk.classification, "preserve")
        self.assertIn(dirty_husk.content_safety, {"dirty", "husk"})

    def test_classify_is_read_only(self):
        repo = self.make_seeded_repo("readonly-repo")
        worktree = self.add_worktree(repo, "feat/readonly")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        common_dir = git(
            worktree,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
        lease = lease_mod.build_lease(
            worktree,
            "feat/readonly",
            common_dir,
            boot="old-boot",
        )
        lease_path = lease_mod.write_lease(worktree, lease)
        with state_mod.State() as state:
            state.upsert_lease(lease)
        awa_roots.heartbeat(
            worktree,
            branch="feat/readonly",
            common_dir=common_dir,
            session_id="readonly-session",
        )
        observed_identity = native_entry._observe_identity(worktree)
        native_entry._write_receipt(
            native_entry.EntryPayload(
                root=observed_identity.root,
                session_id="readonly-session",
            ),
            observed_identity,
            result="success",
            action="attested",
            lease_id=lease["lease_id"],
            reason="registered",
        )

        db_path = self.state_home / "awa" / "state.db"
        uri = f"file:{quote(str(db_path.resolve()), safe='/')}?mode=ro"
        read_only = sqlite3.connect(uri, uri=True, isolation_level=None)
        try:
            read_only.execute("PRAGMA query_only=ON")
            read_only.execute("BEGIN")
            self.assertEqual(
                read_only.execute("PRAGMA query_only").fetchone()[0],
                1,
            )
            with self.assertRaises(sqlite3.OperationalError):
                read_only.execute("UPDATE leases SET status='retired'")
        finally:
            read_only.close()

        git_dir = Path(
            git(
                worktree,
                "rev-parse",
                "--path-format=absolute",
                "--git-dir",
            ).stdout.strip()
        )
        observed_files = (
            db_path,
            lease_path,
            Path(worktree) / "README.md",
            git_dir / "index",
            Path(awa_roots.record_path(worktree)),
            native_entry.receipt_path(worktree, "readonly-session"),
        )
        before = {
            path: (
                path.stat().st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in observed_files
        }
        state_names = sorted(
            str(path.relative_to(self.state_home))
            for path in self.state_home.rglob("*")
        )

        with mock.patch.dict(
            os.environ,
            {"AWA_INTEGRITY_PROBE_REPO": repo},
            clear=False,
        ), mock.patch.object(
            state_mod,
            "State",
            side_effect=AssertionError("read path constructed State()"),
        ):
            rows = lifecycle_reconcile.classify()

        self.assertTrue(
            any(row.worktree_path == str(Path(worktree).resolve()) for row in rows)
        )
        self.assertEqual(
            {
                path: (
                    path.stat().st_mtime_ns,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
                for path in observed_files
            },
            before,
        )
        self.assertEqual(
            sorted(
                str(path.relative_to(self.state_home))
                for path in self.state_home.rglob("*")
            ),
            state_names,
        )

    def test_leaseless_root_is_adopt_candidate(self):
        repo = self.make_seeded_repo("adopt-repo")
        worktree = self.add_worktree(repo, "feat/adopt")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        with state_mod.State():
            pass

        with mock.patch.dict(
            os.environ,
            {"AWA_INTEGRITY_PROBE_REPO": repo},
            clear=False,
        ):
            rows = lifecycle_reconcile.classify()

        row = next(
            item
            for item in rows
            if item.worktree_path == str(Path(worktree).resolve())
        )
        self.assertEqual(row.classification, "adopt_candidate")
        self.assertEqual(row.topology, "present_registered")
        self.assertEqual(row.content_safety, "clean")
        self.assertEqual(row.cached_remote, "redundant")

    def test_active_root_seeds_unleased_linked_discovery_and_problem_counts(self):
        repo = self.make_seeded_repo("active-root-repo")
        worktree = self.add_worktree(repo, "feat/active-native")
        branch = git(worktree, "symbolic-ref", "--short", "HEAD").stdout.strip()
        common = git(
            worktree,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
        awa_roots.heartbeat(
            worktree,
            branch=branch,
            common_dir=common,
            session_id="active-native-session",
        )

        with mock.patch.dict(
            os.environ,
            {"AWA_INTEGRITY_PROBE_REPO": str(self.state_home / "missing-probe")},
            clear=False,
        ):
            rows = lifecycle_reconcile.classify()
        row = next(
            item
            for item in rows
            if item.worktree_path == str(Path(worktree).resolve())
        )
        self.assertEqual(row.activity, "active")
        self.assertIsNone(row.lease_id)
        self.assertEqual(row.classification, "preserve")
        self.assertEqual(
            lifecycle_reconcile.summarize(rows),
            {
                "discovered_linked": 1,
                "managed": 0,
                "active": 1,
                "unleased": 1,
                "conflicts": 0,
                "problems": 1,
            },
        )
        with mock.patch.dict(
            os.environ,
            {"AWA_INTEGRITY_PROBE_REPO": str(self.state_home / "missing-probe")},
            clear=False,
        ):
            facts = integrity._lifecycle_facts(integrity._source_root())
        self.assertEqual(facts[:4], (None, None, None, None))
        self.assertEqual(facts[4]["discovered_linked"], 1)
        self.assertEqual(facts[4]["unleased"], 1)
        self.assertEqual(facts[4]["problems"], 1)

    def test_native_receipt_alone_seeds_repository_discovery(self):
        repo = self.make_seeded_repo("receipt-seed-repo")
        worktree = Path(self.add_worktree(repo, "feat/receipt-seed"))
        policy = Path(self._tmp.name) / "receipt-policy.yml"
        policy.write_text(
            "version: 1\n"
            f"governed_roots:\n  - {Path(repo).parent}\n"
            "default: include\n"
            "default_mode: on\n"
            "include:\n  - '*'\n"
            "exclude: []\n",
            encoding="utf-8",
        )
        with mock.patch.dict(
            os.environ,
            {
                "AWA_POLICY": str(policy),
                "AWA_GOVERNED_ROOT": str(Path(repo).parent),
            },
            clear=False,
        ):
            result = native_entry.register_session_start(
                {
                    "hook_event_name": "sessionStart",
                    "workspace_roots": [str(worktree)],
                    "session_id": "receipt-seed",
                }
            )
        self.assertEqual(result.result, "success")
        lease = lease_mod.read_lease(str(worktree))
        self.assertIsNotNone(lease)
        with state_mod.State() as state:
            state.conn.execute(
                "DELETE FROM leases WHERE lease_id=?",
                (lease["lease_id"],),
            )
        (worktree / ".awa" / "lease.json").unlink()
        (worktree / ".awa").rmdir()

        with mock.patch.dict(
            os.environ,
            {"AWA_INTEGRITY_PROBE_REPO": ""},
            clear=False,
        ):
            rows = lifecycle_reconcile.classify()
        self.assertTrue(
            any(
                row.worktree_path == str(worktree.resolve())
                for row in rows
            )
        )

    def test_on_disk_lease_without_active_db_lease_is_preserved(self):
        repo = self.make_seeded_repo("orphaned-lease-repo")
        (Path(repo) / ".gitignore").write_text(".awa/\n", encoding="utf-8")
        git(repo, "add", ".gitignore")
        git(repo, "commit", "-m", "ignore awa lease state")
        worktree = self.add_worktree(repo, "feat/orphaned-lease")
        git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        common_dir = git(
            worktree,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ).stdout.strip()
        lease_mod.write_lease(
            worktree,
            lease_mod.build_lease(
                worktree,
                "feat/orphaned-lease",
                common_dir,
                boot="old-boot",
            ),
        )
        with state_mod.State():
            pass

        with mock.patch.dict(
            os.environ,
            {"AWA_INTEGRITY_PROBE_REPO": repo},
            clear=False,
        ):
            rows = lifecycle_reconcile.classify()

        row = next(
            item
            for item in rows
            if item.worktree_path == str(Path(worktree).resolve())
        )
        self.assertIs(row.diagnostics["lease_on_disk"], True)
        self.assertEqual(row.classification, "preserve")
        unknown = _classify_one(
            _observation(
                leased=False,
                root_exists=True,
                registered=True,
                disposition="untracked",
                live_session=False,
                lease_on_disk=None,
                dirty=False,
                cached_remote=True,
            )
        )
        self.assertNotEqual(unknown.classification, "adopt_candidate")

    def test_pid_boot_are_diagnostic_only(self):
        first = _classify_one(
            _observation(pid=1, boot_id="current-looking-boot")
        )
        second = _classify_one(
            _observation(pid=999_999, boot_id="old-boot")
        )
        self.assertEqual(first.classification, second.classification)
        self.assertEqual(first.topology, second.topology)
        self.assertEqual(first.content_safety, second.content_safety)
        self.assertEqual(first.activity, second.activity)
        self.assertEqual(first.cached_remote, second.cached_remote)
        self.assertNotEqual(first.diagnostics["pid"], second.diagnostics["pid"])
        self.assertNotEqual(
            first.diagnostics["boot_id"],
            second.diagnostics["boot_id"],
        )

    def test_legacy_recovery_ambiguity_is_preserved(self):
        trash = self.state_home / "awa" / "recovery" / ".trash"
        trash.mkdir(parents=True)
        (trash / "legacy-unclassified.tar.gz").write_bytes(b"recovery")
        ambiguous = lifecycle_reconcile._journal_or_recovery_ambiguity(
            "/missing/worktree"
        )
        self.assertIs(ambiguous, True)
        self.assertEqual(
            _classify_one(
                replace(
                    _observation(),
                    journal_or_recovery_ambiguous=ambiguous,
                )
            ).classification,
            "preserve",
        )

    def test_git_probe_is_local_only_and_disables_locks_and_lazy_fetch(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
        inherited = {
            "GIT_DIR": "/wrong/repo",
            "GIT_SSH_COMMAND": "false network forbidden",
        }
        with mock.patch.dict(os.environ, inherited, clear=False), mock.patch.object(
            lifecycle_reconcile.subprocess,
            "run",
            return_value=completed,
        ) as run:
            lifecycle_reconcile._local_git(
                "/repo",
                "worktree",
                "list",
                "--porcelain",
                "-z",
            )

        command = run.call_args.args[0]
        env = run.call_args.kwargs["env"]
        self.assertEqual(
            command[-5:],
            ["-C", "/repo", "worktree", "list", "--porcelain", "-z"][-5:],
        )
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(env["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertNotIn("GIT_DIR", env)
        self.assertNotIn("GIT_SSH_COMMAND", env)
        self.assertFalse(
            {"fetch", "push", "pull", "ls-remote", "remote"}.intersection(
                command
            )
        )
        for remote_command in ("fetch", "push", "pull", "ls-remote", "remote"):
            with self.subTest(remote_command=remote_command):
                with self.assertRaises(ValueError):
                    lifecycle_reconcile._local_git("/repo", remote_command)

    def test_integrity_view_lifecycle_is_read_only_report(self):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status = {
            "schema": integrity.SCHEMA,
            "overall": "green",
            "triggers": {"launchd": {"last_success": now}},
        }
        row = _classify_one(_observation())
        args = cli.build_parser().parse_args(
            ["integrity", "view", "--lifecycle"]
        )
        stdout = io.StringIO()
        with mock.patch.object(
            cli.integrity_mod,
            "read_status",
            return_value=status,
        ), mock.patch.object(
            cli.lifecycle_reconcile_mod,
            "classify",
            return_value=[row],
        ) as classify, mock.patch.object(
            cli.integrity_mod,
            "_commit",
            side_effect=AssertionError("view attempted an integrity write"),
        ), contextlib.redirect_stdout(stdout):
            code = args.fn(args)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], integrity.SCHEMA)
        self.assertEqual(
            payload["lifecycle"][0]["classification"],
            "retire_candidate",
        )
        self.assertNotIn("lifecycle", status)
        classify.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
