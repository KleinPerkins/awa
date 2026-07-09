#!/usr/bin/env python3
"""Bounded, marker-validated fixture for the real-PM trial harness."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


OWNER_SCHEMA = "awa-trial-fixture/v1"
OWNER_FILE = ".awa-trial-owner.json"
NOTES_FILE = "pm-notes.txt"
INITIAL_NOTES = "A small piece of trial work.\n"
DIRTY_LINE = "A new PM edit that is not saved anywhere else.\n"
COMMAND_TIMEOUT_SECONDS = 60


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
        base_env = dict(os.environ if env is None else env)
        self.awa_repo_root = _canonical(awa_repo_root)
        env_home = Path(base_env.get("HOME", str(Path.home()))).expanduser()
        self.governed_root = _canonical(governed_root or (env_home / "dev"))
        self.personal_root = _canonical(personal_root or (self.governed_root / "personal"))
        cli_override = base_env.get("AWA_TRIAL_AWA_CLI")
        self.awa_cli = _canonical(
            awa_cli
            or (Path(cli_override) if cli_override else None)
            or (self.governed_root / "_ops" / "bin" / "dev-worktree.sh")
        )
        data_home = Path(
            base_env.get("XDG_DATA_HOME", str(env_home / ".local" / "share"))
        )
        self.managed_root = _canonical(
            managed_root or (data_home / "awa" / "trial-fixtures")
        )
        self.nonce = nonce or secrets.token_hex(8)
        self.primary = self.personal_root / ("awa-trial-" + self.nonce)
        self.origin = self.personal_root / (".awa-trial-origin-" + self.nonce + ".git")
        self.fixture_root = self.managed_root / self.nonce
        self.worktree = self.fixture_root / "worktree"
        self.branch = "awa-trial/" + self.nonce
        self.base_env = base_env
        self.env = self._isolated_git_env(base_env)
        self.commands: List[Dict[str, Any]] = []
        self.facts: Optional[Dict[str, Any]] = None
        self.consequence: Optional[Dict[str, Any]] = None
        self.status_output = ""
        self.created = False
        self.cleaned = False
        self.preserved_reason: Optional[str] = None
        self.directory_identities: Dict[str, tuple[int, int]] = {}
        self.notes_identity: Optional[tuple[int, int]] = None
        self.quarantine_paths: List[str] = []

    @staticmethod
    def _identity_from_git(env: Dict[str, str], variable: str) -> tuple[str, str]:
        try:
            proc = subprocess.run(
                ["git", "var", variable],
                env=env,
                text=True,
                capture_output=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise FixtureIdentityError(
                "fixture identity lookup timed out"
            ) from exc
        match = re.match(r"^(.*) <([^<>]+)> \d+ [+-]\d+$", proc.stdout.strip())
        if proc.returncode or match is None:
            raise FixtureIdentityError(
                "fixture commit stopped: no existing effective git identity"
            )
        return match.group(1), match.group(2)

    @classmethod
    def _isolated_git_env(cls, base_env: Dict[str, str]) -> Dict[str, str]:
        author_name, author_email = cls._identity_from_git(base_env, "GIT_AUTHOR_IDENT")
        committer_name, committer_email = cls._identity_from_git(
            base_env, "GIT_COMMITTER_IDENT"
        )
        env = dict(base_env)
        env.update(
            {
                "GIT_AUTHOR_NAME": author_name,
                "GIT_AUTHOR_EMAIL": author_email,
                "GIT_COMMITTER_NAME": committer_name,
                "GIT_COMMITTER_EMAIL": committer_email,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_COUNT": "3",
                "GIT_CONFIG_KEY_0": "core.hooksPath",
                "GIT_CONFIG_VALUE_0": os.devnull,
                "GIT_CONFIG_KEY_1": "commit.gpgSign",
                "GIT_CONFIG_VALUE_1": "false",
                "GIT_CONFIG_KEY_2": "tag.gpgSign",
                "GIT_CONFIG_VALUE_2": "false",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    @property
    def created_paths(self) -> List[str]:
        return [
            str(self.origin),
            str(self.primary),
            str(self.fixture_root),
            str(self.worktree),
        ]

    @property
    def recovery_guidance(self) -> str:
        paths = self.quarantine_paths or [
            path for path in self.created_paths if os.path.lexists(path)
        ]
        command = "ls -ld -- " + " ".join(shlex.quote(path) for path in paths)
        return (
            "inspect only these preserved paths; do not recursively delete until ownership is "
            "revalidated: {0}; read-only command: {1}".format(", ".join(paths), command)
        )

    def _record_directory(self, path: Path) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise FixtureError("fixture root is not a real directory: " + str(path))
        self.directory_identities[str(path)] = (info.st_dev, info.st_ino)

    def _assert_directory(self, path: Path, *, original: Optional[Path] = None) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise FixtureError("fixture directory became a symlink/non-directory: " + str(path))
        key = str(original or path)
        expected = self.directory_identities.get(key)
        if expected is None or (info.st_dev, info.st_ino) != expected:
            raise FixtureError("fixture directory identity changed: " + str(path))

    @staticmethod
    def _read_regular(path: Path, expected: Optional[tuple[int, int]] = None) -> tuple[bytes, tuple[int, int]]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise FixtureError("fixture file is not regular: " + str(path))
            identity = (info.st_dev, info.st_ino)
            if expected is not None and identity != expected:
                raise FixtureError("fixture file identity changed: " + str(path))
            chunks = []
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks), identity
        finally:
            os.close(fd)

    @staticmethod
    def _write_existing_regular(
        path: Path, content: bytes, expected: tuple[int, int]
    ) -> None:
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != expected:
                raise FixtureError("fixture file identity changed before write: " + str(path))
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            view = memoryview(content)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
            after = os.fstat(fd)
            if (after.st_dev, after.st_ino) != expected:
                raise FixtureError("fixture file identity changed during write: " + str(path))
        finally:
            os.close(fd)

    def _run(
        self,
        argv: List[str],
        *,
        cwd: Optional[Path] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                env=self.env,
                text=True,
                capture_output=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            self.commands.append(
                {
                    "argv": list(argv),
                    "cwd": str(cwd) if cwd else None,
                    "returncode": None,
                    "stdout": exc.stdout or "",
                    "stderr": exc.stderr or "",
                }
            )
            raise FixtureError(
                "command timed out after {0}s: {1}".format(
                    COMMAND_TIMEOUT_SECONDS,
                    " ".join(shlex.quote(part) for part in argv),
                )
            ) from exc
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
        content = (
            json.dumps(self._owner_record(), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags, 0o600)
        try:
            os.write(fd, content)
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read_owner(self, root: Path) -> Optional[Dict[str, str]]:
        try:
            raw, _ = self._read_regular(root / OWNER_FILE)
            value = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return value if value == self._owner_record() else None

    def _assert_root_not_active(self) -> None:
        gate = self._run(
            [
                sys.executable,
                "-I",
                "-B",
                str(self.awa_repo_root / "kernel" / "lib" / "awa_roots.py"),
                "gate",
                "--root",
                str(self.worktree),
            ]
        ).stdout.rstrip("\n").split("\t")
        if len(gate) != 5:
            raise FixtureError("root disposition gate returned unknown evidence")
        if gate[0] not in ("stale", "untracked"):
            raise FixtureError(
                "root disposition {0} blocks teardown: {1}".format(gate[0], gate[1])
            )

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
        required = (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
        )
        if not all(self.env.get(key) for key in required):
            raise FixtureIdentityError(
                "fixture commit stopped: no existing git author/committer identity"
            )

    def create(self) -> "TrialFixture":
        if not self.awa_cli.is_file() or not os.access(str(self.awa_cli), os.X_OK):
            raise FixtureError("AWA worktree CLI is unavailable: " + str(self.awa_cli))
        if not self.personal_root.is_dir():
            raise FixtureError("personal fixture parent is unavailable: " + str(self.personal_root))
        for path in (self.primary, self.origin, self.fixture_root, self.worktree):
            if os.path.lexists(str(path)):
                raise FixtureError("refusing to reuse an existing fixture path: " + str(path))

        self._run(
            ["git", "init", "--bare", "--initial-branch=main", str(self.origin)]
        )
        self._record_directory(self.origin)
        self._write_owner(self.origin)
        self._run(["git", "clone", str(self.origin), str(self.primary)])
        self._record_directory(self.primary)
        self._write_owner(self.primary)
        notes = self.primary / NOTES_FILE
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(notes), flags, 0o600)
        try:
            os.write(fd, INITIAL_NOTES.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
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

        self._record_directory(self.fixture_root)
        self._record_directory(self.worktree)
        notes = self.worktree / NOTES_FILE
        content, self.notes_identity = self._read_regular(notes)
        if content.decode("utf-8") != INITIAL_NOTES:
            raise FixtureError("fixture notes did not match the seeded content")
        self._write_existing_regular(
            notes,
            (INITIAL_NOTES + DIRTY_LINE).encode("utf-8"),
            self.notes_identity,
        )
        self._validate_live_relationships()
        self.created = True
        return self

    def _validate_live_relationships(self) -> None:
        for path in (self.origin, self.primary, self.fixture_root, self.worktree):
            self._assert_directory(path)
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
        if (
            primary_common != _canonical(self.primary / ".git")
            or primary_common != worktree_common
            or worktree_git == worktree_common
            or _canonical(worktree_git.parent.parent) != worktree_common
        ):
            raise FixtureError("fixture is not a linked worktree of the generated primary")
        primary_branch = self._run(
            ["git", "-C", str(self.primary), "symbolic-ref", "--short", "HEAD"]
        ).stdout.strip()
        worktree_branch = self._run(
            ["git", "-C", str(self.worktree), "symbolic-ref", "--short", "HEAD"]
        ).stdout.strip()
        if primary_branch != "main" or worktree_branch != self.branch:
            raise FixtureError("fixture symbolic HEAD does not match the requested branches")
        primary_head = self._run(
            ["git", "-C", str(self.primary), "rev-parse", "HEAD"]
        ).stdout.strip()
        worktree_head = self._run(
            ["git", "-C", str(self.worktree), "rev-parse", "HEAD"]
        ).stdout.strip()
        if primary_head != worktree_head:
            raise FixtureError("fixture linked worktree HEAD drifted from its requested base")
        registry = self._run(
            ["git", "-C", str(self.primary), "worktree", "list", "--porcelain"]
        ).stdout
        blocks = [block.splitlines() for block in registry.strip().split("\n\n")]
        matches = [
            block
            for block in blocks
            if "worktree " + str(_canonical(self.worktree)) in block
        ]
        expected_branch = "branch refs/heads/" + self.branch
        if (
            len(matches) != 1
            or "HEAD " + worktree_head not in matches[0]
            or expected_branch not in matches[0]
        ):
            raise FixtureError("git worktree registry does not map the requested path/branch/HEAD")
        remote = self._run(
            ["git", "-C", str(self.primary), "remote", "get-url", "origin"]
        ).stdout.strip()
        if _canonical(Path(remote)) != _canonical(self.origin):
            raise FixtureError("fixture origin relationship changed")
        if self.notes_identity is None:
            raise FixtureError("fixture notes identity was not recorded")
        notes_content, _ = self._read_regular(
            self.worktree / NOTES_FILE, self.notes_identity
        )
        if notes_content.decode("utf-8") != INITIAL_NOTES + DIRTY_LINE:
            raise FixtureError("known generated edit changed; preserving fixture")
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

    def _quarantine(self, path: Path, label: str) -> Path:
        self._assert_directory(path)
        if self._read_owner(path) is None:
            raise FixtureError("ownership marker changed before quarantine: " + str(path))
        destination = path.parent / (
            ".awa-trial-quarantine-{0}-{1}".format(self.nonce, label)
        )
        if os.path.lexists(str(destination)):
            raise FixtureError("quarantine destination already exists: " + str(destination))
        os.rename(str(path), str(destination))
        self._assert_directory(destination, original=path)
        if self._read_owner(destination) is None:
            raise FixtureError("ownership marker changed during quarantine: " + str(destination))
        self.quarantine_paths.append(str(destination))
        return destination

    def teardown(self) -> bool:
        """Remove only exact, marker-proven fixture paths; preserve everything on uncertainty."""
        if self.cleaned:
            return True
        try:
            self._assert_root_not_active()
            self._validate_live_relationships()
            notes = self.worktree / NOTES_FILE
            if self.notes_identity is None:
                raise FixtureError("fixture notes identity was not recorded")
            content, _ = self._read_regular(notes, self.notes_identity)
            if content.decode("utf-8") != INITIAL_NOTES + DIRTY_LINE:
                raise FixtureError("known generated edit changed; preserving fixture")
            self._assert_root_not_active()
            self._validate_live_relationships()
            self._write_existing_regular(
                notes, INITIAL_NOTES.encode("utf-8"), self.notes_identity
            )
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
            for path in (self.origin, self.primary, self.fixture_root, self.worktree):
                self._assert_directory(path)
            self._assert_root_not_active()
            self._run(
                [str(self.awa_cli), "clean", "--path", str(self.worktree), "--delete-branch"],
                cwd=self.primary,
            )
            if self.worktree.exists():
                raise FixtureError("AWA cleanup returned success but the worktree still exists")

            # These recursive removals are bounded to nonce-named, marker-validated helper paths.
            if self._read_owner(self.primary) is None or self._read_owner(self.origin) is None:
                raise FixtureError("ownership marker changed after AWA cleanup; preserving repos")
            self._assert_directory(self.primary)
            self._assert_directory(self.origin)
            quarantined_primary = self._quarantine(self.primary, "primary")
            quarantined_origin = self._quarantine(self.origin, "origin")
            for quarantined, original in (
                (quarantined_primary, self.primary),
                (quarantined_origin, self.origin),
            ):
                self._assert_directory(quarantined, original=original)
                if self._read_owner(quarantined) is None:
                    raise FixtureError(
                        "quarantined ownership marker changed: " + str(quarantined)
                    )
            shutil.rmtree(str(quarantined_primary))
            shutil.rmtree(str(quarantined_origin))
            self.quarantine_paths = []
            self._assert_directory(self.fixture_root)
            self.fixture_root.rmdir()
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
