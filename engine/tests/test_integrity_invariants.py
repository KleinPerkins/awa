"""M1-A.2: invariant registry, checks, and deterministic severity reducer."""

from __future__ import annotations

import contextlib
import copy
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from engine import guard, integrity, mcp_server


_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_HOOKS = _ROOT / "kernel" / "hooks" / "install-hooks.sh"
_CONTRACT_FREEZE = _ROOT / "kernel" / "checks" / "awa-contract-freeze.sh"
_SAFE_FACTS = {
    "guard_primary_deny": True,
    "guard_cd_bypass_deny": True,
    "guard_linked_allow": True,
    "parity_ok": True,
    "hook_rows_present": True,
    "hook_fail_open": True,
    "mcp_matches": True,
    "release_matches": True,
    "recovery_last_status": "ok",
    "needs_repair": 0,
    "leases_unreconciled": 0,
    "sessions_dangling": 0,
    "husks": 0,
    "disposition_map": {},
    "handoff_state": "closed",
    "launchd_last_success_age_s": 0.0,
    "delivered": {"native": "accepted", "slack": "opted_out"},
}


def facts(**overrides) -> integrity.Facts:
    values = copy.deepcopy(_SAFE_FACTS)
    values.update(overrides)
    return integrity.Facts(**values)


def invariant(status: dict, invariant_id: str) -> dict:
    return next(item for item in status["invariants"] if item["id"] == invariant_id)


def materialize_role_commands(source: Path, roles: list[dict]) -> None:
    for role in roles:
        command = source / role["direct_command_role"]
        command.parent.mkdir(parents=True, exist_ok=True)
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)


