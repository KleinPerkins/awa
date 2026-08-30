"""Bounded M3 guard-boundary profile with PATH-scoped Git process counts.

The profile is test evidence only. It executes guard decisions against private
temporary repositories and never authorizes a verification skip or guard action.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple
from unittest import mock

from engine import guard as engine_guard

from . import verification_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_GUARD = REPO_ROOT / "kernel" / "hooks" / "worktree-guard.sh"
SOURCE_CHECKER = REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh"
SOURCE_POLICY = REPO_ROOT / "kernel" / "lib" / "awa_policy.py"
INSTALL = REPO_ROOT / "install.sh"

GIT_COUNTER_SCOPE = "PATH-resolved git children only"
NOT_COUNTED_SCOPE = "not counted"
PROFILE_BOUNDARIES = ("engine", "source", "installed", "owner")

INSTALLED_DECISION_CANARIES = (
    "direct_allow_deny",
    "external_zero_access",
    "installed_allow_deny",
    "kernel_off",
    "maintenance",
    "malformed_input",
    "owner_mode",
    "source_engine_parity",
    "uncertainty",
)
INSTALLED_DECISION_CANARY_TESTS = {
    "direct_allow_deny": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_m3_profile_manifest_matches_source_and_installed_permissions"
    ),
    "external_zero_access": (
        "engine.tests.test_hook_owner_v2_matrix.TestHookOwnerV2Matrix."
        "test_external_mode_is_zero_access"
    ),
    "installed_allow_deny": (
        "engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest."
        "test_all_boundaries_consume_same_case_ids"
    ),
    "kernel_off": (
        "engine.tests.test_kernel_off_matrix.KernelOffMatrixTest."
        "test_engine_is_actually_off_under_matrix_env"
    ),
    "maintenance": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_primary_maintenance_command_corpus_engine_source_installed_parity"
    ),
    "malformed_input": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_unparseable_payload_on_included_primary_asks"
    ),
    "owner_mode": (
        "engine.tests.test_hook_owner_modes.TestHookOwnerParity."
        "test_m3_profile_manifest_matches_owner_paths"
    ),
    "source_engine_parity": (
        "engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest."
        "test_all_boundaries_consume_same_case_ids"
    ),
    "uncertainty": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_classifier_unavailable_asks_not_denies"
    ),
}

_IDENTITY_KEYS = frozenset(
    {
        "source_guard_sha256",
        "installed_guard_sha256",
        "source_checker_sha256",
        "installed_checker_sha256",
        "source_policy_sha256",
        "installed_policy_sha256",
        "source_python",
        "installed_python",
        "source_bash",
        "installed_bash",
    }
)
_RISKY_GIT_ENV = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_EXEC_PATH",
        "GIT_NAMESPACE",
        "GIT_SHALLOW_FILE",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    }
)
_CLOUD_ENV = frozenset(
    {
        "CURSOR_BACKGROUND_AGENT",
        "CURSOR_CLOUD_AGENT",
        "IS_BACKGROUND_AGENT",
        "is_background_agent",
        "AWA_FORCE_CLOUD",
        "cloud_agent_identity_broker",
        "CURSOR_AGENT_IDENTITY_BROKER",
    }
)
_IDENT = (
    "-c",
    "user.email=fixture@example.invalid",
    "-c",
    "user.name=AWA M3 Fixture",
)


@dataclasses.dataclass(frozen=True)
class GuardCase:
    label: str
    command: str
    expected_permission: str
    state_fixture: str


GUARD_BOUNDARY_CASES = (
    GuardCase("maintenance_allow", "git fetch", "allow", "clean"),
    GuardCase("maintenance_dirty_deny", "git fetch", "deny", "dirty_untracked"),
    GuardCase(
        "maintenance_near_miss_deny",
        "git fetch --prune",
        "deny",
        "clean",
    ),
    GuardCase(
        "mutation_deny",
        "git commit --allow-empty -m profile",
        "deny",
        "clean",
    ),
    GuardCase("readonly_allow", "git status", "allow", "clean"),
)


class ProfileError(RuntimeError):
    """The bounded profile could not produce trustworthy evidence."""


@dataclasses.dataclass(frozen=True)
class _CaseFixture:
    root: Path
    repo: Path
    policy: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_manifest_sha256(cases: Sequence[GuardCase]) -> str:
    encoded = json.dumps(
        [dataclasses.asdict(case) for case in cases],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_cases(cases: Sequence[GuardCase]) -> Tuple[GuardCase, ...]:
    result = tuple(cases)
    if not result:
        raise ValueError("guard profile requires at least one case")
    labels = []
    for case in result:
        if not isinstance(case, GuardCase):
            raise TypeError("guard profile cases must be GuardCase values")
        if (
            not case.label
            or not case.command
            or case.expected_permission not in ("allow", "deny", "ask")
            or case.state_fixture not in ("clean", "dirty_untracked")
        ):
            raise ValueError("guard profile case is invalid")
        labels.append(case.label)
    if labels != sorted(labels) or len(labels) != len(set(labels)):
        raise ValueError("guard profile case labels must be sorted and unique")
    return result


def _private_environment(root: Path) -> dict:
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith("AWA_") or name in _RISKY_GIT_ENV or name in _CLOUD_ENV:
            env.pop(name, None)
    home = root / "home"
    data = root / "data"
    config = root / "config"
    state = root / "state"
    cache = root / "cache"
    tmp = root / "tmp"
    for path in (home, data, config, state, cache, tmp):
        path.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "XDG_DATA_HOME": str(data),
            "XDG_CONFIG_HOME": str(config),
            "XDG_STATE_HOME": str(state),
            "XDG_CACHE_HOME": str(cache),
            "TMPDIR": str(tmp),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env["PATH"] = env.get("PATH") or os.defpath
    return env


def _run_git(real_git: str, env: Mapping[str, str], *args: str) -> None:
    result = subprocess.run(
        [real_git, *args],
        check=False,
        capture_output=True,
        text=True,
        env=dict(env),
        timeout=30,
    )
    if result.returncode != 0:
        raise ProfileError(
            "fixture Git command failed: {0}".format(result.stderr.strip())
        )


def _make_case_fixture(
    profile_root: Path,
    case: GuardCase,
    real_git: str,
    base_env: Mapping[str, str],
    fixture_label: Optional[str] = None,
) -> _CaseFixture:
    label = fixture_label or case.label
    case_root = profile_root / "cases" / label
    repo = case_root / "project"
    remote = profile_root / "remotes" / (label + ".git")
    repo.mkdir(parents=True)
    remote.parent.mkdir(parents=True, exist_ok=True)

    _run_git(real_git, base_env, "init", "-q", str(repo))
    (repo / "file.txt").write_text("base\n", encoding="utf-8")
    _run_git(real_git, base_env, "-C", str(repo), "add", "file.txt")
    _run_git(
        real_git,
        base_env,
        "-C",
        str(repo),
        *_IDENT,
        "commit",
        "-qm",
        "initial",
    )
    _run_git(real_git, base_env, "-C", str(repo), "branch", "-M", "main")
    _run_git(real_git, base_env, "init", "-q", "--bare", str(remote))
    _run_git(
        real_git,
        base_env,
        "-C",
        str(repo),
        "remote",
        "add",
        "origin",
        str(remote),
    )
    _run_git(
        real_git,
        base_env,
        "-C",
        str(repo),
        "push",
        "-q",
        "-u",
        "origin",
        "main",
    )

    if case.state_fixture == "dirty_untracked":
        (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    policy = case_root / "policy.yml"
    policy.write_text(
        "version: 1\n"
        "governed_roots:\n"
        "  - {0}\n"
        "default: include\n"
        "include:\n"
        "  - '*'\n"
        "exclude:\n"
        "  - .\n"
        "detectors:\n"
        "  governed_markers:\n"
        "    - _ops/POLICY.md\n"
        "  foreign_hook_frameworks:\n"
        "    - husky\n".format(case_root),
        encoding="utf-8",
    )
    return _CaseFixture(case_root, repo, policy)


def _git_counting_environment(
    profile_root: Path,
    label: str,
    base_env: Mapping[str, str],
    real_git: str,
    count_git: bool,
) -> Tuple[dict, Path]:
    env = dict(base_env)
    log_path = profile_root / "git-counts" / (label + ".log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    if not count_git:
        return env, log_path

    wrapper_dir = profile_root / "git-wrappers" / label
    wrapper_dir.mkdir(parents=True)
    wrapper = wrapper_dir / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' git >>\"$AWA_GIT_PROCESS_LOG\"\n"
        "exec \"$AWA_REAL_GIT\" \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    env.update(
        {
            "AWA_REAL_GIT": real_git,
            "AWA_GIT_PROCESS_LOG": str(log_path),
            "PATH": str(wrapper_dir) + os.pathsep + env["PATH"],
        }
    )
    return env, log_path


def _log_count(path: Path) -> int:
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def _hook_permission(
    guard_path: Path,
    fixture: _CaseFixture,
    command: str,
    env: Mapping[str, str],
) -> str:
    hook_env = dict(env)
    hook_env.update(
        {
            "AWA_GOVERNED_ROOT": str(fixture.root),
            "AWA_POLICY": str(fixture.policy),
        }
    )
    payload = {
        "hook_event_name": "beforeShellExecution",
        "cwd": str(fixture.repo),
        "command": command,
    }
    result = subprocess.run(
        [str(guard_path)],
        input=json.dumps(payload),
        check=False,
        capture_output=True,
        text=True,
        env=hook_env,
        timeout=30,
    )
    if result.returncode != 0:
        return "error"
    try:
        response = json.loads(result.stdout)
    except (TypeError, ValueError):
        return "error"
    permission = response.get("permission")
    return permission if permission in ("allow", "deny", "ask") else "error"


def _engine_permission(
    fixture: _CaseFixture,
    command: str,
    env: Mapping[str, str],
) -> str:
    try:
        with mock.patch.dict(os.environ, dict(env), clear=True):
            decision = engine_guard.decide_shell(
                str(fixture.repo),
                command,
                str(fixture.policy),
            )
    except Exception:
        return "error"
    return (
        decision.permission
        if decision.permission in ("allow", "deny", "ask")
        else "error"
    )


def _owner_permission(
    profile_root: Path,
    direct_fixture: _CaseFixture,
    delegated_fixture: _CaseFixture,
    command: str,
    direct_env: Mapping[str, str],
    delegated_env: Mapping[str, str],
) -> str:
    direct = _hook_permission(
        SOURCE_GUARD,
        direct_fixture,
        command,
        direct_env,
    )
    delegator = profile_root / "owner" / "external-delegator.sh"
    if not delegator.exists():
        delegator.parent.mkdir(parents=True)
        delegator.write_text(
            "#!/bin/sh\n"
            "target=\"${AWA_DELEGATE_TARGET:?}\"\n"
            "export AWA_POLICY=\"${AWA_EXTERNAL_POLICY:?}\"\n"
            "export AWA_GOVERNED_ROOT=\"${AWA_EXTERNAL_ROOT:?}\"\n"
            "exec \"$target\"\n",
            encoding="utf-8",
        )
        delegator.chmod(0o700)
    external_env = dict(delegated_env)
    external_env.update(
        {
            "AWA_DELEGATE_TARGET": str(SOURCE_GUARD),
            "AWA_EXTERNAL_POLICY": str(delegated_fixture.policy),
            "AWA_EXTERNAL_ROOT": str(delegated_fixture.root),
        }
    )
    delegated = _hook_permission(
        delegator,
        delegated_fixture,
        command,
        external_env,
    )
    return direct if direct == delegated else "error"


def _install_runtime(profile_root: Path, base_env: Mapping[str, str]) -> Path:
    install_env = dict(base_env)
    hooks = profile_root / "selected-hooks" / "hooks.json"
    install_env["AWA_HOOKS_JSON"] = str(hooks)
    result = subprocess.run(
        [str(INSTALL)],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
        env=install_env,
        timeout=120,
    )
    if result.returncode != 0:
        raise ProfileError(
            "isolated AWA install failed: {0}".format(result.stderr.strip())
        )
    runtime = Path(install_env["XDG_DATA_HOME"]) / "awa" / "current"
    if not runtime.is_dir():
        raise ProfileError("isolated AWA install did not create a runtime")
    return runtime


def _profile_cases(
    boundary: str,
    cases: Sequence[GuardCase],
    *,
    count_git: bool,
    guard_path: Optional[Path] = None,
) -> dict:
    selected = _validate_cases(cases)
    if boundary not in PROFILE_BOUNDARIES:
        raise ValueError("unknown guard profile boundary")

    with tempfile.TemporaryDirectory(prefix="awa-guard-boundary-profile.") as raw:
        profile_root = Path(raw)
        real_git = shutil.which("git", path=os.environ.get("PATH") or os.defpath)
        if not real_git:
            raise ProfileError("git is unavailable")

        installed_guard = None
        if boundary == "installed":
            install_env = _private_environment(
                profile_root / "install-environment"
            )
            runtime = _install_runtime(profile_root, install_env)
            installed_guard = runtime / "kernel" / "hooks" / "worktree-guard.sh"
            if not installed_guard.is_file():
                raise ProfileError("installed guard is unavailable")

        outcomes = {}
        expected_outcomes = {}
        elapsed_by_case = {}
        git_by_case = {}
        for case in selected:
            if boundary == "owner":
                direct_base_env = _private_environment(
                    profile_root / "case-environments" / (case.label + "-direct")
                )
                delegated_base_env = _private_environment(
                    profile_root / "case-environments" / (case.label + "-external")
                )
                direct_fixture = _make_case_fixture(
                    profile_root,
                    case,
                    real_git,
                    direct_base_env,
                    case.label + "-direct",
                )
                delegated_fixture = _make_case_fixture(
                    profile_root,
                    case,
                    real_git,
                    delegated_base_env,
                    case.label + "-external",
                )
                direct_env, direct_log = _git_counting_environment(
                    profile_root,
                    case.label + "-direct",
                    direct_base_env,
                    real_git,
                    count_git,
                )
                delegated_env, delegated_log = _git_counting_environment(
                    profile_root,
                    case.label + "-external",
                    delegated_base_env,
                    real_git,
                    count_git,
                )
                started = time.monotonic()
                permission = _owner_permission(
                    profile_root,
                    direct_fixture,
                    delegated_fixture,
                    case.command,
                    direct_env,
                    delegated_env,
                )
                git_count = (
                    _log_count(direct_log) + _log_count(delegated_log)
                    if count_git
                    else 0
                )
            else:
                base_env = _private_environment(
                    profile_root / "case-environments" / case.label
                )
                fixture = _make_case_fixture(
                    profile_root,
                    case,
                    real_git,
                    base_env,
                )
                run_env, log_path = _git_counting_environment(
                    profile_root,
                    case.label,
                    base_env,
                    real_git,
                    count_git,
                )
                started = time.monotonic()
                if boundary == "engine":
                    permission = _engine_permission(
                        fixture,
                        case.command,
                        run_env,
                    )
                else:
                    selected_guard = (
                        installed_guard
                        if boundary == "installed"
                        else (guard_path or SOURCE_GUARD)
                    )
                    permission = _hook_permission(
                        selected_guard,
                        fixture,
                        case.command,
                        run_env,
                    )
                git_count = _log_count(log_path) if count_git else 0

            elapsed_by_case[case.label] = int(
                max(0.0, time.monotonic() - started) * 1000
            )
            git_by_case[case.label] = git_count
            outcomes[case.label] = permission
            expected_outcomes[case.label] = case.expected_permission

        document = {
            "schema": verification_contract.GUARD_BOUNDARY_PROFILE_SCHEMA,
            "boundary": boundary,
            "producer_sha256": _sha256(Path(__file__)),
            "case_manifest_sha256": _case_manifest_sha256(selected),
            "case_ids": [case.label for case in selected],
            "outcomes": outcomes,
            "expected_outcomes": expected_outcomes,
            "case_elapsed_ms": elapsed_by_case,
            "case_git_processes": git_by_case,
            "elapsed_ms": sum(elapsed_by_case.values()),
            "git_processes": sum(git_by_case.values()),
            "counter_scope": (
                GIT_COUNTER_SCOPE if count_git else NOT_COUNTED_SCOPE
            ),
            "passed": outcomes == expected_outcomes,
        }
        verification_contract.validate_guard_boundary_profile(document)
        return document


def run_engine_cases(
    cases: Sequence[GuardCase],
    count_git: bool = False,
) -> dict:
    return _profile_cases("engine", cases, count_git=count_git)


def run_source_hook_cases(
    cases: Sequence[GuardCase],
    count_git: bool = False,
    guard_path: Optional[Path] = None,
) -> dict:
    return _profile_cases(
        "source",
        cases,
        count_git=count_git,
        guard_path=guard_path,
    )


def run_installed_hook_cases(
    cases: Sequence[GuardCase],
    count_git: bool = False,
) -> dict:
    return _profile_cases("installed", cases, count_git=count_git)


def run_owner_mode_cases(
    cases: Sequence[GuardCase],
    count_git: bool = False,
) -> dict:
    return _profile_cases("owner", cases, count_git=count_git)


def _interpreter_identity(name: str, env: Mapping[str, str]) -> str:
    executable = shutil.which(name, path=env["PATH"])
    if not executable:
        raise ProfileError("{0} is unavailable".format(name))
    result = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
        env=dict(env),
        timeout=10,
    )
    if result.returncode != 0:
        raise ProfileError("{0} version probe failed".format(name))
    version = (result.stdout or result.stderr).splitlines()
    if not version:
        raise ProfileError("{0} version probe was empty".format(name))
    return "{0}|{1}".format(os.path.realpath(executable), version[0].strip())


def probe_installed_identity() -> dict:
    """Install into a private HOME and compare every guard decision dependency."""

    with tempfile.TemporaryDirectory(prefix="awa-guard-installed-identity.") as raw:
        profile_root = Path(raw)
        source_env = _private_environment(profile_root / "source-environment")
        installed_env = _private_environment(profile_root / "installed-environment")
        runtime = _install_runtime(profile_root, installed_env)
        installed_guard = runtime / "kernel" / "hooks" / "worktree-guard.sh"
        installed_checker = runtime / "kernel" / "bin" / "dev-worktree.sh"
        installed_policy = runtime / "kernel" / "lib" / "awa_policy.py"
        identity = {
            "source_guard_sha256": _sha256(SOURCE_GUARD),
            "installed_guard_sha256": _sha256(installed_guard),
            "source_checker_sha256": _sha256(SOURCE_CHECKER),
            "installed_checker_sha256": _sha256(installed_checker),
            "source_policy_sha256": _sha256(SOURCE_POLICY),
            "installed_policy_sha256": _sha256(installed_policy),
            "source_python": _interpreter_identity("python3", source_env),
            "installed_python": _interpreter_identity("python3", installed_env),
            "source_bash": _interpreter_identity("bash", source_env),
            "installed_bash": _interpreter_identity("bash", installed_env),
        }
    return identity


def installed_matrix_decision(
    identity: Mapping[str, str],
    canaries: Mapping[str, bool],
    *,
    full_engine_kernel_parity: bool,
) -> str:
    """Return the closed M3-A installed-matrix decision without overriding a gate."""

    if frozenset(identity) != _IDENTITY_KEYS:
        raise ValueError("installed identity keys are not closed")
    if any(not isinstance(identity[name], str) or not identity[name] for name in identity):
        raise ValueError("installed identity values must be non-empty strings")
    if frozenset(canaries) != frozenset(INSTALLED_DECISION_CANARIES):
        raise ValueError("installed decision canary keys are not closed")
    if any(type(canaries[name]) is not bool for name in canaries):
        raise ValueError("installed decision canaries must be booleans")
    if type(full_engine_kernel_parity) is not bool:
        raise ValueError("full_engine_kernel_parity must be a boolean")

    identity_matches = all(
        identity[source] == identity[installed]
        for source, installed in (
            ("source_guard_sha256", "installed_guard_sha256"),
            ("source_checker_sha256", "installed_checker_sha256"),
            ("source_policy_sha256", "installed_policy_sha256"),
            ("source_python", "installed_python"),
            ("source_bash", "installed_bash"),
        )
    )
    if (
        identity_matches
        and full_engine_kernel_parity
        and all(canaries.values())
    ):
        return "byte_identity_plus_canaries"
    return "retain_full"


def _write_json(path: Path, document: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                document,
                handle,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", required=True, choices=PROFILE_BOUNDARIES)
    parser.add_argument("--count-git", action="store_true")
    parser.add_argument("--json-out", required=True)
    args = parser.parse_args(argv)

    runners: Mapping[str, Callable[..., dict]] = {
        "engine": run_engine_cases,
        "source": run_source_hook_cases,
        "installed": run_installed_hook_cases,
        "owner": run_owner_mode_cases,
    }
    document = runners[args.boundary](
        GUARD_BOUNDARY_CASES,
        count_git=args.count_git,
    )
    _write_json(Path(args.json_out), document)
    print(
        "guard boundary {0}: {1}; {2} Git processes ({3})".format(
            args.boundary,
            "passed" if document["passed"] else "failed",
            document["git_processes"],
            document["counter_scope"],
        )
    )
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
