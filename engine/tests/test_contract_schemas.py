"""Frozen v1 behavior plus the exact v7 private-runtime successor overlay.

V1 remains byte-identical. V2 replaces only registration runtime entry while
the clean-receipt/active-root v1 behaviors remain contract-compatible.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from .helpers import EngineTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT = _REPO_ROOT / "contracts" / "awa-contract.v1.json"
_ROOTS_PY = _REPO_ROOT / "kernel" / "lib" / "awa_roots.py"


def _load_awa_roots():
    spec = importlib.util.spec_from_file_location("awa_roots_contract", _ROOTS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AR = _load_awa_roots()


class ContractSchemasTest(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.contract = json.loads(_CONTRACT.read_text(encoding="utf-8"))

    def test_v1_preserved_and_v2_successor_contracts_are_exact(self) -> None:
        self.assertEqual(self.contract["version"], 1)
        expected = {
            "awa-contract.v1.json":
                "408e271e9f55269d276e6d34e2aa3bb2bbc072fea3b6c8a841ede1912978c4d9",
            "awa-contract.v2.json":
                "db0a007ec7b0b8829fa721ff2b1835c1a9d783d5e151d2dda5d1bcaae85b2b0a",
            "awa-registration-admin-audit.v1.json":
                "a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a",
            "awa-registration-owner-signers.v1":
                "9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e",
            "awa-registration-owner-signers.v2":
                "690c6c7f7f4f12705763520a52eb61181bd5afe7914a5729cc7d4d4abdfa7ff3",
            "awa-registration-platform-bootstrap.v1.json":
                "4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c",
            "awa-registration-private-runtime.v1.json":
                "f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321",
            "awa-registration-privileged-envelope.v1.json":
                "7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034",
        }
        for name, digest in expected.items():
            with self.subTest(name=name):
                raw = (_REPO_ROOT / "contracts" / name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
                if name.endswith(".json") and name != "awa-contract.v1.json":
                    value = json.loads(raw)
                    self.assertEqual(
                        raw,
                        json.dumps(
                            value,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                            allow_nan=False,
                        ).encode("utf-8") + b"\n",
                    )
        v2 = json.loads(
            (_REPO_ROOT / "contracts/awa-contract.v2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(v2["schema"], "awa-contract/v2")
        self.assertEqual(v2["successor_of"], "awa-contract/v1")
        self.assertEqual(v2["registration_runtime"], "PROTECTED_PRIVATE")
        self.assertTrue(v2["private_runtime_required"])

    def test_clean_receipt_block(self) -> None:
        cr = self.contract["clean_receipt"]
        self.assertEqual(cr["schema"], "clean_receipt/v1")
        self.assertEqual(set(cr["disposition_values"]), {"removed", "refused", "error"})
        self.assertEqual(set(cr["flags_keys"]), {"bundle", "force", "delete_branch"})
        self.assertIn("WITHIN v1", cr["bundle_rule"])
        self.assertTrue(cr["required_keys"])
        for k in ("ignored_files_are_child_state", "unknown_evidence_blocks",
                  "every_terminal_path_rule"):
            self.assertIn(k, cr)

    def test_active_root_block(self) -> None:
        ar = self.contract["active_root"]
        self.assertEqual(ar["schema"], "active_root/v1")
        self.assertEqual(set(ar["disposition_values"]),
                         {"active", "stale", "dead", "untracked", "absent"})
        self.assertIn("source of truth", ar["canonical_disposition"].lower())
        self.assertIn("removal_rule", ar)
        # locked decision: NO OS lock / macOS immutable flag for active worktrees (K0/K1)
        self.assertIn("no_os_lock", ar)
        self.assertRegex(ar["no_os_lock"].lower(), r"not.*(os lock|immutable)")

    def test_bundle_is_frozen_clean_flag(self) -> None:
        flags = [f.lstrip("-") for f in self.contract["cli"]["flags"]["clean"]]
        self.assertIn("bundle", flags, "--bundle must remain a frozen clean flag (v1 compat)")
        self.assertIn("clean", self.contract["cli"]["verbs"])

    def test_declared_receipt_keys_subset_of_emitted(self) -> None:
        """Contract<->code lock: every declared clean_receipt required key is actually emitted."""
        dest = AR.write_receipt(disposition="refused", reason="contract_probe", path="/x")
        emitted = json.loads(Path(dest).read_text(encoding="utf-8"))
        for k in self.contract["clean_receipt"]["required_keys"]:
            self.assertIn(k, emitted, f"contract requires '{k}' but the receipt does not emit it")

    def test_declared_active_root_keys_subset_of_emitted(self) -> None:
        rec = AR.heartbeat(str(self.data_home))
        for k in self.contract["active_root"]["required_keys"]:
            self.assertIn(k, rec, f"contract requires '{k}' but the heartbeat does not emit it")

    def test_install_check_is_single_pre_pr_freeze_owner(self) -> None:
        """Executable freeze integration belongs only to install --check."""
        source = Path(__file__).read_text(encoding="utf-8")
        imported = {
            alias.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse({"os", "subprocess"} & imported)
        install = (_REPO_ROOT / "install.sh").read_text(encoding="utf-8")
        makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        source_command = (
            'AWA_HOME="$SRC_ROOT" /bin/bash '
            '"$SRC_ROOT/kernel/checks/awa-contract-freeze.sh"'
        )
        self.assertEqual(install.count(source_command), 1)
        verify_body = makefile.split("verify:", 1)[1].split(
            "verify-docs:", 1
        )[0]
        install_check_lines = [
            line.strip()
            for line in verify_body.splitlines()
            if "install.sh --check" in line
        ]
        self.assertEqual(
            install_check_lines,
            ["bash ./install.sh --check; \\"],
            "install --check must remain a single Bash-mediated pre-PR freeze owner",
        )


if __name__ == "__main__":
    import unittest
    unittest.main()
