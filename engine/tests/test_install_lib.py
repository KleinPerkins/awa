"""Regression tests for kernel/lib/install-lib.sh and install.sh's write/read primitives.

Targets two defects fixed together, both discovered on `bash bootstrap.sh --reconcile`:

1. `awa_write_backup` EPERM-ing when the destination carries the macOS/BSD user-immutable
   flag (`uchg`) -- e.g. Cursor sets `uchg` on the `~/.cursor/mcp.json` files it manages --
   instead of clearing/restoring the flag around the atomic rename.
2. `install.sh` silently downgrading an already-configured `AWA_POLICY` (e.g. a host overlay
   pointer recorded in mcp.json) back to the generic installed default whenever a reconcile
   runs without that env exported (a `cmp` idempotency mismatch that then reaches #1's `mv`).

Pure subprocess-over-bash / stdlib only, no network. Every scratch file lives in a fresh
`tempfile.TemporaryDirectory`; nothing here ever touches the operator's real HOME or
`~/.cursor/mcp.json`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_LIB = REPO_ROOT / "kernel" / "lib" / "install-lib.sh"
INSTALL_SH = REPO_ROOT / "install.sh"

_HAS_CHFLAGS = shutil.which("chflags") is not None

# Minimal valid policy schema, same shape engine/tests/test_guard.py uses.
_POLICY_YAML = """\
version: 1
governed_roots:
  - {root}
default: include
include:
  - '*'
exclude:
  - .
detectors:
  governed_markers:
    - _ops/POLICY.md
  foreign_hook_frameworks:
    - husky
