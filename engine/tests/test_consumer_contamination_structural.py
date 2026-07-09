"""A0 deliverable 7a (KI2): STRUCTURAL non-contamination — the kernel reads ZERO router artifacts.

A standing audit that greps the WHOLE kernel surface (every kernel/*.py and *.sh, including the new
awa_consequence.py) for any IMPORT or READ of a router artifact. This is = zero, forever: if a
future edit couples the kernel to the router, this test fails. Matching is USAGE-based (import/from/
artifact-file/env/state-path), never the bare word "router", so the kernel's own "router-OFF"
documentation prose stays legal."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _REPO_ROOT / "kernel"

# Router-artifact USAGE patterns (not the bare word). If ANY matches inside the kernel, the kernel
# has grown a router coupling.
_ROUTER_USAGE = [
    re.compile(r"\bimport\s+\w*router", re.I),
    re.compile(r"\bfrom\s+\w*router\b", re.I),
    re.compile(r"\bimport\s+intent_router", re.I),
    re.compile(r"intent[_-]router", re.I),
    re.compile(r"intent-(proposal|catalog|map|feedback|constitution)", re.I),
    re.compile(r"\bintent_router\b", re.I),
    re.compile(r"router[\w-]*\.(json|db|state|ya?ml)", re.I),
    re.compile(r"/(intent-)?router/", re.I),
    re.compile(r"AWA_ROUTER|INTENT_ROUTER", re.I),
    re.compile(r"router_(state|dir|home|path)", re.I),
]

_SKIP_PARTS = {"__pycache__", ".git"}
# stdlib + the ONE kernel sibling awa_consequence.py is allowed to import.
_KNOWN_STDLIB = {
    "__future__", "argparse", "hashlib", "json", "os", "platform", "subprocess", "sys",
    "time", "calendar", "re", "fnmatch", "shlex", "dataclasses", "pathlib", "typing",
    "functools", "itertools", "collections", "datetime", "tempfile", "importlib", "ast",
    "io", "math", "contextlib", "shutil", "stat", "glob", "textwrap", "enum", "errno",
}
_ALLOWED_KERNEL_SIBLINGS = {"awa_roots", "awa_policy", "awa_consequence"}


def _kernel_source_files():
    for p in sorted(_KERNEL.rglob("*")):
        if p.is_file() and p.suffix in (".py", ".sh") and not (_SKIP_PARTS & set(p.parts)):
            yield p


class TestStructuralContamination(unittest.TestCase):
    def test_kernel_reads_zero_router_artifacts(self):
        offenders = []
        for f in _kernel_source_files():
            text = f.read_text(encoding="utf-8", errors="replace")
            for rx in _ROUTER_USAGE:
                m = rx.search(text)
                if m is not None:
                    offenders.append(f"{f.relative_to(_REPO_ROOT)}: {rx.pattern!r} matched {m.group(0)!r}")
        self.assertEqual(offenders, [],
                         "the kernel must import/read ZERO router artifacts (KI2):\n"
                         + "\n".join(offenders))

    def test_consequence_module_imports_only_stdlib_and_kernel_siblings(self):
        """awa_consequence.py (the new consequence source) imports ONLY stdlib + a kernel sibling
        (awa_roots) — never the engine, never the router."""
        py = _KERNEL / "lib" / "awa_consequence.py"
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    roots.add(node.module.split(".")[0])
                # relative imports (level>0) are kernel siblings by construction
        offenders = {r for r in roots if r not in _KNOWN_STDLIB and r not in _ALLOWED_KERNEL_SIBLINGS}
        self.assertEqual(offenders, set(),
                         f"awa_consequence.py imports beyond stdlib+kernel-siblings: {offenders}")
        self.assertNotIn("engine", roots)
        self.assertNotIn("intent_router", roots)


if __name__ == "__main__":
    unittest.main()