class TestIntegrityInvariants(unittest.TestCase):
    def evaluate(self, **overrides) -> dict:
        return integrity.evaluate(
            "deep",
            trigger="cli",
            facts=facts(**overrides),
        )

    def test_guard_holds_is_green(self):
        status = self.evaluate()
        self.assertEqual(invariant(status, "guard_safety")["severity"], "green")
        self.assertEqual(status["overall"], "green")

    def test_guard_or_parity_unknown_is_red(self):
        for field, invariant_id in (
            ("guard_primary_deny", "guard_safety"),
            ("parity_ok", "parity"),
        ):
            with self.subTest(field=field):
                status = self.evaluate(**{field: None})
                self.assertEqual(
                    invariant(status, invariant_id)["severity"],
                    "unknown",
                )
                self.assertEqual(status["overall"], "red")

    def test_hooks_missing_row_or_fail_closed_is_degraded(self):
        for overrides in (
            {"hook_rows_present": False},
            {"hook_fail_open": False},
        ):
            with self.subTest(overrides=overrides):
                status = self.evaluate(**overrides)
                self.assertEqual(invariant(status, "hooks")["severity"], "degraded")
                self.assertEqual(status["overall"], "degraded")

    def test_mcp_engine_disagreement_is_red(self):
        status = self.evaluate(mcp_matches=False)
        self.assertEqual(invariant(status, "mcp_engine_parity")["severity"], "red")
        self.assertEqual(status["overall"], "red")

    def test_alert_delivery_prior_all_failed_while_nongreen_is_red(self):
        status = self.evaluate(
            release_matches=False,
            delivered={"native": "failed", "slack": "opted_out"},
        )
        self.assertEqual(invariant(status, "alert_delivery")["severity"], "red")
        self.assertEqual(status["overall"], "red")

    def test_alert_delivery_prior_failure_does_not_stick_recovered_green(self):
        status = self.evaluate(
            delivered={"native": "failed", "slack": "opted_out"}
        )
        self.assertEqual(invariant(status, "alert_delivery")["severity"], "green")
        self.assertEqual(status["overall"], "green")

    def test_alert_delivery_requires_explicit_slack_opt_out(self):
        status = self.evaluate(
            release_matches=False,
            delivered={"native": "accepted"},
        )
        self.assertEqual(
            invariant(status, "alert_delivery")["severity"],
            "unknown",
        )
        self.assertEqual(status["overall"], "degraded")

    def test_leases_unreconciled_make_lifecycle_degraded(self):
        status = self.evaluate(
            leases_unreconciled=1,
            disposition_map={"/redacted/root": "dead"},
        )
        self.assertEqual(invariant(status, "lifecycle")["severity"], "degraded")
        self.assertEqual(status["overall"], "degraded")

    def test_recovery_error_is_degraded(self):
        status = self.evaluate(recovery_last_status="errors", needs_repair=1)
        self.assertEqual(invariant(status, "recovery")["severity"], "degraded")
        self.assertEqual(status["overall"], "degraded")

    def test_stale_launchd_freshness_nongreen(self):
        status = self.evaluate(
            launchd_last_success_age_s=integrity.DEEP_BOUND_SECONDS + 1
        )
        self.assertEqual(
            invariant(status, "surveillance_freshness")["severity"],
            "red",
        )
        self.assertEqual(status["overall"], "red")

    def test_launchd_deep_pass_refreshes_own_freshness(self):
        status = integrity.evaluate(
            "deep",
            trigger="launchd",
            facts=facts(launchd_last_success_age_s=None),
        )
        self.assertEqual(
            invariant(status, "surveillance_freshness")["severity"],
            "green",
        )
        self.assertEqual(status["overall"], "green")

    def test_release_mismatch_degraded(self):
        status = self.evaluate(release_matches=False)
        self.assertEqual(
            invariant(status, "release_identity")["severity"],
            "degraded",
        )
        self.assertEqual(status["overall"], "degraded")

    def test_entry_absent_until_handoff_metadata(self):
        status = self.evaluate(handoff_state="absent")
        entry = invariant(status, "entry_handshake")
        self.assertEqual(entry["severity"], "unknown")
        self.assertEqual(entry["evidence"], "handoff metadata absent")
        self.assertEqual(status["overall"], "degraded")
        self.assertNotIn("retry", entry["evidence"])

    def test_reduce_requires_all_required_green_and_fresh(self):
        expected_ids = {
            "guard_safety",
            "entry_handshake",
            "recovery",
            "lifecycle",
            "parity",
            "hooks",
            "mcp_engine_parity",
            "release_identity",
            "surveillance_freshness",
            "alert_delivery",
        }
        self.assertEqual(set(integrity.REGISTRY), expected_ids)
        self.assertTrue(all(len(spec) == 4 for spec in integrity.REGISTRY.values()))

        healthy = self.evaluate()
        self.assertEqual(
            integrity.reduce(healthy["invariants"], healthy["triggers"]),
            "green",
        )

        degraded = copy.deepcopy(healthy["invariants"])
        invariant({"invariants": degraded}, "hooks")["severity"] = "degraded"
        self.assertEqual(integrity.reduce(degraded, healthy["triggers"]), "degraded")

        stale_triggers = copy.deepcopy(healthy["triggers"])
        stale_triggers["launchd"]["last_success"] = "2000-01-01T00:00:00Z"
        self.assertEqual(
            integrity.reduce(healthy["invariants"], stale_triggers),
            "red",
        )

    def test_lifecycle_loads_disposition_from_source_root(self):
        class FakeConnection:
            def execute(self, _query):
                return self

            def fetchall(self):
                return [("/redacted/missing-worktree",)]

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            module_path = source / "kernel" / "lib" / "awa_roots.py"
            module_path.parent.mkdir(parents=True)
            module_path.write_text(
                "def disposition(_path):\n"
                "    return {'disposition': 'dead', 'record': {}}\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                integrity,
                "_ro_conn",
                return_value=FakeConnection(),
            ):
                observed = integrity._lifecycle_facts(source)

        self.assertEqual(observed[:3], (1, 0, 0))
        self.assertEqual(list(observed[3].values()), ["dead"])

    def test_mcp_parity_evaluates_adapter_with_source_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            policy = (
                source
                / "kernel"
                / "policy"
                / "default-worktree-policy.yml"
            )
            policy.parent.mkdir(parents=True)
            policy.write_text("version: 1\n", encoding="utf-8")
            seen_policies = []

            def direct(_cwd, _command, policy_path):
                seen_policies.append(str(policy_path))
                return SimpleNamespace(
                    permission="allow",
                    classification="read_only",
                )

            def adapted(_args):
                seen_policies.append(mcp_server._policy_path())
                return {
                    "permission": "allow",
                    "classification": "read_only",
                }

            with mock.patch.object(guard, "decide_shell", side_effect=direct), \
                    mock.patch.object(
                        mcp_server,
                        "_tool_guard_shell",
                        side_effect=adapted,
                    ):
                self.assertTrue(
                    integrity._mcp_parity(
                        source,
                        [(source, "git status")],
                    )
                )

        self.assertEqual(seen_policies, [str(policy), str(policy)])

    def test_kernel_parity_accepts_public_permission_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            hook = source / "kernel" / "hooks" / "worktree-guard.sh"
            policy = (
                source
                / "kernel"
                / "policy"
                / "default-worktree-policy.yml"
            )
            hook.parent.mkdir(parents=True)
            policy.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\n", encoding="utf-8")
            policy.write_text("version: 1\n", encoding="utf-8")
            direct = SimpleNamespace(
                permission="allow",
                classification="read_only",
            )
            mirrored = SimpleNamespace(
                returncode=0,
                stdout='{"permission":"allow"}',
            )
            with mock.patch.object(
                guard,
                "decide_shell",
                return_value=direct,
            ), mock.patch.object(
                integrity.subprocess,
                "run",
                return_value=mirrored,
            ):
                self.assertTrue(
                    integrity._kernel_parity(
                        source,
                        [(source, "git status")],
                    )
                )

    def test_fast_profile_skips_deep_collectors_and_carries_prior_evidence(self):
        previous = self.evaluate()
        deep_ids = (
            "recovery",
            "lifecycle",
            "parity",
            "mcp_engine_parity",
            "release_identity",
        )
        prior_deep = {
            invariant_id: copy.deepcopy(invariant(previous, invariant_id))
            for invariant_id in deep_ids
        }
        deep_collectors = (
            "_recovery_facts",
            "_lifecycle_facts",
            "_kernel_parity",
            "_mcp_parity",
        )
        with contextlib.ExitStack() as stack:
            collectors = [
                stack.enter_context(
                    mock.patch.object(
                        integrity,
                        name,
                        side_effect=AssertionError(f"fast called {name}"),
                    )
                )
                for name in deep_collectors
            ]
            stack.enter_context(
                mock.patch.object(integrity, "read_status", return_value=previous)
            )
            stack.enter_context(
                mock.patch.object(
                    integrity,
                    "_source_root",
                    return_value=Path("/source"),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    integrity,
                    "_guard_probes",
                    return_value=(True, True, True, []),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    integrity,
                    "_hook_facts",
                    return_value=(True, True),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    integrity,
                    "_release_matches",
                    return_value=True,
                )
            )
            status = integrity.evaluate("fast", trigger="cli")

        for collector in collectors:
            collector.assert_not_called()
        for invariant_id, prior in prior_deep.items():
            self.assertEqual(invariant(status, invariant_id), prior)