"""


def _run_bash(script: str, *, input_text: str = "",
              env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], input=input_text,
                           capture_output=True, text=True, env=env)


def _has_uchg(path: Path) -> bool:
    out = subprocess.run(["stat", "-f", "%Sf", str(path)], capture_output=True, text=True)
    return "uchg" in out.stdout


@unittest.skipUnless(_HAS_CHFLAGS, "chflags is macOS/BSD-only; the guarded no-op path is "
                                    "covered separately by TestAwaWriteBackupNoChflags")
class TestAwaWriteBackupUchg(unittest.TestCase):
    """FIX 1: a uchg'd destination (a Cursor-managed mcp.json) must not EPERM the atomic
    rename inside awa_write_backup; the flag must be cleared before and restored after."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-install-lib-test.")
        self.addCleanup(self._cleanup_tmp)
        self.dest = Path(self.tmp.name) / "mcp.json"
        self.dest.write_text('{"mcpServers": {"other": {"command": "/usr/bin/true"}}}\n')
        subprocess.run(["chflags", "uchg", str(self.dest)], check=True)

    def _cleanup_tmp(self) -> None:
        # cp -p inherits uchg onto the timestamped backup too; clear everything before rmtree.
        for p in Path(self.tmp.name).glob("*"):
            subprocess.run(["chflags", "nouchg", str(p)], check=False)
        self.tmp.cleanup()

    def test_write_backup_succeeds_on_uchg_destination(self) -> None:
        self.assertTrue(_has_uchg(self.dest), "precondition: fixture must start uchg'd")
        script = f'. "{INSTALL_SH}"\nawa_write_backup "{self.dest}"'
        result = _run_bash(script, input_text='{"different": true}\n')
        self.assertEqual(
            result.returncode, 0,
            f"awa_write_backup must succeed on a uchg destination; stderr={result.stderr!r}",
        )
        self.assertEqual(json.loads(self.dest.read_text()), {"different": True})

    def test_uchg_is_restored_after_a_successful_write(self) -> None:
        script = f'. "{INSTALL_SH}"\nawa_write_backup "{self.dest}"'
        result = _run_bash(script, input_text='{"different": true}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            _has_uchg(self.dest),
            "Cursor manages the uchg flag on mcp.json; AWA must restore it after writing "
            "rather than permanently weakening the file's existing protection",
        )

    def test_no_orphan_temp_file_after_a_successful_write(self) -> None:
        env = dict(os.environ)
        env["TMPDIR"] = self.tmp.name
        before = set(Path(self.tmp.name).glob("tmp.*"))
        script = f'. "{INSTALL_SH}"\nawa_write_backup "{self.dest}"'
        result = _run_bash(script, input_text='{"different": true}\n', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = set(Path(self.tmp.name).glob("tmp.*"))
        self.assertEqual(before, after, "no orphaned mktemp scratch file after a successful write")
        backups = list(Path(self.tmp.name).glob("mcp.json.bak-*"))
        self.assertEqual(len(backups), 1, "differing prior content must be backed up exactly once")


class TestAwaWriteBackupMvFailureIsDiagnosed(unittest.TestCase):
    """A REMAINING rename failure after clearing uchg (e.g. a real system-immutable `schg`,
    which a non-root owner cannot clear -- reasoned-not-executed here, see the report; it needs
    root) must surface as a clear awa_die message, not a raw `mv` EPERM leaking under the
    caller's `set -e`, and must never leave an orphaned temp file or a corrupted destination.
    Exercised deterministically by shadowing `mv` on PATH with an always-failing stub, which
    forces the exact same "cleared uchg, mv still fails" branch without needing root/schg."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-install-lib-test.")
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "target.json"
        self.dest.write_text('{"old": true}\n')
        fake_bin = Path(self.tmp.name) / "fakebin"
        fake_bin.mkdir()
        mv_stub = fake_bin / "mv"
        mv_stub.write_text("#!/bin/sh\nexit 1\n")
        mv_stub.chmod(0o755)
        self.env = dict(os.environ)
        self.env["PATH"] = f"{fake_bin}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["TMPDIR"] = self.tmp.name

    def test_mv_failure_is_diagnosed_not_raw_and_leaves_no_mess(self) -> None:
        script = f'. "{INSTALL_SH}"\nawa_write_backup "{self.dest}"'
        result = _run_bash(script, input_text='{"new": true}\n', env=self.env)
        self.assertNotEqual(result.returncode, 0, "a genuine rename failure must still fail")
        self.assertIn("cannot write", result.stderr)
        self.assertIn("ls -lO", result.stderr, "diagnostic must point the operator at `ls -lO`")
        self.assertNotIn("Operation not permitted", result.stderr,
                          "must not leak a raw, unexplained mv error")
        leftover = list(Path(self.tmp.name).glob("tmp.*"))
        self.assertEqual(leftover, [], "a failed write must not leave an orphaned temp file")
        self.assertEqual(self.dest.read_text(), '{"old": true}\n',
                          "destination must remain untouched (never truncated/corrupted) on failure")


@unittest.skipUnless(_HAS_CHFLAGS, "meaningful only where chflags exists to shadow away")
class TestAwaWriteBackupNoChflags(unittest.TestCase):
    """E3: on a platform without `chflags` (e.g. Linux/CI), the uchg-handling must be a fully
    guarded no-op -- write still succeeds, no crash. No Linux/container runner is available in
    this session, so this is exercised via a PATH-shadow trick that hides `chflags` locally,
    proving the exact guarded branch deterministically (see the report for this label)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-install-lib-test.")
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "target.json"
        self.dest.write_text('{"old": true}\n')
        self.env = dict(os.environ)
        self.env["PATH"] = self._path_hiding_chflags()

    def _path_hiding_chflags(self) -> str:
        """Real PATH with `chflags` specifically absent, every other tool intact. Any directory
        that exposes chflags is replaced by a same-position shim of symlinks to that directory's
        OTHER entries (mktemp/dirname/cmp/etc. all commonly share a dir with chflags on macOS,
        so simply dropping the whole directory -- as opposed to just the one binary -- would
        silently break the script's other dependencies rather than isolate chflags)."""
        shim_root = Path(self.tmp.name) / "path-shim"
        shim_root.mkdir(exist_ok=True)
        out_dirs = []
        for i, d in enumerate(os.environ.get("PATH", "").split(os.pathsep)):
            if not d:
                continue
            real = Path(d)
            if not (real / "chflags").exists():
                out_dirs.append(d)
                continue
            shim = shim_root / f"dir{i}"
            shim.mkdir()
            for entry in real.iterdir():
                if entry.name == "chflags":
                    continue
                try:
                    (shim / entry.name).symlink_to(entry)
                except OSError:
                    pass
            out_dirs.append(str(shim))
        return os.pathsep.join(out_dirs)

    def test_write_succeeds_without_chflags_on_path(self) -> None:
        probe = subprocess.run(["bash", "-c", "command -v chflags"], capture_output=True,
                                text=True, env=self.env)
        self.assertNotEqual(probe.returncode, 0, "PATH shadow must actually hide chflags")
        script = f'. "{INSTALL_SH}"\nawa_write_backup "{self.dest}"'
        result = _run_bash(script, input_text='{"new": true}\n', env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.dest.read_text()), {"new": True})


