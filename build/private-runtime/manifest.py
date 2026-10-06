#!/usr/bin/env python3
"""Deterministic private-runtime manifest and bounded synthetic fixtures.

This module deliberately performs no network access and has no privileged
write path.  The separately gated shell driver owns real qualification input
collection; ordinary verification exercises only small caller-provided trees.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


SOURCE_LOCK_SHA256 = (
    "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
)
SOURCE_LOCK_SIZE = 3654
SOURCE_LOCK_SCHEMA = "awa-private-runtime-source-lock/v1"
MANIFEST_SCHEMA = "awa-private-runtime-manifest/v1"
MANIFEST_DOMAIN = b"awa-private-runtime-manifest/v1\0"
TREE_DOMAIN = b"awa-private-runtime-synthetic-tree/v1\0"
ALLOWED_FILE_MODES = {0o444, 0o555}
CODESIGN_PATH = Path("/usr/bin/codesign")
CODESIGN_SHA256 = (
    "3635f18db517033a4786ea7ddb0acc1801e642eaf6171e208e24cb9a1922f518"
)
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
}


class DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


def _object_pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def canonical_bytes(value: object) -> bytes:
    """Return this repository's bounded JCS subset without its terminal LF."""

    def validate(item: object, path: str = "$") -> None:
        if item is None or isinstance(item, (str, bool)):
            return
        if type(item) is int:
            if item < 0 or item > (1 << 64) - 1:
                raise ValueError(f"{path}: integer outside unsigned 64-bit")
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError(f"{path}: object key is not text")
            for key, child in item.items():
                validate(child, f"{path}.{key}")
            return
        raise ValueError(f"{path}: unsupported JCS value {type(item).__name__}")

    validate(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_lf_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authority_digest(domain: str, value: Mapping[str, object]) -> str:
    return _sha256(
        domain.encode("ascii") + b"\0" + canonical_lf_bytes(dict(value))
    )


def parse_canonical_lf(raw: bytes) -> object:
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise ValueError("authority must have exactly one terminal LF")
    if b"\r" in raw or b"\x00" in raw or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("authority contains forbidden framing bytes")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_pairs_no_duplicates,
            parse_float=lambda _: (_ for _ in ()).throw(
                ValueError("floats are forbidden")
            ),
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("non-finite numbers are forbidden")
            ),
        )
    except UnicodeDecodeError as exc:
        raise ValueError("authority is not UTF-8") from exc
    if canonical_lf_bytes(value) != raw:
        raise ValueError("authority is not canonical JCS+LF")
    return value


def validate_source_lock(value: Mapping[str, object]) -> dict:
    candidate = dict(value)
    if candidate.get("schema") != SOURCE_LOCK_SCHEMA:
        raise ValueError("source-lock schema mismatch")
    raw = canonical_lf_bytes(candidate)
    if len(raw) != SOURCE_LOCK_SIZE or _sha256(raw) != SOURCE_LOCK_SHA256:
        raise ValueError("source lock differs from accepted v7 bytes")
    return candidate


def read_source_lock(path: os.PathLike[str] | str) -> dict:
    raw = Path(path).read_bytes()
    if len(raw) != SOURCE_LOCK_SIZE or _sha256(raw) != SOURCE_LOCK_SHA256:
        raise ValueError("source-lock bytes/hash mismatch")
    value = parse_canonical_lf(raw)
    if not isinstance(value, dict):
        raise ValueError("source lock must be a JSON object")
    return validate_source_lock(value)


def _verify_exact_file(
    path: Path, *, expected_size: int, expected_sha256: str
) -> bytes:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size != expected_size
    ):
        raise ValueError(f"qualification input metadata mismatch: {path.name}")
    raw = path.read_bytes()
    if (
        len(raw) != expected_size
        or _sha256(raw) != expected_sha256
        or path.lstat().st_mtime_ns != metadata.st_mtime_ns
    ):
        raise ValueError(f"qualification input content mismatch: {path.name}")
    return raw