class TestInstalledTopologyFacts(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-integrity-topology.")
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _repo(self, name: str, *, linked: bool) -> tuple[Path, Path | None]:
        primary = self.root / name
        primary.mkdir()
        self._git(primary, "init", "-q")
        self._git(primary, "config", "user.name", "AWA Test")
        self._git(primary, "config", "user.email", "awa-test@example.invalid")
        self._git(primary, "remote", "add", "origin", "https://example.invalid/awa.git")
        (primary / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        self._git(primary, "add", "tracked.txt")
        self._git(primary, "commit", "-qm", "seed")
        if not linked:
            return primary, None
        worktree = self.root / f"{name}-linked"
        self._git(primary, "worktree", "add", "-q", "-b", f"{name}-linked", str(worktree))
        return primary, worktree

    def _runtime(self) -> Path:
        runtime = self.root / "runtime"
        shutil.copytree(_ROOT / "kernel", runtime / "kernel")
        return runtime

    def _clean_env(self, **updates: str) -> dict[str, str]:
        env = os.environ.copy()
        for name in (
            "AWA_GOVERNED_ROOT",
            "CURSOR_BACKGROUND_AGENT",
            "CURSOR_CLOUD_AGENT",
            "IS_BACKGROUND_AGENT",
            "is_background_agent",
            "AWA_FORCE_CLOUD",
            "cloud_agent_identity_broker",
            "CURSOR_AGENT_IDENTITY_BROKER",
        ):
            env.pop(name, None)
        env.update(updates)
        return env

    def test_installed_runtime_uses_explicit_host_probe_topology(self):
        runtime = self._runtime()
        source, _ = self._repo("detached-source", linked=False)
        self._git(source, "checkout", "-q", "--detach")
        probe, linked = self._repo("host-probe", linked=True)
        self.assertIsNotNone(linked)
        policy = runtime / "kernel" / "policy" / "default-worktree-policy.yml"
        policy.write_text(
            "version: 1\n"
            "governed_roots:\n"
            f"  - {self.root}\n"
            f"managed_location: {self.root / 'managed'}\n"
            "default: include\n"
            "default_mode: on\n"
            "include:\n"
            "  - '*'\n"
            "exclude: []\n"
            "detectors:\n"
            "  governed_markers: []\n"
            "  foreign_hook_frameworks: []\n"
            "  read_only_paths: []\n"
            "overrides:\n"
            "  include: []\n"
            "  exclude: []\n",
            encoding="utf-8",
        )
        now = 1_800_000_000.0
        previous = {
            "triggers": {"launchd": {"last_success": integrity._iso_at(now)}},
            "alert": {
                "delivered": {"native": "accepted", "slack": "opted_out"}
            },
        }
        pointer = {"runtime": str(runtime), "source": str(source)}
        env = self._clean_env(
            AWA_INTEGRITY_PROBE_REPO=str(probe),
            AWA_POLICY=str(policy),
        )

        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(integrity, "_release_pointer", return_value=pointer), \
                mock.patch.object(integrity, "_recovery_facts", return_value=("ok", 0)), \
                mock.patch.object(
                    integrity,
                    "_lifecycle_facts",
                    return_value=(0, 0, 0, {}),
                ), \
                mock.patch.object(integrity, "_hook_facts", return_value=(True, True)), \
                mock.patch.object(integrity, "_release_matches", return_value=True):
            self.assertEqual(integrity._source_root(), runtime.resolve())
            observed = integrity._collect_facts(
                previous,
                profile="deep",
                now=now,
            )

        self.assertIs(observed.guard_primary_deny, True)
        self.assertIs(observed.guard_cd_bypass_deny, True)
        self.assertIs(observed.guard_linked_allow, True)
        self.assertIs(observed.parity_ok, True)
        self.assertIs(observed.mcp_matches, True)
        self.assertEqual(observed.handoff_state, "absent")
        status = integrity.evaluate(
            "deep",
            trigger="launchd",
            facts=observed,
        )
        self.assertEqual(invariant(status, "guard_safety")["severity"], "green")
        self.assertEqual(invariant(status, "parity")["severity"], "green")
        self.assertEqual(
            invariant(status, "mcp_engine_parity")["severity"],
            "green",
        )
        self.assertEqual(
            invariant(status, "entry_handshake")["severity"],
            "unknown",
        )
        self.assertEqual(status["overall"], "degraded")

    def test_explicit_probe_absence_or_single_worktree_stays_unknown(self):
        runtime = self._runtime()
        fallback, _ = self._repo("fallback", linked=True)
        single, _ = self._repo("single", linked=False)
        pointer = {"runtime": str(runtime), "source": str(fallback)}

        for candidate in (self.root / "missing", single):
            with self.subTest(candidate=candidate), \
                    mock.patch.dict(
                        os.environ,
                        self._clean_env(AWA_INTEGRITY_PROBE_REPO=str(candidate)),
                        clear=True,
                    ), \
                    mock.patch.object(
                        integrity,
                        "_release_pointer",
                        return_value=pointer,
                    ):
                self.assertLess(
                    len(integrity._probe_worktree_paths(runtime)),
                    2,
                )
                self.assertEqual(
                    integrity._guard_probes(runtime),
                    (None, None, None, []),
                )

    def test_single_release_source_does_not_fabricate_linked_topology(self):
        runtime = self._runtime()
        source, _ = self._repo("single-source", linked=False)
        self._git(source, "checkout", "-q", "--detach")
        pointer = {"runtime": str(runtime), "source": str(source)}

        with mock.patch.dict(os.environ, self._clean_env(), clear=True), \
                mock.patch.object(
                    integrity,
                    "_release_pointer",
                    return_value=pointer,
                ):
            self.assertEqual(integrity._probe_worktree_paths(runtime), [])
            self.assertEqual(
                integrity._guard_probes(runtime),
                (None, None, None, []),
            )


class TestLiveHookFacts(unittest.TestCase):
    """The live collector follows the same preferred contract as installation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-facts.")
        self.root = Path(self._tmp.name)
        self.hooks_path = self.root / "hooks.json"
        env = os.environ.copy()
        env.update(
            {
                "AWA_HOOK_OWNER": "direct",
                "AWA_HOOKS_JSON": str(self.hooks_path),
                "HOME": str(self.root / "home"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        self.env = env
        installed = subprocess.run(
            [str(_INSTALL_HOOKS)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(
            installed.returncode,
            0,
            installed.stdout + installed.stderr,
        )
        self.projected = json.loads(self.hooks_path.read_text(encoding="utf-8"))

    def tearDown(self):
        self._tmp.cleanup()

    def _collect(self, source: Path = _ROOT) -> tuple[tuple, dict]:
        with mock.patch.dict(
            os.environ,
            {
                "AWA_HOOK_OWNER": "direct",
                "AWA_HOOKS_JSON": str(self.hooks_path),
            },
            clear=False,
        ):
            observed = integrity._hook_facts(source)
        status = integrity.evaluate(
            "fast",
            trigger="beforeShell",
            facts=facts(
                hook_rows_present=observed[0],
                hook_fail_open=observed[1],
            ),
        )
        return observed, invariant(status, "hooks")

    def _write_projection(self, document: dict) -> None:
        self.hooks_path.write_text(
            json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )

    def _parity_runtime(self, name: str) -> tuple[Path, Path]:
        runtime = self.root / name
        shutil.copytree(_ROOT / "kernel", runtime / "kernel")
        shutil.copytree(_ROOT / "contracts", runtime / "contracts")
        (runtime / "engine").mkdir()
        shutil.copy2(
            _ROOT / "engine" / "integrity_detach.py",
            runtime / "engine" / "integrity_detach.py",
        )
        (runtime / "dashboard").mkdir()
        shutil.copy2(
            _ROOT / "dashboard" / "emitter.py",
            runtime / "dashboard" / "emitter.py",
        )
        bounded_freeze = runtime / "kernel" / "checks" / "hook-owner-freeze.sh"
        freeze_source = _CONTRACT_FREEZE.read_text(encoding="utf-8")
        bounded_freeze.write_text(
            freeze_source.split("# 0a) M1-C hook mechanics:", 1)[0]
            + 'exit "$fail"\n',
            encoding="utf-8",
        )
        bounded_freeze.chmod(0o755)

        projected = runtime / "projected-hooks.json"
        env = dict(self.env)
        env["AWA_HOOKS_JSON"] = str(projected)
        installed = subprocess.run(
            [str(runtime / "kernel" / "hooks" / "install-hooks.sh")],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(
            installed.returncode,
            0,
            installed.stdout + installed.stderr,
        )
        return runtime, projected

    def _parity_acceptance(self, runtime: Path, projected: Path) -> dict[str, bool]:
        env = dict(self.env)
        env["AWA_HOOKS_JSON"] = str(runtime / "candidate-hooks.json")
        installer = subprocess.run(
            [str(runtime / "kernel" / "hooks" / "install-hooks.sh")],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        doctor = subprocess.run(
            [str(runtime / "kernel" / "bin" / "dev-worktree.sh"), "doctor"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        freeze_env = dict(env)
        freeze_env["AWA_HOME"] = str(runtime)
        contract_freeze = subprocess.run(
            [str(runtime / "kernel" / "checks" / "hook-owner-freeze.sh")],
            capture_output=True,
            text=True,
            env=freeze_env,
            timeout=30,
        )
        with mock.patch.dict(
            os.environ,
            {
                "AWA_HOOK_OWNER": "direct",
                "AWA_HOOKS_JSON": str(projected),
            },
            clear=False,
        ):
            effective = integrity._effective_hook_roles(runtime)
            observed = integrity._hook_facts(runtime)
        status = integrity.evaluate(
            "fast",
            trigger="beforeShell",
            facts=facts(
                hook_rows_present=observed[0],
                hook_fail_open=observed[1],
            ),
        )
        return {
            "install": installer.returncode == 0,
            "doctor": doctor.returncode == 0,
            "contract-freeze": contract_freeze.returncode == 0,
            "integrity": effective is not None,
            "integrity-unknown": (
                observed == (False, None)
                and invariant(status, "hooks")["severity"] == "unknown"
            ),
            "integrity-green": (
                observed == (True, True)
                and invariant(status, "hooks")["severity"] == "green"
            ),
        }

    def test_v2_validation_acceptance_parity_matrix(self):
        header_cases = {
            "schema": ("schema", "wrong"),
            "version": ("version", 3),
            "successor": ("successor_of", "wrong"),
            "v1-contract": ("v1_contract", "wrong"),
            "modes": ("modes", ["external", "direct"]),
            "default-mode": ("default_mode", "external"),
            "selection-env": ("selection_env", "WRONG"),
            "selection-schema": ("selection_schema", "wrong"),
            "external-writes": ("external_real_hook_file_writes", True),
            "supersedes": ("supersedes_roles", []),
            "composition-rule": ("composition_rule", ""),
            "external-rule": ("external_rule", ""),
        }

        def mutate_header(document, _runtime, field, value):
            document[field] = value

        def mutate_role(document, _runtime, index, field, value):
            document["roles"][index][field] = value

        def mutate_entry(document, _runtime, index, field, value):
            document["roles"][index]["entry"][field] = value

        cases = [
            (
                f"header.{name}",
                lambda document, runtime, field=field, value=value: mutate_header(
                    document, runtime, field, value
                ),
            )
            for name, (field, value) in header_cases.items()
        ]
        cases.extend(
            [
                ("roles.count", lambda document, _runtime: document["roles"].pop()),
                (
                    "role.id",
                    lambda document, runtime: mutate_role(
                        document, runtime, 0, "id", "wrong"
                    ),
                ),
                (
                    "role.event",
                    lambda document, runtime: mutate_role(
                        document, runtime, 0, "event", "afterFileEdit"
                    ),
                ),
                (
                    "role.path-containment",
                    lambda document, runtime: mutate_role(
                        document, runtime, 0, "direct_command_role", "../escape.sh"
                    ),
                ),
                (
                    "role.external-class",
                    lambda document, runtime: mutate_role(
                        document,
                        runtime,
                        0,
                        "external_command_path_class",
                        "installed-awa",
                    ),
                ),
                (
                    "role.dormancy",
                    lambda document, runtime: mutate_role(
                        document,
                        runtime,
                        2,
                        "dormant_until_milestone",
                        "M9",
                    ),
                ),
                (
                    "role.unexpected-dormancy",
                    lambda document, runtime: mutate_role(
                        document,
                        runtime,
                        0,
                        "dormant_until_milestone",
                        "M2.4",
                    ),
                ),
                (
                    "role.extra-field",
                    lambda document, runtime: mutate_role(
                        document, runtime, 0, "unexpected", True
                    ),
                ),
                (
                    "role.missing-entry",
                    lambda document, _runtime: document["roles"][0].pop("entry"),
                ),
                (
                    "entry.type",
                    lambda document, runtime: mutate_entry(
                        document, runtime, 0, "type", "prompt"
                    ),
                ),
                (
                    "entry.timeout",
                    lambda document, runtime: mutate_entry(
                        document, runtime, 0, "timeout", 0
                    ),
                ),
                (
                    "entry.timeout-missing",
                    lambda document, _runtime: document["roles"][0]["entry"].pop(
                        "timeout"
                    ),
                ),
                (
                    "entry.fail-closed",
                    lambda document, runtime: mutate_entry(
                        document, runtime, 0, "failClosed", True
                    ),
                ),
                (
                    "entry.fail-closed-missing",
                    lambda document, _runtime: document["roles"][0]["entry"].pop(
                        "failClosed"
                    ),
                ),
                (
                    "entry.command",
                    lambda document, runtime: mutate_entry(
                        document, runtime, 0, "command", "/wrong"
                    ),
                ),
                (
                    "entry.extra-field",
                    lambda document, runtime: mutate_entry(
                        document, runtime, 0, "unexpected", True
                    ),
                ),
                (
                    "executable.missing",
                    lambda _document, runtime: (
                        runtime / "kernel" / "hooks" / "awa-integrity-observer.sh"
                    ).unlink(),
                ),
                (
                    "executable.non-executable",
                    lambda _document, runtime: (
                        runtime / "kernel" / "hooks" / "awa-integrity-observer.sh"
                    ).chmod(0o644),
                ),
                (
                    "executable.symlink-escape",
                    lambda _document, runtime: (
                        (
                            runtime
                            / "kernel"
                            / "hooks"
                            / "awa-integrity-observer.sh"
                        ).unlink(),
                        (
                            runtime
                            / "kernel"
                            / "hooks"
                            / "awa-integrity-observer.sh"
                        ).symlink_to(self.root / "outside-observer.sh"),
                    ),
                ),
            ]
        )

        valid_runtime, valid_projection = self._parity_runtime("parity-valid")
        outside = self.root / "outside-observer.sh"
        outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        outside.chmod(0o755)
        self.assertEqual(
            self._parity_acceptance(valid_runtime, valid_projection),
            {
                "install": True,
                "doctor": True,
                "contract-freeze": True,
                "integrity": True,
                "integrity-unknown": False,
                "integrity-green": True,
            },
        )

        for name, mutate in cases:
            with self.subTest(name=name):
                runtime, projected = self._parity_runtime(f"parity-{name}")
                contract_path = (
                    runtime / "contracts" / "awa-hook-owner.v2.json"
                )
                document = json.loads(contract_path.read_text(encoding="utf-8"))
                mutate(document, runtime)
                contract_path.write_text(
                    json.dumps(document, indent=2) + "\n",
                    encoding="utf-8",
                )
                self.assertEqual(
                    self._parity_acceptance(runtime, projected),
                    {
                        "install": False,
                        "doctor": False,
                        "contract-freeze": False,
                        "integrity": False,
                        "integrity-unknown": True,
                        "integrity-green": False,
                    },
                )

    def test_v2_direct_projection_collects_green_hooks(self):
        observed, hook_invariant = self._collect()
        self.assertEqual(observed, (True, True))
        self.assertEqual(hook_invariant["severity"], "green")

    def test_v2_composite_drift_degrades(self):
        composite_name = "worktree-guard-with-integrity.sh"
        original = copy.deepcopy(self.projected)

        def composite_row(document):
            return next(
                row
                for row in document["hooks"]["beforeShellExecution"]
                if Path(row["command"]).name == composite_name
            )

        mutations = {}

        missing = copy.deepcopy(original)
        missing["hooks"]["beforeShellExecution"].remove(composite_row(missing))
        mutations["missing"] = missing

        wrong_command = copy.deepcopy(original)
        composite_row(wrong_command)["command"] += ".lookalike"
        mutations["wrong-command"] = wrong_command

        wrong_event = copy.deepcopy(original)
        moved = composite_row(wrong_event)
        wrong_event["hooks"]["beforeShellExecution"].remove(moved)
        wrong_event["hooks"].setdefault("afterFileEdit", []).append(moved)
        mutations["wrong-event"] = wrong_event

        fail_closed = copy.deepcopy(original)
        composite_row(fail_closed)["failClosed"] = True
        mutations["fail-closed"] = fail_closed

        for name, document in mutations.items():
            with self.subTest(name=name):
                self._write_projection(document)
                observed, hook_invariant = self._collect()
                self.assertEqual(hook_invariant["severity"], "degraded")
                if name == "fail-closed":
                    self.assertEqual(observed, (True, False))
                else:
                    self.assertEqual(observed, (False, True))

    def test_v1_contract_projection_remains_green(self):
        source = self.root / "v1-source"
        contract_path = source / "contracts" / "awa-contract.v1.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_bytes(
            (_ROOT / "contracts" / "awa-contract.v1.json").read_bytes()
        )
        owner = json.loads(contract_path.read_text(encoding="utf-8"))[
            "hook_ownership"
        ]
        materialize_role_commands(source, owner["roles"])
        hooks: dict[str, list[dict]] = {}
        for role in owner["roles"]:
            row = dict(role["entry"])
            row["command"] = str(
                (source / role["direct_command_role"]).resolve()
            )
            hooks.setdefault(role["event"], []).append(row)
        self._write_projection({"version": 1, "hooks": hooks})

        observed, hook_invariant = self._collect(source)
        self.assertEqual(observed, (True, True))
        self.assertEqual(hook_invariant["severity"], "green")

    def test_invalid_shipped_v2_does_not_fallback_to_v1(self):
        source = self.root / "invalid-v2-source"
        contracts = source / "contracts"
        contracts.mkdir(parents=True)
        v1_path = contracts / "awa-contract.v1.json"
        v1_path.write_bytes(
            (_ROOT / "contracts" / "awa-contract.v1.json").read_bytes()
        )
        (contracts / "awa-hook-owner.v2.json").write_text(
            '{"schema":"awa-hook-owner/v2","roles":[]}\n',
            encoding="utf-8",
        )
        owner = json.loads(v1_path.read_text(encoding="utf-8"))[
            "hook_ownership"
        ]
        materialize_role_commands(source, owner["roles"])
        hooks: dict[str, list[dict]] = {}
        for role in owner["roles"]:
            row = dict(role["entry"])
            row["command"] = str(
                (source / role["direct_command_role"]).resolve()
            )
            hooks.setdefault(role["event"], []).append(row)
        self._write_projection({"version": 1, "hooks": hooks})

        observed, hook_invariant = self._collect(source)
        self.assertEqual(observed, (False, None))
        self.assertEqual(hook_invariant["severity"], "unknown")


class TestExternalOwnerHookFacts(unittest.TestCase):
    """External ownership resolves one coherent, exact role projection."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-external-hook-facts.")
        self.root = Path(self._tmp.name).resolve()
        self.hooks_path = self.root / "hooks.json"
        self.owner_dir = self.root / "external-owner" / "hooks"
        self.selection = self.root / "config" / "awa" / "hook-owner.json"
        self.selection.parent.mkdir(parents=True)
        self.selection.write_text(
            json.dumps(
                {
                    "schema": "awa-hook-owner-selection/v1",
                    "contract": "awa-hook-owner/v1",
                    "mode": "external",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.selection.chmod(0o600)

    def tearDown(self):
        self._tmp.cleanup()

    def _projection(
        self,
        source: Path = _ROOT,
    ) -> tuple[dict, list[dict]]:
        if self.owner_dir.exists():
            shutil.rmtree(self.owner_dir)
        roles = integrity._effective_hook_roles(source)
        self.assertIsNotNone(roles)
        assert roles is not None
        hooks: dict[str, list[dict]] = {}
        for role in roles:
            if role["external_command_path_class"] == "host-policy-delegator":
                target = self.owner_dir / Path(role["direct_command_role"]).name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.parent.chmod(0o755)
                target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                target.chmod(0o755)
            else:
                target = (source / role["direct_command_role"]).resolve()
            row = dict(role["entry"])
            row["command"] = str(target)
            hooks.setdefault(role["event"], []).append(row)
        return {"version": 1, "hooks": hooks}, roles

    def _write_projection(self, document: dict) -> None:
        self.hooks_path.write_text(
            json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )

    def _collect(self, source: Path = _ROOT) -> tuple[bool | None, bool | None]:
        with mock.patch.dict(
            os.environ,
            {
                "AWA_HOOKS_JSON": str(self.hooks_path),
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "XDG_DATA_HOME": str(self.root / "data"),
                "XDG_STATE_HOME": str(self.root / "state"),
            },
            clear=False,
        ):
            os.environ.pop("AWA_HOOK_OWNER", None)
            return integrity._hook_facts(source)

    @staticmethod
    def _role_row(
        document: dict,
        roles: list[dict],
        role_id: str,
    ) -> tuple[list[dict], dict, dict]:
        role = next(item for item in roles if item["id"] == role_id)
        rows = document["hooks"][role["event"]]
        row = next(
            item
            for item in rows
            if Path(item["command"]).name
            == Path(role["direct_command_role"]).name
        )
        return rows, row, role

    def test_external_owner_seven_role_projection_is_green(self):
        document, roles = self._projection()
        self.assertEqual(len(roles), 7)
        self.assertEqual(
            sum(len(rows) for rows in document["hooks"].values()),
            7,
        )
        self._write_projection(document)

        observed = self._collect()
        status = integrity.evaluate(
            "fast",
            trigger="beforeShell",
            facts=facts(
                hook_rows_present=observed[0],
                hook_fail_open=observed[1],
            ),
        )

        self.assertEqual(observed, (True, True))
        self.assertEqual(invariant(status, "hooks")["severity"], "green")
        self.assertEqual(
            invariant(status, "hooks")["evidence"],
            "required hook rows are present and fail open",
        )

    def test_external_owner_rejects_invalid_role_rows(self):
        cases = {
            "malformed": (False, None),
            "missing": (False, True),
            "duplicate": (False, True),
            "wrong-target": (False, True),
            "untrusted-owner": (False, True),
            "mixed-owner": (False, True),
            "non-executable": (False, True),
            "symlink": (False, True),
            "invalid-command": (False, True),
            "stale-shell-wrapper": (False, True),
            "mixed-direct": (False, True),
            "installed-role-external": (False, True),
            "fail-closed": (True, False),
        }
        for case, expected in cases.items():
            with self.subTest(case=case):
                document, roles = self._projection()
                rows, row, role = self._role_row(
                    document,
                    roles,
                    "worktree.stop-observer",
                )
                if case == "malformed":
                    rows[rows.index(row)] = "not-an-object"
                elif case == "missing":
                    rows.remove(row)
                elif case == "duplicate":
                    rows.append(copy.deepcopy(row))
                elif case == "wrong-target":
                    wrong = self.owner_dir / "wrong-target.sh"
                    wrong.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    wrong.chmod(0o755)
                    row["command"] = str(wrong)
                elif case == "untrusted-owner":
                    self.owner_dir.chmod(0o777)
                elif case == "mixed-owner":
                    untrusted = (
                        self.root
                        / "untrusted"
                        / Path(role["direct_command_role"]).name
                    )
                    untrusted.parent.mkdir()
                    untrusted.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    untrusted.chmod(0o755)
                    row["command"] = str(untrusted)
                elif case == "non-executable":
                    Path(row["command"]).chmod(0o644)
                elif case == "symlink":
                    link = Path(row["command"])
                    target = link.with_suffix(".real")
                    link.replace(target)
                    link.symlink_to(target)
                elif case == "invalid-command":
                    row["command"] = (
                        "/invalid\x00/"
                        + Path(role["direct_command_role"]).name
                    )
                elif case == "stale-shell-wrapper":
                    stale = copy.deepcopy(row)
                    stale["command"] = f"bash {row['command']}"
                    rows.append(stale)
                elif case == "mixed-direct":
                    direct = dict(role["entry"])
                    direct["command"] = str(
                        (_ROOT / role["direct_command_role"]).resolve()
                    )
                    rows.append(direct)
                elif case == "installed-role-external":
                    rows, row, role = self._role_row(
                        document,
                        roles,
                        "recovery.maintenance",
                    )
                    target = self.owner_dir / Path(
                        role["direct_command_role"]
                    ).name
                    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    target.chmod(0o755)
                    row["command"] = str(target)
                elif case == "fail-closed":
                    row["failClosed"] = True
                self._write_projection(document)
                self.assertEqual(self._collect(), expected)

    def test_external_owner_rejects_direct_projection(self):
        env = os.environ.copy()
        env.update(
            {
                "AWA_HOOK_OWNER": "direct",
                "AWA_HOOKS_JSON": str(self.hooks_path),
                "HOME": str(self.root / "direct-home"),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        installed = subprocess.run(
            [str(_INSTALL_HOOKS)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(
            installed.returncode,
            0,
            installed.stdout + installed.stderr,
        )
        self.assertNotEqual(self._collect(), (True, True))

    def test_external_owner_v1_projection_remains_green(self):
        source = self.root / "v1-source"
        contract_path = source / "contracts" / "awa-contract.v1.json"
        contract_path.parent.mkdir(parents=True)
        contract_path.write_bytes(
            (_ROOT / "contracts" / "awa-contract.v1.json").read_bytes()
        )
        owner = json.loads(contract_path.read_text(encoding="utf-8"))[
            "hook_ownership"
        ]
        materialize_role_commands(source, owner["roles"])
        document, roles = self._projection(source)
        self.assertEqual(len(roles), 5)
        self._write_projection(document)

        self.assertEqual(self._collect(source), (True, True))

    def test_malformed_external_owner_selection_is_unknown(self):
        document, _roles = self._projection()
        self._write_projection(document)
        malformed = (
            {"mode": "external"},
            {
                "schema": "awa-hook-owner-selection/v1",
                "contract": "awa-hook-owner/v1",
                "mode": [],
            },
        )
        for selection in malformed:
            with self.subTest(selection=selection):
                self.selection.write_text(
                    json.dumps(selection) + "\n",
                    encoding="utf-8",
                )
                self.assertEqual(self._collect(), (False, None))

    def test_release_pointer_fallback_resolves_external_owner(self):
        document, _roles = self._projection()
        self._write_projection(document)
        self.selection.unlink()
        pointer = self.root / "data" / "awa" / "release-pointer.json"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(
            json.dumps(
                {
                    "schema": "awa-release-pointer/v1",
                    "version": "1.7.0",
                    "source": str(_ROOT),
                    "commit": "a" * 40,
                    "runtime": str(_ROOT),
                    "policy": str(
                        _ROOT / "kernel" / "policy" / "default-worktree-policy.yml"
                    ),
                    "installed_at": "2026-08-28T00:00:00Z",
                    "hook_owner_contract": "awa-hook-owner/v1",
                    "hook_owner_mode": "external",
                    "hook_owner_contract_sha256": "b" * 64,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(self._collect(), (True, True))

    def test_partial_owner_release_pointer_is_unknown(self):
        document, _roles = self._projection()
        self._write_projection(document)
        self.selection.unlink()
        pointer = self.root / "data" / "awa" / "release-pointer.json"
        pointer.parent.mkdir(parents=True)
        pointer.write_text(
            json.dumps(
                {
                    "schema": "awa-release-pointer/v1",
                    "version": "1.7.0",
                    "source": str(_ROOT),
                    "commit": "a" * 40,
                    "runtime": str(_ROOT),
                    "policy": str(
                        _ROOT / "kernel" / "policy" / "default-worktree-policy.yml"
                    ),
                    "installed_at": "2026-08-28T00:00:00Z",
                    "hook_owner_mode": "external",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.assertEqual(self._collect(), (False, None))


if __name__ == "__main__":
    unittest.main()
