"""A0 deliverable 7a (KI2): STRUCTURAL non-contamination — the kernel (and the engine) read ZERO
router artifacts, and the engine never imports the consumer.

A standing audit that greps the WHOLE kernel surface (every kernel/*.py and *.sh, including
awa_consequence.py) for any IMPORT or READ of a router artifact — = zero, forever. Extended
(SHOULD-FIX 7) to the ENGINE package: every engine/*.py (EXCLUDING the test suite, which
legitimately drives the consumer) must import NEITHER the consumer NOR the router and must read no
router artifact. Matching is USAGE-based (import/from/artifact-file/env/state-path) via the ONE
shared comprehensive scanner in consumer_test_support, never the bare word "router", so a module's
own "router-OFF" documentation prose stays legal."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from . import consumer_test_support as support

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _REPO_ROOT / "kernel"
_ENGINE = _REPO_ROOT / "engine"

# stdlib + the kernel siblings awa_consequence.py is allowed to import.
_KNOWN_STDLIB = {
    "__future__", "argparse", "hashlib", "json", "os", "platform", "subprocess", "sys",
    "time", "calendar", "re", "fnmatch", "shlex", "dataclasses", "pathlib", "typing",
    "functools", "itertools", "collections", "datetime", "tempfile", "importlib", "ast",
    "io", "math", "contextlib", "shutil", "stat", "glob", "textwrap", "enum", "errno",
}
_ALLOWED_KERNEL_SIBLINGS = {"awa_roots", "awa_policy", "awa_consequence"}


def _import_roots(py: Path) -> set[str]:
    """The set of top-level import roots in a Python file (level-0 imports only; relative imports are
    package-internal by construction)."""
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


class TestStructuralContamination(unittest.TestCase):
    def test_kernel_reads_zero_router_artifacts(self):
        offenders = support.scan_tree_for_router_usage(_KERNEL)
        self.assertEqual(offenders, [],
                         "the kernel must import/read ZERO router artifacts (KI2):\n"
                         + "\n".join(offenders))

    def test_engine_imports_neither_consumer_nor_router(self):
        """SHOULD-FIX 7 — KI2 'forever', EXTENDED beyond the kernel. The ENGINE package
        (observability) imports NEITHER the consumer NOR the router and reads zero router artifacts:
        the dependency arrow is consumer->kernel and the engine is independent. The engine TEST
        suite legitimately drives the consumer, so tests/ is excluded."""
        offenders: list[str] = []
        for p in sorted(_ENGINE.rglob("*.py")):
            if "tests" in p.parts or "__pycache__" in p.parts:
                continue
            roots = _import_roots(p)
            for bad in ("consumer", "intent_router"):
                if bad in roots:
                    offenders.append(f"{p.relative_to(_REPO_ROOT)}: imports {bad!r}")
        # reuse the ONE comprehensive router-artifact scan over the same engine surface
        offenders += support.scan_tree_for_router_usage(_ENGINE, skip_dir_parts=("tests",))
        self.assertEqual(offenders, [],
                         "the engine must import neither the consumer nor a router artifact "
                         "(forever):\n" + "\n".join(offenders))

    def test_consequence_module_imports_only_stdlib_and_kernel_siblings(self):
        """awa_consequence.py (the consequence source) imports ONLY stdlib + a kernel sibling
        (awa_roots) — never the engine, never the router."""
        roots = _import_roots(_KERNEL / "lib" / "awa_consequence.py")
        offenders = {r for r in roots if r not in _KNOWN_STDLIB and r not in _ALLOWED_KERNEL_SIBLINGS}
        self.assertEqual(offenders, set(),
                         f"awa_consequence.py imports beyond stdlib+kernel-siblings: {offenders}")
        self.assertNotIn("engine", roots)
        self.assertNotIn("intent_router", roots)


if __name__ == "__main__":
    unittest.main()
