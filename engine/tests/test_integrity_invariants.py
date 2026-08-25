"""M1-A.2: invariant registry, checks, and deterministic severity reducer."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from engine import guard, integrity, mcp_server


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


if __name__ == "__main__":
    unittest.main()
