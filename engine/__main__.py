"""Enable `python3 -m engine` (from _ops/awa) to run the AWA engine CLI."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