def _bundle_candidates(value: object) -> Iterable[dict]:
    if isinstance(value, dict):
        if (
            value.get("mediaType")
            == "application/vnd.dev.sigstore.bundle.v0.3+json"
            and isinstance(value.get("dsseEnvelope"), dict)
        ):
            yield value
        for child in value.values():
            yield from _bundle_candidates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _bundle_candidates(child)


def _select_attestation_bundle(raw: bytes, source_lock: Mapping[str, object]) -> dict:
    downloaded = json.loads(
        raw,
        object_pairs_hook=_object_pairs_no_duplicates,
        parse_float=lambda _: (_ for _ in ()).throw(
            ValueError("attestation floats are forbidden")
        ),
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("attestation constants are forbidden")
        ),
    )
    matches: list[dict] = []
    for bundle in _bundle_candidates(downloaded):
        envelope = bundle["dsseEnvelope"]
        try:
            payload = base64.b64decode(
                envelope["payload"], validate=True
            )
            statement = json.loads(
                payload,
                object_pairs_hook=_object_pairs_no_duplicates,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        subjects = statement.get("subject", [])
        subject_matches = [
            subject
            for subject in subjects
            if isinstance(subject, dict)
            and subject.get("name")
            == source_lock["attestation_subject_name"]
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha256")
            == source_lock["attestation_subject_sha256"]
        ]
        predicate = statement.get("predicate", {})
        build_definition = (
            predicate.get("buildDefinition", {})
            if isinstance(predicate, dict)
            else {}
        )
        if (
            envelope.get("payloadType")
            != source_lock["attestation_payload_type"]
            or len(payload) != source_lock["attestation_payload_size"]
            or _sha256(payload)
            != source_lock["attestation_payload_sha256"]
            or statement.get("predicateType")
            != source_lock["attestation_predicate_type"]
            or build_definition.get("buildType")
            != source_lock["attestation_build_type"]
            or len(subjects) != source_lock["attestation_subject_count"]
            or len(subject_matches) != 1
        ):
            continue
        canonical = canonical_lf_bytes(bundle)
        if (
            len(canonical)
            != source_lock["attestation_bundle_jcs_lf_size"]
            or _sha256(canonical)
            != source_lock["attestation_bundle_jcs_lf_sha256"]
        ):
            continue
        matches.append(bundle)
    if len(matches) != 1:
        raise ValueError("exactly one frozen SLSA-v1 attestation is required")
    return matches[0]


def verify_qualification_cache(
    cache: os.PathLike[str] | str,
    source_lock: Mapping[str, object],
) -> dict:
    root = Path(cache)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("qualification cache must be a real directory")
    expected_names = {
        source_lock["artifact_name"],
        source_lock["full_build_archive_name"],
        source_lock["sha256sums_name"],
        "attestation-bundle.json",
    }
    observed_names = {path.name for path in root.iterdir()}
    if observed_names != expected_names:
        raise ValueError("qualification cache inventory mismatch")
    artifact = _verify_exact_file(
        root / str(source_lock["artifact_name"]),
        expected_size=int(source_lock["artifact_size"]),
        expected_sha256=str(source_lock["artifact_sha256"]),
    )
    full_archive = _verify_exact_file(
        root / str(source_lock["full_build_archive_name"]),
        expected_size=int(source_lock["full_build_archive_size"]),
        expected_sha256=str(source_lock["full_build_archive_sha256"]),
    )
    sums = _verify_exact_file(
        root / str(source_lock["sha256sums_name"]),
        expected_size=int(source_lock["sha256sums_size"]),
        expected_sha256=str(source_lock["sha256sums_sha256"]),
    )
    line = str(source_lock["sha256sums_artifact_line"]).encode("ascii")
    if sums.splitlines().count(line) != 1:
        raise ValueError("SHA256SUMS exact artifact line mismatch")
    attestation_raw = (root / "attestation-bundle.json").read_bytes()
    bundle = _select_attestation_bundle(attestation_raw, source_lock)
    python_json = subprocess.run(
        [
            "/usr/bin/tar",
            "-xOf",
            str(root / str(source_lock["full_build_archive_name"])),
            str(source_lock["python_json_path"]),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        timeout=60,
    )
    if (
        python_json.returncode != 0
        or len(python_json.stdout) != source_lock["python_json_size"]
        or _sha256(python_json.stdout)
        != source_lock["python_json_sha256"]
    ):
        raise ValueError("full-build PYTHON.json mismatch")
    return {
        "artifact_sha256": _sha256(artifact),
        "full_build_archive_sha256": _sha256(full_archive),
        "attestation_bundle_sha256": _sha256(canonical_lf_bytes(bundle)),
        "python_json_sha256": _sha256(python_json.stdout),
        "sha256sums_sha256": _sha256(sums),
    }


def _validate_relative_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("archive path must be nonempty text")
    if "\x00" in raw or "\\" in raw:
        raise ValueError(f"unsafe archive path: {raw!r}")
    try:
        encoded = raw.encode("utf-8")
        encoded.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("archive path must be UTF-8") from exc
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive path: {raw!r}")
    if str(path) != raw:
        raise ValueError(f"non-normalized archive path: {raw!r}")
    return raw


def validate_archive_members(
    members: Iterable[Mapping[str, object]],
) -> tuple[dict, ...]:
    accepted: list[dict] = []
    seen: set[bytes] = set()
    folded: set[str] = set()
    for member in members:
        path = _validate_relative_path(member.get("path"))  # type: ignore[arg-type]
        kind = member.get("kind")
        if kind not in {"file", "directory"}:
            raise ValueError(f"unsupported archive member kind: {kind!r}")
        encoded = path.encode("utf-8")
        case_key = path.casefold()
        if encoded in seen:
            raise ValueError(f"duplicate archive path: {path}")
        if case_key in folded:
            raise ValueError(f"case-colliding archive path: {path}")
        seen.add(encoded)
        folded.add(case_key)
        accepted.append({"path": path, "kind": kind})
    accepted.sort(key=lambda row: row["path"].encode("utf-8"))
    return tuple(accepted)


def manifest_record_bytes(record: Mapping[str, object]) -> bytes:
    expected = {"path", "mode", "size", "sha256", "macho"}
    if set(record) != expected:
        raise ValueError("manifest record field drift")
    path = _validate_relative_path(record["path"])  # type: ignore[arg-type]
    mode = record["mode"]
    size = record["size"]
    digest = record["sha256"]
    macho = record["macho"]
    if not isinstance(mode, str) or len(mode) != 3 or not mode.isdigit():
        raise ValueError("manifest mode must be three octal digits")
    if (
        not isinstance(size, str)
        or not size.isdigit()
        or (len(size) > 1 and size.startswith("0"))
    ):
        raise ValueError("manifest size must be canonical decimal text")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise ValueError("manifest sha256 must be lowercase 64-hex")
    if type(macho) is not bool:
        raise ValueError("manifest macho must be boolean")
    return (
        path.encode("utf-8")
        + b"\0"
        + mode.encode("ascii")
        + b"\0"
        + size.encode("ascii")
        + b"\0"
        + digest.encode("ascii")
        + b"\0"
        + (b"1" if macho else b"0")
        + b"\n"
    )


def _walk_regular_files(root: Path) -> list[tuple[str, Path]]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("manifest root must be a real directory")
    rows: list[tuple[str, Path]] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in list(dirnames):
            path = directory_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(
                metadata.st_mode
            ):
                raise ValueError(f"non-directory in directory set: {path}")
            if metadata.st_mode & 0o022:
                raise ValueError(f"writable directory refused: {path}")
        for name in filenames:
            path = directory_path / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"non-regular payload object: {path}")
            if metadata.st_nlink != 1:
                raise ValueError(f"payload link count is not one: {path}")
            relative = path.relative_to(root).as_posix()
            _validate_relative_path(relative)
            rows.append((relative, path))
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    paths = [{"path": path, "kind": "file"} for path, _ in rows]
    validate_archive_members(paths)
    return rows


def build_manifest(
    root: os.PathLike[str] | str,
    *,
    source_lock_sha256: str,
    normalizer_source_sha256: str,
    signing_recipe_source_sha256: str,
    macho_paths: frozenset[str] = frozenset(),
) -> dict:
    payload_root = Path(root)
    records: list[dict] = []
    for relative, path in _walk_regular_files(payload_root):
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if mode not in ALLOWED_FILE_MODES:
            raise ValueError(f"payload mode is not normalized: {relative}")
        content = path.read_bytes()
        if len(content) != metadata.st_size:
            raise ValueError(f"payload changed while reading: {relative}")
        post = path.lstat()
        if (
            post.st_dev,
            post.st_ino,
            post.st_size,
            post.st_mtime_ns,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ):
            raise ValueError(f"payload metadata changed while reading: {relative}")
        records.append(
            {
                "path": relative,
                "mode": format(mode, "03o"),
                "size": str(len(content)),
                "sha256": _sha256(content),
                "macho": relative in macho_paths,
            }
        )
    framing = b"".join(manifest_record_bytes(record) for record in records)
    return {
        "schema": MANIFEST_SCHEMA,
        "source_lock_sha256": source_lock_sha256,
        "normalizer_source_sha256": normalizer_source_sha256,
        "signing_recipe_source_sha256": signing_recipe_source_sha256,
        "record_framing_digest": _sha256(framing),
        "records": records,
    }


def manifest_digest(manifest: Mapping[str, object]) -> str:
    return _sha256(MANIFEST_DOMAIN + canonical_bytes(dict(manifest)))


def _copy_normalized(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"synthetic destination already exists: {destination}")
    source_rows = _walk_regular_files(source)
    destination.mkdir(parents=True, mode=0o755)
    for relative, source_path in source_rows:
        destination_path = destination / relative
        destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        mode = stat.S_IMODE(source_path.lstat().st_mode)
        normalized_mode = 0o555 if mode & 0o111 else 0o444
        content = source_path.read_bytes()
        with destination_path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        destination_path.chmod(normalized_mode)
        os.utime(destination_path, ns=(0, 0), follow_symlinks=False)
    for directory, _, _ in os.walk(destination, topdown=False):
        path = Path(directory)
        path.chmod(0o755)
        os.utime(path, ns=(0, 0), follow_symlinks=False)


def extract_regular_archive(
    archive: os.PathLike[str] | str,
    destination: os.PathLike[str] | str,
) -> tuple[str, ...]:
    """Extract a gzip tar with no links, special files, or path ambiguity."""

    archive_path = Path(archive)
    destination_path = Path(destination)
    destination_path.mkdir(mode=0o700, parents=False, exist_ok=False)
    accepted: list[dict[str, str]] = []
    with tarfile.open(archive_path, mode="r:gz") as handle:
        members = handle.getmembers()
        validate_archive_members(
            {
                "path": member.name.removesuffix("/"),
                "kind": "directory" if member.isdir() else "file",
            }
            for member in members
        )
        for member in members:
            name = member.name.removesuffix("/")
            _validate_relative_path(name)
            target = destination_path / name
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if (
                not member.isfile()
                or member.issym()
                or member.islnk()
                or member.devmajor
                or member.devminor
                or member.size < 0
                or member.size > 1 << 30
            ):
                raise ValueError(f"archive member type refused: {name}")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = handle.extractfile(member)
            if source is None:
                raise ValueError(f"archive member unreadable: {name}")
            with target.open("xb") as output:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(remaining, 65_536))
                    if not chunk:
                        raise ValueError(f"archive member truncated: {name}")
                    output.write(chunk)
                    remaining -= len(chunk)
                if source.read(1):
                    raise ValueError(f"archive member overflow: {name}")
                output.flush()
                os.fsync(output.fileno())
            target.chmod(0o700 if member.mode & 0o111 else 0o600)
            accepted.append({"path": name, "kind": "file"})
    for directory, _, _ in os.walk(destination_path, topdown=False):
        path = Path(directory)
        path.chmod(0o700)
        _fsync_directory(path)
    _fsync_directory(destination_path.parent)
    return tuple(
        item["path"]
        for item in sorted(accepted, key=lambda row: row["path"].encode())
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_macho(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(4) in MACHO_MAGICS


def _normalise_private_app(source_root: Path, destination: Path) -> frozenset[str]:
    if set(path.name for path in source_root.iterdir()) != {"python"}:
        raise ValueError("install-only archive top-level inventory mismatch")
    python_root = source_root / "python"
    contents = destination / "Python.app/Contents"
    contents.mkdir(parents=True, mode=0o755)
    rows = _walk_regular_files(python_root)
    executable_candidates = [
        row
        for row in rows
        if row[0] in {"bin/python3", "bin/python3.14"}
    ]
    if len(executable_candidates) != 1:
        raise ValueError("exact private Python executable is unavailable")
    for relative, source in rows:
        target = contents / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        raw = source.read_bytes()
        with target.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        target.chmod(0o555 if stat.S_IMODE(source.stat().st_mode) & 0o111 else 0o444)
        os.utime(target, ns=(0, 0), follow_symlinks=False)
    executable = contents / "MacOS/Python"
    executable.parent.mkdir(mode=0o755)
    shutil.copyfile(executable_candidates[0][1], executable)
    executable.chmod(0o555)
    os.utime(executable, ns=(0, 0), follow_symlinks=False)
    macho = frozenset(
        path.relative_to(destination).as_posix()
        for _, path in _walk_regular_files(destination)
        if _is_macho(path)
    )
    return macho


def _codesign_payload(root: Path, macho_paths: frozenset[str]) -> tuple[dict, ...]:
    codesign_raw = CODESIGN_PATH.read_bytes()
    if _sha256(codesign_raw) != CODESIGN_SHA256:
        raise ValueError("codesign tool hash differs from v7 toolchain")
    ordered = sorted(
        macho_paths,
        key=lambda value: (
            -len(PurePosixPath(value).parts),
            value.encode("utf-8"),
        ),
    )
    records: list[dict] = []
    for relative in ordered:
        path = root / relative
        subprocess.run(
            [str(CODESIGN_PATH), "--remove-signature", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=30,
        )
        identifier = "org.awa.runtime." + _sha256(relative.encode("utf-8"))
        signed = subprocess.run(
            [
                str(CODESIGN_PATH),
                "--force",
                "--sign",
                "-",
                "--timestamp=none",
                "--identifier",
                identifier,
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=30,
        )
        if signed.returncode != 0:
            raise ValueError(f"ad-hoc codesign failed: {relative}")
        observed = subprocess.run(
            [str(CODESIGN_PATH), "-d", "--verbose=4", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=30,
        )
        detail = observed.stdout + observed.stderr
        marker = b"CDHash="
        start = detail.find(marker)
        if observed.returncode != 0 or start < 0:
            raise ValueError(f"codesign verification failed: {relative}")
        digest = detail[start + len(marker) :].splitlines()[0].decode("ascii")
        if not digest or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"codesign CDHash malformed: {relative}")
        records.append({"object": relative, "digest": digest})
        path.chmod(0o555 if os.access(path, os.X_OK) else 0o444)
        os.utime(path, ns=(0, 0), follow_symlinks=False)
    records.sort(key=lambda row: row["object"].encode("utf-8"))
    return tuple(records)


def deterministic_archive(root: Path) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for relative, path in _walk_regular_files(root):
                metadata = path.stat()
                info = tarfile.TarInfo(relative)
                info.size = metadata.st_size
                info.mode = stat.S_IMODE(metadata.st_mode)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                with path.open("rb") as handle:
                    tar.addfile(info, handle)
    return output.getvalue()


def deterministic_license_archive(
    root: Path, manifest: Mapping[str, object]
) -> bytes:
    selected = [
        record
        for record in manifest["records"]  # type: ignore[index]
        if any(
            token in PurePosixPath(record["path"]).name.lower()  # type: ignore[index]
            for token in ("license", "copying", "notice")
        )
    ]
    if not selected:
        raise ValueError("private runtime contains no license records")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for record in selected:
            relative = record["path"]
            path = root / relative
            info = tarfile.TarInfo(relative)
            info.size = int(record["size"])
            info.mode = int(record["mode"], 8)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as handle:
                tar.addfile(info, handle)
    return output.getvalue()


def build_spdx(manifest: Mapping[str, object], manifest_sha256: str) -> dict:
    files = []
    for index, record in enumerate(manifest["records"]):  # type: ignore[index]
        files.append(
            {
                "SPDXID": f"SPDXRef-File-{index + 1}",
                "fileName": "./" + record["path"],
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": record["sha256"],
                    }
                ],
            }
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "AWA protected private runtime",
        "documentNamespace": "urn:awa:private-runtime:" + manifest_sha256,
        "files": files,
    }


def qualification_build(
    cache: os.PathLike[str] | str,
    work_root: os.PathLike[str] | str,
    source_lock: Mapping[str, object],
) -> dict:
    cache_path = Path(cache)
    work = Path(work_root)
    verify_qualification_cache(cache_path, source_lock)
    if work.exists():
        if work.is_symlink() or not work.is_dir() or any(work.iterdir()):
            raise ValueError("qualification work root must be empty")
    else:
        work.mkdir(mode=0o700)
    source = work / "source"
    extract_regular_archive(
        cache_path / str(source_lock["artifact_name"]), source
    )
    results: list[dict] = []
    for build_id in ("a", "b"):
        root = work / f"build-{build_id}"
        macho = _normalise_private_app(source, root)
        signatures = _codesign_payload(root, macho)
        manifest = build_manifest(
            root,
            source_lock_sha256=SOURCE_LOCK_SHA256,
            normalizer_source_sha256=_sha256(Path(__file__).read_bytes()),
            signing_recipe_source_sha256=_sha256(
                Path(__file__).with_name("build.sh").read_bytes()
            ),
            macho_paths=macho,
        )
        measurement_path = work / f"measurement-{build_id}.manifest.json"
        measurement_path.write_bytes(canonical_lf_bytes(manifest))
        measurement_path.chmod(0o600)
        private_python = root / "Python.app/Contents/MacOS/Python"
        bootstrap = (
            Path(__file__).resolve().parents[2]
            / "kernel/bin/awa-registration-bootstrap.py"
        )
        measured = subprocess.run(
            [
                str(private_python),
                "-I",
                "-S",
                "-B",
                str(bootstrap),
                "--measure-private-runtime",
                str(root),
                str(measurement_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=120,
        )
        if measured.returncode != 0:
            raise ValueError(
                "private runtime capability measurement failed: "
                + measured.stderr.decode("utf-8", "replace")[:512]
            )
        measurement = parse_canonical_lf(measured.stdout)
        if not isinstance(measurement, dict):
            raise ValueError("private runtime measurement is not an object")
        archive = deterministic_archive(root)
        licenses = deterministic_license_archive(root, manifest)
        sbom = build_spdx(manifest, manifest_digest(manifest))
        results.append(
            {
                "build_id": build_id,
                "root": str(root),
                "manifest": manifest,
                "manifest_digest": manifest_digest(manifest),
                "signature_inventory": list(signatures),
                "signature_inventory_digest": authority_digest(
                    "awa-private-runtime-signature-inventory/v1",
                    {"records": list(signatures)},
                ),
                "measurement": measurement,
                "licenses": licenses,
                "license_inventory_sha256": _sha256(licenses),
                "sbom": sbom,
                "sbom_sha256": _sha256(canonical_lf_bytes(sbom)),
                "archive_sha256": _sha256(archive),
                "archive_size": str(len(archive)),
                "archive": archive,
            }
        )
    comparable = (
        "manifest",
        "manifest_digest",
        "signature_inventory",
        "signature_inventory_digest",
        "measurement",
        "licenses",
        "license_inventory_sha256",
        "sbom",
        "sbom_sha256",
        "archive_sha256",
        "archive_size",
        "archive",
    )
    comparison_values = []
    for result in results:
        measurement = dict(result["measurement"])
        measurement.pop("private_executable_path", None)
        measurement.pop("private_executable_dev", None)
        measurement.pop("private_executable_ino", None)
        measurement["loaded_images"] = [
            value.replace(str(result["root"]), "<PRIVATE_RUNTIME_ROOT>")
            for value in measurement["loaded_images"]
        ]
        comparison_values.append(
            {
                field: result[field]
                for field in comparable
                if field != "measurement"
            }
            | {"measurement": measurement}
        )
    if comparison_values[0] != comparison_values[1]:
        raise ValueError("independent qualification builds differ")
    manifest_sha = results[0]["manifest_digest"]
    output = work / "output"
    output.mkdir(mode=0o700)
    manifest_path = output / f"awa-private-runtime-{manifest_sha}.manifest.json"
    archive_path = output / f"awa-private-runtime-{manifest_sha}.tar.gz"
    signature_path = (
        output
        / f"awa-private-runtime-{manifest_sha}.signature-inventory.json"
    )
    capability_path = (
        output / f"awa-private-runtime-{manifest_sha}.capability.json"
    )
    compile_options_path = (
        output
        / f"awa-private-runtime-{manifest_sha}.sqlite-compile-options.json"
    )
    sbom_path = output / f"awa-private-runtime-{manifest_sha}.sbom.spdx.json"
    licenses_path = (
        output / f"awa-private-runtime-{manifest_sha}.licenses.tar"
    )
    transcript_path = (
        output / f"awa-private-runtime-{manifest_sha}.build-transcript.jsonl"
    )
    manifest_path.write_bytes(canonical_lf_bytes(results[0]["manifest"]))
    archive_path.write_bytes(results[0]["archive"])
    signature_path.write_bytes(
        canonical_lf_bytes(
            {
                "schema": "awa-private-runtime-signature-inventory/v1",
                "records": results[0]["signature_inventory"],
            }
        )
    )
    capability_path.write_bytes(
        canonical_lf_bytes(results[0]["measurement"]["capability"])
    )
    compile_options_path.write_bytes(
        canonical_lf_bytes(results[0]["measurement"]["compile_options"])
    )
    sbom_path.write_bytes(canonical_lf_bytes(results[0]["sbom"]))
    licenses_path.write_bytes(results[0]["licenses"])
    transcript_rows = (
        {
            "schema": "awa-private-runtime-build-transcript-event/v1",
            "event": "SOURCE_LOCK_VERIFIED",
            "source_lock_sha256": SOURCE_LOCK_SHA256,
        },
        {
            "schema": "awa-private-runtime-build-transcript-event/v1",
            "event": "INDEPENDENT_BUILDS_EQUAL",
            "manifest_sha256": manifest_sha,
            "archive_sha256": results[0]["archive_sha256"],
            "signature_inventory_digest": results[0][
                "signature_inventory_digest"
            ],
            "capability_digest": results[0]["measurement"][
                "capability_digest"
            ],
        },
    )
    transcript_path.write_bytes(
        b"".join(canonical_lf_bytes(row) for row in transcript_rows)
    )
    for path in (
        manifest_path,
        archive_path,
        signature_path,
        capability_path,
        compile_options_path,
        sbom_path,
        licenses_path,
        transcript_path,
    ):
        path.chmod(0o600)
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    _fsync_directory(output)
    return {
        "schema": "awa-private-runtime-qualification-build/v1",
        "manifest_sha256": manifest_sha,
        "archive_sha256": results[0]["archive_sha256"],
        "archive_size": results[0]["archive_size"],
        "signature_inventory_digest": results[0][
            "signature_inventory_digest"
        ],
        "capability_digest": results[0]["measurement"][
            "capability_digest"
        ],
        "compile_options_digest": results[0]["measurement"][
            "compile_options_digest"
        ],
        "sbom_sha256": results[0]["sbom_sha256"],
        "license_inventory_sha256": results[0][
            "license_inventory_sha256"
        ],
        "build_transcript_sha256": _sha256(transcript_path.read_bytes()),
        "builds_equal": True,
        "output_files": sorted(
            (path.name for path in output.iterdir()),
            key=lambda value: value.encode("utf-8"),
        ),
    }


def _tree_digest(root: Path, manifest: Mapping[str, object]) -> str:
    framed = bytearray(TREE_DOMAIN)
    for record in manifest["records"]:  # type: ignore[index]
        framed.extend(manifest_record_bytes(record))
        framed.extend((root / record["path"]).read_bytes())  # type: ignore[index]
    return _sha256(bytes(framed))


def build_synthetic_fixture(
    source: os.PathLike[str] | str,
    work_root: os.PathLike[str] | str,
    *,
    source_lock_sha256: str = SOURCE_LOCK_SHA256,
) -> dict:
    """Normalize one bounded tree twice and compare every emitted authority."""

    source_path = Path(source)
    work_path = Path(work_root)
    work_path.mkdir(parents=True, exist_ok=False)
    normalizer_hash = _sha256(Path(__file__).read_bytes())
    recipe_path = Path(__file__).with_name("build.sh")
    recipe_hash = _sha256(
        recipe_path.read_bytes() if recipe_path.is_file() else b"synthetic-recipe"
    )
    outputs: dict[str, dict] = {}
    for build_id in ("a", "b"):
        destination = work_path / f"build-{build_id}"
        _copy_normalized(source_path, destination)
        manifest = build_manifest(
            destination,
            source_lock_sha256=source_lock_sha256,
            normalizer_source_sha256=normalizer_hash,
            signing_recipe_source_sha256=recipe_hash,
        )
        outputs[f"build_{build_id}"] = {
            "root": str(destination),
            "manifest": manifest,
            "manifest_digest": manifest_digest(manifest),
            "tree_digest": _tree_digest(destination, manifest),
        }
    outputs["equal"] = (
        outputs["build_a"]["manifest"] == outputs["build_b"]["manifest"]
        and outputs["build_a"]["tree_digest"]
        == outputs["build_b"]["tree_digest"]
    )
    if not outputs["equal"]:
        raise ValueError("synthetic private-runtime builds differ")
    return outputs


def _check(source_lock: Path) -> int:
    read_source_lock(source_lock)
    print(
        json.dumps(
            {
                "schema": "awa-private-runtime-build-check/v1",
                "source_lock_sha256": SOURCE_LOCK_SHA256,
                "source_lock_size": str(SOURCE_LOCK_SIZE),
                "valid": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-lock",
        type=Path,
        default=Path(__file__).with_name("sources.lock.json"),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--synthetic-fixture", nargs=2, metavar=("SOURCE", "WORK"))
    group.add_argument("--verify-qualification-cache", metavar="CACHE")
    group.add_argument(
        "--qualification-build", nargs=2, metavar=("CACHE", "WORK")
    )
    args = parser.parse_args(argv)
    source_lock = read_source_lock(args.source_lock)
    if args.check:
        return _check(args.source_lock)
    if args.synthetic_fixture:
        result = build_synthetic_fixture(
            args.synthetic_fixture[0],
            args.synthetic_fixture[1],
        )
    elif args.verify_qualification_cache:
        result = {
            "schema": "awa-private-runtime-qualification-cache/v1",
            **verify_qualification_cache(
                args.verify_qualification_cache, source_lock
            ),
        }
    else:
        result = qualification_build(
            args.qualification_build[0],
            args.qualification_build[1],
            source_lock,
        )
    print(canonical_lf_bytes(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
