"""V7 deterministic private-runtime source-lock and synthetic build tests."""

from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import os
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_LOCK = ROOT / "build/private-runtime/sources.lock.json"
MANIFEST_TOOL = ROOT / "build/private-runtime/manifest.py"
BUILD_SCRIPT = ROOT / "build/private-runtime/build.sh"


def _load_manifest_tool():
    spec = importlib.util.spec_from_file_location(
        "awa_private_runtime_manifest", MANIFEST_TOOL
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("private-runtime manifest tool is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceLockTest(unittest.TestCase):
    def test_source_lock_is_exact_jcs_lf(self) -> None:
        raw = SOURCE_LOCK.read_bytes()
        self.assertEqual(len(raw), 3654)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72",
        )
        value = json.loads(raw)
        self.assertEqual(
            raw,
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n",
        )
        self.assertEqual(value["python_version"], "3.14.8")
        self.assertEqual(value["sqlite_version"], "3.53.1")
        self.assertEqual(value["openssl_version"], "3.5.9")
        self.assertEqual(
            value["attestation_predicate_type"],
            "https://slsa.dev/provenance/v1",
        )
        self.assertEqual(
            value["attestation_selection_rule"],
            "EXACTLY_ONE_MATCHING_SLSA_PROVENANCE_V1",
        )
        self.assertEqual(
            value["attestation_rejected_predicate_types"],
            ["https://in-toto.io/attestation/release/v0.2"],
        )

    def test_source_lock_validator_rejects_every_bound_input_drift(self) -> None:
        tool = _load_manifest_tool()
        source = tool.read_source_lock(SOURCE_LOCK)
        for field in (
            "artifact_name",
            "artifact_sha256",
            "artifact_size",
            "artifact_url",
            "attestation_bundle_jcs_lf_sha256",
            "attestation_predicate_type",
            "attestation_workflow_sha",
            "python_json_sha256",
            "sha256sums_sha256",
            "upstream_release_commit",
        ):
            with self.subTest(field=field):
                changed = dict(source)
                value = changed[field]
                changed[field] = (
                    value + "x" if isinstance(value, str) else value + 1
                )
                with self.assertRaises(ValueError):
                    tool.validate_source_lock(changed)


class SyntheticManifestTest(unittest.TestCase):
    def test_secure_extractor_and_archive_are_deterministic_on_bounded_fixture(
        self,
    ) -> None:
        tool = _load_manifest_tool()
        with tempfile.TemporaryDirectory(
            prefix="awa-private-runtime-archive."
        ) as raw:
            root = Path(raw)
            archive = root / "fixture.tar.gz"
            with tarfile.open(archive, "w:gz") as handle:
                info = tarfile.TarInfo("python/bin/python3")
                info.mode = 0o755
                info.size = 7
                handle.addfile(info, io.BytesIO(b"python\n"))
                license_info = tarfile.TarInfo("python/LICENSE")
                license_info.mode = 0o644
                license_info.size = 8
                handle.addfile(license_info, io.BytesIO(b"license\n"))
            extracted = root / "extracted"
            self.assertEqual(
                tool.extract_regular_archive(archive, extracted),
                ("python/LICENSE", "python/bin/python3"),
            )
            normalized = root / "normalized"
            macho = tool._normalise_private_app(extracted, normalized)
            self.assertEqual(macho, frozenset())
            first = tool.deterministic_archive(normalized)
            second = tool.deterministic_archive(normalized)
            self.assertEqual(first, second)
            self.assertTrue(
                (normalized / "Python.app/Contents/MacOS/Python").is_file()
            )
            manifest = tool.build_manifest(
                normalized,
                source_lock_sha256="1" * 64,
                normalizer_source_sha256="2" * 64,
                signing_recipe_source_sha256="3" * 64,
            )
            licenses = tool.deterministic_license_archive(
                normalized, manifest
            )
            self.assertEqual(licenses, tool.deterministic_license_archive(
                normalized, manifest
            ))
            self.assertEqual(
                tool.build_spdx(manifest, tool.manifest_digest(manifest))[
                    "spdxVersion"
                ],
                "SPDX-2.3",
            )

            linked = root / "linked.tar.gz"
            with tarfile.open(linked, "w:gz") as handle:
                info = tarfile.TarInfo("python/bin/python3")
                info.type = tarfile.SYMTYPE
                info.linkname = "python3.14"
                handle.addfile(info)
            with self.assertRaises(ValueError):
                tool.extract_regular_archive(linked, root / "linked-output")

    def test_manifest_records_are_bytewise_sorted_and_framed(self) -> None:
        tool = _load_manifest_tool()
        with tempfile.TemporaryDirectory(
            prefix="awa-private-runtime-manifest."
        ) as raw:
            root = Path(raw)
            (root / "z.txt").write_bytes(b"z\n")
            (root / "z.txt").chmod(0o444)
            (root / "a").mkdir()
            (root / "a/a.txt").write_bytes(b"a\n")
            (root / "a/a.txt").chmod(0o444)
            (root / "bin").mkdir()
            executable = root / "bin/python"
            executable.write_bytes(b"synthetic python\n")
            executable.chmod(0o555)
            manifest = tool.build_manifest(
                root,
                source_lock_sha256="1" * 64,
                normalizer_source_sha256="2" * 64,
                signing_recipe_source_sha256="3" * 64,
                macho_paths=frozenset({"bin/python"}),
            )
        records = manifest["records"]
        self.assertEqual(
            [record["path"] for record in records],
            ["a/a.txt", "bin/python", "z.txt"],
        )
        self.assertEqual(
            records[1],
            {
                "path": "bin/python",
                "mode": "555",
                "size": "17",
                "sha256": hashlib.sha256(b"synthetic python\n").hexdigest(),
                "macho": True,
            },
        )
        framed = b"".join(
            tool.manifest_record_bytes(record) for record in records
        )
        self.assertEqual(
            manifest["record_framing_digest"],
            hashlib.sha256(framed).hexdigest(),
        )
        self.assertEqual(
            tool.manifest_digest(manifest),
            hashlib.sha256(
                b"awa-private-runtime-manifest/v1\0"
                + tool.canonical_bytes(manifest)
            ).hexdigest(),
        )

    def test_normalizer_rejects_links_collisions_and_escape_members(self) -> None:
        tool = _load_manifest_tool()
        with self.assertRaises(ValueError):
            tool.validate_archive_members(
                (
                    {"path": "../escape", "kind": "file"},
                    {"path": "ok", "kind": "file"},
                )
            )
        with self.assertRaises(ValueError):
            tool.validate_archive_members(
                (
                    {"path": "A", "kind": "file"},
                    {"path": "a", "kind": "file"},
                )
            )
        with self.assertRaises(ValueError):
            tool.validate_archive_members(
                ({"path": "link", "kind": "symlink"},)
            )
        with tempfile.TemporaryDirectory(
            prefix="awa-private-runtime-links."
        ) as raw:
            root = Path(raw)
            target = root / "target"
            target.write_bytes(b"x")
            os.link(target, root / "hard")
            with self.assertRaises(ValueError):
                tool.build_manifest(
                    root,
                    source_lock_sha256="1" * 64,
                    normalizer_source_sha256="2" * 64,
                    signing_recipe_source_sha256="3" * 64,
                )

    def test_two_synthetic_builds_are_byte_identical_without_real_archive(
        self,
    ) -> None:
        tool = _load_manifest_tool()
        with tempfile.TemporaryDirectory(
            prefix="awa-private-runtime-fixture."
        ) as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "LICENSE").write_text("synthetic\n", encoding="utf-8")
            (source / "bin").mkdir()
            python = source / "bin/python"
            python.write_bytes(b"synthetic-runtime\n")
            python.chmod(0o555)
            result = tool.build_synthetic_fixture(
                source,
                root / "work",
                source_lock_sha256="1" * 64,
            )
            self.assertTrue(result["equal"])
            self.assertEqual(
                result["build_a"]["manifest_digest"],
                result["build_b"]["manifest_digest"],
            )
            self.assertEqual(
                result["build_a"]["tree_digest"],
                result["build_b"]["tree_digest"],
            )
            for build in ("build_a", "build_b"):
                output = Path(result[build]["root"])
                self.assertTrue(output.is_relative_to(root))
                self.assertEqual(
                    stat.S_IMODE((output / "bin/python").stat().st_mode),
                    0o555,
                )
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--synthetic-fixture", script)
        self.assertIn("AWA_PRIVATE_RUNTIME_QUALIFICATION_GO", script)
        self.assertNotIn("curl |", script)

    def test_darwin_empty_private_directory_requires_link_count_two(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="awa-private-runtime-empty."
        ) as raw:
            private = Path(raw) / "private"
            private.mkdir(mode=0o700)
            private.chmod(0o700)
            metadata = private.stat()
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o700)
            self.assertEqual(tuple(private.iterdir()), ())
            self.assertEqual(metadata.st_nlink, 2)

        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        guard = script.split(
            "require_empty_private_directory() {", 1
        )[1].split("\n}\n\nlock_value()", 1)[0]
        self.assertIn(
            """[ "$(/usr/bin/stat -f '%Lp:%l' "$path")" = "700:2" ]""",
            guard,
        )
        self.assertNotIn("700:1", guard)


if __name__ == "__main__":
    unittest.main()
