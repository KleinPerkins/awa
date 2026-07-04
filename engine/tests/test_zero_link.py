"""D3 zero-link: the shelf-bound engine master must carry ZERO org-specific literals.

A global capability master is gated by `orchestrator zero-link --mode global` against
a forbidden-token list. This test is the in-repo pre-flight for that gate: it scans
every engine source file and fails if a forbidden org/vendor token appears. Exclusion
of a self-governed sibling repo is decided GENERICALLY (governed-marker detector), so
no literal is ever needed in the master.

The forbidden tokens are assembled from fragments below so THIS scanner file itself
stays token-clean (and it excludes itself from the scan for the same reason).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

# Assemble the forbidden tokens from fragments (mirrors the orchestrator's
# forbidden list) so this file contains no literal token.
_card = "card-" + "platform-" + "product"
_org = "af" + "firm"
_gov = "c" + "pp"

_FORBIDDEN = [
    re.compile(re.escape(_card)),
    re.compile(_org + r"/(src|vendor)"),
    re.compile(re.escape(_gov + "-stuff")),
    re.compile(r"(^|[^A-Za-z0-9_])" + _gov + r"([^A-Za-z0-9_]|$)"),
]

_ENGINE_DIR = Path(__file__).resolve().parent.parent
_SELF = Path(__file__).resolve().name


class TestZeroLink(unittest.TestCase):
    def test_no_forbidden_literals_in_engine(self):
        offenders: list[str] = []
        for py in sorted(_ENGINE_DIR.rglob("*.py")):
            if py.name == _SELF:
                continue  # the scanner necessarily references the tokens (as fragments)
            text = py.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                for rx in _FORBIDDEN:
                    if rx.search(line):
                        offenders.append(f"{py.relative_to(_ENGINE_DIR)}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [], "forbidden org/vendor literal(s):\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
