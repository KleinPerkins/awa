"""modes.py — generalized verbs over the tool-owned per-repo modes file.

This is the single mode-management module (the "RECORD tooling" of the per-repo MODE
feature). It owns the machine-owned, source-tracked modes file (schema ``awa-modes/v1``)
that the zero-link classifier consumes via a host ``modes_file:`` pointer.

Design invariants:

  * ZERO-LINK — no org/host literals. The modes-file PATH is always supplied by the
    caller (host/policy), never hardcoded. ``resolve_modes_file()`` derives the path from
    a host policy's ``modes_file`` pointer; it never invents a location.
  * ATOMIC — every write goes to a temp file in the same directory and is swapped in with
    ``os.replace`` (crash-safe, never a half-written file).
  * VALIDATED — mode values are checked against ``MODE_VALUES`` (from the classifier), and
    invalid input is rejected with a clear ``ModesError``.
  * PATH-SCOPED — verbs touch ONLY the modes file. They never touch a repo, git, or a
    primary checkout.
  * ROUND-TRIP — the file is parsed with the SAME loader the classifier uses
    (``policy._parse_mini_yaml`` + ``policy._modes_from_data``) so writes are guaranteed to
    read back identically in ``PolicyConfig.load``.

Verbs (all return a JSON-serializable dict for the CLI/MCP surfaces):
  list / get / set / remove / repair / sync
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from .policy import (
    MODE_VALUES,
    _modes_from_data,
    _parse_mini_yaml,
)

SCHEMA = "awa-modes/v1"
# Default governing mode for eligible repos with no explicit entry, used ONLY when a file
# is (re)created without an existing/explicit default. "on" reproduces today's derived
# classification byte-for-byte (product back-compat). The host overlay may seed "ask_on".
DEFAULT_DEFAULT_MODE = "on"


class ModesError(ValueError):
    """Raised on invalid input (bad mode value, empty key, missing modes file)."""


# ---- path resolution (host-supplied; zero-link) -----------------------------
def resolve_modes_file(policy_path: str | Path) -> Optional[str]:
    """Resolve the modes-file path from a host policy's ``modes_file:`` pointer.

    The pointer is host-owned (may name a machine path); this module ships none of its own.
    Relative pointers resolve against the policy file's directory; ``~``/absolute honored.
    Returns None when the policy is absent or declares no ``modes_file``. The referenced
    file itself need not exist yet (``sync`` creates it).
    """
    p = Path(policy_path)
    if not p.exists():
        return None
    data = _parse_mini_yaml(p.read_text(encoding="utf-8"))
    mf = data.get("modes_file")
    if not mf:
        return None
    mf = os.path.expanduser(str(mf))
    if not os.path.isabs(mf):
        mf = str(p.resolve().parent / mf)
    return mf


# ---- low-level read/write ---------------------------------------------------
def _read(path: str | Path) -> tuple[dict, Optional[str], Optional[str], bool]:
    """Read the modes file with the classifier's own loader.

    Returns (modes, default_mode, schema, exists). ``modes`` values and ``default_mode``
    are case-normalized by ``_modes_from_data``; ``default_mode``/``schema`` are None when
    absent so callers can distinguish "unset" from a value.
    """
    p = Path(path)
    if not p.exists():
        return {}, None, None, False
    data = _parse_mini_yaml(p.read_text(encoding="utf-8"))
    modes, default_mode = _modes_from_data(data)
    schema = data.get("schema")
    schema = str(schema) if schema is not None else None
    return modes, default_mode, schema, True


def _serialize(modes: dict, default_mode: str) -> str:
    lines = [f"schema: {SCHEMA}", f"default_mode: {default_mode}"]
    if modes:
        lines.append("modes:")
        for key, val in modes.items():
            lines.append(f"  {key}: {val}")
    else:
        lines.append("modes: {}")
    return "\n".join(lines) + "\n"


def _write_atomic(path: str | Path, modes: dict, default_mode: str) -> None:
    """Atomically (temp file + ``os.replace``) write the modes file. Never leaves a
    half-written file: a crash mid-write leaves the previous file intact."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = _serialize(modes, default_mode)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".worktree-modes.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, str(p))
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def _validate_mode(mode) -> str:
    m = str(mode).strip().lower()
    if m not in MODE_VALUES:
        raise ModesError(
            f"invalid mode {mode!r}; must be one of: {', '.join(MODE_VALUES)}"
        )
    return m


def _preserved_default(existing: Optional[str]) -> str:
    """Keep the file's existing default_mode when valid; else fall back safely."""
    if existing in MODE_VALUES:
        return existing  # type: ignore[return-value]
    return DEFAULT_DEFAULT_MODE


