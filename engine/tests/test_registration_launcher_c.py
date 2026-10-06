"""Body C isolated launcher and hostile import-environment tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from engine import registration_projection


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "engine/registration_launcher.py"


class IsolatedLauncherTest(unittest.TestCase):
    def _bundle(
        self, root: Path, *, hostile_import: bool = False
    ) -> tuple[Path, Path]:
        engine = root / "engine"
        engine.mkdir(parents=True, mode=0o700, exist_ok=True)
        package = b""
        host = (
            b"from . import extra\n"
            if hostile_import
            else (
                b"import json,os,sys\n"
                b"def main(argv):\n"
                b" print(json.dumps({'route':argv[0],"
                b"'bundle':os.environ.get("
                b"'AWA_REGISTRATION_BUNDLE_ROOT'),"
                b"'path0':sys.path[0]},sort_keys=True))\n"
                b" return 0\n"
            )
        )
        (engine / "__init__.py").write_bytes(package)
        (engine / "registration_host.py").write_bytes(host)
        (engine / "extra.py").write_bytes(b"VALUE = 'shadow'\n")
        for path in engine.iterdir():
            path.chmod(0o644)
        manifest = registration_projection.ImportManifest(
            schema="awa-registration-import-manifest/v1",
            entry_modules=("engine.registration_host",),
            records=(
                registration_projection.ImportRecord(
                    "engine/__init__.py",
                    "PACKAGE_INITIALIZER",
                    str(0o644),
                    str(len(package)),
                    hashlib.sha256(package).hexdigest(),
                ),
                registration_projection.ImportRecord(
                    "engine/registration_host.py",
                    "MODULE",
                    str(0o644),
                    str(len(host)),
                    hashlib.sha256(host).hexdigest(),
                ),
            ),
        )
        manifest_path = root / "import-manifest.json"
        manifest_path.write_bytes(manifest.to_bytes())
        manifest_path.chmod(0o644)
        interpreter = Path(sys.executable).resolve()
        config = registration_projection.LauncherConfig(
            schema="awa-registration-launcher-config/v1",
            bundle_generation="2",
            interpreter_path=str(interpreter),
            external_interpreter_hash="a" * 64,
            interpreter_capability_hash="b" * 64,
            import_manifest_hash=manifest.digest,
            entry_module="engine.registration_host",
            isolated_flags=("-I", "-S", "-B"),
        )
        config_path = root / "runtime-config.json"
        config_path.write_bytes(config.to_bytes())
        config_path.chmod(0o600)
        return interpreter, config_path

    def _run(
        self,
        interpreter: Path,
        config: Path,
        *,
        flags: tuple[str, ...] = ("-I", "-S", "-B"),
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        environment = {
            **os.environ,
            "PYTHONPATH": "/hostile/pythonpath",
            "PYTHONHOME": "/hostile/pythonhome",
            "PYTHONSTARTUP": "/hostile/startup.py",
            "PYTHONINSPECT": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # PYTHONHOME can prevent startup before isolated mode takes effect on
        # some builds; -I ignores it, while the negative no--I case removes it.
        if "-I" not in flags:
            environment.pop("PYTHONHOME")
        return subprocess.run(
            [
                str(interpreter),
                *flags,
                str(LAUNCHER),
                str(config),
                "tick",
            ],
            cwd=cwd,
            env=environment,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def test_legacy_external_config_refuses_before_product_import(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve() / "bundle"
            root.mkdir(mode=0o700)
            interpreter, config = self._bundle(root)
            shadow = root.parent / "shadow"
            (shadow / "engine").mkdir(parents=True)
            (shadow / "engine/__init__.py").write_bytes(b"")
            (shadow / "engine/registration_host.py").write_text(
                "raise RuntimeError('shadow imported')\n",
                encoding="utf-8",
            )
            result = self._run(
                interpreter, config, cwd=shadow
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b"")
            self.assertNotIn(
                str(root).encode("utf-8"),
                result.stderr,
            )

    def test_unmanifested_product_import_and_byte_drift_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve() / "bundle"
            root.mkdir(mode=0o700)
            interpreter, config = self._bundle(
                root, hostile_import=True
            )
            self.assertEqual(
                self._run(interpreter, config).returncode, 1
            )
            interpreter, config = self._bundle(root)
            (root / "engine/registration_host.py").write_bytes(b"drift")
            self.assertEqual(
                self._run(interpreter, config).returncode, 1
            )

    def test_legacy_config_refuses_with_or_without_isolated_flags(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve() / "bundle"
            root.mkdir(mode=0o700)
            interpreter, config = self._bundle(root)
            self.assertEqual(
                self._run(interpreter, config).returncode,
                1,
            )
            self.assertEqual(
                self._run(
                    interpreter,
                    config,
                    flags=("-S", "-B"),
                ).returncode,
                1,
            )


if __name__ == "__main__":
    unittest.main()
