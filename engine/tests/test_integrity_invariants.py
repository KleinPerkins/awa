"""M1-A.2: invariant registry, checks, and deterministic severity reducer."""

from __future__ import annotations

import contextlib
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from engine import guard, integrity, mcp_server


_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_HOOKS = _ROOT / "kernel" / "hooks" / "install-hooks.sh"
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
            {"AWA_HOOKS_JSON": str(self.hooks_path)},
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


if __name__ == "__main__":
    unittest.main()
