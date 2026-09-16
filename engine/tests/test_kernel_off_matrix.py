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
import json
import os
import subprocess
import sys
from pathlib import Path

from .consumer_test_support import scan_tree_for_router_usage
from .helpers import EngineTestCase, commit_all, git

_REPO_ROOT = Path(__file__).resolve().parents[2]
_KERNEL = _REPO_ROOT / "kernel"
_ENGINE = _REPO_ROOT / "engine"
_DEV_WORKTREE = _KERNEL / "bin" / "dev-worktree.sh"
_GUARD = _KERNEL / "hooks" / "worktree-guard.sh"
_ROOTS_PY = _KERNEL / "lib" / "awa_roots.py"

# stdlib roots the kernel libs are ALLOWED to import (union'd with sys.stdlib_module_names when
# present, so the check also works on Python 3.9 where that attribute does not exist).
_KNOWN_STDLIB = {
    "__future__", "argparse", "hashlib", "json", "os", "platform", "subprocess", "sys",
    "time", "calendar", "re", "fnmatch", "shlex", "dataclasses", "pathlib", "typing",
    "functools", "itertools", "collections", "datetime", "tempfile", "importlib", "ast",
    "io", "math", "contextlib", "shutil", "stat", "glob", "textwrap", "enum", "errno", "fcntl",
}
# macOS immutable-flag primitives — forbidden PRODUCT-WIDE for K0/K1 (archive-only is K2).
_IMMUTABLE_TOKENS = ("chflags", "uchg", "schg", "uappnd", "SF_IMMUTABLE", "st_flags")
# advisory-lock primitives — forbidden in the KERNEL change surface (the engine's pre-existing
# SQLite / common-dir advisory locks are allowed; they serialize writers, they do NOT lock a
# worktree against removal).
_LOCK_TOKENS = ("flock", "fcntl", "lockf")
# The genuine advisory-lock APIs. `fcntl` imported ONLY for the Darwin F_FULLFSYNC durability
# barrier is NOT one of these; but `fcntl.flock` / `fcntl.lockf` and the fcntl range-lock command
# family (F_SETLK*) ARE real advisory locks — they must be flagged even inside a durability module.
_ADVISORY_FCNTL_CMDS = (
    "flock", "lockf", "F_SETLK", "F_SETLKW", "F_GETLK",
    "F_OFD_SETLK", "F_OFD_SETLKW", "F_OFD_GETLK", "LOCK_EX", "LOCK_SH", "LOCK_NB",
)


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
        """SHOULD-FIX 7 — delegate to the ONE comprehensive kernel rglob scan
        (consumer_test_support.scan_tree_for_router_usage) instead of a narrow hardcoded 3-file list,
        so the WHOLE kernel surface (every kernel/*.py and *.sh) is covered — not just three files."""
        offenders = scan_tree_for_router_usage(_KERNEL)
        self.assertEqual(offenders, [],
                         "the kernel must import/read ZERO router artifacts (KI2):\n"
                         + "\n".join(offenders))

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

    def test_maintenance_context_stays_live_with_engine_off(self) -> None:
        repo = self.make_repo("engoff-maintenance")
        remote = self.add_bare_remote(repo, "engoff-maintenance-origin.git")
        git(repo, "push", "-q", "-u", "origin", "main")
        policy = self.data_home / "engoff-maintenance-policy.yml"
        policy.write_text(
            "version: 1\n"
            "governed_roots:\n"
            "  - {0}\n"
            "default: include\n"
            "include:\n"
            "  - '*'\n"
            "exclude:\n"
            "  - .\n"
            "detectors:\n"
            "  governed_markers:\n"
            "    - _ops/POLICY.md\n"
            "  foreign_hook_frameworks:\n"
            "    - husky\n".format(self.data_home),
            encoding="utf-8",
        )
        env = self._engine_off_env()
        env.update(
            {
                "AWA_GOVERNED_ROOT": str(self.data_home),
                "AWA_POLICY": str(policy),
            }
        )

        def guard(command: str) -> dict:
            result = subprocess.run(
                ["bash", str(_GUARD)],
                input=json.dumps({"cwd": repo, "command": command}),
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)

        self.assertEqual(guard("git fetch"), {"permission": "allow"})
        Path(repo, "dirty").write_text("dirty\n", encoding="utf-8")
        denied = guard("git fetch")
        self.assertEqual(denied.get("permission"), "deny", denied)

    def test_maintenance_context_has_no_persistent_cache_surface(self) -> None:
        source = _GUARD.read_text(encoding="utf-8")
        for forbidden in (
            "functools.lru_cache",
            "functools.cache",
            "PRIMARY_MAINTENANCE_CONTEXT=",
            "AWA_PRIMARY_MAINTENANCE_CONTEXT",
        ):
            self.assertNotIn(forbidden, source)

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
        r = subprocess.run(["bash", str(_DEV_WORKTREE), "clean", "--path", wt],
                           env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "an active root must block even engine-off")
        self.assertTrue(Path(wt).exists())
        # a receipt was still written (engine-off)
        disp = subprocess.run(["python3", str(_ROOTS_PY), "list-receipts", "--limit", "1"],
                              env=env, capture_output=True, text=True)
        self.assertIn("active_root", disp.stdout)

    def test_refusal_writes_receipt_with_engine_off(self) -> None:
        env = self._engine_off_env()
        subprocess.run(["bash", str(_DEV_WORKTREE), "clean",
                        "--path", str(self.data_home / "nope")],
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

    # Root-bound finish (2026-07-10) shares the engine's per-common-dir WRITE-SERIALIZATION flock.
    # awa_finish.py is EXEMPT from the worktree-lock ban for EXACTLY the same reason engine/lock.py
    # is: it serializes the finish critical section against ordinary clean + engine maintenance
    # (byte-identical lock ABI, asserted in
    # test_finish_kernel.EngineOffAndLockAbiTest.test_lock_path_is_byte_identical_to_engine_abi);
    # it does NOT lock a worktree against removal (a busy lock makes finish REFUSE = fail-safe
    # preserve, never force-remove). dev-worktree.sh is exempt for the SAME reason (Fix 3,
    # 2026-07-10): the ordinary `clean --path` destructive section now HOLDS that same shared lock
    # (opening the byte-identical lockfile on an fd and delegating the flock to awa_finish.py's
    # flock-fd helper) so an ordinary clean serializes against a concurrent finish/engine mutation.
    # A busy lock makes the clean REFUSE (clean_lock_busy) and preserve the worktree — it never
    # locks a worktree against removal. The disposition/protection decision remains advisory kernel
    # state (no OS lock). The exempted files carry only the shared write-serialization lock; the
    # behavioral fail-safe (busy -> refuse, never force-remove) is proven in the finish/clean suites.
    # awa_roots.py uses the identical lock ABI only for the root-bound current-session CAS, so a
    # fire-and-forget sessionStart cannot erase a conversation attached by the first prompt.
    _LOCK_EXEMPT = {
        "awa_finish.py",
        "awa_handoff.py",
        "awa_roots.py",
        "dev-worktree.sh",
    }

    # Darwin durability (2026-07-10) requires fcntl(fd, F_FULLFSYNC) — a physical write BARRIER,
    # not an advisory lock. awa_durability.py therefore imports fcntl SOLELY for F_FULLFSYNC. It is
    # NOT in _LOCK_EXEMPT (it holds no lock at all): the carve-out below allows the bare `fcntl`
    # token ONLY while the file proves F_FULLFSYNC use and introduces NO genuine advisory-lock API,
    # so a real range-lock / flock added there is still flagged (see the biting regression
    # test_fsync_fcntl_carveout_still_flags_real_locks).
    _FSYNC_ONLY_FCNTL = {"awa_durability.py"}

    @classmethod
    def _lock_offenders_in(cls, name: str, text: str) -> list:
        """Advisory-lock tokens a single kernel source file introduces (empty == clean).

        A durability module may import fcntl only for the F_FULLFSYNC barrier; that lone use is
        allowed, but every real advisory-lock API (flock / lockf / fcntl range-lock command) is
        still reported, keeping the no-worktree-lock invariant's teeth intact."""
        if name in cls._LOCK_EXEMPT:
            return []
        hits = []
        for tok in _LOCK_TOKENS:
            if tok not in text:
                continue
            if (tok == "fcntl" and name in cls._FSYNC_ONLY_FCNTL
                    and "F_FULLFSYNC" in text
                    and not any(cmd in text for cmd in _ADVISORY_FCNTL_CMDS)):
                continue
            hits.append(tok)
        return hits

    def test_no_advisory_lock_in_kernel_change_surface(self) -> None:
        """The KERNEL introduces no OS advisory lock ON WORKTREES. (The engine's pre-existing
        SQLite / common-dir advisory locks serialize writers and are out of scope — they do
        NOT lock a worktree against removal. The finish core's shared write-serialization lock and
        handoff's dedicated metadata CAS lock are exempt for the same reason; see _LOCK_EXEMPT.
        awa_durability.py's fcntl is the F_FULLFSYNC durability barrier — not a lock — and is
        carved out by _FSYNC_ONLY_FCNTL.)"""
        offenders = [f"{p.relative_to(_REPO_ROOT)}: {tok}"
                     for p in self._src_files(_KERNEL)
                     for tok in self._lock_offenders_in(
                         p.name, p.read_text(encoding="utf-8", errors="replace"))]
        self.assertEqual(offenders, [],
                         "the kernel clean/roots path must introduce no OS advisory lock:\n"
                         + "\n".join(offenders))

    def test_fsync_fcntl_carveout_still_flags_real_locks(self) -> None:
        """The F_FULLFSYNC carve-out for awa_durability.py permits fcntl used ONLY for the Darwin
        durability barrier, yet MUST keep flagging any genuine advisory lock — otherwise a real
        worktree lock could hide behind the durability import."""
        dur = "awa_durability.py"
        # Allowed: fcntl imported purely for the F_FULLFSYNC write barrier.
        self.assertEqual(
            self._lock_offenders_in(
                dur, "import fcntl\nfcntl.fcntl(fd, fcntl.F_FULLFSYNC)\n"),
            [], "F_FULLFSYNC-only fcntl is a durability barrier, not an advisory lock")
        # Flagged: an fcntl range-lock (advisory) hidden behind the same durability import.
        self.assertIn(
            "fcntl",
            self._lock_offenders_in(
                dur, "import fcntl\nfcntl.fcntl(fd, fcntl.F_SETLK)  # F_FULLFSYNC\n"),
            "a real fcntl range-lock in the durability module must still be flagged")
        # Flagged: flock / lockf are advisory locks regardless of file.
        self.assertIn(
            "flock",
            self._lock_offenders_in(
                dur, "import fcntl\nfcntl.flock(fd, fcntl.LOCK_EX)  # F_FULLFSYNC\n"),
            "fcntl.flock is an advisory lock even inside the durability module")
        # The carve-out is durability-module-scoped: any OTHER kernel file using bare fcntl is
        # still flagged, even if it names F_FULLFSYNC.
        self.assertIn(
            "fcntl",
            self._lock_offenders_in(
                "awa_policy.py", "import fcntl\nfcntl.fcntl(fd, F_FULLFSYNC)\n"),
            "the F_FULLFSYNC carve-out is scoped to the durability module only")


if __name__ == "__main__":
    import unittest
    unittest.main()
