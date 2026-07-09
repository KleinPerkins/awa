"""Shared helpers for the AWA consumer (A0) test suite. NOT a test module itself."""

from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSUMER = REPO_ROOT / "consumer"
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