# ---- verbs ------------------------------------------------------------------
def list_modes(path: str | Path) -> dict:
    """List every explicit entry + the governing default_mode (read-only)."""
    modes, dm, schema, exists = _read(path)
    return {
        "action": "list",
        "path": str(path),
        "exists": exists,
        "schema": schema,
        "default_mode": dm if exists else None,
        "modes": modes,
    }


def get_mode(path: str | Path, rel: str) -> dict:
    """Return the explicit entry for ``rel`` (exact key), or "" when unset (read-only)."""
    if not rel or not str(rel).strip():
        raise ModesError("rel (repo path/glob) must be non-empty")
    rel = str(rel).strip()
    modes, dm, schema, exists = _read(path)
    return {
        "action": "get",
        "path": str(path),
        "rel": rel,
        "present": rel in modes,
        "mode": modes.get(rel, ""),
        "default_mode": dm,
    }


def set_mode(path: str | Path, rel: str, mode) -> dict:
    """Set (add or update) ``rel`` -> ``mode``. Validated + atomic; default_mode preserved."""
    if not rel or not str(rel).strip():
        raise ModesError("rel (repo path/glob) must be non-empty")
    rel = str(rel).strip()
    m = _validate_mode(mode)
    modes, dm, schema, exists = _read(path)
    default_mode = _preserved_default(dm)
    previous = modes.get(rel)
    modes[rel] = m
    _write_atomic(path, modes, default_mode)
    warning = None
    if m == "off":
        warning = ("set off disables AWA guard protection for this path "
                   "(operator intent)")
    return {
        "action": "set",
        "path": str(path),
        "rel": rel,
        "mode": m,
        "previous": previous,
        "default_mode": default_mode,
        "warning": warning,
    }


def remove_mode(path: str | Path, rel: str) -> dict:
    """Remove ``rel``'s explicit entry. No-op (removed=False) when absent; atomic."""
    if not rel or not str(rel).strip():
        raise ModesError("rel (repo path/glob) must be non-empty")
    rel = str(rel).strip()
    modes, dm, schema, exists = _read(path)
    default_mode = _preserved_default(dm)
    removed = rel in modes
    if removed:
        previous = modes.pop(rel)
        _write_atomic(path, modes, default_mode)
    else:
        previous = None
    return {
        "action": "remove",
        "path": str(path),
        "rel": rel,
        "removed": removed,
        "previous": previous,
        "default_mode": default_mode,
    }


def repair(path: str | Path) -> dict:
    """Rewrite/normalize the file: drop invalid mode values + empty keys, normalize
    default_mode, and report what changed. Idempotent."""
    modes, dm, schema, exists = _read(path)
    if not exists:
        raise ModesError(f"modes file does not exist: {path} (run `sync` first)")
    cleaned: dict = {}
    dropped: dict = {}
    for key, val in modes.items():
        k = str(key).strip()
        v = str(val).strip().lower()
        if not k:
            dropped[str(key)] = val
            continue
        if v in MODE_VALUES:
            cleaned[k] = v
        else:
            dropped[k] = val
    default_normalized = bool(dm is not None and dm not in MODE_VALUES)
    default_mode = dm if dm in MODE_VALUES else DEFAULT_DEFAULT_MODE
    _write_atomic(path, cleaned, default_mode)
    return {
        "action": "repair",
        "path": str(path),
        "modes": cleaned,
        "dropped": dropped,
        "default_mode": default_mode,
        "default_mode_normalized": default_normalized,
        "schema": SCHEMA,
    }


def sync(path: str | Path, default_mode: Optional[str] = None) -> dict:
    """Ensure the modes file exists with schema ``awa-modes/v1`` + a default_mode.

    Idempotent and non-destructive: an existing valid default_mode is PRESERVED (the
    ``default_mode`` argument only seeds a brand-new / previously-invalid default);
    existing entries are preserved (normalized casing). Never overwrites operator entries.
    """
    modes, dm, schema, exists = _read(path)
    if dm in MODE_VALUES:
        resolved_default = dm  # preserve existing operator choice
    elif default_mode is not None:
        resolved_default = _validate_mode(default_mode)  # seed value (validated)
    else:
        resolved_default = DEFAULT_DEFAULT_MODE
    norm_modes: dict = {}
    for key, val in modes.items():
        k = str(key).strip()
        if k:
            norm_modes[k] = str(val).strip().lower()
    _write_atomic(path, norm_modes, resolved_default)
    return {
        "action": "sync",
        "path": str(path),
        "created": not exists,
        "exists": True,
        "schema": SCHEMA,
        "default_mode": resolved_default,
        "modes": norm_modes,
    }
