#!/usr/bin/env python3
"""Isolated, manifest-first launcher for an immutable registration bundle."""

from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import platform
import sqlite3
import stat
import sys
from pathlib import Path


_CONFIG_FIELDS = {
    "schema",
    "bundle_generation",
    "interpreter_path",
    "external_interpreter_hash",
    "interpreter_capability_hash",
    "import_manifest_hash",
    "entry_module",
    "isolated_flags",
}
_MANIFEST_FIELDS = {"schema", "entry_modules", "records"}
_RECORD_FIELDS = {"path", "role", "mode", "size", "sha256"}
_HEX = frozenset("0123456789abcdef")


class LegacyRuntimeRefusal(ValueError):
    """Config-v1/external-interpreter authority is historical only."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _canonical(raw: bytes) -> dict:
    if (
        not isinstance(raw, bytes)
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\0" in raw
    ):
        raise ValueError("authority file framing is invalid")
    value = json.loads(
        raw[:-1].decode("utf-8", "strict"),
        object_pairs_hook=_pairs,
        parse_constant=lambda item: (_ for _ in ()).throw(
            ValueError(item)
        ),
    )
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if not isinstance(value, dict) or encoded != raw:
        raise ValueError("authority file is not canonical")
    return value


def _read_regular(path: Path, *, mode: int, limit: int) -> bytes:
    before = path.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_nlink != 1
        or not 0 <= before.st_size <= limit
    ):
        raise ValueError("bundle file identity is unsafe")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise ValueError("bundle file changed while opening")
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(raw) > limit
            or (
                opened.st_dev,
                opened.st_ino,
                opened.st_mode,
                opened.st_uid,
                opened.st_nlink,
                opened.st_size,
                opened.st_mtime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
            )
        ):
            raise ValueError("bundle file changed while reading")
        return raw
    finally:
        os.close(descriptor)


def _hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _relative(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\0" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("manifest path is invalid")
    return value


def _validate_interpreter_runtime(interpreter: Path) -> None:
    before = interpreter.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid not in {0, os.geteuid()}
        or before.st_nlink != 1
        or before.st_mode & stat.S_IXUSR == 0
        or before.st_mode & 0o022
    ):
        raise ValueError("signed interpreter file is unsafe")
    descriptor = os.open(
        interpreter,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        visible = interpreter.lstat()
        identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_gid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
        )
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_gid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        ) or identity != (
            visible.st_dev,
            visible.st_ino,
            visible.st_mode,
            visible.st_uid,
            visible.st_gid,
            visible.st_nlink,
            visible.st_size,
            visible.st_mtime_ns,
        ):
            raise ValueError("signed interpreter identity changed")
    finally:
        os.close(descriptor)
    if (
        platform.system() != "Darwin"
        or sys.implementation.name != "cpython"
        or sys.version_info < (3, 12)
        or sqlite3.sqlite_version_info < (3, 51, 3)
        or not hasattr(sqlite3.Connection, "setconfig")
        or not hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE")
        or not hasattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE")
        or not hasattr(os, "O_NOFOLLOW")
    ):
        raise ValueError("signed interpreter capability is unsupported")


class _BundleImportGuard(importlib.abc.MetaPathFinder):
    def __init__(self, root: Path, allowed: frozenset[Path]) -> None:
        self.root = root
        self.allowed = allowed

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None:
            return None
        candidates = []
        if spec.origin and spec.origin not in {"built-in", "frozen"}:
            candidates.append(Path(spec.origin))
        if spec.submodule_search_locations:
            candidates.extend(
                Path(item) / "__init__.py"
                for item in spec.submodule_search_locations
            )
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(self.root)
            except ValueError:
                continue
            if resolved not in self.allowed:
                raise ImportError(
                    f"unmanifested product import refused: {fullname}"
                )
        return None


def _prepare(config_path: Path) -> tuple[str, Path]:
    # V7 may parse legacy bytes only far enough to classify them. It never
    # accepts config-v1 as private-runtime authority and never imports through
    # the historical external interpreter path.
    raise LegacyRuntimeRefusal(
        "external-interpreter/config-v1 authority is not executable under v7"
    )
    if (
        not config_path.is_absolute()
        or os.path.normpath(str(config_path)) != str(config_path)
        or os.path.realpath(config_path) != str(config_path)
        or config_path.name != "runtime-config.json"
    ):
        raise ValueError("launcher config path is not canonical")
    config_raw = _read_regular(config_path, mode=0o600, limit=65_536)
    config = _canonical(config_raw)
    if (
        set(config) != _CONFIG_FIELDS
        or config["schema"] != "awa-registration-launcher-config/v1"
        or config["isolated_flags"] != ["-I", "-S", "-B"]
        or not all(
            _hex64(config[field])
            for field in (
                "external_interpreter_hash",
                "interpreter_capability_hash",
                "import_manifest_hash",
            )
        )
    ):
        raise ValueError("launcher config is not exact")
    interpreter = Path(config["interpreter_path"])
    if (
        not interpreter.is_absolute()
        or os.path.realpath(interpreter) != str(interpreter)
        or Path(sys.executable).resolve() != interpreter
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.dont_write_bytecode
    ):
        raise ValueError("launcher interpreter/flags are not signed")
    _validate_interpreter_runtime(interpreter)
    root = config_path.parent.resolve(strict=True)
    manifest_path = root / "import-manifest.json"
    manifest_raw = _read_regular(
        manifest_path, mode=0o644, limit=8 * 1024 * 1024
    )
    manifest = _canonical(manifest_raw)
    if (
        set(manifest) != _MANIFEST_FIELDS
        or manifest["schema"] != "awa-registration-import-manifest/v1"
        or not isinstance(manifest["entry_modules"], list)
        or not isinstance(manifest["records"], list)
        or config["entry_module"] not in manifest["entry_modules"]
    ):
        raise ValueError("import manifest is not exact")
    manifest_digest = hashlib.sha256(
        b"awa-registration-import-manifest/v1\0" + manifest_raw[:-1]
    ).hexdigest()
    if manifest_digest != config["import_manifest_hash"]:
        raise ValueError("import manifest hash mismatch")
    allowed = []
    prior = None
    for record in manifest["records"]:
        if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
            raise ValueError("import-manifest record is not exact")
        relative = _relative(record["path"])
        encoded = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if prior is not None and encoded <= prior:
            raise ValueError("import-manifest records are not JCS sorted")
        prior = encoded
        if record["role"] not in {"PACKAGE_INITIALIZER", "MODULE"}:
            raise ValueError("import-manifest role is invalid")
        if not all(
            isinstance(record[field], str)
            and record[field].isascii()
            and record[field].isdecimal()
            for field in ("mode", "size")
        ) or not _hex64(record["sha256"]):
            raise ValueError("import-manifest metadata is invalid")
        path = root / relative
        raw = _read_regular(
            path,
            mode=int(record["mode"]),
            limit=8 * 1024 * 1024,
        )
        if (
            len(raw) != int(record["size"])
            or hashlib.sha256(raw).hexdigest() != record["sha256"]
        ):
            raise ValueError("manifested runtime bytes drifted")
        allowed.append(path.resolve(strict=True))
    sanitized = []
    for item in sys.path:
        if not item:
            continue
        try:
            resolved = Path(item).resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root)
        except ValueError:
            sanitized.append(item)
    sys.path[:] = [str(root), *sanitized]
    sys.meta_path.insert(
        0, _BundleImportGuard(root, frozenset(allowed))
    )
    os.environ["AWA_REGISTRATION_BUNDLE_ROOT"] = str(root)
    for hostile in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
    ):
        os.environ.pop(hostile, None)
    return str(config["entry_module"]), root


def _load_bootstrap_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "kernel/bin/awa-registration-bootstrap.py"
    )
    name = "_awa_registration_platform_bootstrap"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("platform bootstrap authority is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


_BOOTSTRAP = _load_bootstrap_module()
ProtocolRefusal = _BOOTSTRAP.ProtocolRefusal
SpawnIntent = _BOOTSTRAP.SpawnIntent
InMemoryIntentStore = _BOOTSTRAP.InMemoryIntentStore
FilesystemIntentStore = _BOOTSTRAP.FilesystemIntentStore
FakeProcessObserver = _BOOTSTRAP.FakeProcessObserver
IntentReconciler = _BOOTSTRAP.IntentReconciler
ReconcileDecision = _BOOTSTRAP.ReconcileDecision
SPAWN_PHASES = _BOOTSTRAP.SPAWN_PHASES
CONFIRMED_INERT_MESSAGE = _BOOTSTRAP.CONFIRMED_INERT_MESSAGE
AMBIGUOUS_RESIDUE_MESSAGE = _BOOTSTRAP.AMBIGUOUS_RESIDUE_MESSAGE
pidversion = _BOOTSTRAP.pidversion
boot_identity = _BOOTSTRAP.boot_identity


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) != 2 or values[1] not in {
        "admission",
        "receiver",
        "startup",
        "tick",
    }:
        return 2
    try:
        _prepare(Path(values[0]))
    except LegacyRuntimeRefusal:
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
