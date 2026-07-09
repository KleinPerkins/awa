#!/usr/bin/env python3
"""Bounded, marker-validated fixture for the real-PM trial harness."""

from __future__ import annotations

import importlib.util
import json
import os
import secrets
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


OWNER_SCHEMA = "awa-trial-fixture/v1"
OWNER_FILE = ".awa-trial-owner.json"
NOTES_FILE = "pm-notes.txt"
INITIAL_NOTES = "A small piece of trial work.\n"
DIRTY_LINE = "A new PM edit that is not saved anywhere else.\n"


class FixtureError(RuntimeError):
    """The fixture could not be created or safely removed."""


class FixtureIdentityError(FixtureError):
    """The generated fixture commit has no usable existing identity."""


class FixtureCommitError(FixtureError):
    """The generated fixture commit failed."""


def _canonical(path: Path) -> Path:
    return Path(os.path.realpath(str(path)))


class TrialFixture:
    """Create one real repo + AWA linked worktree and tear down only proven-owned paths."""

    def __init__(
        self,
        *,
        awa_repo_root: Path,
        governed_root: Optional[Path] = None,
        personal_root: Optional[Path] = None,
        awa_cli: Optional[Path] = None,
        managed_root: Optional[Path] = None,
        nonce: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.awa_repo_root = _canonical(awa_repo_root)
        self.governed_root = _canonical(governed_root or (Path.home() / "dev"))
        self.personal_root = _canonical(personal_root or (self.governed_root / "personal"))
        cli_override = os.environ.get("AWA_TRIAL_AWA_CLI")
        self.awa_cli = _canonical(
            awa_cli
            or (Path(cli_override) if cli_override else None)
            or (self.governed_root / "_ops" / "bin" / "dev-worktree.sh")
        )
        data_home = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        self.managed_root = _canonical(
            managed_root or (data_home / "awa" / "trial-fixtures")
        )
        self.nonce = nonce or secrets.token_hex(8)
        self.primary = self.personal_root / ("awa-trial-" + self.nonce)
        self.origin = self.personal_root / (".awa-trial-origin-" + self.nonce + ".git")
        self.fixture_root = self.managed_root / self.nonce
        self.worktree = self.fixture_root / "worktree"
        self.branch = "awa-trial/" + self.nonce
        self.env = dict(os.environ if env is None else env)
        self.commands: List[Dict[str, Any]] = []
        self.facts: Optional[Dict[str, Any]] = None
        self.consequence: Optional[Dict[str, Any]] = None
        self.status_output = ""
        self.created = False
        self.cleaned = False
        self.preserved_reason: Optional[str] = None

    @property
    def created_paths(self) -> List[str]:
        return [str(self.origin), str(self.primary), str(self.worktree)]

    def _run(
        self,
        argv: List[str],
        *,
        cwd: Optional[Path] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.commands.append(
            {
                "argv": list(argv),
                "cwd": str(cwd) if cwd else None,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        )
        if check and proc.returncode:
            rendered = " ".join(shlex.quote(part) for part in argv)
            raise FixtureError(
                "command failed ({0}): {1}\n{2}".format(
                    proc.returncode, rendered, (proc.stderr or proc.stdout).strip()
                )
            )
        return proc

    def _owner_record(self) -> Dict[str, str]:
        return {
            "schema": OWNER_SCHEMA,
            "nonce": self.nonce,
            "origin": str(self.origin),
            "primary": str(self.primary),
            "worktree": str(self.worktree),
            "branch": self.branch,
        }

    def _write_owner(self, root: Path) -> None:
        path = root / OWNER_FILE
        path.write_text(
            json.dumps(self._owner_record(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _read_owner(self, root: Path) -> Optional[Dict[str, str]]:
        try:
            value = json.loads((root / OWNER_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return value if value == self._owner_record() else None

    def _git_path(self, root: Path, name: str) -> Path:
        proc = self._run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute", name]
        )
        return _canonical(Path(proc.stdout.strip()))

    def _load_kernel(self):
        path = self.awa_repo_root / "kernel" / "lib" / "awa_consequence.py"
        spec = importlib.util.spec_from_file_location(
            "awa_trial_fixture_consequence_" + self.nonce, str(path)
        )
        if spec is None or spec.loader is None:
            raise FixtureError("could not load the live AWA kernel probe")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _verify_existing_identity(self) -> None:
        name = self._run(
            ["git", "-C", str(self.primary), "config", "--get", "user.name"],
            check=False,
        ).stdout.strip()
        email = self._run(
            ["git", "-C", str(self.primary), "config", "--get", "user.email"],
            check=False,
        ).stdout.strip()
        env_name = self.env.get("GIT_AUTHOR_NAME") and self.env.get("GIT_COMMITTER_NAME")
        env_email = self.env.get("GIT_AUTHOR_EMAIL") and self.env.get("GIT_COMMITTER_EMAIL")
        if not ((name and email) or (env_name and env_email)):
            raise FixtureIdentityError(
                "fixture commit stopped: no existing git author/committer identity"
            )

    def create(self) -> "TrialFixture":
        if not self.awa_cli.is_file() or not os.access(str(self.awa_cli), os.X_OK):
            raise FixtureError("AWA worktree CLI is unavailable: " + str(self.awa_cli))
        if not self.personal_root.is_dir():
            raise FixtureError("personal fixture parent is unavailable: " + str(self.personal_root))
        for path in (self.primary, self.origin, self.fixture_root, self.worktree):
            if path.exists():
                raise FixtureError("refusing to reuse an existing fixture path: " + str(path))

        self._run(
            ["git", "init", "--bare", "--initial-branch=main", str(self.origin)]
        )
        self._write_owner(self.origin)
        self._run(["git", "clone", str(self.origin), str(self.primary)])
        self._write_owner(self.primary)
        (self.primary / NOTES_FILE).write_text(INITIAL_NOTES, encoding="utf-8")
        self._verify_existing_identity()
        self._run(["git", "-C", str(self.primary), "add", OWNER_FILE, NOTES_FILE])
        commit = self._run(
            ["git", "-C", str(self.primary), "commit", "-m", "Seed AWA PM trial fixture"],
            check=False,
        )
        if commit.returncode:
            detail = (commit.stderr or commit.stdout).strip()
            lowered = detail.lower()
            if "identity" in lowered or "who you are" in lowered or "user.email" in lowered:
                raise FixtureIdentityError("fixture commit stopped: " + detail)
            raise FixtureCommitError("fixture commit failed: " + detail)
        self._run(["git", "-C", str(self.primary), "push", "origin", "main"])

        ensure = self._run(
            [
                str(self.awa_cli),
                "ensure",
                "--base",
                "main",
                "--branch",
                self.branch,
                "--path",
                str(self.worktree),
                "--json",
            ],
            cwd=self.primary,
        )
        try:
            payload = json.loads(ensure.stdout)
        except ValueError as exc:
            raise FixtureError("AWA ensure returned invalid JSON") from exc
        if payload.get("action") != "created" or _canonical(
            Path(payload.get("rootPath", ""))
        ) != _canonical(self.worktree):
            raise FixtureError("AWA did not create the requested linked worktree")

        notes = self.worktree / NOTES_FILE
        if notes.read_text(encoding="utf-8") != INITIAL_NOTES:
            raise FixtureError("fixture notes did not match the seeded content")
        notes.write_text(INITIAL_NOTES + DIRTY_LINE, encoding="utf-8")
        self._validate_live_relationships()
        self.created = True
        return self

    def _validate_live_relationships(self) -> None:
        if self._read_owner(self.origin) is None:
            raise FixtureError("origin ownership marker is missing or changed")
        if self._read_owner(self.primary) is None or self._read_owner(self.worktree) is None:
            raise FixtureError("fixture ownership marker is missing or changed")
        if _canonical(self.primary.parent) != self.personal_root:
            raise FixtureError("fixture primary escaped the bounded personal directory")
        if _canonical(self.origin.parent) != self.personal_root:
            raise FixtureError("fixture origin escaped the bounded personal directory")
        if _canonical(self.worktree.parent) != self.fixture_root:
            raise FixtureError("fixture worktree escaped the bounded managed directory")

        primary_common = self._git_path(self.primary, "--git-common-dir")
        worktree_common = self._git_path(self.worktree, "--git-common-dir")
        worktree_git = self._git_path(self.worktree, "--git-dir")
        if primary_common != worktree_common or worktree_git == worktree_common:
            raise FixtureError("fixture is not a linked worktree of the generated primary")
        remote = self._run(
            ["git", "-C", str(self.primary), "remote", "get-url", "origin"]
        ).stdout.strip()
        if _canonical(Path(remote)) != _canonical(self.origin):
            raise FixtureError("fixture origin relationship changed")
        status = self._run(
            ["git", "-C", str(self.worktree), "status", "--porcelain"]
        ).stdout.splitlines()
        if status != [" M " + NOTES_FILE]:
            raise FixtureError("fixture contains changes other than the known generated edit")

        kernel = self._load_kernel()
        self.facts = kernel.probe_target(str(self.worktree))
        self.consequence = kernel.consequence_for_verb("cleanup", str(self.worktree))
        if not (
            self.facts.get("exists")
            and self.facts.get("has_uncommitted_changes")
            and self.consequence.get("destroys_unshared_work")
            and self.consequence.get("irreversible")
        ):
            raise FixtureError("live kernel probe did not see the known unsaved edit")
        self.status_output = self._run(
            [str(self.awa_cli), "status"], cwd=self.worktree
        ).stdout
        if "linked-worktree: yes" not in self.status_output:
            raise FixtureError("AWA status did not recognize the generated linked worktree")

    def teardown(self) -> bool:
        """Remove only exact, marker-proven fixture paths; preserve everything on uncertainty."""
        if self.cleaned:
            return True
        try:
            self._validate_live_relationships()
            notes = self.worktree / NOTES_FILE
            if notes.read_text(encoding="utf-8") != INITIAL_NOTES + DIRTY_LINE:
                raise FixtureError("known generated edit changed; preserving fixture")
            notes.write_text(INITIAL_NOTES, encoding="utf-8")
            status = self._run(
                ["git", "-C", str(self.worktree), "status", "--porcelain"]
            ).stdout.strip()
            if status:
                raise FixtureError("fixture did not become clean after restoring its known edit")

            # Validate every destructive boundary before asking AWA's normal, non-force clean path.
            if self._read_owner(self.origin) is None:
                raise FixtureError("origin ownership marker changed; preserving fixture")
            if self._read_owner(self.primary) is None or self._read_owner(self.worktree) is None:
                raise FixtureError("ownership marker changed; preserving fixture")
            self._run(
                [str(self.awa_cli), "clean", "--path", str(self.worktree), "--delete-branch"],
                cwd=self.primary,
            )
            if self.worktree.exists():
                raise FixtureError("AWA cleanup returned success but the worktree still exists")

            # These recursive removals are bounded to nonce-named, marker-validated helper paths.
            if self._read_owner(self.primary) is None or self._read_owner(self.origin) is None:
                raise FixtureError("ownership marker changed after AWA cleanup; preserving repos")
            shutil.rmtree(str(self.primary))
            shutil.rmtree(str(self.origin))
            try:
                self.fixture_root.rmdir()
            except OSError:
                pass
            self.cleaned = True
            return True
        except (FixtureError, OSError, ValueError) as exc:
            self.preserved_reason = str(exc)
            return False


__all__ = [
    "DIRTY_LINE",
    "FixtureCommitError",
    "FixtureError",
    "FixtureIdentityError",
    "INITIAL_NOTES",
    "NOTES_FILE",
    "OWNER_FILE",
    "OWNER_SCHEMA",
    "TrialFixture",
]
