"""Fail-CLOSED regression tests for the K1 removal gate.

The K0/K1 adversarial review proved a consistent fail-OPEN theme: several UNCERTAIN outcomes in the
active-root removal gate let a destructive `git worktree remove` proceed. A safety kernel MUST fail
CLOSED. Each test drives the REAL bash gate (engine OFF, awa_roots.py is stdlib-only) and proves a
former fail-open path now REFUSES + PRESERVES the worktree — or, for the operator override, removes
ONLY with an explicit `--force` ack.

Coverage:
  * BLOCKER #1 disposition-unavailable  -> refused/disposition_unavailable (+ receipt still written)
  * MAJOR   #2 TOCTOU re-read           -> refused/reactivated_during_clean
  * MINOR   #4 kernel lib absent        -> refused/roots_lib_missing
  * MINOR   #5 receipt-write failure     -> non-zero audit status (3) + stderr breadcrumb
  * MINOR   #7 operator override         -> --force overrides ONLY a fail-safe-active; `forget` clears
MAJOR #3 (guard hot-path refresh) and MINOR #6 (TTL clamp) are proven in test_active_root.py.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

from .helpers import EngineTestCase, commit_all, git

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOTS_PY = _REPO_ROOT / "kernel" / "lib" / "awa_roots.py"


def _load_awa_roots():
    spec = importlib.util.spec_from_file_location("awa_roots_failclosed", _ROOTS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AR = _load_awa_roots()

# A drop-in stand-in the kernel invokes as AWA_ROOTS_LIB. It can (a) force a chosen subcommand to
# FAIL (AWA_STUB_FAIL_CMD), and (b) SCRIPT the `gate` subcommand line-by-line (AWA_GATE_SCRIPT) to
# simulate an unavailable disposition ("FAIL") or a mid-clean re-activation. EVERY other subcommand
# (write-receipt / heartbeat / remove-root / ...) DELEGATES to the real awa_roots.py, so a receipt
# is still written on the refusal path (proving #1 keeps its audit trail). Raw string: the literal
# "\n" sequences are interpreted by the STUB's own Python at its runtime.
_STUB = r'''#!/usr/bin/env python3
import os, sys, importlib.util
REAL = os.environ["AWA_ROOTS_REAL"]
def _real():
    spec = importlib.util.spec_from_file_location("awa_roots_real", REAL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.main(sys.argv[1:])
argv = sys.argv[1:]
cmd = argv[0] if argv else ""
fail = set(x for x in os.environ.get("AWA_STUB_FAIL_CMD", "").split(",") if x)
if cmd in fail:
    sys.stderr.write("stub: forced failure for " + cmd + "\n")
    sys.exit(1)
if cmd == "gate":
    ctl = os.environ.get("AWA_GATE_SCRIPT", "")
    lines = []
    if ctl and os.path.exists(ctl):
        with open(ctl) as fh:
            lines = [ln.rstrip("\n") for ln in fh]
    if lines:
        resp = lines[0]
        rest = lines[1:]
        with open(ctl, "w") as fh:
            fh.write("\n".join(rest) + ("\n" if rest else ""))
        if resp == "FAIL":
            sys.exit(1)
        if resp != "DELEGATE":
            sys.stdout.write(resp + "\n")
            sys.exit(0)
sys.exit(_real())
'''


class FailClosedGateTest(EngineTestCase):
    # ---- plumbing -----------------------------------------------------------
    @property
    def dev_worktree(self) -> str:
        return str(_REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh")

    @property
    def awa_roots(self) -> str:
        return str(_ROOTS_PY)

    @property
    def receipts_root(self) -> Path:
        return self.state_home / "awa" / "receipts"

    def run_clean(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        e = os.environ.copy()
        e["AWA_HOME"] = str(_REPO_ROOT)
        if env:
            e.update(env)
        return subprocess.run([self.dev_worktree, "clean", *args], cwd=str(_REPO_ROOT),
                              env=e, capture_output=True, text=True)

    def safe_worktree(self, name: str, branch: str = "feat/x") -> tuple[str, str]:
        """A worktree whose branch is squash-merged into main -> content-safe (removable but for
        the active-root gate)."""
        repo = self.make_repo(name)
        wt = self.add_worktree(repo, branch)
        Path(wt, "feature.txt").write_text("feature\n", encoding="utf-8")
        commit_all(wt, "feature")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", branch)
        commit_all(repo, "squash feature")
        return repo, wt

    def receipts(self) -> list[dict]:
        if not self.receipts_root.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(self.receipts_root.glob("clean-*.json"))]

    def stub_env(self, *, fail_cmds: list[str] | None = None,
                 gate_script: list[str] | None = None) -> dict:
        d = Path(self._tmp.name) / f"stub-{len(list((Path(self._tmp.name)).glob('stub-*')))}"
        d.mkdir(parents=True, exist_ok=True)
        stub = d / "awa_roots_stub.py"
        stub.write_text(_STUB, encoding="utf-8")
        env = {"AWA_ROOTS_LIB": str(stub), "AWA_ROOTS_REAL": str(_ROOTS_PY)}
        if fail_cmds:
            env["AWA_STUB_FAIL_CMD"] = ",".join(fail_cmds)
        if gate_script is not None:
            ctl = d / "gate_script.txt"
            ctl.write_text("\n".join(gate_script) + ("\n" if gate_script else ""), encoding="utf-8")
            env["AWA_GATE_SCRIPT"] = str(ctl)
        return env

    # ---- BLOCKER #1: disposition unavailable -> fail CLOSED -----------------
    def test_disposition_unavailable_refuses_and_preserves(self) -> None:
        """An ACTIVE record is on disk but the canonical-disposition tool cannot report it. The
        OLD gate did `[ -n "$disp" ] || return 0` = ALLOW and DESTROYED the active workspace. It
        must now REFUSE (fail closed) and still write an audit receipt."""
        _, wt = self.safe_worktree("dispunavail")
        self.assertEqual(subprocess.run(  # an ACTIVE record really is on disk
            ["python3", self.awa_roots, "heartbeat", "--root", wt],
            env=os.environ.copy(), capture_output=True, text=True).returncode, 0)
        env = self.stub_env(gate_script=["FAIL"])  # ...but disposition emits nothing / non-zero
        r = self.run_clean("--path", wt, env=env)
        self.assertNotEqual(r.returncode, 0, "clean MUST refuse when disposition is unavailable")
        self.assertTrue(Path(wt).exists(), "the active workspace MUST be preserved (fail closed)")
        recs = self.receipts()
        self.assertEqual(len(recs), 1, "a refusal receipt must still be written")
        self.assertEqual((recs[0]["disposition"], recs[0]["reason_code"]),
                         ("refused", "disposition_unavailable"))

    def test_disposition_unavailable_force_overrides(self) -> None:
        """The operator escape: --force overrides an UNAVAILABLE disposition (so a broken tool
        cannot permanently wedge cleanup)."""
        _, wt = self.safe_worktree("dispunavailforce")
        env = self.stub_env(gate_script=["FAIL", "FAIL"])  # pre-gate + recheck both unavailable
        r = self.run_clean("--path", wt, "--force", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists(), "--force overrides an unavailable disposition")

    # ---- MAJOR #2: TOCTOU re-read immediately before remove ----------------
    def test_reactivation_during_clean_refuses_and_preserves(self) -> None:
        """Disposition was read ONCE at the top, then the safe-check + ignored scan + optional
        --bundle tar (minutes) ran before `git worktree remove`. If the root is re-activated in
        that window it must be REFUSED at the re-read, not removed."""
        _, wt = self.safe_worktree("toctou")
        env = self.stub_env(gate_script=[
            "stale\tttl-expired\t0\t0\t1",          # pre-gate: proceed
            "active\treactivated-mid-clean\t0\t0\t1",  # recheck (pre-remove): re-activated
        ])
        r = self.run_clean("--path", wt, env=env)
        self.assertNotEqual(r.returncode, 0, "a mid-clean re-activation MUST refuse")
        self.assertTrue(Path(wt).exists(), "the re-activated workspace MUST be preserved")
        recs = self.receipts()
        self.assertEqual((recs[-1]["disposition"], recs[-1]["reason_code"]),
                         ("refused", "reactivated_during_clean"))

    # ---- MINOR #4: kernel lib absent -> fail CLOSED ------------------------
    def test_roots_lib_absent_fails_closed(self) -> None:
        _, wt = self.safe_worktree("libgone")
        env = {"AWA_ROOTS_LIB": str(Path(self._tmp.name) / "nope" / "awa_roots.py")}
        r = self.run_clean("--path", wt, env=env)
        self.assertNotEqual(r.returncode, 0, "a missing kernel lib MUST fail closed (refuse)")
        self.assertTrue(Path(wt).exists(), "the workspace MUST be preserved")
        self.assertIn("active-root safety gate is unavailable", r.stderr)

    def test_roots_lib_absent_force_overrides(self) -> None:
        _, wt = self.safe_worktree("libgoneforce")
        env = {"AWA_ROOTS_LIB": str(Path(self._tmp.name) / "nope" / "awa_roots.py")}
        r = self.run_clean("--path", wt, "--force", env=env)
        # The removal itself proceeds (operator ack); no receipt can be written (the writer is the
        # missing lib), which surfaces as the audit status (3) + a breadcrumb, never a silent success.
        self.assertFalse(Path(wt).exists(), "--force overrides a missing-lib gate")
        self.assertEqual(r.returncode, 3, "no-receipt-possible must surface as audit status 3")
        self.assertIn("cannot write clean receipt", r.stderr)

    # ---- MINOR #5: a receipt-write failure is NOT swallowed -----------------
    def test_receipt_write_failure_surfaces_audit_status(self) -> None:
        _, wt = self.safe_worktree("receiptfail")
        env = self.stub_env(fail_cmds=["write-receipt"])  # gate delegates (real); only audit fails
        r = self.run_clean("--path", wt, env=env)
        self.assertFalse(Path(wt).exists(), "the removal itself still succeeds")
        self.assertEqual(r.returncode, 3, "a receipt-write failure must surface as audit status 3")
        self.assertIn("receipt write FAILED", r.stderr)

    # ---- MINOR #7: operator override of a fail-safe-active ------------------
    def test_failsafe_active_refuses_but_force_overrides(self) -> None:
        _, wt = self.safe_worktree("failsafe")
        subprocess.run(["python3", self.awa_roots, "heartbeat", "--root", wt],
                       env=os.environ.copy(), capture_output=True, text=True, check=True)
        Path(AR.record_path(wt)).write_text("{ not json", encoding="utf-8")  # fail-safe ACTIVE
        self.assertTrue(AR.disposition(wt)["failsafe"], "precondition: fail-safe active")
        # Without --force: a fail-safe active blocks removal.
        r = self.run_clean("--path", wt)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(Path(wt).exists())
        self.assertEqual((self.receipts()[-1]["disposition"], self.receipts()[-1]["reason_code"]),
                         ("refused", "active_root"))
        # With --force: an operator ack overrides a fail-safe active NOT backed by a live pid.
        r2 = self.run_clean("--path", wt, "--force")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertFalse(Path(wt).exists())

    def test_force_does_not_override_genuine_fresh_active(self) -> None:
        """--force overrides ONLY a fail-safe active; a GENUINE fresh heartbeat is never
        force-removable (the operator must close/park the session or `forget` it)."""
        _, wt = self.safe_worktree("genuineactive")
        subprocess.run(["python3", self.awa_roots, "heartbeat", "--root", wt],
                       env=os.environ.copy(), capture_output=True, text=True, check=True)
        r = self.run_clean("--path", wt, "--force")
        self.assertNotEqual(r.returncode, 0, "a genuine active session is never force-removable")
        self.assertTrue(Path(wt).exists())

    def test_forget_operator_override_clears_stuck_record(self) -> None:
        _, wt = self.safe_worktree("forget")
        subprocess.run(["python3", self.awa_roots, "heartbeat", "--root", wt],
                       env=os.environ.copy(), capture_output=True, text=True, check=True)
        Path(AR.record_path(wt)).write_text("{ corrupt", encoding="utf-8")  # stuck fail-safe active
        self.assertEqual(AR.disposition(wt)["disposition"], "active")
        out = subprocess.run(["python3", self.awa_roots, "forget", "--root", wt],
                             env=os.environ.copy(), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        r = self.run_clean("--path", wt)  # now removable by a normal clean
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
