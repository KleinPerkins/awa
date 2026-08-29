"""K0: clean_receipt/v1 + active_root/v1 are frozen ADDITIVE-WITHIN AWA contract v1 (no v2),
and `clean --bundle` stays contract-compatible within v1.

Proves the contract DECLARES both new schema blocks with the exact vocabularies the kernel
emits, that the declared receipt required_keys are a subset of what awa_roots actually writes
(contract <-> code lock), that --bundle remains a frozen `clean` flag, and that the wired
freeze checker (kernel/checks/awa-contract-freeze.sh) passes end-to-end.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

from .helpers import EngineTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT = _REPO_ROOT / "contracts" / "awa-contract.v1.json"
_FREEZE = _REPO_ROOT / "kernel" / "checks" / "awa-contract-freeze.sh"
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

    def test_still_v1_no_v2(self) -> None:
        self.assertEqual(self.contract["version"], 1)
        self.assertFalse((_REPO_ROOT / "contracts" / "awa-contract.v2.json").exists(),
                         "K0/K1 is additive-within-v1; there must be NO v2 contract")

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

    def test_freeze_checker_passes(self) -> None:
        """Retained direct integration path after the Makefile duplicate is removed."""
        env = os.environ.copy()
        env["AWA_HOME"] = str(_REPO_ROOT)
        r = subprocess.run(["/bin/bash", str(_FREEZE)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("clean_receipt/v1 declared", r.stdout)
        self.assertIn("active_root/v1 declared", r.stdout)
        self.assertIn("awa-contract-freeze: OK", r.stdout)


if __name__ == "__main__":
    import unittest
    unittest.main()
