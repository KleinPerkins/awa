"""Body C stable wrapper routing to the exact active receiver projection."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine import registration_projection


ROOT = Path(__file__).resolve().parents[2]


class RegistrationReceiverRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(
            prefix="awa-registration-receiver."
        )
        self.root = Path(self.tmp.name).resolve()
        self.receiver = self.root / "receivers/candidate/receiver"
        self.receiver.parent.mkdir(parents=True, mode=0o700)
        self.receiver.write_text(
            "#!/bin/sh\n"
            "route=$1\n"
            "payload=$(cat)\n"
            "printf '{\"route\":\"%s\",\"payload\":%s}\\n' "
            "\"$route\" \"${payload:-null}\"\n",
            encoding="utf-8",
        )
        self.receiver.chmod(0o700)
        base = registration_projection.DirectReceipt.vector_r1()
        self.receipt = registration_projection.DirectReceipt.from_mapping(
            {
                **base.to_mapping(),
                "installed_file_hash": (
                    registration_projection.installed_file_hash(
                        self.receiver
                    )
                ),
            }
        )
        self.receipt_path = self.root / "direct-receipt.json"
        self.receipt_path.write_bytes(self.receipt.to_bytes())
        self.receipt_path.chmod(0o600)
        self.projection = self.root / "active-projection.json"
        self.projection.write_text(
            json.dumps(
                {
                    "schema": "awa-registration-receiver-projection/v1",
                    "candidate_digest": self.receipt.candidate_digest,
                    "receiver": str(self.receiver),
                    "installed_file_hash": self.receipt.installed_file_hash,
                    "direct_receipt_hash": self.receipt.digest,
                    "projection_file_generation": (
                        self.receipt.projection_file_generation
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="ascii",
        )
        self.projection.chmod(0o600)
        self.env = {
            **os.environ,
            "AWA_REGISTRATION_PROJECTION": str(self.projection),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, route: str, payload: bytes = b"null"):
        return subprocess.run(
            [
                "python3",
                "-B",
                "-m",
                "engine.registration_receiver",
                route,
            ],
            input=payload,
            capture_output=True,
            env=self.env,
            timeout=10,
        )

    def test_exact_projection_routes_admission_startup_and_tick(self) -> None:
        for route in ("admission", "startup", "tick"):
            with self.subTest(route=route):
                result = self._run(route, b'{"fixture":true}')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {"route": route, "payload": {"fixture": True}},
                )

    def test_missing_projection_and_tampered_receiver_fail_open_quietly(
        self,
    ) -> None:
        self.projection.unlink()
        missing = self._run("admission")
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(missing.stdout, b"")
        self.assertEqual(missing.stderr, b"")

        self.setUp_projection_only()
        self.receiver.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tampered = self._run("admission")
        self.assertNotEqual(tampered.returncode, 0)
        self.assertEqual(tampered.stdout, b"")
        self.assertEqual(tampered.stderr, b"")

    def setUp_projection_only(self) -> None:
        self.projection.write_text(
            json.dumps(
                {
                    "schema": "awa-registration-receiver-projection/v1",
                    "candidate_digest": self.receipt.candidate_digest,
                    "receiver": str(self.receiver),
                    "installed_file_hash": self.receipt.installed_file_hash,
                    "direct_receipt_hash": self.receipt.digest,
                    "projection_file_generation": (
                        self.receipt.projection_file_generation
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="ascii",
        )
        self.projection.chmod(0o600)

    def test_unknown_route_is_refused_without_exec(self) -> None:
        result = self._run("repair")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
