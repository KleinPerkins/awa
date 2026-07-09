"""K0/K1: the engine-OFF + router-OFF invariant harness (kernel safety holds).

The kernel safety guarantee must hold with the Python engine OFF and NO router installed. This
matrix proves it structurally and behaviorally:

  * the kernel libs (awa_roots.py, awa_policy.py) import ONLY the stdlib — zero engine imports,
    zero third-party deps, so the shell kernel can invoke them with the engine package absent;
  * the kernel reads NO router artifact (no router exists — the structural contamination guard
    keeps it that way);
  * with the engine package deliberately UNIMPORTABLE, the kernel clean gate STILL blocks an
    active root and STILL writes a clean_receipt (the safety behavior does not depend on the
    engine being importable);
  * no active OS lock / macOS immutable (uchg) flag is introduced (locked decision for K0/K1).
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

from .helpers import EngineTestCase, commit_all, git

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _REPO_ROOT / "kernel"
_ENGINE = _REPO_ROOT / "engine"
_DEV_WORKTREE = _KERNEL / "bin" / "dev-worktree.sh"
_ROOTS_PY = _KERNEL / "lib" / "awa_roots.py"
_SESSION = _KERNEL / "hooks" / "worktree-session.sh"

# stdlib roots the kernel libs are ALLOWED to import (union'd with sys.stdlib_module_names when
# present, so the check also works on Python 3.9 where that attribute does not exist).
_KNOWN_STDLIB = {
    "__future__", "argparse", "hashlib", "json", "os", "platform", "subprocess", "sys",
    "time", "calendar", "re", "fnmatch", "shlex", "dataclasses", "pathlib", "typing",
    "functools", "itertools", "collections", "datetime", "tempfile", "importlib", "ast",
    "io", "math", "contextlib", "shutil", "stat", "glob", "textwrap", "enum", "errno",
}
# router artifacts do NOT exist yet; the kernel must never grow an IMPORT or a READ of one.
# NOTE: matched as usage patterns (import/from/path/env/state file), NOT the bare word, so the
# kernel's own "router-OFF" / "no router installed" documentation prose is allowed.
_ROUTER_USAGE = [
    re.compile(r"\bimport\s+\w*router", re.I),
    re.compile(r"\bfrom\s+\w*router", re.I),
    re.compile(r"\b(intent[_-]?router|egress)\s*[=(.]", re.I),
    re.compile(r"router[\w-]*\.(json|db|state|ya?ml)", re.I),
    re.compile(r"/router/", re.I),
    re.compile(r"AWA_ROUTER", re.I),
    re.compile(r"router_(state|dir|home|path)", re.I),
]
# macOS immutable-flag primitives — forbidden PRODUCT-WIDE for K0/K1 (archive-only is K2).
_IMMUTABLE_TOKENS = ("chflags", "uchg", "schg", "uappnd", "SF_IMMUTABLE", "st_flags")
# advisory-lock primitives — forbidden in the KERNEL change surface (the engine's pre-existing
# SQLite / common-dir advisory locks are allowed; they serialize writers, they do NOT lock a
# worktree against removal).
_LOCK_TOKENS = ("flock", "fcntl", "lockf")


class KernelOffMatrixTest(EngineTestCase):
    # ---- stdlib-only: no engine / third-party imports in the kernel libs ----
    def test_kernel_libs_are_stdlib_only(self) -> None:
        stdlib = _KNOWN_STDLIB | set(getattr(sys, "stdlib_module_names", set()))
        for py in sorted(_KERNEL.rglob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            roots: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module:
                        roots.add(node.module.split(".")[0])
            offenders = {r for r in roots if r != "__future__" and r not in stdlib}
            self.assertEqual(offenders, set(),
                             f"{py.relative_to(_REPO_ROOT)} imports non-stdlib: {offenders} "
                             "(kernel must run engine-OFF, stdlib-only)")
            self.assertNotIn("engine", roots, f"{py.name} must not import the engine package")

    # ---- router-off: the kernel imports/reads no router artifact ------------
    def test_kernel_has_no_router_import_or_read(self) -> None:
        for f in (_ROOTS_PY, _DEV_WORKTREE, _SESSION):
            text = f.read_text(encoding="utf-8")
            for rx in _ROUTER_USAGE:
                m = rx.search(text)
                if m is not None:
                    self.fail(f"{f.name} imports/reads router state ({rx.pattern!r} matched "
                              f"{m.group(0)!r}) — the kernel must have ZERO router coupling")

    # ---- behavioral: engine unimportable, kernel still blocks an active root -
    def _engine_off_env(self) -> dict[str, str]:
        env = {}
        for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"):
            if k in os.environ:
                env[k] = os.environ[k]
        env["AWA_HOME"] = str(_REPO_ROOT)
        env["XDG_STATE_HOME"] = str(self.state_home)
        # deliberately point PYTHONPATH at an EMPTY dir so the engine package is NOT importable
        empty = self.data_home / "empty-pp"
        empty.mkdir(parents=True, exist_ok=True)
        env["PYTHONPATH"] = str(empty)
        return env

    def test_engine_is_actually_off_under_matrix_env(self) -> None:
        env = self._engine_off_env()
        r = subprocess.run(["python3", "-c", "import engine"], env=env,
                           capture_output=True, text=True, cwd=str(self.data_home))
        self.assertNotEqual(r.returncode, 0,
                            "matrix env must make the engine package UNIMPORTABLE (engine-off)")

    def test_active_root_blocks_with_engine_off(self) -> None:
        repo = self.make_repo("engoff")
        wt = self.add_worktree(repo, "feat/off")
        Path(wt, "feature.txt").write_text("f\n", encoding="utf-8")
        commit_all(wt, "feature")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", "feat/off")
        commit_all(repo, "squash")
        env = self._engine_off_env()
        # mark ACTIVE via the kernel lib subprocess (also engine-off)
        subprocess.run(["python3", str(_ROOTS_PY), "heartbeat", "--root", wt],
                       env=env, capture_output=True, text=True, check=True)
        r = subprocess.run([str(_DEV_WORKTREE), "clean", "--path", wt],
                           env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "an active root must block even engine-off")
        self.assertTrue(Path(wt).exists())
        # a receipt was still written (engine-off)
        disp = subprocess.run(["python3", str(_ROOTS_PY), "list-receipts", "--limit", "1"],
                              env=env, capture_output=True, text=True)
        self.assertIn("active_root", disp.stdout)

    def test_refusal_writes_receipt_with_engine_off(self) -> None:
        env = self._engine_off_env()
        subprocess.run([str(_DEV_WORKTREE), "clean", "--path", str(self.data_home / "nope")],
                       env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True)
        r = subprocess.run(["python3", str(_ROOTS_PY), "list-receipts", "--limit", "1"],
                           env=env, capture_output=True, text=True)
        self.assertIn("not_a_directory", r.stdout)
        self.assertIn("clean_receipt/v1", r.stdout)

    @staticmethod
    def _src_files(base: Path):
        for path in sorted(base.rglob("*")):
            if (path.is_file() and path.suffix in (".py", ".sh")
                    and "__pycache__" not in path.parts and "tests" not in path.parts):
                yield path

    def test_no_macos_immutable_flag_product_wide(self) -> None:
        """The macOS immutable (uchg) flag is forbidden PRODUCT-WIDE for K0/K1."""
        offenders = [f"{p.relative_to(_REPO_ROOT)}: {tok}"
                     for base in (_KERNEL, _ENGINE)
                     for p in self._src_files(base)
                     for tok in _IMMUTABLE_TOKENS
                     if tok in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(offenders, [],
                         "no macOS immutable flag may protect active worktrees (K0/K1); "
                         "archive-only hardening is K2:\n" + "\n".join(offenders))

    def test_no_advisory_lock_in_kernel_change_surface(self) -> None:
        """The KERNEL introduces no OS advisory lock on worktrees. (The engine's pre-existing
        SQLite / common-dir advisory locks serialize writers and are out of scope — they do
        NOT lock a worktree against removal.)"""
        offenders = [f"{p.relative_to(_REPO_ROOT)}: {tok}"
                     for p in self._src_files(_KERNEL)
                     for tok in _LOCK_TOKENS
                     if tok in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual(offenders, [],
                         "the kernel clean/roots path must introduce no OS advisory lock:\n"
                         + "\n".join(offenders))


if __name__ == "__main__":
    import unittest
    unittest.main()
