"""AWA engine — kernel + engine core for Agent Worktree Automation.

Kernel-first invariant (plan v2.1, frozen): the safety guarantee — detection,
recovery, cleanup-refusal, and safe lifecycle decisions — MUST hold with the
daemon/watcher OFF. The engine only observes, bookkeeps, and eases. Nothing here
may become a *new* safety dependency for the core guarantee.

Zero-link (§D3): this package is destined for the global `tools/awa` shelf and
therefore carries ZERO org-specific literals. Repo classification is decided
generically (governed-marker / foreign-hook detectors + include/exclude globs
supplied by a machine-local policy file). Any org/vendor literals live only in the
machine-local `_ops/policy/worktree-policy.yml`, never here.

Stdlib + sqlite3 only (no third-party deps).
"""

from __future__ import annotations

__all__ = ["__version__"]
__version__ = "1.7.2"
