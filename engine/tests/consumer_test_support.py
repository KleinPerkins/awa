"""Shared helpers for the AWA consumer (A0) test suite. NOT a test module itself."""

from __future__ import annotations

import importlib.util as _ilu
import json
import re as _re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSUMER = REPO_ROOT / "consumer"

# Router-artifact USAGE patterns (import/from/artifact-file/env/state-path) — matched as USAGE, NOT
# the bare word "router", so a module's own "router-OFF" / "no router installed" documentation prose
# stays legal. This is the ONE comprehensive list, reused by BOTH the structural contamination guard
# (kernel + engine) and the kernel-off matrix, so neither drifts into a narrow hardcoded file list.
ROUTER_USAGE_PATTERNS = [
    _re.compile(r"\bimport\s+\w*router", _re.I),
    _re.compile(r"\bfrom\s+\w*router\b", _re.I),
    _re.compile(r"\bimport\s+intent_router", _re.I),
    _re.compile(r"intent[_-]router", _re.I),
    _re.compile(r"intent-(proposal|catalog|map|feedback|constitution)", _re.I),
    _re.compile(r"\bintent_router\b", _re.I),
    _re.compile(r"router[\w-]*\.(json|db|state|ya?ml)", _re.I),
    _re.compile(r"/(intent-)?router/", _re.I),
    _re.compile(r"AWA_ROUTER|INTENT_ROUTER", _re.I),
    _re.compile(r"router_(state|dir|home|path)", _re.I),
]


def scan_tree_for_router_usage(root: Path, *, suffixes=(".py", ".sh"),
                               skip_dir_parts=()) -> list[str]:
    """Comprehensive rglob scan: every source file under `root` scanned for a router-artifact USAGE.
    Returns 'relpath: pattern matched text' offenders (empty = clean). ONE scan reused by the
    structural contamination guard and the kernel-off matrix (no divergent hardcoded file lists)."""
    skip = {"__pycache__", ".git", *skip_dir_parts}
    offenders: list[str] = []
    for p in sorted(root.rglob("*")):
        if not (p.is_file() and p.suffix in suffixes and not (skip & set(p.parts))):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for rx in ROUTER_USAGE_PATTERNS:
            m = rx.search(text)
            if m is not None:
                try:
                    rel = p.relative_to(REPO_ROOT)
                except ValueError:
                    rel = p
                offenders.append(f"{rel}: {rx.pattern!r} matched {m.group(0)!r}")
    return offenders
CATALOG_PATH = CONSUMER / "intent-catalog.v1.json"
GOLDEN_PATH = CONSUMER / "golden" / "awa-consumer.golden.json"
EGRESS_PATH = CONSUMER / "egress-terms.json"
ROUTER_PIN_PATH = CONSUMER / "router-pin.json"


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def load_router_pin() -> dict:
    return json.loads(ROUTER_PIN_PATH.read_text(encoding="utf-8"))


def load_kernel_consequence():
    """Load kernel/lib/awa_consequence.py BY PATH (matching the repo's kernel-first convention: the
    kernel libs are a standalone, stdlib-only surface loaded by path, never a `kernel.lib` package)."""
    path = REPO_ROOT / "kernel" / "lib" / "awa_consequence.py"
    spec = _ilu.spec_from_file_location("awa_consequence", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def router_engine():
    """Return the router engine module if the router is INSTALLED (importable), else None. This is
    the off-switch pivot: router-dependent tests skip when this is None, and AWA's `make verify`
    passes with the router uninstalled precisely because of that."""
    try:
        from intent_router import engine  # type: ignore
        return engine
    except Exception:
        return None


def router_available() -> bool:
    return router_engine() is not None


def make_proposal(*, consumer="awa", verb="", params=None, start_point="current",
                  safety_class="read", tool_path="cli", confidence=1.0, verdict="strong",
                  why=None, missing_params=None, requires_confirmation=False) -> dict:
    """Build an intent-proposal/v1-shaped envelope for router-INDEPENDENT loop tests (so routing/
    gating logic is covered even with the router uninstalled)."""
    return {
        "consumer": consumer, "verb": verb, "params": params or {},
        "start_point": start_point, "safety_class": safety_class, "tool_path": tool_path,
        "confidence": confidence, "verdict": verdict, "why": why or ["verdict:" + verdict],
        "missing_params": missing_params or [], "requires_confirmation": requires_confirmation,
    }


class FakeRouter:
    """A stand-in router module for loop tests: returns a canned proposal per utterance."""

    def __init__(self, mapping: dict):
        self._mapping = mapping

    def propose(self, consumer: str, utterance: str, catalog: dict) -> dict:
        return self._mapping.get(utterance, make_proposal(verdict="none", requires_confirmation=True,
                                                          safety_class="destructive"))
