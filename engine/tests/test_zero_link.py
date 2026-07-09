"""Zero-link: the AWA product (kernel + engine + dashboard) must carry ZERO org literals.

A global capability master is gated by `orchestrator zero-link --mode global`, which runs
`grep -rEniI` recursively over the WHOLE payload (every file type) against a forbidden-token
list (config/forbidden-cpp.txt). The AWA repo's CI has no OTHER kernel guard, so THIS in-repo
pre-flight is the SOLE kernel guard and must be AT LEAST AS STRICT as that gate.

Scope: the shipped/vendored runtime + build/doc surface (engine, kernel, dashboard, contracts,
bin, .github, and the top-level shipped files). Operator harnesses that are never installed or
vendored (hook-probe/, live-verify/) are out of the shipped surface and out of scope here.

Exclusion of a self-governed sibling repo is decided GENERICALLY (governed-marker detector), so
no org literal is ever needed anywhere in the product. The forbidden tokens are assembled from
fragments so THIS scanner file stays token-clean, and it excludes itself from the scan.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

# Assemble the forbidden tokens from fragments (MIRRORS the orchestrator forbidden-cpp.txt
# EXACTLY: card-platform-product ; cpp-stuff ; affirm/(src|vendor) ; (^|[^A-Za-z])cpp([^A-Za-z]|$))
# so this file itself contains no literal token.
_card = "card-" + "platform-" + "product"
_org = "af" + "firm"
_gov = "c" + "pp"

_FORBIDDEN = [
    re.compile(re.escape(_card)),
    re.compile(_org + r"/(src|vendor)"),
    re.compile(re.escape(_gov + "-stuff")),
    re.compile(r"(^|[^A-Za-z])" + _gov + r"([^A-Za-z]|$)"),
]

_ENGINE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _ENGINE_DIR.parent
_SELF = Path(__file__).resolve()

# Shipped/vendored surface — kept in lock-step with install.sh COPY_TREES/COPY_FILES + CI.
_SCAN_DIRS = ["engine", "kernel", "dashboard", "contracts", "bin", "consumer", ".github"]
_SCAN_FILES = ["install.sh", "bootstrap.sh", "Makefile", "ARCHITECTURE.md", "README.md",
               "SECURITY.md", "pyproject.toml"]
_SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git", "node_modules", ".mypy_cache", ".ruff_cache"}


def _iter_shipped_files():
    for d in _SCAN_DIRS:
        base = _REPO_ROOT / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not (_SKIP_PARTS & set(path.parts)):
                yield path
    for f in _SCAN_FILES:
        path = _REPO_ROOT / f
        if path.is_file():
            yield path


class TestZeroLink(unittest.TestCase):
    def test_no_forbidden_literals_in_shipped_surface(self):
        offenders: list[str] = []
        for path in _iter_shipped_files():
            if path.resolve() == _SELF:
                continue  # the scanner necessarily references the tokens (as fragments)
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                for rx in _FORBIDDEN:
                    if rx.search(line):
                        offenders.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()}")
        self.assertEqual(
            offenders, [],
            "forbidden org/vendor literal(s) in shipped surface — move to a host policy overlay:\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
