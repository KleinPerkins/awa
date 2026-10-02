from __future__ import annotations

import json
import unittest

from engine import registration_jcs


H0 = "00" * 32
H1 = "11" * 32
H2 = "22" * 32
H3 = "33" * 32


def _action_relation() -> dict:
    return {
        "actions": [
            {
                "ordinal": "1",
                "kind": "PUBLISH_EFFECT_PROOF",
                "action_hash": H0,
                "postcondition_hash": H1,
            },
            {
                "ordinal": "2",
                "kind": "CONVERGE_LEGACY_LEASE",
                "action_hash": H1,
                "postcondition_hash": H2,
            },
            {
                "ordinal": "3",
                "kind": "CONVERGE_LEGACY_LIFECYCLE",
                "action_hash": H2,
                "postcondition_hash": H3,
            },
            {
                "ordinal": "4",
                "kind": "COLLECT_FINAL_BASIS",
                "action_hash": H3,
                "postcondition_hash": H0,
            },
        ],
        "external_growth_reservation_bytes": "4096",
        "outcome_reservation_bytes": "4096",
        "successor_reservation_bytes": "4096",
    }


class RegistrationJcsTest(unittest.TestCase):
    def test_action_plan_is_relationally_derived_and_byte_canonical(self) -> None:
        relation = _action_relation()
        raw = registration_jcs.encode_blob("action_plan", relation)
        parsed = registration_jcs.validate_blob("action_plan", raw, relation)
        self.assertEqual(parsed["schema"], "awa-registration-action-plan/v1")
        self.assertEqual(raw, registration_jcs.canonical_bytes(parsed))

        noncanonical = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
        self.assertNotEqual(noncanonical, raw)
        with self.assertRaises(registration_jcs.JcsError):
            registration_jcs.validate_blob("action_plan", noncanonical, relation)

    def test_closed_parser_rejects_duplicate_unknown_float_integer_and_unicode(self) -> None:
        relation = _action_relation()
        raw = registration_jcs.encode_blob("action_plan", relation)
        cases = [
            raw[:-1] + b',"schema":"awa-registration-action-plan/v1"}',
            raw[:-1] + b',"unknown":"x"}',
            raw.replace(b'"4096"', b"1.5", 1),
            raw.replace(b'"4096"', b"4096", 1),
            raw.replace(b'"4096"', b'"\\ud800"', 1),
        ]
        for case in cases:
            with self.subTest(case=case[-80:]):
                with self.assertRaises(registration_jcs.JcsError):
                    registration_jcs.validate_blob("action_plan", case, relation)

    def test_prohibited_keys_and_sentinels_reject_at_depth(self) -> None:
        relation = _action_relation()
        prohibited_keys = registration_jcs.PROHIBITED_KEYS
        prohibited_values = registration_jcs.PROHIBITED_SENTINELS
        for key in prohibited_keys:
            mutated = _action_relation()
            mutated["actions"][2][key] = "x"
            raw = registration_jcs.canonical_bytes(
                {"schema": "awa-registration-action-plan/v1", **mutated},
                enforce_privacy=False,
            )
            with self.subTest(key=key):
                with self.assertRaises(registration_jcs.JcsError):
                    registration_jcs.validate_blob("action_plan", raw, relation)
        for sentinel in prohibited_values:
            mutated = _action_relation()
            mutated["actions"][1]["postcondition_hash"] = sentinel
            raw = registration_jcs.canonical_bytes(
                {"schema": "awa-registration-action-plan/v1", **mutated},
                enforce_privacy=False,
            )
            with self.subTest(sentinel=sentinel):
                with self.assertRaises(registration_jcs.JcsError):
                    registration_jcs.validate_blob("action_plan", raw, relation)

    def test_row_hash_has_exact_columns_and_excludes_backlinks(self) -> None:
        columns = ("effect_id", "member_id", "member_epoch")
        row = {"effect_id": H0, "member_id": H1, "member_epoch": 7}
        first = registration_jcs.row_hash("awa-test-row/v1", columns, row)
        self.assertEqual(
            first,
            registration_jcs.row_hash(
                "awa-test-row/v1",
                columns,
                {**row, "write_operation_id": H2},
            ),
        )
        self.assertNotEqual(
            first,
            registration_jcs.row_hash(
                "awa-test-row/v1", columns, {**row, "member_epoch": 8}
            ),
        )
        with self.assertRaises(registration_jcs.JcsError):
            registration_jcs.row_hash(
                "awa-test-row/v1",
                columns,
                {"effect_id": H0, "member_id": H1},
            )
        for boolean in (False, True):
            with self.subTest(boolean=boolean), self.assertRaises(
                registration_jcs.JcsError
            ):
                registration_jcs.row_hash(
                    "awa-test-row/v1",
                    columns,
                    {**row, "member_epoch": boolean},
                )

    def test_size_depth_and_node_limits_are_closed(self) -> None:
        with self.assertRaises(registration_jcs.JcsError):
            registration_jcs.parse_canonical(b'"' + b"x" * 65_536 + b'"')
        nested: object = "x"
        for _ in range(registration_jcs.MAX_DEPTH + 1):
            nested = [nested]
        with self.assertRaises(registration_jcs.JcsError):
            registration_jcs.canonical_bytes(nested)
        with self.assertRaises(registration_jcs.JcsError):
            registration_jcs.canonical_bytes(
                ["x"] * (registration_jcs.MAX_NODES + 1)
            )


if __name__ == "__main__":
    unittest.main()
