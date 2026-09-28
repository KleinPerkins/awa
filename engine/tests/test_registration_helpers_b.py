from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine import registration_admission, registration_runtime


ACTION = registration_runtime.ActionWork(
    effect_id="aa" * 32,
    ordinal=1,
    kind="PUBLISH_EFFECT_PROOF",
    action_hash="bb" * 32,
    postcondition_hash="cc" * 32,
)


class ProofFileHelperTest(unittest.TestCase):
    def test_absent_apply_exact_is_immutable_private_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve() / "proofs"
            parent.mkdir(mode=0o700)
            path = parent / "effect.json"
            helper = registration_runtime.ProofFileHelper(
                path, b'{"schema":"proof-fixture/v1"}'
            )
            self.assertEqual(helper.inspect(ACTION).kind, "ABSENT")
            helper.apply(ACTION, None)  # type: ignore[arg-type]
            observed = helper.inspect(ACTION)
            self.assertEqual(observed.kind, "EXACT")
            metadata = path.stat()
            self.assertEqual(metadata.st_mode & 0o777, 0o600)
            self.assertEqual(metadata.st_nlink, 1)
            self.assertEqual(
                sorted(item.name for item in parent.iterdir()),
                ["effect.json"],
            )

    def test_existing_divergent_proof_is_conflict_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve() / "proofs"
            parent.mkdir(mode=0o700)
            path = parent / "effect.json"
            path.write_bytes(b"different")
            path.chmod(0o600)
            before = path.read_bytes()
            helper = registration_runtime.ProofFileHelper(
                path, b'{"schema":"proof-fixture/v1"}'
            )
            self.assertEqual(helper.inspect(ACTION).kind, "CONFLICT")
            with self.assertRaises(FileExistsError):
                helper.apply(ACTION, None)  # type: ignore[arg-type]
            self.assertEqual(path.read_bytes(), before)

    def test_proof_bytes_reject_prohibited_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve() / "proofs"
            parent.mkdir(mode=0o700)
            with self.assertRaises(ValueError):
                registration_runtime.ProofFileHelper(
                    parent / "effect.json",
                    b'{"prompt":"PRIVATE"}',
                )


class FinalBasisHelperTest(unittest.TestCase):
    def test_final_basis_is_exact_conflict_or_unavailable_without_write(self) -> None:
        event = registration_admission.RegistrationEvent(
            ("/fixture/root",),
            "conversation-1",
            "generation-1",
            "cursor-hook/v1",
            "beforeShellExecution",
        )

        class Collector:
            def __init__(self, value):
                self.value = value

            def collect(self, _event):
                if isinstance(self.value, Exception):
                    raise self.value
                return self.value

        sample = registration_admission.BasisSample(
            "/fixture/root",
            "01" * 32,
            "02" * 32,
            ACTION.postcondition_hash,
            "03" * 32,
            "04" * 32,
            "05" * 32,
            "06" * 32,
            "07" * 32,
        )
        self.assertEqual(
            registration_runtime.FinalBasisHelper(
                Collector(sample), event
            ).inspect(ACTION).kind,
            "EXACT",
        )
        divergent = registration_admission.BasisSample(
            **{**sample.__dict__, "current_basis_hash": "ff" * 32}
        )
        self.assertEqual(
            registration_runtime.FinalBasisHelper(
                Collector(divergent), event
            ).inspect(ACTION).kind,
            "CONFLICT",
        )
        self.assertEqual(
            registration_runtime.FinalBasisHelper(
                Collector(RuntimeError("unavailable")), event
            ).inspect(ACTION).kind,
            "UNAVAILABLE",
        )


if __name__ == "__main__":
    unittest.main()
