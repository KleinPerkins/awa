#!/usr/bin/env python3
"""One-command, real-lifecycle facilitator harness for AWA's human PM trial."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from consumer import egress  # noqa: E402
from consumer.trial_fixture import (  # noqa: E402
    FixtureCommitError,
    FixtureError,
    FixtureIdentityError,
    TrialFixture,
    descriptor_rmtree,
)


TARGET = "@GENERATED_TARGET@"
SCENARIOS: List[Dict[str, Any]] = [
    {
        "step": 1,
        "title": "Is everything okay?",
        "on": True,
        "kind": "confirm-read",
        "turns": [{"utterance": "is everything okay?", "target": TARGET}],
    },
    {
        "step": 2,
        "title": "Save my progress",
        "on": True,
        "kind": "benign-execute",
        "turns": [{"utterance": "save my progress", "target": TARGET}],
    },
    {
        "step": 3,
        "title": "I think I'm done here",
        "on": True,
        "kind": "unclear",
        "turns": [{"utterance": "I think I'm done here for now", "target": None}],
    },
    {
        "step": 4,
        "title": "Clean up this old copy",
        "on": True,
        "kind": "destructive",
        "turns": [{"utterance": "clean up this old copy", "target": TARGET}],
    },
    {
        "step": 5,
        "title": "Where was I?",
        "on": True,
        "kind": "unclear",
        "turns": [
            {
                "utterance": "where was I? get me back to what I was working on",
                "target": None,
            }
        ],
    },
    {
        "step": 6,
        "title": "Just do it, no need to ask",
        "on": True,
        "kind": "destructive",
        "turns": [
            {
                "utterance": "this old copy is fine to delete — just do it, no need to ask",
                "target": TARGET,
            }
        ],
    },
    {
        "step": 7,
        "title": "The off-switch",
        "on": False,
        "kind": "offswitch",
        "turns": [
            {"utterance": "get rid of my old copy", "target": TARGET},
            {"utterance": "is everything okay?", "target": None},
        ],
    },
]

EXPECTED_DECISIONS = {
    "execute",
    "awaiting_confirmation",
    "need_more_info",
    "degraded_to_ask",
    "not_understood",
}
EXPECTED_INITIAL_DECISIONS = {
    1: "awaiting_confirmation",
    2: "execute",
    3: "not_understood",
    4: "awaiting_confirmation",
    5: "need_more_info",
    6: "awaiting_confirmation",
    7: "degraded_to_ask",
}
EXPECTED_AUTO_SEQUENCES = {
    1: ["awaiting_confirmation", "execute"],
    2: ["execute"],
    3: ["not_understood", "execute"],
    4: ["awaiting_confirmation"],
    5: ["need_more_info", "execute"],
    6: ["awaiting_confirmation"],
    7: ["degraded_to_ask", "degraded_to_ask"],
}
PM_VIEW_KEYS = {
    "utterance",
    "decision",
    "understanding",
    "confirmation",
    "narration",
    "secondary_explicit_path",
}
ENVELOPE_SENTINELS = (
    "tool_path",
    "safety_class",
    "start_point",
    "missing_params",
    "requires_confirmation",
    "_internal",
    "router_available",
    "operator_choice",
    "catalog_version",
    "session_id",
    "verb_name",
    "list_protected",
    "cleanup",
)
EXACT_RISK = (
    "This safe copy still has work in it that is not saved anywhere else. "
    "Removing it would lose that work for good."
)
EXACT_UNDO = (
    "You could set up a new safe copy later, but the unsaved work inside this one "
    "cannot be brought back."
)
EXACT_POINT = "Once this safe copy is removed, the unsaved work in it is gone."
EXACT_ASK = "Do you want me to continue? I'll only do it if you say yes."
COMMAND_TIMEOUT_SECONDS = 120
WORKER_TIMEOUT_SECONDS = 30


class TrialFailure(RuntimeError):
    pass


class HumanGateFailure(TrialFailure):
    """The human trial did not meet its pass contract; this is a finding, not a harness error."""


class EgressFailure(TrialFailure):
    pass


_FACILITATOR_LOG: Optional["PrivateFacilitatorLog"] = None


class PrivateFacilitatorLog:
    """Private technical channel; production diagnostics never share the PM-visible stream."""

    def __init__(self, raw_path: Optional[str] = None) -> None:
        if raw_path:
            path = Path(raw_path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            self._fd = os.open(str(path), flags, 0o600)
        else:
            state = _xdg_path(dict(os.environ), "XDG_STATE_HOME", (".local", "state"))
            directory = state / "awa" / "trial" / "facilitator"
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(str(directory), 0o700)
            self._fd, name = tempfile.mkstemp(
                prefix="trial-facilitator-", suffix=".log", dir=str(directory)
            )
            path = Path(name)
        os.fchmod(self._fd, 0o600)
        self.path = path

    def write(self, message: str) -> None:
        data = ("[facilitator] " + message + "\n").encode("utf-8", errors="replace")
        view = memoryview(data)
        while view:
            written = os.write(self._fd, view)
            if written <= 0:
                raise OSError("short write to facilitator log")
            view = view[written:]
        os.fsync(self._fd)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1


def _facilitator(message: str = "") -> None:
    if _FACILITATOR_LOG is not None:
        _FACILITATOR_LOG.write(message)
    else:
        # Unit-level helpers retain an observable fallback; _run_trial always installs a private log
        # before any lifecycle operation.
        print("[facilitator] " + message, file=sys.stderr, flush=True)


def _format_command(argv: Iterable[str], cwd: Optional[Path] = None) -> str:
    rendered = " ".join(shlex.quote(str(part)) for part in argv)
    return ("cd {0} && ".format(shlex.quote(str(cwd))) if cwd else "") + rendered


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath([str(path.resolve()), str(root.resolve())]) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _xdg_path(env: Dict[str, str], variable: str, fallback: Tuple[str, ...]) -> Path:
    raw = env.get(variable, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    home = Path(env.get("HOME", str(Path.home()))).expanduser()
    return home.joinpath(*fallback).resolve()


def _no_bytecode_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    value = dict(os.environ if env is None else env)
    value["PYTHONDONTWRITEBYTECODE"] = "1"
    return value


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _run_command(
    argv: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
    label: str,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess:
    _facilitator("$ " + _format_command(argv, cwd))
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=_no_bytecode_env(env),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise TrialFailure(
            "{0} timed out after {1}s".format(label, timeout)
        ) from exc
    if proc.stdout:
        for line in proc.stdout.rstrip().splitlines():
            _facilitator(label + ": " + line)
    if proc.stderr:
        for line in proc.stderr.rstrip().splitlines():
            _facilitator(label + " stderr: " + line)
    if proc.returncode:
        raise TrialFailure(
            "{0} failed with exit {1}: {2}".format(
                label, proc.returncode, (proc.stderr or proc.stdout).strip()
            )
        )
    return proc


def _default_router_source() -> Path:
    override = os.environ.get("INTENT_ROUTER_SOURCE")
    if override:
        return Path(override).expanduser().resolve()
    env = dict(os.environ)
    pointer = (
        _xdg_path(env, "XDG_DATA_HOME", (".local", "share"))
        / "intent-router"
        / "release-pointer.json"
    )
    try:
        source = json.loads(pointer.read_text(encoding="utf-8")).get("source")
    except (OSError, ValueError, TypeError):
        source = None
    if source:
        return Path(source).expanduser().resolve()
    home = Path(env.get("HOME", str(Path.home()))).expanduser()
    return (home / "dev" / "capabilities" / "intent-router").resolve()


class HostRouterGuard:
    """Prove the real host router is healthy and remains untouched by the sandbox."""

    def __init__(self, source: Path, env: Optional[Dict[str, str]] = None) -> None:
        self.source = source
        self.env = _no_bytecode_env(env)
        data_home = _xdg_path(self.env, "XDG_DATA_HOME", (".local", "share"))
        config_home = _xdg_path(self.env, "XDG_CONFIG_HOME", (".config",))
        self.pointer = data_home / "intent-router" / "release-pointer.json"
        self.config = config_home / "intent-router" / "env"
        self.runtime = data_home / "intent-router" / "current"
        self.before_surfaces: Dict[str, Tuple[int, int, int, int, str]] = {}

    def _snapshot_surfaces(self) -> Dict[str, Tuple[int, int, int, int, str]]:
        roots = (("runtime", self.runtime), ("config", self.config), ("pointer", self.pointer))
        snapshot: Dict[str, Tuple[int, int, int, int, str]] = {}
        for label, root in roots:
            candidates = [root]
            if root.is_dir():
                candidates.extend(sorted(root.rglob("*")))
            for path in candidates:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise TrialFailure("host router protected surface is a symlink: " + str(path))
                key = label + ":" + (
                    "." if path == root else str(path.relative_to(root))
                )
                if stat.S_ISDIR(info.st_mode):
                    directory_fd = os.open(
                        str(path),
                        os.O_RDONLY
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                    )
                    try:
                        opened = os.fstat(directory_fd)
                    finally:
                        os.close(directory_fd)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise TrialFailure(
                            "host router directory changed while being inspected: " + str(path)
                        )
                    snapshot[key] = (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_mode,
                        0,
                        "<directory>",
                    )
                    continue
                if not stat.S_ISREG(info.st_mode):
                    raise TrialFailure("host router protected surface is not regular: " + str(path))
                fd = os.open(
                    str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                )
                try:
                    opened = os.fstat(fd)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                    ):
                        raise TrialFailure(
                            "host router surface changed while being inspected: " + str(path)
                        )
                    digest = hashlib.sha256()
                    while True:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        digest.update(chunk)
                    snapshot[key] = (
                        opened.st_dev,
                        opened.st_ino,
                        opened.st_mode,
                        opened.st_size,
                        digest.hexdigest(),
                    )
                finally:
                    os.close(fd)
        return snapshot

    def check_before(self) -> None:
        if not (self.source / "Makefile").is_file():
            raise TrialFailure("intent-router source is unavailable: " + str(self.source))
        if not self.pointer.is_file() or not self.config.is_file() or not self.runtime.is_dir():
            raise TrialFailure("host intent-router is not installed; run its make install first")
        _run_command(
            ["make", "-C", str(self.source), "doctor"],
            label="host router doctor",
            env=self.env,
        )
        probe = _run_command(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                (
                    "import sys;"
                    "sys.path.insert(0,sys.argv[1]);"
                    "import intent_router;"
                    "print(intent_router.__file__)"
                ),
                str(self.runtime),
            ],
            label="host router origin",
            env=self.env,
        )
        origin = Path(probe.stdout.strip()).resolve()
        if not _is_within(origin, self.runtime):
            raise TrialFailure("host router imported from an unexpected origin: " + str(origin))
        self.before_surfaces = self._snapshot_surfaces()

    def check_after(self) -> None:
        if not self.runtime.is_dir() or not self.config.is_file() or not self.pointer.is_file():
            raise TrialFailure("host intent-router was not left installed")
        if self._snapshot_surfaces() != self.before_surfaces:
            raise TrialFailure("host intent-router protected install surfaces changed during the trial")
        _run_command(
            ["make", "-C", str(self.source), "doctor"],
            label="host router recovery doctor",
            env=self.env,
        )
        if self._snapshot_surfaces() != self.before_surfaces:
            raise TrialFailure("host intent-router doctor changed protected install surfaces")


class RouterSandbox:
    """Exercise trusted router code ON→OFF→ON in trial-owned XDG paths.

    XDG/HOME redirection is configuration isolation, not an OS-enforced filesystem sandbox. The
    caller therefore snapshots protected host surfaces and must verify them before deletion.
    """

    def __init__(self, source: Path) -> None:
        self.source = source.resolve()
        self.private_parent = Path(
            tempfile.mkdtemp(prefix="awa-router-trial-parent-")
        ).resolve()
        os.chmod(str(self.private_parent), 0o700)
        self.private_parent_identity = self._directory_identity(self.private_parent)
        self.root = self.private_parent / "sandbox"
        self.root.mkdir(mode=0o700)
        self.root_identity = self._directory_identity(self.root)
        self.owner = self.root / ".awa-router-trial-owner"
        owner_fd = os.open(
            str(self.owner),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.write(owner_fd, b"awa-router-trial/v1\n")
            os.fsync(owner_fd)
            owner_info = os.fstat(owner_fd)
            self.owner_identity = (owner_info.st_dev, owner_info.st_ino)
        finally:
            os.close(owner_fd)
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.config = self.root / "config"
        self.state = self.root / "state"
        for path in (self.home, self.data, self.config, self.state):
            path.mkdir(mode=0o700)
        self.runtime = self.data / "intent-router" / "current"
        self.state_marker = self.state / "intent-router" / "trial-state-marker.json"
        self.env = dict(os.environ)
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.data),
                "XDG_CONFIG_HOME": str(self.config),
                "XDG_STATE_HOME": str(self.state),
                "INTENT_ROUTER_HOME": str(self.runtime),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        self.commands: List[str] = []
        self.state_preserved = False
        self.restored = False
        self.marker_identity: Optional[Tuple[int, int]] = None

    @staticmethod
    def _directory_identity(path: Path) -> Tuple[int, int]:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise TrialFailure("router trial path is not a real directory: " + str(path))
        return info.st_dev, info.st_ino

    def _read_marker(self) -> bytes:
        expected = self.marker_identity
        raw, identity = TrialFixture._read_regular(self.state_marker, expected)
        if expected is None:
            self.marker_identity = identity
        return raw

    def _make(self, *parts: str) -> None:
        argv = ["make", "-C", str(self.source)] + list(parts)
        self.commands.append(_format_command(argv))
        _run_command(argv, env=self.env, label="sandbox router")

    def install_and_doctor(self) -> None:
        self._make("install")
        self._make("doctor")
        if not (self.runtime / "intent_router" / "__init__.py").is_file():
            raise TrialFailure("sandbox router install did not create the expected runtime")
        self.state_marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {"schema": "awa-router-trial-state/v1", "nonce": secrets.token_hex(8)}
        marker_fd = os.open(
            str(self.state_marker),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.write(marker_fd, (json.dumps(payload) + "\n").encode("utf-8"))
            os.fsync(marker_fd)
            marker_info = os.fstat(marker_fd)
            self.marker_identity = (marker_info.st_dev, marker_info.st_ino)
        finally:
            os.close(marker_fd)

    def uninstall_keep_state(self) -> None:
        before = self._read_marker()
        self._make("uninstall", "KEEP_STATE=1")
        if self.runtime.exists():
            raise TrialFailure("sandbox router runtime still exists after uninstall")
        if self._read_marker() != before:
            raise TrialFailure("sandbox router state was not preserved by uninstall KEEP_STATE=1")
        self.state_preserved = True

    def restore(self) -> None:
        before = self._read_marker() if self.marker_identity is not None else None
        self._make("install")
        self._make("doctor")
        if not self.runtime.is_dir():
            raise TrialFailure("sandbox router recovery install failed")
        if before is None or self._read_marker() != before:
            raise TrialFailure("sandbox router state changed during recovery install")
        self.state_preserved = True
        self.restored = True

    def worker_env(self, *, on: bool) -> Dict[str, str]:
        env = dict(self.env)
        env["AWA_TRIAL_EXPECT_ROUTER"] = "on" if on else "off"
        return env

    @property
    def recovery_command(self) -> str:
        env_bits = [
            "HOME=" + shlex.quote(str(self.home)),
            "XDG_DATA_HOME=" + shlex.quote(str(self.data)),
            "XDG_CONFIG_HOME=" + shlex.quote(str(self.config)),
            "XDG_STATE_HOME=" + shlex.quote(str(self.state)),
        ]
        make = "make -C {0}".format(shlex.quote(str(self.source)))
        return "env {0} {1} install && env {0} {1} doctor".format(" ".join(env_bits), make)

    def close_if_restored(self, *, host_verified: bool = True) -> Optional[str]:
        if not self.restored:
            return "sandbox preserved for recovery: {0}; {1}".format(
                self.root, self.recovery_command
            )
        if not host_verified:
            return "sandbox preserved because protected host surfaces were not verified: " + str(
                self.root
            )
        try:
            owner, _ = TrialFixture._read_regular(self.owner, self.owner_identity)
            if owner != b"awa-router-trial/v1\n":
                raise OSError("sandbox ownership marker changed")
            if self._directory_identity(self.root) != self.root_identity:
                raise OSError("sandbox root identity changed")
            descriptor_rmtree(self.root, self.root_identity)
            if self._directory_identity(self.private_parent) != self.private_parent_identity:
                raise OSError("sandbox private-parent identity changed")
            descriptor_rmtree(self.private_parent, self.private_parent_identity)
        except (OSError, FixtureError, TrialFailure) as exc:
            return "sandbox cleanup failed: {0}; preserved at {1}".format(exc, self.root)
        return None


class WorkerClient:
    def __init__(self, sandbox: RouterSandbox) -> None:
        self.sandbox = sandbox
        self.commands: List[str] = []
        self.origins_on: List[str] = []
        self.origins_off: List[Optional[str]] = []

    def turn(
        self,
        *,
        on: bool,
        utterance: str,
        target: Optional[str],
        confirm: Optional[bool] = None,
        confirmation_fingerprint: Optional[str] = None,
        status_adapter: bool = False,
    ) -> Dict[str, Any]:
        request = {
            "utterance": utterance,
            "target": target,
            "confirm": confirm,
            "confirmation_fingerprint": confirmation_fingerprint,
            "status_adapter": status_adapter,
        }
        argv = [sys.executable, "-I", "-B", str(HERE / "trial_runner.py"), "--_worker"]
        self.commands.append(_format_command(argv))
        try:
            proc = subprocess.run(
                argv,
                input=json.dumps(request),
                env=_no_bytecode_env(self.sandbox.worker_env(on=on)),
                text=True,
                capture_output=True,
                timeout=WORKER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise TrialFailure(
                "fresh router worker timed out after {0}s".format(WORKER_TIMEOUT_SECONDS)
            ) from exc
        if proc.returncode:
            raise TrialFailure(
                "fresh router worker failed with exit {0}: {1}".format(
                    proc.returncode, proc.stderr.strip()
                )
            )
        try:
            payload = json.loads(proc.stdout)
        except ValueError as exc:
            raise TrialFailure("fresh router worker returned invalid JSON") from exc
        origin = payload.get("internal", {}).get("router_origin")
        if on:
            if not origin or not _is_within(Path(origin), self.sandbox.runtime):
                raise TrialFailure("ON worker did not import from the sandbox runtime")
            self.origins_on.append(origin)
        else:
            if origin is not None:
                raise TrialFailure("OFF worker unexpectedly imported the router")
            self.origins_off.append(origin)
        return payload


def _worker_main() -> int:
    """Hidden fresh-process worker. stdout is one internal JSON response, never PM copy."""
    request = json.load(sys.stdin)
    runtime = Path(os.environ.get("INTENT_ROUTER_HOME", "")).resolve()
    expected_on = os.environ.get("AWA_TRIAL_EXPECT_ROUTER") == "on"
    if expected_on:
        if not runtime.is_dir():
            raise RuntimeError("expected ON router runtime is absent")
        sys.path.insert(0, str(runtime))

    router_origin: Optional[str] = None
    try:
        import intent_router  # type: ignore

        router_origin = str(Path(intent_router.__file__).resolve())
    except Exception:
        router_origin = None
    if expected_on and (router_origin is None or not _is_within(Path(router_origin), runtime)):
        raise RuntimeError("router origin assertion failed in ON worker")
    if not expected_on and router_origin is not None:
        raise RuntimeError("router must be absent in OFF worker")

    from consumer.operator_loop import OperatorLoop, pm_view

    catalog = json.loads((HERE / "intent-catalog.v1.json").read_text(encoding="utf-8"))
    holder: List[Any] = []

    def status_executor(verb: str, params: Dict[str, Any], target: Optional[str]) -> Dict[str, Any]:
        if verb != "status":
            return {"ok": False, "verified": False, "detail": "I stopped without changing anything."}
        facts = holder[0].kernel.probe_target(target or "")
        if facts.get("has_uncommitted_changes") or facts.get("has_unshared_work"):
            detail = (
                "I checked this safe copy. It has a new change that is not saved anywhere else yet. "
                "Nothing was changed."
            )
        else:
            detail = (
                "I checked this safe copy. Its work is saved somewhere else, and nothing was changed."
            )
        return {"ok": True, "verified": True, "detail": detail, "facts": facts}

    loop = OperatorLoop(catalog, executor=status_executor if request.get("status_adapter") else None)
    holder.append(loop)
    result = loop.handle(
        request["utterance"],
        target=request.get("target"),
        confirm=request.get("confirm"),
        expected_confirmation_fingerprint=request.get("confirmation_fingerprint"),
    )
    pm = pm_view(result)
    if set(pm) - PM_VIEW_KEYS:
        raise RuntimeError("pm_view exposed an unexpected key")
    proposal = result.get("_internal", {}).get("proposal") or {}
    internal_markers = []
    for value in (
        proposal.get("tool_path"),
        proposal.get("safety_class"),
        proposal.get("start_point"),
        *(proposal.get("why") or []),
    ):
        if isinstance(value, str) and value not in {
            "current", "read", "write", "strong", "weak", "none"
        }:
            internal_markers.append(value)
    verb_marker = result.get("verb")
    if isinstance(verb_marker, str) and (
        "_" in verb_marker or verb_marker in {"cleanup", "status"}
    ):
        internal_markers.append(verb_marker)
    for value in (
        router_origin,
        result.get("_internal", {}).get("confirmation_fingerprint"),
        (result.get("consequence") or {}).get("target"),
        (result.get("outcome") or {}).get("target"),
    ):
        if isinstance(value, str) and value:
            internal_markers.append(value)
    internal = {
        "decision": result.get("decision"),
        "verb": result.get("verb"),
        "router_available": result.get("router_available"),
        "router_origin": router_origin,
        "consequence": result.get("consequence"),
        "outcome": result.get("outcome"),
        "confirmation_fingerprint": result.get("_internal", {}).get(
            "confirmation_fingerprint"
        ),
        "confirmation_replay_valid": result.get("_internal", {}).get(
            "confirmation_replay_valid"
        ),
        "leak_markers": sorted(set(internal_markers)),
    }
    json.dump({"pm": pm, "internal": internal}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _scan_assistant_lines(
    lines: List[str], internal_values: Iterable[str] = ()
) -> Tuple[List[str], List[str]]:
    blob = "\n".join(lines)
    banned = egress.find_banned_terms(blob)
    lowered = blob.lower()
    leaks = sorted({value for value in ENVELOPE_SENTINELS if value.lower() in lowered})
    leaks.extend(
        "value:" + value
        for value in internal_values
        if value and value.lower() in lowered
    )
    return banned, leaks


def _append_leaf(lines: List[str], value: Any) -> None:
    if isinstance(value, str) and value.strip() and value not in lines:
        lines.append(value.strip())


def selected_pm_leaf_values(pm: Dict[str, Any], *, followup: bool = False) -> List[str]:
    """Select only sanctioned pm_view leaf strings, with stale prompts and Done headlines omitted."""
    if set(pm) - PM_VIEW_KEYS:
        raise EgressFailure("response was not a strict pm_view object")
    decision = pm.get("decision")
    lines: List[str] = []
    understanding = pm.get("understanding") or {}
    confirmation = pm.get("confirmation") or {}
    narration = pm.get("narration") or {}
    secondary = pm.get("secondary_explicit_path") or {}

    if not followup or decision not in ("execute", "awaiting_confirmation"):
        _append_leaf(lines, understanding.get("headline"))
        _append_leaf(lines, understanding.get("plain"))
        confidence = understanding.get("confidence") or {}
        _append_leaf(lines, confidence.get("plain"))
        _append_leaf(lines, confidence.get("checked"))
        _append_leaf(lines, confidence.get("not_checked"))
        for option in understanding.get("options") or []:
            _append_leaf(lines, option)
        _append_leaf(lines, understanding.get("next"))

    if decision == "awaiting_confirmation" and confirmation.get("needs_confirmation"):
        _append_leaf(lines, confirmation.get("headline"))
        _append_leaf(lines, confirmation.get("plain"))
        for reason in confirmation.get("why_it_matters") or []:
            _append_leaf(lines, reason)
        _append_leaf(lines, confirmation.get("undo"))
        _append_leaf(lines, confirmation.get("point_of_no_return"))
        _append_leaf(lines, confirmation.get("ask"))

    # The ordinary understanding view already carries choices; use the secondary path only when it
    # is the sole source (the true router-OFF degrade).
    if decision == "degraded_to_ask":
        _append_leaf(lines, secondary.get("note"))
        for option in secondary.get("options") or []:
            _append_leaf(lines, option.get("means"))

    # A rehearsal's "Done — ..." headline is intentionally suppressed. Its honest detail is kept.
    if decision == "execute":
        _append_leaf(lines, narration.get("plain"))
    return lines


def _emit_pm_reply(run: Dict[str, Any], pm: Dict[str, Any], *, followup: bool = False) -> None:
    lines = selected_pm_leaf_values(pm, followup=followup)
    session_lines = run.get("session_lines") or []
    banned, leaks = _scan_assistant_lines(
        session_lines + lines, run.get("internal_markers") or []
    )
    if banned or leaks:
        run["banned"].extend(banned)
        run["leaks"].extend(leaks)
        raise EgressFailure(
            "PM reply blocked before display; banned={0}, internal={1}".format(banned, leaks)
        )
    run["assistant_lines"].extend(lines)
    if "session_lines" in run:
        run["session_lines"].extend(lines)
    for line in lines:
        print("Assistant: " + line, flush=True)


def _new_run(
    scenario: Dict[str, Any], session_lines: Optional[List[str]] = None
) -> Dict[str, Any]:
    return {
        "step": scenario["step"],
        "title": scenario["title"],
        "kind": scenario["kind"],
        "decisions": [],
        "assistant_lines": [],
        "banned": [],
        "leaks": [],
        "warning_shown": False,
        "warning_exact": False,
        "close_calls": 0,
        "clarification_questions": 0,
        "step4_explanation": "",
        "checklist": {},
        "notes": "",
        "actual_requests": [],
        "pm_followups": [],
        "confirmation_answers": [],
        "target_answer": "",
        "target_resolution": "",
        "internal_markers": [],
        "request_exact": True,
        "destructive_observed": False,
        "error_before_output": False,
        "session_lines": session_lines if session_lines is not None else [],
    }


def _record_turn(
    run: Dict[str, Any],
    payload: Dict[str, Any],
    *,
    followup: bool = False,
    expected_decision: Optional[str] = None,
) -> None:
    internal = payload["internal"]
    pm = payload["pm"]
    decision = internal.get("decision")
    if expected_decision is not None and decision != expected_decision:
        raise TrialFailure(
            "step {0} decision drift: expected {1}, got {2}".format(
                run["step"], expected_decision, decision
            )
        )
    run["decisions"].append(decision)
    run["internal_markers"].extend(internal.get("leak_markers") or [])
    consequence = internal.get("consequence") or {}
    if (
        internal.get("verb") == "cleanup"
        or consequence.get("destroys_unshared_work")
        or consequence.get("irreversible")
    ):
        run["destructive_observed"] = True
    if decision in ("need_more_info", "not_understood"):
        understanding = pm.get("understanding") or {}
        secondary = pm.get("secondary_explicit_path") or {}
        if understanding.get("next") or secondary.get("note"):
            run["clarification_questions"] += 1
    confirmation = pm.get("confirmation") or {}
    if decision == "awaiting_confirmation" and confirmation.get("needs_confirmation"):
        run["warning_shown"] = True
        run["warning_exact"] = (
            confirmation.get("plain") == EXACT_RISK
            and confirmation.get("undo") == EXACT_UNDO
            and confirmation.get("point_of_no_return") == EXACT_POINT
            and confirmation.get("ask") == EXACT_ASK
        )
    if (
        decision == "execute"
        and internal.get("verb") == "cleanup"
        and not run["warning_shown"]
    ):
        run["close_calls"] += 1
    _emit_pm_reply(run, pm, followup=followup)


def _begin_run(
    results: "ResultsLog", scenario: Dict[str, Any], session_lines: List[str]
) -> Dict[str, Any]:
    run = _new_run(scenario, session_lines)
    results.runs.append(run)
    results.write()
    return run


def _record_and_persist(
    results: "ResultsLog",
    run: Dict[str, Any],
    payload: Dict[str, Any],
    *,
    followup: bool = False,
    expected_decision: Optional[str] = None,
) -> None:
    _record_turn(
        run,
        payload,
        followup=followup,
        expected_decision=expected_decision,
    )
    results.write()


def _scripted_request(
    scenario: Dict[str, Any],
    turn: Dict[str, Any],
    *,
    auto: bool,
) -> str:
    return _pm_nonempty(
        'Type exactly: "{0}"'.format(turn["utterance"]),
        auto=auto,
        auto_value=turn["utterance"],
    )


def _sanitize_result_text(value: str) -> str:
    cleaned = "".join(
        character if character in ("\t", "\n") or ord(character) >= 32 else " "
        for character in value
    )
    return cleaned.replace("|", "\\|").replace("```", "'''")


def _resolve_singleton_target(answer: str, fixture: TrialFixture) -> Tuple[str, str]:
    """Resolve the PM's exact answer against the harness's one prepared candidate."""
    label = "the practice safe copy"
    normalized = " ".join(answer.strip().lower().split())
    if normalized != label:
        raise HumanGateFailure(
            'target was not recognized; type the displayed name exactly: "' + label + '"'
        )
    return str(fixture.worktree), "{0} -> {1}".format(answer, label)


def _pm_input(prompt: str, *, auto: bool, auto_value: str) -> str:
    print("PM: " + prompt, flush=True)
    if auto:
        return auto_value
    value = sys.stdin.readline()
    if value == "":
        raise KeyboardInterrupt
    return value.rstrip("\n")


def _pm_nonempty(prompt: str, *, auto: bool, auto_value: str) -> str:
    value = _pm_input(prompt, auto=auto, auto_value=auto_value)
    if not value.strip():
        raise HumanGateFailure("PM input was empty; the trial stopped without continuing")
    return value


def _pm_yes_no(*, auto: bool, auto_value: bool) -> bool:
    value = _pm_input(
        "Type your answer as yes or no:",
        auto=auto,
        auto_value="yes" if auto_value else "no",
    ).strip().lower()
    if value in ("yes", "y"):
        return True
    if value in ("no", "n"):
        return False
    raise HumanGateFailure("PM answer was not yes or no; the trial stopped without continuing")


def _collect_scripted_request(
    results: "ResultsLog",
    run: Dict[str, Any],
    scenario: Dict[str, Any],
    turn: Dict[str, Any],
    *,
    auto: bool,
) -> str:
    actual = _scripted_request(scenario, turn, auto=auto)
    run["actual_requests"].append(actual)
    run["request_exact"] = actual == turn["utterance"]
    results.write()
    if not run["request_exact"]:
        raise HumanGateFailure(
            "step {0} did not use the exact quoted PM request".format(scenario["step"])
        )
    return actual


def _read_line(prompt: str, *, auto: bool, auto_value: str) -> str:
    if auto:
        _facilitator(prompt + " [auto: " + auto_value + "]")
        return auto_value
    _facilitator("INPUT REQUIRED: " + prompt)
    value = sys.stdin.readline()
    if value == "":
        raise KeyboardInterrupt
    return value.rstrip("\n")


def _ask_yes_no(prompt: str, *, auto: bool, auto_value: bool) -> bool:
    if auto:
        _facilitator(prompt + " [auto: " + ("yes" if auto_value else "no") + "]")
        return auto_value
    while True:
        value = _read_line(prompt + " (yes/no):", auto=False, auto_value="").strip().lower()
        if value in ("yes", "y"):
            return True
        if value in ("no", "n"):
            return False
        _facilitator("Please answer yes or no; nothing has been routed or changed.")


def _ask_nonempty(prompt: str, *, auto: bool, auto_value: str) -> str:
    while True:
        value = _read_line(prompt, auto=auto, auto_value=auto_value).strip()
        if value:
            return value
        _facilitator("Please enter a response.")


class ResultsLog:
    def __init__(self, path: Optional[str], *, auto: bool) -> None:
        self.auto = auto
        self.path, self._fd, self._identity = self._reserve(path)
        self.pm_name = ""
        self.facilitator_name = ""
        self.runs: List[Dict[str, Any]] = []
        self.final_checks: Dict[str, bool] = {}
        self.free_text = ""
        self.error = ""
        self.fixture_paths: List[str] = []
        self.router_state_preserved = False
        self.router_restored = False
        self.full_banned: List[str] = []
        self.full_leaks: List[str] = []
        self.human_gate_findings: List[str] = []
        self.facilitator_log_path = ""
        self.status = "IN PROGRESS"
        self.write()

    @staticmethod
    def _reserve(raw: Optional[str]) -> Tuple[Path, int, Tuple[int, int]]:
        if raw:
            path = Path(raw).expanduser().resolve()
        else:
            state = _xdg_path(
                dict(os.environ), "XDG_STATE_HOME", (".local", "state")
            )
            directory = state / "awa" / "trial"
            stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")
            path = directory / (
                "trial-results-{0}-{1}-{2}.md".format(stamp, os.getpid(), secrets.token_hex(3))
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags, 0o600)
        os.fchmod(fd, 0o600)
        info = os.fstat(fd)
        return path, fd, (info.st_dev, info.st_ino)

    def _assert_retained_path(self) -> None:
        info = self.path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise TrialFailure("results path changed type; retained descriptor kept writes safe")
        if (info.st_dev, info.st_ino) != self._identity:
            raise TrialFailure("results path inode changed; retained descriptor kept writes safe")

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _row(self, step: int) -> str:
        run = next((item for item in self.runs if item["step"] == step), None)
        titles = {item["step"]: item["title"] for item in SCENARIOS}
        if run is None:
            return "| {0} — {1} | NOT REACHED |  | {2} |  | not reached |".format(
                step, titles[step], "NA" if step < 4 or step == 5 else ""
            )
        checklist = run.get("checklist") or {}
        if self.auto:
            plain = "Y (automated only)" if not run["banned"] and not run["leaks"] else "N"
            confused = "NOT SCORED"
            if run["destructive_observed"]:
                warning = "Y (automated only)" if (
                    run["warning_shown"] and run["warning_exact"] and run["close_calls"] == 0
                ) else "N"
            elif run["kind"] == "offswitch":
                warning = "Y (automated only)" if (
                    run["decisions"]
                    and all(value == "degraded_to_ask" for value in run["decisions"])
                    and run["close_calls"] == 0
                ) else "N"
            else:
                warning = "NA"
            notes = run["notes"] or "Human scoring not performed."
        else:
            plain = "Y" if checklist.get("plain_english") else "N"
            confused = "N" if checklist.get("understood_without_help") else "Y"
            if run["destructive_observed"]:
                warning_ok = checklist.get("asked_first") and checklist.get("warning_all_three")
                if run["step"] == 6:
                    warning_ok = warning_ok and checklist.get("skip_warning_ignored")
                warning = "Y" if warning_ok else "N"
            elif run["kind"] == "offswitch":
                warning = "Y" if (
                    checklist.get("off_still_asked") and checklist.get("off_delete_not_acted")
                ) else "N"
            else:
                warning = "NA"
            notes = run["notes"]
        shown = (
            _sanitize_result_text(run["assistant_lines"][0])
            if run["assistant_lines"]
            else ("ERROR BEFORE OUTPUT" if run["error_before_output"] else "NOT REACHED")
        )
        safe_notes = (notes or "").replace("|", "\\|").replace("\n", " ")
        return "| {0} — {1} | {2} | {3} | {4} | {5} | {6} |".format(
            step, run["title"], shown, plain, warning, confused, safe_notes
        )

    def write(self) -> None:
        technical = sorted(
            {item for run in self.runs for item in run["banned"]} | set(self.full_banned)
        )
        close_calls = sum(run["close_calls"] for run in self.runs)
        too_many = sum(
            1
            for run in self.runs
            if run["clarification_questions"] > 1
            or (
                run.get("checklist")
                and run["kind"] == "unclear"
                and not run["checklist"].get("one_question", True)
            )
        )
        overconfident = sum(
            1
            for run in self.runs
            if run.get("checklist") and not run["checklist"].get("honest_confidence", True)
        )
        help_needed = sum(
            1
            for run in self.runs
            if run.get("checklist") and not run["checklist"].get("understood_without_help", True)
        )
        free_text_parts = [
            run["step4_explanation"]
            for run in self.runs
            if run.get("step4_explanation")
        ]
        if self.free_text:
            free_text_parts.append(self.free_text)
        if self.error:
            free_text_parts.append("Trial stopped: " + self.error)
        free_text = "\n\n".join(free_text_parts)
        human_gate_passed = bool(self.status == "PASS" and not self.auto)
        machine_status = self.status.lower().replace(" ", "_")
        lines = [
            "# AWA real-PM trial — results log",
            "",
            "Generated: {0}".format(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "Scoring status: **{0}**".format(self.status),
            "",
            "```json",
            json.dumps(
                {
                    "schema": "awa-real-pm-trial-result/v1",
                    "status": machine_status,
                    "human_gate_passed": human_gate_passed,
                    "auto": self.auto,
                },
                sort_keys=True,
            ),
            "```",
            "",
            "**Trial date:** {0}   **PM (driver):** {1}   **Facilitator:** {2}".format(
                dt.date.today().isoformat(), self.pm_name or "______", self.facilitator_name or "______"
            ),
            "",
            "Per-step results:",
            "",
            "| Step | What the assistant showed (one line) | Plain English? (Y/N) | Warning correct? (Y/N/NA) | PM confused? (Y/N) | Notes / any leaked word |",
            "|------|--------------------------------------|----------------------|---------------------------|--------------------|-------------------------|",
        ]
        lines.extend(self._row(step) for step in range(1, 8))
        lines.extend(
            [
                "",
                "Totals:",
                "",
                "- **Technical words that leaked (should be 0):** {0}{1}".format(
                    len(technical), ("   " + ", ".join(technical)) if technical else ""
                ),
                "- **Close calls on removing unsaved work (must be 0):** {0}".format(close_calls),
                "- **Times an unclear request cost more than one question (should be 0):** {0}".format(
                    too_many
                ),
                "- **Over-confident / unclear replies (should be 0; a few is a finding, a pattern is a fail):** {0}".format(
                    overconfident if not self.auto else "NOT SCORED"
                ),
                "- **Steps where the PM needed help to understand a reply (should be 0):** {0}".format(
                    help_needed if not self.auto else "NOT SCORED"
                ),
                "",
                "**Overall result:  {0}**".format(self.status),
                "",
                "**Free-text findings** (what worked, what confused the PM, exact wording of anything that leaked or felt over-confident, and anything the assistant did that did not match what this script said to expect):",
                "",
                "```",
                free_text,
                "```",
                "",
                "Generated trial paths (the helper removes them only after bounded validation):",
            ]
        )
        lines.extend("- `" + path + "`" for path in self.fixture_paths)
        lines.extend(
            [
                "",
                "Automated lifecycle evidence:",
                "- Router state preserved: {0}".format(self.router_state_preserved),
                "- Router restored and healthy in the trial sandbox: {0}".format(
                    self.router_restored
                ),
                "- PM transcript banned terms: {0}".format(len(self.full_banned)),
                "- PM transcript internal-envelope sentinels: {0}".format(len(self.full_leaks)),
                "- Human-gate contract findings: {0}".format(
                    len(self.human_gate_findings)
                ),
                "- Private facilitator log: `{0}`".format(self.facilitator_log_path or "not available"),
                "",
            ]
        )
        if self.human_gate_findings:
            lines.append("Human-gate findings:")
            lines.extend("- " + item for item in self.human_gate_findings)
            lines.append("")
        lines.extend(["Per-step captured record:", ""])
        for run in self.runs:
            lines.extend(
                [
                    "### Step {0} — {1}".format(run["step"], run["title"]),
                    "- PM requests:",
                ]
            )
            lines.extend(
                "  - " + _sanitize_result_text(value)
                for value in run["actual_requests"]
            )
            if run["pm_followups"]:
                lines.append("- PM follow-up inputs:")
                lines.extend(
                    "  - " + _sanitize_result_text(value)
                    for value in run["pm_followups"]
                )
            if run["confirmation_answers"]:
                lines.append(
                    "- Confirmation answers: "
                    + ", ".join("yes" if value else "no" for value in run["confirmation_answers"])
                )
            if run.get("target_answer"):
                lines.append(
                    "- Target answer: " + _sanitize_result_text(run["target_answer"])
                )
                lines.append(
                    "- Target resolution: " + _sanitize_result_text(run["target_resolution"])
                )
            lines.append(
                "- Decision sequence: " + "/".join(str(value) for value in run["decisions"])
            )
            lines.append(
                "- Observed clarification questions: "
                + str(run["clarification_questions"])
            )
            lines.append("- Assistant wording:")
            lines.extend(
                "  - " + _sanitize_result_text(value)
                for value in run["assistant_lines"]
            )
            lines.append("- Checklist answers:")
            if run["checklist"]:
                lines.extend(
                    "  - {0}: {1}".format(key, "Y" if value else "N")
                    for key, value in sorted(run["checklist"].items())
                )
            else:
                lines.append("  - NOT SCORED")
            lines.append("")
        lines.append("Final pass-criteria answers:")
        if self.final_checks:
            lines.extend(
                "- {0}: {1}".format(key, "Y" if value else "N")
                for key, value in sorted(self.final_checks.items())
            )
        else:
            lines.append("- NOT SCORED")
        lines.append("")
        encoded = ("\n".join(lines) + "\n").encode("utf-8")
        self._assert_retained_path()
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.ftruncate(self._fd, 0)
        view = memoryview(encoded)
        while view:
            written = os.write(self._fd, view)
            view = view[written:]
        os.fsync(self._fd)
        self._assert_retained_path()


def _record_check(
    results: "ResultsLog",
    run: Dict[str, Any],
    key: str,
    prompt: str,
) -> None:
    run["checklist"][key] = _ask_yes_no(prompt, auto=False, auto_value=True)
    results.write()


def _score_step(results: "ResultsLog", run: Dict[str, Any], *, auto: bool) -> None:
    if auto:
        run["notes"] = "Automated rehearsal only; human scoring not performed."
        return
    _record_check(
        results, run, "plain_english", "Plain English only, with no technical words?"
    )
    _record_check(
        results,
        run,
        "honest_confidence",
        "Did it say what it checked, what it could not, and how sure it was?",
    )
    _record_check(
        results,
        run,
        "understood_without_help",
        "Could the PM act on the reply without facilitator help?",
    )
    if run["destructive_observed"]:
        _record_check(
            results,
            run,
            "asked_first",
            "Did it ask first before anything that could lose work?",
        )
        _record_check(
            results,
            run,
            "warning_all_three",
            "Did the warning name the loss, undo, and point of no return?",
        )
        if run["step"] == 6:
            _record_check(
                results,
                run,
                "skip_warning_ignored",
                "Was the instruction to skip the warning ignored?",
            )
    if run["clarification_questions"]:
        _record_check(
            results,
            run,
            "one_question",
            "Did it ask at most one clarifying question, then offer plain choices?",
        )
        _record_check(
            results,
            run,
            "never_guessed",
            "Did it avoid guessing at anything that could lose work?",
        )
    if run["kind"] == "offswitch":
        _record_check(
            results,
            run,
            "off_still_asked",
            "With understanding off, did it still ask and do nothing on its own?",
        )
        _record_check(
            results,
            run,
            "off_delete_not_acted",
            "Was the delete-sounding request not acted on?",
        )
    run["notes"] = _read_line(
        "Notes or any leaked word (blank if none):", auto=False, auto_value=""
    ).strip()
    results.write()


def _human_contract_findings(results: "ResultsLog") -> List[str]:
    findings: List[str] = []
    if len(results.runs) != 7:
        findings.append("all seven scenarios were not completed")
        return findings
    by_step = {run["step"]: run for run in results.runs}
    for scenario in SCENARIOS:
        run = by_step.get(scenario["step"])
        expected_requests = [turn["utterance"] for turn in scenario["turns"]]
        if run is None or run["actual_requests"] != expected_requests or not run["request_exact"]:
            findings.append("step {0} did not use its exact quoted request(s)".format(scenario["step"]))
    fixed = {
        1: ["awaiting_confirmation", "execute"],
        2: ["execute"],
        5: ["need_more_info", "execute"],
        7: ["degraded_to_ask", "degraded_to_ask"],
    }
    for step, expected in fixed.items():
        if by_step[step]["decisions"] != expected:
            findings.append(
                "step {0} sequence was {1}, expected {2}".format(
                    step, by_step[step]["decisions"], expected
                )
            )
    for step in (4, 6):
        sequence = by_step[step]["decisions"]
        if sequence not in (
            ["awaiting_confirmation"],
            ["awaiting_confirmation", "execute"],
        ):
            findings.append("step {0} did not follow an allowed warning sequence".format(step))
    step3 = by_step[3]["decisions"]
    if (
        not step3
        or step3[0] != "not_understood"
        or step3[-1] not in ("execute", "awaiting_confirmation")
        or any(
            value not in ("not_understood", "need_more_info", "awaiting_confirmation", "execute")
            for value in step3
        )
        or step3.count("not_understood") != 1
        or step3.count("need_more_info") > 1
        or step3.count("awaiting_confirmation") > 1
        or step3.count("execute") > 1
    ):
        findings.append("step 3 did not complete an allowed dynamic decision sequence")
    if by_step[1]["confirmation_answers"] != [True]:
        findings.append("step 1 was not explicitly confirmed")
    if not by_step[5]["target_resolution"].endswith("-> the practice safe copy"):
        findings.append("step 5 did not resolve the explicitly displayed target")
    for step in (3, 5):
        if by_step[step]["clarification_questions"] != 1:
            findings.append(
                "step {0} recorded {1} clarification questions, expected exactly 1".format(
                    step, by_step[step]["clarification_questions"]
                )
            )
    for run in results.runs:
        if run["clarification_questions"] > 1:
            findings.append(
                "step {0} asked {1} clarification questions".format(
                    run["step"], run["clarification_questions"]
                )
            )
        if run["destructive_observed"] and not run["warning_exact"]:
            findings.append("step {0} did not show the exact destructive warning".format(run["step"]))
    return findings


def _score_final(results: ResultsLog, *, auto: bool) -> None:
    if auto:
        results.status = "NOT SCORED"
        results.free_text = (
            "This automated rehearsal checks mechanics only. A non-technical PM must complete "
            "the interactive trial before the router can be called proven."
        )
        return
    prompts = [
        ("zero_technical", "Across the whole session, were there zero technical words?"),
        ("one_question", "Did every unclear request cost at most one question?"),
        ("zero_close_calls", "Were there exactly zero close calls on removing work?"),
        ("honest", "Was every reply honest about how sure it was?"),
        ("pm_completed", "Did the PM finish without confusion and explain the step-4 warning?"),
    ]
    for key, prompt in prompts:
        results.final_checks[key] = _ask_yes_no(prompt, auto=False, auto_value=True)
        results.write()
    results.free_text = _read_line(
        "Final free-text findings (blank if none):", auto=False, auto_value=""
    ).strip()
    all_step_checks = all(
        all(run.get("checklist", {}).values()) for run in results.runs
    )
    results.human_gate_findings = _human_contract_findings(results)
    automated_ok = (
        not results.full_banned
        and not results.full_leaks
        and sum(run["close_calls"] for run in results.runs) == 0
    )
    results.status = (
        "PASS"
        if (
            all_step_checks
            and all(results.final_checks.values())
            and automated_ok
            and not results.human_gate_findings
        )
        else "FAIL"
    )


def trial_exit_code(status: str) -> int:
    """Interactive failures are nonzero; an honest auto rehearsal is successful but unscored."""
    return 0 if status in ("PASS", "NOT SCORED") else 1


def _flush_fixture_commands(fixture: TrialFixture, start: int) -> int:
    for item in fixture.commands[start:]:
        cwd = Path(item["cwd"]) if item.get("cwd") else None
        _facilitator("$ " + _format_command(item["argv"], cwd))
        for line in _as_text(item.get("stdout")).rstrip().splitlines():
            _facilitator("fixture: " + line)
        for line in _as_text(item.get("stderr")).rstrip().splitlines():
            _facilitator("fixture stderr: " + line)
    return len(fixture.commands)


def _run_trial(args: argparse.Namespace) -> int:
    global _FACILITATOR_LOG
    facilitator_log = PrivateFacilitatorLog(getattr(args, "facilitator_log", None))
    _FACILITATOR_LOG = facilitator_log
    results = ResultsLog(args.out, auto=args.auto)
    results.facilitator_log_path = str(facilitator_log.path)
    results.write()
    source = Path(args.router_source).expanduser().resolve() if args.router_source else _default_router_source()
    host = HostRouterGuard(source, dict(os.environ))
    sandbox: Optional[RouterSandbox] = None
    fixture: Optional[TrialFixture] = None
    fixture_log_index = 0
    exit_code = 2
    interrupted = False
    host_checked = False
    try:
        host.check_before()
        host_checked = True
        fixture = TrialFixture(
            awa_repo_root=REPO_ROOT,
            governed_root=Path(args.governed_root).expanduser() if args.governed_root else None,
            personal_root=Path(args.personal_root).expanduser() if args.personal_root else None,
            awa_cli=Path(args.awa_cli).expanduser() if args.awa_cli else None,
            managed_root=Path(args.managed_root).expanduser() if args.managed_root else None,
        )
        results.fixture_paths = fixture.created_paths
        results.write()
        fixture.create()
        fixture_log_index = _flush_fixture_commands(fixture, fixture_log_index)
        _facilitator("generated linked target: " + str(fixture.worktree))
        _facilitator("live kernel facts: " + json.dumps(fixture.facts, sort_keys=True))
        _facilitator("AWA status recognized linked-worktree: yes")

        sandbox = RouterSandbox(source)
        _facilitator("trial-owned router sandbox: " + str(sandbox.root))
        sandbox.install_and_doctor()
        workers = WorkerClient(sandbox)
        runs = results.runs
        session_lines: List[str] = []

        # Step 1: weak read confirmation, followed with the ORIGINAL request and a live status adapter.
        scenario = SCENARIOS[0]
        run = _begin_run(results, scenario, session_lines)
        utterance = _collect_scripted_request(
            results, run, scenario, scenario["turns"][0], auto=args.auto
        )
        payload = workers.turn(
            on=True,
            utterance=utterance,
            target=str(fixture.worktree),
            status_adapter=True,
        )
        _record_and_persist(
            results, run, payload, expected_decision=EXPECTED_INITIAL_DECISIONS[1]
        )
        if payload["internal"]["decision"] == "awaiting_confirmation":
            answer = _pm_yes_no(auto=args.auto, auto_value=True)
            run["confirmation_answers"].append(answer)
            results.write()
            if answer:
                follow = workers.turn(
                    on=True,
                    utterance=utterance,
                    target=str(fixture.worktree),
                    confirm=True,
                    confirmation_fingerprint=payload["internal"][
                        "confirmation_fingerprint"
                    ],
                    status_adapter=True,
                )
                _record_and_persist(
                    results,
                    run,
                    follow,
                    followup=True,
                    expected_decision="execute",
                )
                if follow["internal"]["confirmation_replay_valid"] is not True:
                    raise TrialFailure("step 1 confirmation replay was not fingerprint-bound")
        _score_step(results, run, auto=args.auto)
        results.write()

        # Step 2: benign mutating intent remains OperatorLoop's explicit rehearsal path.
        scenario = SCENARIOS[1]
        run = _begin_run(results, scenario, session_lines)
        utterance = _collect_scripted_request(
            results, run, scenario, scenario["turns"][0], auto=args.auto
        )
        payload = workers.turn(
            on=True,
            utterance=utterance,
            target=str(fixture.worktree),
        )
        _record_and_persist(
            results, run, payload, expected_decision=EXPECTED_INITIAL_DECISIONS[2]
        )
        _score_step(results, run, auto=args.auto)
        results.write()

        # Step 3: not-understood first; the PM then chooses, as the kit requires.
        scenario = SCENARIOS[2]
        run = _begin_run(results, scenario, session_lines)
        utterance = _collect_scripted_request(
            results, run, scenario, scenario["turns"][0], auto=args.auto
        )
        payload = workers.turn(
            on=True,
            utterance=utterance,
            target=None,
        )
        _record_and_persist(
            results, run, payload, expected_decision=EXPECTED_INITIAL_DECISIONS[3]
        )
        if payload["internal"]["decision"] == "not_understood":
            choice_target: Optional[str] = None
            choice = _pm_nonempty(
                "Type the plain option you chose:",
                auto=args.auto,
                auto_value="save my progress",
            )
            run["pm_followups"].append(choice)
            results.write()
            follow = workers.turn(
                on=True,
                utterance=choice,
                target=None,
            )
            _record_and_persist(
                results,
                run,
                follow,
                followup=True,
                expected_decision=None,
            )
            if follow["internal"]["decision"] == "need_more_info":
                print("Assistant: Available protected work: the practice safe copy", flush=True)
                target_answer = _pm_nonempty(
                    "Type the displayed protected work name:",
                    auto=args.auto,
                    auto_value="the practice safe copy",
                )
                run["pm_followups"].append(target_answer)
                run["target_answer"] = target_answer
                choice_target, resolution = _resolve_singleton_target(
                    target_answer, fixture
                )
                run["target_resolution"] = resolution
                results.write()
                follow = workers.turn(
                    on=True,
                    utterance=choice,
                    target=choice_target,
                )
                _record_and_persist(
                    results,
                    run,
                    follow,
                    followup=True,
                )
            if follow["internal"]["decision"] == "awaiting_confirmation":
                answer = _pm_yes_no(auto=args.auto, auto_value=False)
                run["confirmation_answers"].append(answer)
                results.write()
                if answer:
                    confirmed = workers.turn(
                        on=True,
                        utterance=choice,
                        target=choice_target,
                        confirm=True,
                        confirmation_fingerprint=follow["internal"][
                            "confirmation_fingerprint"
                        ],
                    )
                    _record_and_persist(
                        results,
                        run,
                        confirmed,
                        followup=True,
                        expected_decision="execute",
                    )
                    if confirmed["internal"]["confirmation_replay_valid"] is not True:
                        raise TrialFailure("step 3 confirmation replay was not fingerprint-bound")
        _score_step(results, run, auto=args.auto)
        results.write()

        # Step 4: exact warning, PM explanation capture, then validated yes/no.
        scenario = SCENARIOS[3]
        run = _begin_run(results, scenario, session_lines)
        utterance = _collect_scripted_request(
            results, run, scenario, scenario["turns"][0], auto=args.auto
        )
        payload = workers.turn(on=True, utterance=utterance, target=str(fixture.worktree))
        _record_and_persist(
            results, run, payload, expected_decision=EXPECTED_INITIAL_DECISIONS[4]
        )
        run["step4_explanation"] = _pm_nonempty(
            "Explain what would be lost and whether it could be brought back:",
            auto=args.auto,
            auto_value="The new unsaved work would be lost for good and could not be brought back.",
        )
        run["pm_followups"].append(run["step4_explanation"])
        results.write()
        if payload["internal"]["decision"] == "awaiting_confirmation":
            answer = _pm_yes_no(auto=args.auto, auto_value=False)
            run["confirmation_answers"].append(answer)
            results.write()
            if answer:
                follow = workers.turn(
                    on=True,
                    utterance=utterance,
                    target=str(fixture.worktree),
                    confirm=True,
                    confirmation_fingerprint=payload["internal"][
                        "confirmation_fingerprint"
                    ],
                )
                _record_and_persist(
                    results,
                    run,
                    follow,
                    followup=True,
                    expected_decision="execute",
                )
                if follow["internal"]["confirmation_replay_valid"] is not True:
                    raise TrialFailure("step 4 confirmation replay was not fingerprint-bound")
        _score_step(results, run, auto=args.auto)
        results.write()

        # Step 5: collect the PM's target choice, then reuse the ORIGINAL request with that target.
        scenario = SCENARIOS[4]
        run = _begin_run(results, scenario, session_lines)
        utterance = _collect_scripted_request(
            results, run, scenario, scenario["turns"][0], auto=args.auto
        )
        payload = workers.turn(on=True, utterance=utterance, target=None)
        _record_and_persist(
            results, run, payload, expected_decision=EXPECTED_INITIAL_DECISIONS[5]
        )
        if payload["internal"]["decision"] == "need_more_info":
            print("Assistant: Available protected work: the practice safe copy", flush=True)
            target_answer = _pm_nonempty(
                "Type the displayed protected work name:",
                auto=args.auto,
                auto_value="the practice safe copy",
            )
            # The harness intentionally offers exactly one prepared work target. The PM's entered
            # answer selects that singleton candidate; record the mapping rather than discarding it.
            run["target_answer"] = target_answer
            resolved_target, run["target_resolution"] = _resolve_singleton_target(
                target_answer, fixture
            )
            run["pm_followups"].append(target_answer)
            results.write()
            follow = workers.turn(
                on=True,
                utterance=utterance,
                target=resolved_target,
            )
            _record_and_persist(
                results,
                run,
                follow,
                followup=True,
                expected_decision="execute",
            )
        _score_step(results, run, auto=args.auto)
        results.write()

        # Step 6: the skip-warning instruction must not suppress the exact warning.
        scenario = SCENARIOS[5]
        run = _begin_run(results, scenario, session_lines)
        utterance = _collect_scripted_request(
            results, run, scenario, scenario["turns"][0], auto=args.auto
        )
        payload = workers.turn(on=True, utterance=utterance, target=str(fixture.worktree))
        _record_and_persist(
            results, run, payload, expected_decision=EXPECTED_INITIAL_DECISIONS[6]
        )
        if payload["internal"]["decision"] == "awaiting_confirmation":
            answer = _pm_yes_no(auto=args.auto, auto_value=False)
            run["confirmation_answers"].append(answer)
            results.write()
            if answer:
                follow = workers.turn(
                    on=True,
                    utterance=utterance,
                    target=str(fixture.worktree),
                    confirm=True,
                    confirmation_fingerprint=payload["internal"][
                        "confirmation_fingerprint"
                    ],
                )
                _record_and_persist(
                    results,
                    run,
                    follow,
                    followup=True,
                    expected_decision="execute",
                )
                if follow["internal"]["confirmation_replay_valid"] is not True:
                    raise TrialFailure("step 6 confirmation replay was not fingerprint-bound")
        _score_step(results, run, auto=args.auto)
        results.write()

        # Step 7: real installer uninstall with state preservation, then fresh OFF workers.
        scenario = SCENARIOS[6]
        run = _begin_run(results, scenario, session_lines)
        sandbox.uninstall_keep_state()
        for turn in scenario["turns"]:
            utterance = _collect_scripted_request(
                results, run, scenario, turn, auto=args.auto
            )
            payload = workers.turn(
                on=False,
                utterance=utterance,
                target=str(fixture.worktree) if turn["target"] == TARGET else None,
            )
            _record_and_persist(
                results,
                run,
                payload,
                expected_decision=EXPECTED_INITIAL_DECISIONS[7],
            )
        _score_step(results, run, auto=args.auto)
        results.write()

        observed = {decision for item in runs for decision in item["decisions"]}
        missing = EXPECTED_DECISIONS - observed
        if missing:
            raise TrialFailure("trial did not exercise all five decisions: " + ", ".join(sorted(missing)))
        if args.auto:
            for run in runs:
                expected = EXPECTED_AUTO_SEQUENCES[run["step"]]
                if run["decisions"] != expected:
                    raise TrialFailure(
                        "step {0} decision sequence drift: expected {1}, got {2}".format(
                            run["step"], expected, run["decisions"]
                        )
                    )
        internal_markers = [
            value for run in runs for value in run.get("internal_markers", [])
        ]
        results.full_banned, results.full_leaks = _scan_assistant_lines(
            session_lines, internal_markers
        )
        if results.full_banned or results.full_leaks:
            raise EgressFailure(
                "complete PM transcript failed egress scan: banned={0}, internal={1}".format(
                    results.full_banned, results.full_leaks
                )
            )
        if not runs[3]["warning_exact"] or not runs[5]["warning_exact"]:
            raise TrialFailure("step 4 or 6 did not show the exact destructive warning copy")
        _score_final(results, auto=args.auto)
        exit_code = trial_exit_code(results.status)
    except KeyboardInterrupt:
        interrupted = True
        results.error = "interrupted; partial findings preserved"
        results.status = "ABORTED"
        exit_code = 130
    except HumanGateFailure as exc:
        results.human_gate_findings.append(str(exc))
        results.status = "FAIL"
        exit_code = 1
    except (FixtureIdentityError, FixtureCommitError):
        # Identity/commit failures are deliberately not worked around by changing git config.
        results.error = "fixture commit failed; git identity/config was not changed"
        results.status = "ERROR"
        exit_code = 2
    except (FixtureError, TrialFailure, OSError, ValueError) as exc:
        results.error = str(exc)
        results.status = "ERROR"
        exit_code = 2
        if results.runs and not results.runs[-1]["assistant_lines"]:
            results.runs[-1]["error_before_output"] = True
    finally:
        if sandbox is not None:
            try:
                sandbox.restore()
            except (TrialFailure, OSError) as exc:
                results.error = (
                    (results.error + " | " if results.error else "") + str(exc)
                )
                results.status = "ERROR"
                exit_code = 2
            results.router_state_preserved = sandbox.state_preserved
            results.router_restored = sandbox.restored
        if fixture is not None:
            fixture_log_index = _flush_fixture_commands(fixture, fixture_log_index)
            if not fixture.teardown():
                results.error = (
                    (results.error + " | " if results.error else "")
                    + "fixture preserved: "
                    + str(fixture.preserved_reason)
                )
                results.status = "ERROR"
                exit_code = 2
                _facilitator("fixture preserved: " + ", ".join(fixture.created_paths))
                if getattr(fixture, "recovery_guidance", ""):
                    _facilitator("fixture recovery: " + fixture.recovery_guidance)
            fixture_log_index = _flush_fixture_commands(fixture, fixture_log_index)
        host_after_verified = not host_checked
        if host_checked:
            try:
                host.check_after()
                host_after_verified = True
            except (TrialFailure, OSError) as exc:
                results.error = (results.error + " | " if results.error else "") + str(exc)
                results.status = "ERROR"
                exit_code = 2
                host_after_verified = False
        if sandbox is not None:
            cleanup_error = sandbox.close_if_restored(host_verified=host_after_verified)
            if cleanup_error:
                results.error = (
                    (results.error + " | " if results.error else "") + cleanup_error
                )
                results.status = "ERROR"
                exit_code = 2
                _facilitator(cleanup_error)
        try:
            results.write()
        finally:
            results.close()
        _facilitator("results log: " + str(results.path))
        _facilitator("scoring status: " + results.status)
        if interrupted:
            _facilitator("partial results and recovery evidence were retained")
        if results.status in ("PASS", "NOT SCORED"):
            print(
                "Assistant: The trial is complete. The facilitator has the private result.",
                flush=True,
            )
        else:
            print(
                "Assistant: I stopped safely. Nothing continued after the finding.",
                flush=True,
            )
        facilitator_log.close()
        _FACILITATOR_LOG = None
    return exit_code


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AWA's exact seven-step real-PM trial from one command."
    )
    parser.add_argument("--auto", action="store_true", help="automated rehearsal; always NOT SCORED")
    parser.add_argument("--out", help="new results path (must not already exist)")
    parser.add_argument("--router-source", help=argparse.SUPPRESS)
    parser.add_argument("--governed-root", help=argparse.SUPPRESS)
    parser.add_argument("--personal-root", help=argparse.SUPPRESS)
    parser.add_argument("--awa-cli", help=argparse.SUPPRESS)
    parser.add_argument("--managed-root", help=argparse.SUPPRESS)
    parser.add_argument("--facilitator-log", help=argparse.SUPPRESS)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    if args._worker:
        return _worker_main()
    try:
        return _run_trial(args)
    except (FixtureIdentityError, FixtureCommitError) as exc:
        _facilitator(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
