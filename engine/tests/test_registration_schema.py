from __future__ import annotations

import hashlib
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import registration_hashes, registration_schema


ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "plans" / "native-entry-durable-registration-v3.md"
EXPECTED_SCHEMA_HASH = (
    "b97f02ef67d48886f917368fa420fda0c5dd5942441b23a190732e3cc45106c8"
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
    def test_sql_resource_is_loaded_through_retained_resource_authority(self) -> None:
        source = (ROOT / "engine" / "registration_schema.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from importlib import resources", source)
        self.assertIn(
            'resources.files("engine").joinpath("registration_schema.sql")',
            source,
        )
        self.assertNotIn(
            'Path(__file__).with_name("registration_schema.sql")', source
        )

    def test_production_sql_is_exact_frozen_extraction(self) -> None:
        source = _plan_sql()
        self.assertEqual(
            hashlib.sha256(source).hexdigest(),
            registration_schema.SCHEMA_V1_SHA256,
        )
        self.assertEqual(
            (ROOT / "engine" / "registration_schema.sql").read_bytes(),
            source,
        )
        actual = registration_schema.canonical_sql_bytes()
        self.assertTrue(actual.endswith(b";\n"))
        self.assertNotIn(b"--", actual)
        self.assertEqual(len(actual), 130_952)
        self.assertEqual(actual.count(b"\n"), 1_285)
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

    def test_fresh_schema_publication_classifies_both_sides_of_rename(self) -> None:
        for point, expected in (
            ("before_schema_statement:1", registration_schema.FreshSchemaState.ABSENT),
            ("after_schema_statement:1", registration_schema.FreshSchemaState.ABSENT),
            ("before_schema_commit", registration_schema.FreshSchemaState.ABSENT),
            ("after_schema_commit", registration_schema.FreshSchemaState.ABSENT),
            ("before_schema_file_fsync", registration_schema.FreshSchemaState.ABSENT),
            ("after_schema_file_fsync", registration_schema.FreshSchemaState.ABSENT),
            ("before_schema_publish", registration_schema.FreshSchemaState.ABSENT),
            ("after_schema_publish", registration_schema.FreshSchemaState.COMPLETE),
            (
                "before_schema_parent_fsync",
                registration_schema.FreshSchemaState.COMPLETE,
            ),
            (
                "after_schema_parent_fsync",
                registration_schema.FreshSchemaState.COMPLETE,
            ),
            ("before_schema_reopen", registration_schema.FreshSchemaState.COMPLETE),
            ("after_schema_reopen", registration_schema.FreshSchemaState.COMPLETE),
        ):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "registration.db"

                def fault(observed: str) -> None:
                    if observed == point:
                        raise RuntimeError(point)

                with self.assertRaisesRegex(RuntimeError, point):
                    registration_schema.publish_fresh_schema(path, fault=fault)
                self.assertEqual(
                    registration_schema.classify_fresh_schema(path), expected
                )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            path.write_bytes(b"foreign")
            path.chmod(0o600)
            before = path.read_bytes()
            with self.assertRaises(
                registration_schema.FreshSchemaPublicationError
            ):
                registration_schema.publish_fresh_schema(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.UNAVAILABLE,
            )
        for suffix in ("-journal", "-wal", "-shm"):
            with self.subTest(residue=suffix), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "registration.db"
                residue = Path(f"{path}{suffix}")
                residue.write_bytes(b"residue")
                self.assertEqual(
                    registration_schema.classify_fresh_schema(path),
                    registration_schema.FreshSchemaState.UNAVAILABLE,
                )
                with self.assertRaises(
                    registration_schema.FreshSchemaPublicationError
                ):
                    registration_schema.publish_fresh_schema(path)
                self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            registration_schema.publish_fresh_schema(path)
            residue = path.with_name(
                ".registration.db.awa-schema-" + "ab" * 32 + ".tmp-wal"
            )
            residue.write_bytes(b"unknown")
            self.assertTrue(
                registration_schema.has_fresh_schema_residue(path)
            )
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.UNAVAILABLE,
            )

    def test_fresh_schema_publication_binds_candidate_and_destination_identity(
        self,
    ) -> None:
        operation_id = "a1" * 32
        candidate_name = (
            f".registration.db.awa-schema-{operation_id}.tmp"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            candidate = path.with_name(candidate_name)
            candidate.write_bytes(b"deterministic residue")
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.UNAVAILABLE,
            )
            with self.assertRaises(
                registration_schema.FreshSchemaPublicationError
            ):
                registration_schema.publish_fresh_schema(
                    path, operation_id=operation_id
                )
            self.assertFalse(path.exists())
            self.assertEqual(candidate.read_bytes(), b"deterministic residue")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            candidate = path.with_name(candidate_name)
            displaced = path.with_name("displaced-candidate")

            def substitute_candidate(point: str) -> None:
                if point == "before_schema_publish":
                    candidate.rename(displaced)
                    candidate.write_bytes(b"replacement")
                    candidate.chmod(0o600)

            with self.assertRaisesRegex(
                registration_schema.FreshSchemaPublicationError,
                "candidate binding changed",
            ):
                registration_schema.publish_fresh_schema(
                    path,
                    fault=substitute_candidate,
                    operation_id=operation_id,
                )
            self.assertFalse(path.exists())
            self.assertEqual(candidate.read_bytes(), b"replacement")
            self.assertTrue(displaced.exists())
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.UNAVAILABLE,
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            displaced = path.with_name("displaced-destination")

            def substitute_destination(point: str) -> None:
                if point == "after_schema_publish":
                    path.rename(displaced)
                    path.write_bytes(b"replacement")
                    path.chmod(0o600)

            with self.assertRaisesRegex(
                registration_schema.FreshSchemaPublicationError,
                "candidate binding changed",
            ):
                registration_schema.publish_fresh_schema(
                    path,
                    fault=substitute_destination,
                    operation_id=operation_id,
                )
            self.assertEqual(path.read_bytes(), b"replacement")
            self.assertTrue(displaced.exists())
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.UNAVAILABLE,
            )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"

            def create_destination_conflict(point: str) -> None:
                if point == "before_schema_publish":
                    path.write_bytes(b"conflict")
                    path.chmod(0o600)

            with self.assertRaisesRegex(
                registration_schema.FreshSchemaPublicationError,
                "no-replace publication conflict",
            ):
                registration_schema.publish_fresh_schema(
                    path,
                    fault=create_destination_conflict,
                    operation_id=operation_id,
                )
            self.assertEqual(path.read_bytes(), b"conflict")
            self.assertFalse(path.with_name(candidate_name).exists())

    def test_fresh_schema_preserves_primary_across_rollback_and_close(self) -> None:
        class FailingCleanupConnection:
            def __init__(self, connection: sqlite3.Connection) -> None:
                self.connection = connection

            def __getattr__(self, name: str) -> object:
                return getattr(self.connection, name)

            def execute(self, statement: str, *args: object) -> object:
                if statement == "ROLLBACK":
                    self.connection.execute(statement)
                    raise OSError("rollback cleanup fault")
                return self.connection.execute(statement, *args)

            def close(self) -> None:
                self.connection.close()
                raise OSError("close cleanup fault")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            real_connect = sqlite3.connect
            primary = RuntimeError("primary statement fault")

            def connect(*args: object, **kwargs: object) -> object:
                connection = real_connect(*args, **kwargs)
                if str(args[0]) != ":memory:":
                    return FailingCleanupConnection(connection)
                return connection

            def fault(point: str) -> None:
                if point == "after_schema_statement:1":
                    raise primary

            with mock.patch.object(
                registration_schema.sqlite3, "connect", side_effect=connect
            ):
                with self.assertRaises(RuntimeError) as caught:
                    registration_schema.publish_fresh_schema(path, fault=fault)
            self.assertIs(caught.exception, primary)
            notes = getattr(caught.exception, "__notes__", ())
            self.assertTrue(any("rollback failed secondarily" in n for n in notes))
            self.assertTrue(
                any("connection close failed secondarily" in n for n in notes)
            )
            self.assertTrue(any("classified ABSENT" in n for n in notes))
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.ABSENT,
            )
            self.assertFalse(registration_schema.has_fresh_schema_residue(path))

    def test_fresh_schema_native_full_and_ioerr_are_classified(self) -> None:
        with self.subTest(error="SQLITE_FULL"), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"
            real_connect = sqlite3.connect

            def constrained_connect(
                *args: object, **kwargs: object
            ) -> sqlite3.Connection:
                connection = real_connect(*args, **kwargs)
                if str(args[0]) != ":memory:":
                    connection.execute("PRAGMA page_size=512")
                    connection.execute("PRAGMA max_page_count=1")
                return connection

            with mock.patch.object(
                registration_schema.sqlite3,
                "connect",
                side_effect=constrained_connect,
            ):
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    registration_schema.publish_fresh_schema(path)
            self.assertEqual(
                caught.exception.sqlite_errorcode, sqlite3.SQLITE_FULL
            )
            self.assertTrue(
                any(
                    "classified ABSENT" in note
                    for note in getattr(caught.exception, "__notes__", ())
                )
            )
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.ABSENT,
            )
            self.assertFalse(registration_schema.has_fresh_schema_residue(path))

        with self.subTest(error="SQLITE_IOERR"), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.db"

            def fault(point: str) -> None:
                if point == "before_schema_commit":
                    journal = next(
                        path.parent.glob(
                            f".{path.name}.awa-schema-*.tmp-journal"
                        )
                    )
                    journal.unlink()

            with self.assertRaises(sqlite3.OperationalError) as caught:
                registration_schema.publish_fresh_schema(path, fault=fault)
            self.assertEqual(
                caught.exception.sqlite_errorcode & 0xFF,
                sqlite3.SQLITE_IOERR,
            )
            self.assertTrue(
                any(
                    "classified ABSENT" in note
                    for note in getattr(caught.exception, "__notes__", ())
                )
            )
            self.assertEqual(
                registration_schema.classify_fresh_schema(path),
                registration_schema.FreshSchemaState.ABSENT,
            )
            self.assertFalse(registration_schema.has_fresh_schema_residue(path))

    def test_exact_generated_leaf_manifest(self) -> None:
        expected = _plan_leaf_groups()
        self.assertEqual(registration_schema.LEAF_GROUPS, expected)
        manifest = "".join(
            f"{trigger}={';'.join(leaves)}\n"
            for trigger, leaves in expected.items()
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(manifest).hexdigest(),
            "a4ad3ebae560cebbfa56667a9dd999be0fa9e88545ef7007f8e66d9be035aba7",
        )
        observed = {
            f"{trigger}|{leaf.replace('@', '|')}"
            for trigger, leaves in expected.items()
            for leaf in leaves
        }
        sorted_leaves = "".join(f"{leaf}\n" for leaf in sorted(observed)).encode()
        self.assertEqual(
            hashlib.sha256(sorted_leaves).hexdigest(),
            "497d16a334fcee798b8b720f845358977882af93dfdaff94b7fa1213a5fb7001",
        )
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
