from __future__ import annotations

import hashlib
import re
import sqlite3
import unittest
from pathlib import Path

from engine import registration_hashes, registration_schema


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "plans" / "native-entry-durable-registration-v3.md"
EXPECTED_SCHEMA_HASH = (
    "221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede"
)
EXPECTED_TABLES = {
    "registration_protocol_epoch",
    "registration_member",
    "registration_episode",
    "registration_effect",
    "registration_effect_action",
    "registration_runtime_status",
    "registration_operation_audit",
}
EXPECTED_TRIGGERS = {
    "trg_protocol_epoch_insert",
    "trg_operation_audit_insert",
    "trg_member_update_state_machine",
    "trg_episode_insert",
    "trg_effect_insert",
    "trg_effect_close",
    "trg_effect_action_append",
    "trg_runtime_status_insert",
    "trg_runtime_status_update",
}


def _between(data: bytes, begin: bytes, end: bytes) -> bytes:
    if data.count(begin) != 1 or data.count(end) != 1:
        raise AssertionError("marker cardinality drift")
    return data.split(begin, 1)[1].split(end, 1)[0]


def _plan_sql() -> bytes:
    return _between(
        PLAN.read_bytes(),
        b"<!-- canonical-registration-sql:begin -->\n```sql\n",
        b"```\n<!-- canonical-registration-sql:end -->",
    )


def _plan_leaf_groups() -> dict[str, tuple[str, ...]]:
    raw = _between(
        PLAN.read_bytes(),
        b"<!-- registration-leaf-manifest:begin -->\n```text\n",
        b"```\n<!-- registration-leaf-manifest:end -->",
    ).decode("utf-8")
    groups: dict[str, tuple[str, ...]] = {}
    for line in raw.splitlines():
        trigger, leaves = line.split("=", 1)
        groups[trigger] = tuple(leaves.split(";"))
    return groups


class RegistrationSchemaTest(unittest.TestCase):
    def test_production_sql_is_exact_frozen_extraction(self) -> None:
        expected = _plan_sql()
        actual = registration_schema.canonical_sql_bytes()
        self.assertEqual(actual, expected)
        self.assertTrue(actual.endswith(b";\n"))
        self.assertNotIn(b"--", actual)
        self.assertEqual(hashlib.sha256(actual).hexdigest(), EXPECTED_SCHEMA_HASH)
        self.assertEqual(registration_schema.SCHEMA_SHA256, EXPECTED_SCHEMA_HASH)

    def test_exact_schema_inventory(self) -> None:
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.executescript(registration_schema.canonical_sql_text())
        rows = connection.execute(
            "SELECT type,name FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        tables = {name for kind, name in rows if kind == "table"}
        triggers = {name for kind, name in rows if kind == "trigger"}
        views = {name for kind, name in rows if kind == "view"}
        indexes = {name for kind, name in rows if kind == "index"}
        self.assertEqual(tables, EXPECTED_TABLES)
        self.assertEqual(triggers, EXPECTED_TRIGGERS)
        self.assertEqual(views, set())
        self.assertEqual(indexes, set())
        self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_exact_generated_leaf_manifest(self) -> None:
        expected = _plan_leaf_groups()
        self.assertEqual(registration_schema.LEAF_GROUPS, expected)
        observed = {
            f"{trigger}|{leaf.replace('@', '|')}"
            for trigger, leaves in expected.items()
            for leaf in leaves
        }
        self.assertEqual(registration_schema.LEAF_IDS, frozenset(observed))
        self.assertEqual(len(observed), 97)
        self.assertNotIn("A30", registration_schema.ACCEPTANCE_IDS)
        self.assertNotIn("A31", registration_schema.ACCEPTANCE_IDS)
        self.assertEqual(
            registration_schema.ACCEPTANCE_IDS,
            tuple(
                [f"A{i:02d}" for i in range(1, 30)]
                + ["A32"]
            ),
        )

    def test_exact_hash_preimage_manifest_and_backlink_exclusions(self) -> None:
        raw = _between(
            PLAN.read_bytes(),
            b"<!-- registration-hash-preimages:begin -->\n```text\n",
            b"```\n<!-- registration-hash-preimages:end -->",
        ).decode("utf-8")
        observed = {}
        for line in raw.splitlines():
            name, domain, columns = line.split("|")
            observed[name] = (domain, tuple(columns.split(",")))
        actual = {
            name: (preimage.domain, preimage.columns)
            for name, preimage in registration_hashes.PREIMAGES.items()
        }
        self.assertEqual(actual, observed)
        self.assertEqual(
            registration_hashes.BACKLINK_EXCLUSIONS["operation"],
            {"operation_envelope_hash"},
        )
        for relation, exclusions in registration_hashes.BACKLINK_EXCLUSIONS.items():
            with self.subTest(relation=relation):
                self.assertTrue(exclusions)
                self.assertTrue(
                    all(
                        field.endswith("_hash")
                        or field.endswith("_id")
                        or field.endswith("_seq")
                        for field in exclusions
                    )
                )

    def test_closed_semantic_budget_and_forbidden_objects(self) -> None:
        sql = registration_schema.canonical_sql_text()

        def values(column: str) -> set[str]:
            matches = re.findall(
                rf"(?<![A-Za-z0-9_]){column} IN\(([^)]+)\)",
                sql,
            )
            self.assertTrue(matches, column)
            return {
                token.strip().strip("'")
                for match in matches
                for token in match.split(",")
            }

        self.assertEqual(len(values("mode")), 4)
        self.assertEqual(len(values("phase")), 3)
        self.assertEqual(len(values("outcome_kind")), 3)
        self.assertEqual(len(values("operation_class")), 3)
        self.assertEqual(len(values("operation_kind")), 24)
        self.assertEqual(len(values("reason_code")), 26)
        self.assertNotIn("member_version", sql)
        self.assertNotIn("admission_epoch", sql)
        for forbidden in (
            "registration_request",
            "registration_archive",
            "registration_notice",
            "registration_proof",
            "registration_membership",
            "registration_alert",
            "registration_outbox",
            "registration_rescue",
            "registration_gc",
            "registration_current_pointer",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(f"CREATE TABLE {forbidden}", sql)


if __name__ == "__main__":
    unittest.main()