class TestAwaMcpEnvGet(unittest.TestCase):
    """Unit coverage for the awa_mcp_env_get read primitive (a Fix 2 building block)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-install-lib-test.")
        self.addCleanup(self.tmp.cleanup)
        self.mcp_json = Path(self.tmp.name) / "mcp.json"

    def _get(self, name: str, key: str) -> str:
        script = f'. "{INSTALL_LIB}"\nawa_mcp_env_get "{self.mcp_json}" "{name}" "{key}"'
        result = _run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_reads_existing_value(self) -> None:
        self.mcp_json.write_text(json.dumps({
            "mcpServers": {"awa": {"command": "x", "env": {"AWA_POLICY": "/overlay/policy.yml"}}}
        }))
        self.assertEqual(self._get("awa", "AWA_POLICY"), "/overlay/policy.yml")

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(self._get("awa", "AWA_POLICY"), "")

    def test_missing_server_returns_empty(self) -> None:
        self.mcp_json.write_text(json.dumps({"mcpServers": {}}))
        self.assertEqual(self._get("awa", "AWA_POLICY"), "")

    def test_malformed_json_returns_empty_not_crash(self) -> None:
        self.mcp_json.write_text("{not valid json")
        self.assertEqual(self._get("awa", "AWA_POLICY"), "")


class TestInstallPolicyPreservation(unittest.TestCase):
    """FIX 2 (end-to-end): a reconcile invoked WITHOUT AWA_POLICY exported -- e.g. bootstrap's
    `install.sh >/dev/null 2>&1` wrapper, which does not re-export a host overlay's value --
    must not downgrade an already-configured AWA_POLICY in mcp.json back to the generic
    installed default. Runs the real install.sh in a throwaway HOME (same sandboxing pattern as
    `make verify-install`); never touches the operator's real HOME/mcp.json."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-install-e2e-test.")
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name)
        self.env = dict(os.environ)
        self.env.update({
            "HOME": str(home),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
        })
        self.mcp_json = home / ".cursor" / "mcp.json"
        self.overlay_policy = home / "overlay-worktree-policy.yml"
        self.overlay_policy.write_text(_POLICY_YAML.format(root=home))

    def _install(self, *, awa_policy: str | None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if awa_policy is None:
            env.pop("AWA_POLICY", None)
        else:
            env["AWA_POLICY"] = awa_policy
        return subprocess.run([str(INSTALL_SH)], capture_output=True, text=True, env=env)

    def _read_policy(self) -> str:
        data = json.loads(self.mcp_json.read_text())
        return data["mcpServers"]["awa"]["env"]["AWA_POLICY"]

    def test_reconcile_without_env_preserves_existing_overlay_policy(self) -> None:
        first = self._install(awa_policy=str(self.overlay_policy))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self._read_policy(), str(self.overlay_policy))

        second = self._install(awa_policy=None)  # simulates bootstrap's suppressed-env reconcile
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            self._read_policy(), str(self.overlay_policy),
            "a reconcile without AWA_POLICY exported must not downgrade an already-configured "
            "host policy back to the generic default",
        )

    def test_explicit_env_still_wins_over_a_prior_value(self) -> None:
        first = self._install(awa_policy=str(self.overlay_policy))
        self.assertEqual(first.returncode, 0, first.stderr)
        other_policy = Path(self.tmp.name) / "other-policy.yml"
        other_policy.write_text(self.overlay_policy.read_text())
        third = self._install(awa_policy=str(other_policy))
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertEqual(self._read_policy(), str(other_policy))

    def test_fresh_install_with_no_env_falls_back_to_default(self) -> None:
        fresh = self._install(awa_policy=None)
        self.assertEqual(fresh.returncode, 0, fresh.stderr)
        policy = self._read_policy()
        self.assertTrue(policy.endswith("kernel/policy/default-worktree-policy.yml"), policy)


class TestInstallPolicyAppliesToModesFileSync(unittest.TestCase):
    """FIX 2 completeness gap caught by pre-merge security-review + bugbot passes:
    ensure_modes_file() and configure_dashboard_refresh() must consume the SAME preserved
    host_policy as the MCP entry, not silently keep falling back to
    ``${AWA_POLICY:-$default_policy}`` / the installed default. The installed default policy
    ships with NO ``modes_file:`` pointer (by design -- see
    kernel/policy/default-worktree-policy.yml), so before this fix, a reconcile run without
    AWA_POLICY exported (exactly what `bootstrap.sh --reconcile` does) would silently no-op
    ensure_modes_file every time instead of syncing the host's real, already-configured modes
    file -- only a rare direct `AWA_POLICY=... bash install.sh` invocation actually worked."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-install-modes-test.")
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name)
        self.env = dict(os.environ)
        self.env.update({
            "HOME": str(home),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
        })
        self.overlay_policy = home / "overlay-worktree-policy.yml"
        # A modes_file pointer is what makes ensure_modes_file's behavior actually diverge
        # between "the preserved overlay" and "the installed default" (the default declares none).
        self.overlay_policy.write_text(_POLICY_YAML.format(root=home) + "modes_file: modes.yml\n")
        self.modes_file = home / "modes.yml"  # relative pointer resolves next to the policy file

    def _install(self, *, awa_policy: str | None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        if awa_policy is None:
            env.pop("AWA_POLICY", None)
        else:
            env["AWA_POLICY"] = awa_policy
        return subprocess.run([str(INSTALL_SH)], capture_output=True, text=True, env=env)

    def test_reconcile_without_env_still_syncs_the_overlays_modes_file(self) -> None:
        first = self._install(awa_policy=str(self.overlay_policy))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(self.modes_file.exists(),
                         "an explicit AWA_POLICY with a modes_file pointer must sync it on install")
        self.modes_file.unlink()  # prove the SECOND run is what (re-)creates it, not a stale leftover

        second = self._install(awa_policy=None)  # simulates bootstrap's suppressed-env reconcile
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(
            self.modes_file.exists(),
            "a reconcile without AWA_POLICY exported must still resolve the PRESERVED host "
            "policy (with its modes_file pointer) for ensure_modes_file, not silently fall back "
            "to the installed default (which has no modes_file pointer and would no-op)",
        )


if __name__ == "__main__":
    unittest.main()
