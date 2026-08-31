"""Phase 1 (Root-Bound Worktree Finish): the DETERMINISTIC KERNEL CORE is independently safe.

The kernel refusal is the ENTIRE safety guarantee in Phase 1 (no conversational surface, no
beforeSubmitPrompt hook). This module proves that guarantee end-to-end, driving the kernel exactly
as it ships: the stdlib-only libs (awa_finish.py / awa_roots.py) are imported directly for
fine-grained determinism/classification checks, and the destructive path is driven as a SUBPROCESS
(dev-worktree.sh clean --finish-current, and awa_finish.py finish-execute) with the engine package
made UNIMPORTABLE — so every safety claim holds engine-OFF and router-OFF.

The four Phase 1 gate proofs are named tests:
  (a) determinism       -> DeterminismGateTest (repeated runs, shuffled orderings, locales)
  (b) no-network        -> NoNetworkGateTest (removal + branch decision with git fetch/ls-remote/
                           push and gh made bombs on PATH)
  (c) identical-refusal -> IdenticalRefusalGateTest (every non-Close/stale/replayed/cross-root/
                           cross-session attempt refuses identically and preserves the worktree)
  (d) hook-independent  -> HookIndependentGateTest (Phase 1 ships no prompt hook; the CLI still
                           REQUIRES an explicit consumed literal `Close`)
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import threading
from pathlib import Path
from unittest import mock

from .helpers import EngineTestCase, commit_all, git

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FINISH_PY = _REPO_ROOT / "kernel" / "lib" / "awa_finish.py"
_ROOTS_PY = _REPO_ROOT / "kernel" / "lib" / "awa_roots.py"
_DEV_WORKTREE = _REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh"


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIN = _load("awa_finish_under_test", _FINISH_PY)
AR = _load("awa_roots_under_test_finish", _ROOTS_PY)


class FinishBase(EngineTestCase):
    """Scratch worktrees + subprocess drivers for the finish kernel core."""

    # ---- worktree builders --------------------------------------------------
    def ephemeral_wt(self, name: str, files: dict | None = None, *,
                     branch: str | None = None) -> tuple[str, str, str]:
        """A repo + a linked worktree on an AWA-ephemeral branch (cursor/worktree/<name>) with
        `files` written (uncommitted). Returns (repo, wt, branch)."""
        repo = self.make_seeded_repo(name)
        br = branch or f"cursor/worktree/{name}"
        wt = repo + ".wt"
        git(repo, "worktree", "add", "-q", "-b", br, wt, "main")
        for rel, content in (files or {}).items():
            p = Path(wt, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return repo, wt, br

    def targets(self, wt: str) -> dict:
        gd = git(wt, "rev-parse", "--path-format=absolute", "--git-dir").stdout.strip()
        cd = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        br = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        hd = git(wt, "rev-parse", "HEAD").stdout.strip()
        return {"git_dir": gd, "common_dir": cd, "branch": br, "head": hd}

    # ---- subprocess env (engine-OFF by default) -----------------------------
    def env(self, *, extra: dict | None = None, engine_off: bool = True,
            path: str | None = None) -> dict:
        """A subprocess env based on the (already XDG-isolated) test environment. By default the
        engine package is made UNIMPORTABLE (PYTHONPATH -> an empty dir) so the finish path is
        proven engine-OFF. Ambient finish knobs are cleared so a stray operator export cannot make
        a test non-deterministic; a test opts in via `extra`."""
        env = os.environ.copy()
        for k in ("DEV_SESSION_ID", "AWA_FINISH_CONVERSATION_ID", "AWA_FINISH_AUTHORIZATION",
                  "AWA_FINISH_CHALLENGE_TTL_SECONDS", "AWA_HEARTBEAT_TTL_SECONDS"):
            env.pop(k, None)
        env["AWA_HOME"] = str(_REPO_ROOT)
        env["XDG_STATE_HOME"] = str(self.state_home)
        env["AWA_ROOTS_LIB"] = str(_ROOTS_PY)
        env["AWA_FINISH_LIB"] = str(_FINISH_PY)
        if path is not None:
            env["PATH"] = path
        if engine_off:
            empty = self.data_home / "empty-pp"
            empty.mkdir(parents=True, exist_ok=True)
            env["PYTHONPATH"] = str(empty)
        if extra:
            env.update(extra)
        return env

    def run_lib(self, *args: str, env: dict | None = None,
                cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(_FINISH_PY), *args],
                              env=env or self.env(), cwd=cwd or str(_REPO_ROOT),
                              capture_output=True, text=True)

    def run_dev_finish(self, *args: str, cwd: str,
                       env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([str(_DEV_WORKTREE), "clean", "--finish-current", *args],
                              cwd=cwd, env=env or self.env(), capture_output=True, text=True)

    # ---- receipts (newest by mtime — receipt_ids collide at second granularity) --------
    def receipts(self) -> list[dict]:
        rd = self.state_home / "awa" / "receipts"
        if not rd.is_dir():
            return []
        files = sorted(rd.glob("clean-*.json"), key=lambda p: p.stat().st_mtime_ns)
        return [json.loads(p.read_text(encoding="utf-8")) for p in files]

    def last_receipt(self) -> dict:
        rs = self.receipts()
        self.assertTrue(rs, "expected at least one clean receipt")
        return rs[-1]

    # ---- finish drivers -----------------------------------------------------
    def preview(self, wt: str, conv: str = "conv", session: str = "sess") -> dict:
        t = self.targets(wt)
        r = self.run_lib("preview", "--root", wt, "--git-dir", t["git_dir"],
                         "--common-dir", t["common_dir"], "--branch", t["branch"],
                         "--head", t["head"], "--session-id", session, "--conversation-id", conv)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def execute(self, wt: str, answer: str, conv: str = "conv", session: str = "sess",
                env: dict | None = None, cwd: str | None = None) -> tuple[dict, subprocess.CompletedProcess]:
        t = self.targets(wt)
        r = self.run_lib("finish-execute", "--root", wt, "--git-dir", t["git_dir"],
                         "--common-dir", t["common_dir"], "--branch", t["branch"],
                         "--head", t["head"], "--session-id", session,
                         "--conversation-id", conv, "--answer", answer, env=env, cwd=cwd)
        return json.loads(r.stdout), r


# =====================================================================================
# Inventory: classification, cruft, secrets, traversal safety, escaping, NUL-safety
# =====================================================================================
class InventoryTest(FinishBase):
    def test_directory_traversal_scans_open_nofollow_descriptors(self) -> None:
        _, wt, _ = self.ephemeral_wt("dirfd-proof", {"nested/file.txt": "proof"})
        real_scandir = FIN.os.scandir
        scanned: list[object] = []

        def tracked_scandir(path):
            scanned.append(path)
            return real_scandir(path)

        FIN.os.scandir = tracked_scandir
        try:
            objects = FIN._capture_complete_tree(wt)
        finally:
            FIN.os.scandir = real_scandir
        self.assertTrue(objects)
        self.assertTrue(scanned)
        self.assertTrue(all(isinstance(path, int) for path in scanned), scanned)

    def test_nested_mount_signal_refuses_inventory(self) -> None:
        _, wt, _ = self.ephemeral_wt("mount-proof", {"nested/file.txt": "proof"})
        target = self.targets(wt)
        real_ismount = FIN.os.path.ismount
        nested = os.path.join(os.fsencode(os.path.realpath(wt)), b"nested")
        FIN.os.path.ismount = lambda path: path == nested
        try:
            inventory = FIN.build_inventory(wt, target["git_dir"])
        finally:
            FIN.os.path.ismount = real_ismount
        self.assertFalse(inventory["safe"], inventory)
        self.assertEqual(inventory["refuse_reason"], "mount_boundary")

    def test_cruft_is_exact_segment_not_substring(self) -> None:
        _, wt, _ = self.ephemeral_wt("cruft", {
            "keep.txt": "k",
            "node_modules/x.js": "a",          # cruft segment -> hidden
            "mynode_modules/y.js": "b",        # substring, NOT a segment -> shown
            "pkg/__pycache__/z.pyc": "c",      # nested cruft segment -> hidden
            "build/out.bin": "d",              # broad name, NOT cruft -> shown
            "trash.pyc": "e",                  # bytecode basename -> hidden
        })
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        by_path = {e["path"]: e for e in inv["entries"]}
        self.assertFalse(by_path["keep.txt"]["hidden"])
        self.assertTrue(by_path["node_modules/x.js"]["hidden"])
        self.assertFalse(by_path["mynode_modules/y.js"]["hidden"], "substring must not match cruft")
        self.assertTrue(by_path["pkg/__pycache__/z.pyc"]["hidden"])
        self.assertFalse(by_path["build/out.bin"]["hidden"], "broad names are not cruft")
        self.assertTrue(by_path["trash.pyc"]["hidden"])

    def test_tracked_files_are_never_hidden(self) -> None:
        # A tracked change is operator work regardless of name; cruft-hiding is scoped to the
        # untracked/ignored classes only.
        for cls in ("staged", "modified", "conflicted"):
            self.assertFalse(FIN._is_cruft("node_modules/whatever", cls),
                             f"{cls} must never be hidden")

    def test_secret_contents_and_private_proof_are_not_rendered(self) -> None:
        _, wt, _ = self.ephemeral_wt("secrets", {
            ".env": "TOKEN=1", "deploy.pem": "x", "id_rsa": "x", "creds/credentials": "x",
        })
        t = self.targets(wt)
        result = self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"])
        inv = json.loads(result.stdout)
        self.assertTrue(inv["entries"])
        self.assertNotIn("TOKEN=1", result.stdout)
        self.assertNotIn("path_hex", result.stdout)
        self.assertNotIn("sha256", result.stdout)
        for e in inv["entries"]:
            self.assertEqual(e["template_id"], "secret", e["display"])
            self.assertIn("not displayed", e["sentence"])

    def test_symlink_escape_refuses(self) -> None:
        outside = Path(self._tmp.name) / "outside-secret"
        outside.write_text("x", encoding="utf-8")
        _, wt, _ = self.ephemeral_wt("symesc")
        os.symlink(str(outside), os.path.join(wt, "link"))
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        self.assertFalse(inv["safe"])
        self.assertEqual(inv["refuse_reason"], "symlink_escape")

    def test_nested_repo_refuses(self) -> None:
        _, wt, _ = self.ephemeral_wt("nested")
        sub = Path(wt, "vendored")
        sub.mkdir()
        Path(sub, "file.txt").write_text("x", encoding="utf-8")  # ensure git lists vendored/
        git(str(sub), "init", "-q", ".")
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        self.assertFalse(inv["safe"])
        self.assertEqual(inv["refuse_reason"], "nested_repo")

    def test_deep_nested_dot_git_refuses_before_manifesting_descendants(self) -> None:
        _, wt, _ = self.ephemeral_wt("deep-nested")
        nested = Path(wt, "one", "two", "three", ".git")
        nested.mkdir(parents=True)
        Path(nested, "config").write_text("private-path=/do/not/render\n", encoding="utf-8")
        t = self.targets(wt)
        result = self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"])
        inv = json.loads(result.stdout)
        self.assertFalse(inv["safe"])
        self.assertEqual(inv["refuse_reason"], "nested_repo")
        self.assertNotIn("private-path", result.stdout)

    def test_special_file_refuses(self) -> None:
        # git does not enumerate a BARE untracked FIFO, so the git-reachable special-file case is a
        # TRACKED file replaced by a FIFO on disk (reported as worktree-modified, then lstat'd).
        _, wt, _ = self.ephemeral_wt("fifo")
        f = os.path.join(wt, "f")
        Path(f).write_text("regular\n", encoding="utf-8")
        commit_all(wt, "add regular f")
        os.remove(f)
        try:
            os.mkfifo(f)
        except (AttributeError, OSError):
            self.skipTest("mkfifo unavailable")
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        self.assertFalse(inv["safe"])
        self.assertEqual(inv["refuse_reason"], "special_file")

    def test_discarded_ignored_dir_with_fifo_refuses_special_file(self) -> None:
        # `git status --ignored=matching` COLLAPSES an ignored dir to ONE entry (`!! cache_dir/`),
        # so the enumeration lstat's ONLY the dir — a FIFO INSIDE would be silently rm -rf'd on a
        # discard. build_inventory must RECURSE (bounded, no-follow) into the discard-set dir and
        # refuse `special_file`. (A bare untracked FIFO-only dir is invisible to git under -uall;
        # an ignored dir is the deterministic collapse vehicle that exercises the recursion.)
        _, wt, _ = self.ephemeral_wt("dirfifo", {".gitignore": "cache_dir/\n"})
        d = Path(wt, "cache_dir")
        d.mkdir()
        try:
            os.mkfifo(str(d / "pipe"))
        except (AttributeError, OSError):
            self.skipTest("mkfifo unavailable")
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        self.assertFalse(inv["safe"], inv)
        self.assertEqual(inv["refuse_reason"], "special_file")

    def test_discarded_ignored_dir_with_escaping_symlink_refuses(self) -> None:
        # Same collapse, escaping-symlink descendant: the recursion must refuse `symlink_escape` so
        # a `git worktree remove --force` never rm -rf's through a link pointing OUT of the root.
        outside = Path(self._tmp.name) / "escape-target"
        outside.mkdir()
        _, wt, _ = self.ephemeral_wt("dirsym", {".gitignore": "cache_dir/\n"})
        d = Path(wt, "cache_dir")
        d.mkdir()
        os.symlink(str(outside), str(d / "out"))
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        self.assertFalse(inv["safe"], inv)
        self.assertEqual(inv["refuse_reason"], "symlink_escape")

    def test_parse_status_z_empty_rename_source_raises(self) -> None:
        # An R/C record whose second (source) path is EMPTY is malformed/truncated: parsing RAISES
        # (safe-direction refuse) instead of lstat'ing the empty path, which would resolve to ROOT.
        with self.assertRaises(FIN.FinishError):
            FIN._parse_status_z(b"R  dest\x00\x00")
        # a well-formed rename still parses (regression guard for the same code path).
        self.assertEqual(FIN._parse_status_z(b"R  dest\x00orig\x00"), [("R ", b"dest", b"orig")])

    def test_control_bidi_markdown_escaped(self) -> None:
        # paths/descriptions are DATA: control chars, RLO bidi, and markdown metachars are escaped.
        name = "a\u202eevil`*_[x].txt"
        _, wt, _ = self.ephemeral_wt("escape", {name: "x"})
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        disp = inv["entries"][0]["display"]
        self.assertNotIn("\u202e", disp, "the bidi override must be escaped")
        self.assertIn("\\u202e", disp)
        self.assertIn("\\`", disp)
        self.assertIn("\\*", disp)

    def test_all_control_ranges_and_real_c1_filename_are_escaped(self) -> None:
        controls = (
            list(range(0x00, 0x20))
            + list(range(0x7F, 0xA0))
            + sorted(FIN._BIDI_CODEPOINTS)
            + list(range(0xD800, 0xE000))
        )
        for codepoint in controls:
            with self.subTest(codepoint=hex(codepoint)):
                escaped = FIN.escape_for_display(chr(codepoint))
                self.assertNotIn(chr(codepoint), escaped)
                self.assertTrue(escaped.startswith(("\\u", "\\x")), escaped)

        c1_name = "c1-" + "".join(chr(cp) for cp in range(0x80, 0xA0)) + ".txt"
        _, wt, _ = self.ephemeral_wt("c1-real-name", {c1_name: "x"})
        target = self.targets(wt)
        inventory = FIN.build_inventory(wt, target["git_dir"])
        self.assertTrue(inventory["safe"], inventory)
        rows = FIN.render_rows(inventory)
        for cp in range(0x80, 0xA0):
            self.assertNotIn(chr(cp), rows)
            self.assertIn(f"\\u{cp:04x}", rows)

    def test_real_staged_deletion_and_dd_conflict_are_deterministic_absent_objects(self) -> None:
        _, wt, _ = self.ephemeral_wt("absent-statuses")
        victim = Path(wt, "victim.txt")
        victim.write_text("base\n", encoding="utf-8")
        commit_all(wt, "add victim")
        target = self.targets(wt)
        git(wt, "rm", "-q", "victim.txt")
        first = FIN.build_inventory(wt, target["git_dir"])
        second = FIN.build_inventory(wt, target["git_dir"])
        self.assertTrue(first["safe"], first)
        self.assertEqual(first, second)
        row = next(item for item in first["entries"] if item["path"] == "victim.txt")
        self.assertEqual((row["code"], row["kind"]), ("D ", "absent"))
        selected = FIN.selected_snapshot(wt, ["victim.txt"])
        self.assertEqual(selected["entries"], [{"path": "victim.txt", "type": "absent"}])
        incarnation = FIN.capture_physical_incarnations(wt, target["git_dir"])
        kwargs = {
            "root": wt, "git_dir": target["git_dir"],
            "common_dir": target["common_dir"], "branch": target["branch"],
            "head": target["head"], "membership": [],
            "root_incarnation": incarnation[0],
            "git_dir_incarnation": incarnation[1],
        }
        self.assertEqual(
            FIN.compute_fingerprint(first, **kwargs),
            FIN.compute_fingerprint(second, **kwargs))

        _, dd_wt, _ = self.ephemeral_wt("dd-absent-status")
        dd_victim = Path(dd_wt, "victim.txt")
        dd_victim.write_text("base\n", encoding="utf-8")
        commit_all(dd_wt, "add victim")
        dd_target = self.targets(dd_wt)
        blob = git(dd_wt, "rev-parse", "HEAD:victim.txt").stdout.strip()
        dd_victim.unlink()
        git(dd_wt, "update-index", "--force-remove", "victim.txt")
        conflict = subprocess.run(
            ["git", "-C", dd_wt, "update-index", "-z", "--index-info"],
            input=f"100644 {blob} 1\tvictim.txt\0".encode(),
            capture_output=True)
        self.assertEqual(conflict.returncode, 0, conflict.stderr)
        status = subprocess.run(
            ["git", "-C", dd_wt, "status", "--porcelain=v1", "-z"],
            capture_output=True, check=True).stdout
        self.assertTrue(status.startswith(b"DD victim.txt\0"), status)
        dd_first = FIN.build_inventory(dd_wt, dd_target["git_dir"])
        dd_second = FIN.build_inventory(dd_wt, dd_target["git_dir"])
        self.assertTrue(dd_first["safe"], dd_first)
        self.assertEqual(dd_first, dd_second)
        dd_row = next(item for item in dd_first["entries"] if item["path"] == "victim.txt")
        self.assertEqual((dd_row["code"], dd_row["class"], dd_row["kind"]),
                         ("DD", "conflicted", "absent"))

        impossible_objects = FIN._capture_complete_tree(dd_wt)
        with mock.patch.object(
                FIN, "_proof_inputs",
                return_value=(
                    b" M impossible.txt\0", b"",
                    bytes.fromhex(dd_first["raw_index_hex"]),
                    dd_first["operation_manifest"], impossible_objects)):
            impossible = FIN.build_inventory(dd_wt, dd_target["git_dir"])
        self.assertFalse(impossible["safe"])
        self.assertEqual(impossible["refuse_reason"], "status_object_missing")

    def test_non_utf8_path_bytes_are_escaped_in_operator_rows(self) -> None:
        display = FIN.escape_for_display(os.fsdecode(b"raw-\xff.txt"))
        rows = FIN.render_rows({"entries": [{
            "display": display, "sentence": "A file not tracked by Git.",
            "hidden": False, "retained": False,
        }]})
        self.assertIn(r"raw-\xff.txt", rows)
        rows.encode("utf-8")

    def test_nul_safe_spaces_and_unicode_and_rename(self) -> None:
        repo = self.make_repo("nul")
        wt = repo + ".wt"
        git(repo, "worktree", "add", "-q", "-b", "cursor/worktree/nul", wt, "main")
        # commit a file FIRST, then a staged rename exercises the two-path -z record parse.
        Path(wt, "orig.txt").write_text("z\n", encoding="utf-8")
        commit_all(wt, "add orig")
        git(wt, "mv", "orig.txt", "renamed.txt")
        # untracked names with a space + non-ASCII exercise NUL-safe enumeration.
        Path(wt, "a file.txt").write_text("x", encoding="utf-8")
        Path(wt, "unicodé.txt").write_text("y", encoding="utf-8")
        t = self.targets(wt)
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", t["git_dir"]).stdout)
        self.assertTrue(inv["safe"], inv)
        paths = {e["path"] for e in inv["entries"]}
        self.assertIn("a file.txt", paths)
        self.assertIn("unicodé.txt", paths)
        self.assertTrue(any(e["class"] == "renamed" for e in inv["entries"]), inv["entries"])

    def test_operation_markers_detected(self) -> None:
        _, wt, _ = self.ephemeral_wt("markers")
        gd = self.targets(wt)["git_dir"]
        oid = git(wt, "rev-parse", "HEAD").stdout.strip()
        Path(gd, "MERGE_HEAD").write_text(oid + "\n", encoding="utf-8")
        inv = json.loads(self.run_lib("inventory", "--root", wt, "--git-dir", gd).stdout)
        self.assertIn("merge", inv["markers"])


# =====================================================================================
# (a) DETERMINISM gate
# =====================================================================================
class DeterminismGateTest(FinishBase):
    def _fp_cli(self, wt: str, env: dict) -> str:
        t = self.targets(wt)
        r = self.run_lib("fingerprint", "--root", wt, "--git-dir", t["git_dir"],
                         "--common-dir", t["common_dir"], "--branch", t["branch"],
                         "--head", t["head"], env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)["fingerprint"]

    def _private_fp(self, wt: str) -> tuple[str, dict]:
        t = self.targets(wt)
        inv = FIN.build_inventory(wt, t["git_dir"])
        self.assertTrue(inv["safe"], inv)
        return FIN.compute_fingerprint(
            inv, root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
            branch=t["branch"], head=t["head"], membership=[]), inv

    def test_fingerprint_stable_across_repeated_runs(self) -> None:
        _, wt, _ = self.ephemeral_wt("det", {"a.txt": "1", "b/c.txt": "2", ".env": "x"})
        fps = {self._fp_cli(wt, self.env()) for _ in range(5)}
        self.assertEqual(len(fps), 1, f"fingerprint not stable across runs: {fps}")

    def test_fingerprint_independent_of_locale(self) -> None:
        _, wt, _ = self.ephemeral_wt("loc", {"a.txt": "1", "ünïcode.txt": "2"})
        seen = set()
        for loc in ({"LC_ALL": "C", "LANG": "C"},
                    {"LC_ALL": "POSIX", "LANG": "POSIX"},
                    {"LC_ALL": "", "LANG": ""}):
            seen.add(self._fp_cli(wt, self.env(extra=loc)))
        self.assertEqual(len(seen), 1, f"fingerprint is locale-dependent: {seen}")

    def test_fingerprint_independent_of_entry_ordering(self) -> None:
        # OS directory ordering is irrelevant: the manifest is canonically re-sorted, so a shuffled
        # entries list yields a byte-identical fingerprint.
        _, wt, _ = self.ephemeral_wt("order", {"a": "1", "b": "2", "c": "3", "d/e": "4"})
        t = self.targets(wt)
        inv = FIN.build_inventory(wt, t["git_dir"])
        shuffled = copy.deepcopy(inv)
        shuffled["entries"] = list(reversed(shuffled["entries"]))
        shuffled["objects"] = list(reversed(shuffled["objects"]))
        kw = dict(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                  branch=t["branch"], head=t["head"], membership=[])
        self.assertEqual(FIN.compute_fingerprint(inv, **kw),
                         FIN.compute_fingerprint(shuffled, **kw))

    def test_fingerprint_changes_when_hidden_cruft_changes(self) -> None:
        # Hidden cruft is OMITTED from operator rows but INCLUDED in the fingerprint, so a race /
        # new file (even ignored/cruft) invalidates a pending challenge.
        _, wt, _ = self.ephemeral_wt("race", {"keep.txt": "k"})
        fp1 = self._fp_cli(wt, self.env())
        Path(wt, "node_modules").mkdir()
        Path(wt, "node_modules", "new.js").write_text("x", encoding="utf-8")
        fp2 = self._fp_cli(wt, self.env())
        self.assertNotEqual(fp1, fp2, "a new hidden cruft file must change the fingerprint")

    def test_same_size_content_mode_and_link_target_drift_change_proof(self) -> None:
        _, wt, _ = self.ephemeral_wt(
            "object-drift", {"draft.txt": "AAAA", "one": "1", "two": "2"})
        os.symlink("one", Path(wt, "current"))
        fp1, inv1 = self._private_fp(wt)
        draft = Path(wt, "draft.txt")
        draft.write_text("BBBB", encoding="utf-8")
        fp2, inv2 = self._private_fp(wt)
        self.assertNotEqual(fp1, fp2, "same-size bytes must remain content-addressed")
        draft.chmod(0o700)
        fp3, inv3 = self._private_fp(wt)
        self.assertNotEqual(fp2, fp3, "permission mode bits must remain content-addressed")
        Path(wt, "current").unlink()
        os.symlink("two", Path(wt, "current"))
        fp4, inv4 = self._private_fp(wt)
        self.assertNotEqual(fp3, fp4, "symlink target bytes must remain content-addressed")
        draft_hex = os.fsencode("draft.txt").hex()
        self.assertNotEqual(
            next(x for x in inv1["objects"] if x["path_hex"] == draft_hex)["sha256"],
            next(x for x in inv2["objects"] if x["path_hex"] == draft_hex)["sha256"])
        self.assertNotEqual(
            next(x for x in inv2["objects"] if x["path_hex"] == draft_hex)["mode"],
            next(x for x in inv3["objects"] if x["path_hex"] == draft_hex)["mode"])
        link_hex = os.fsencode("current").hex()
        self.assertNotEqual(
            next(x for x in inv3["objects"] if x["path_hex"] == link_hex)["target_hex"],
            next(x for x in inv4["objects"] if x["path_hex"] == link_hex)["target_hex"])

    def test_grouped_ignored_directory_has_one_row_but_complete_descendant_proof(self) -> None:
        _, wt, _ = self.ephemeral_wt("ignored-proof", {".gitignore": "cache/\n"})
        commit_all(wt, "ignore cache")
        cache = Path(wt, "cache")
        cache.mkdir()
        (cache / "a.bin").write_text("one", encoding="utf-8")
        fp1, inv1 = self._private_fp(wt)
        ignored_rows = [e for e in inv1["entries"] if e["class"] == "ignored"]
        self.assertEqual(len(ignored_rows), 1, ignored_rows)
        descendants = [
            bytes.fromhex(o["path_hex"]).decode("utf-8")
            for o in inv1["objects"] if bytes.fromhex(o["path_hex"]).startswith(b"cache/")
        ]
        self.assertEqual(descendants, sorted(descendants))
        self.assertIn("cache/a.bin", descendants)

        (cache / "a.bin").write_text("two", encoding="utf-8")
        fp2, _ = self._private_fp(wt)
        (cache / "b.bin").write_text("new", encoding="utf-8")
        fp3, _ = self._private_fp(wt)
        (cache / "a.bin").unlink()
        fp4, _ = self._private_fp(wt)
        self.assertEqual(len({fp1, fp2, fp3, fp4}), 4)


# =====================================================================================
# Literal-Close authorization + content-addressed challenge
# =====================================================================================
class AuthorizeChallengeTest(FinishBase):
    def test_is_literal_close_exact_only(self) -> None:
        self.assertTrue(FIN.is_literal_close("Close"))
        for bad in ("close", "CLOSE", "cLoSe", "Close\n", " Close ", "\tClose\t",
                    "Close please", "please Close", "yes", "true", "", "Close.",
                    "Closed", None, True, 1, ["Close"]):
            self.assertFalse(FIN.is_literal_close(bad), repr(bad))

    def test_authorize_requires_fingerprint_byte_equal(self) -> None:
        ch = {"fingerprint": "abc"}
        self.assertEqual(FIN.authorize("Close", ch, current_fingerprint="abc"), (True, "authorized"))
        self.assertEqual(FIN.authorize("Close", ch, current_fingerprint="xyz")[0], False)
        self.assertEqual(FIN.authorize("close", ch, current_fingerprint="abc")[0], False)

    def test_challenge_replay_once(self) -> None:
        _, wt, _ = self.ephemeral_wt("replay", {"a": "1"})
        self.preview(wt, conv="c1")
        r1 = self.run_lib("challenge-consume", "--conversation-id", "c1")
        self.assertIn("true", r1.stdout)
        r2 = self.run_lib("challenge-consume", "--conversation-id", "c1")
        self.assertIn("false", r2.stdout, "a consumed challenge must not consume again (replay-safe)")

    def test_challenge_stale_backstop_discards(self) -> None:
        _, wt, _ = self.ephemeral_wt("stale", {"a": "1"})
        self.preview(wt, conv="c2")
        # age the challenge well past the default backstop (content-addressed auth is unaffected;
        # this is only the abandoned-challenge cleanup backstop).
        cp = Path(FIN.challenge_path("c2"))
        rec = json.loads(cp.read_text(encoding="utf-8"))
        rec["created_at_epoch"] = FIN._now_epoch() - 100_000
        rec["created_at"] = FIN._iso_from_epoch(rec["created_at_epoch"])
        cp.write_text(json.dumps(rec), encoding="utf-8")
        r = self.run_lib("challenge-read", "--conversation-id", "c2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stale", r.stdout)
        # the backstop DISCARDS the abandoned challenge, so a second read is absent.
        r2 = self.run_lib("challenge-read", "--conversation-id", "c2")
        self.assertIn("absent", r2.stdout)

    def test_stale_expiry_cas_preserves_concurrent_new_generation(self) -> None:
        _, wt, _ = self.ephemeral_wt("stale-race", {"a": "1"})
        self.preview(wt, conv="stale-race")
        cp = Path(FIN.challenge_path("stale-race"))
        stale = json.loads(cp.read_text(encoding="utf-8"))
        stale["created_at_epoch"] = FIN._now_epoch() - 100_000
        stale["created_at"] = FIN._iso_from_epoch(stale["created_at_epoch"])
        FIN._write_private(str(cp), json.dumps(stale))
        newer = copy.deepcopy(stale)
        newer["nonce"] = "concurrent-new-generation"
        newer["generation"] += 1
        newer["created_at_epoch"] = FIN._now_epoch()
        newer["created_at"] = FIN._iso_from_epoch(newer["created_at_epoch"])
        real_delete = FIN.delete_challenge

        def replace_then_delete(*args, **kwargs):
            FIN._write_private(str(cp), json.dumps(newer))
            return real_delete(*args, **kwargs)

        FIN.delete_challenge = replace_then_delete
        try:
            challenge, status = FIN.read_challenge("stale-race")
        finally:
            FIN.delete_challenge = real_delete
        self.assertIsNone(challenge)
        self.assertEqual(status, "stale")
        surviving, surviving_status = FIN._read_challenge_raw("stale-race")
        self.assertEqual(surviving_status, "ok")
        self.assertEqual(surviving["nonce"], newer["nonce"])
        self.assertEqual(surviving["generation"], newer["generation"])

    def test_stale_expiry_lock_busy_reports_stale_without_delete(self) -> None:
        _, wt, _ = self.ephemeral_wt("stale-lock-busy", {"a": "1"})
        self.preview(wt, conv="stale-lock-busy")
        cp = Path(FIN.challenge_path("stale-lock-busy"))
        stale = json.loads(cp.read_text(encoding="utf-8"))
        stale["created_at_epoch"] = FIN._now_epoch() - 100_000
        stale["created_at"] = FIN._iso_from_epoch(stale["created_at_epoch"])
        FIN._write_private(str(cp), json.dumps(stale))
        with FIN.common_dir_lock(stale["common_dir"], blocking=False):
            challenge, status = FIN.read_challenge("stale-lock-busy")
        self.assertIsNone(challenge)
        self.assertEqual(status, "stale")
        surviving, surviving_status = FIN._read_challenge_raw("stale-lock-busy")
        self.assertEqual(surviving_status, "ok")
        self.assertEqual(surviving["nonce"], stale["nonce"])
        self.assertEqual(surviving["generation"], stale["generation"])

    def test_generation_qualified_consume_is_exact_and_replay_safe(self) -> None:
        _, wt, _ = self.ephemeral_wt("consume-cas", {"a": "1"})
        challenge = self.preview(wt, conv="consume-cas")
        self.assertTrue(FIN.consume_challenge(
            "consume-cas", expected_nonce=challenge["nonce"],
            expected_generation=challenge["generation"]))
        self.assertFalse(FIN.consume_challenge(
            "consume-cas", expected_nonce=challenge["nonce"],
            expected_generation=challenge["generation"]))
        _, status = FIN.read_challenge("consume-cas")
        self.assertEqual(status, "absent")

    def test_challenge_delete_is_noop_cancel(self) -> None:
        _, wt, _ = self.ephemeral_wt("cancel", {"a": "1"})
        self.preview(wt, conv="c3")
        self.assertTrue(Path(wt, "a").exists())
        self.run_lib("challenge-delete", "--conversation-id", "c3")
        r = self.run_lib("challenge-read", "--conversation-id", "c3")
        self.assertIn("absent", r.stdout)
        self.assertTrue(Path(wt, "a").exists(), "cancel performs no mutation")

    def test_challenge_and_generation_timestamps_are_single_sample_and_migrate_one_second(self) -> None:
        _, wt, _ = self.ephemeral_wt("canonical-times")
        target = self.targets(wt)
        physical = FIN.capture_physical_incarnations(wt, target["git_dir"])
        epoch = FIN._now_epoch()
        with mock.patch.object(FIN, "_now_epoch", side_effect=[epoch]) as clock:
            challenge = FIN.create_challenge(
                conversation_id="canonical-times", root=wt,
                git_dir=target["git_dir"], common_dir=target["common_dir"],
                branch=target["branch"], head=target["head"], fingerprint="f",
                markers=[], membership=[], root_incarnation=physical[0],
                git_dir_incarnation=physical[1])
        self.assertEqual(clock.call_count, 1)
        self.assertEqual(challenge["created_at_epoch"], epoch)
        self.assertEqual(challenge["created_at"], FIN._iso_from_epoch(epoch))

        challenge_path = Path(FIN.challenge_path("canonical-times"))
        legacy = json.loads(challenge_path.read_text(encoding="utf-8"))
        legacy["created_at"] = FIN._iso_from_epoch(epoch + 1)
        challenge_path.write_text(json.dumps(legacy), encoding="utf-8")
        migrated, status = FIN.read_challenge("canonical-times")
        self.assertEqual(status, "ok")
        self.assertEqual(migrated["created_at"], FIN._iso_from_epoch(epoch))
        self.assertEqual(
            json.loads(challenge_path.read_text(encoding="utf-8"))["created_at"],
            FIN._iso_from_epoch(epoch))

        with mock.patch.object(FIN, "_now_epoch", side_effect=[epoch + 5]) as clock:
            generation = FIN._generation_state_record(
                transition="cancelled", conversation_id="canonical-generation",
                nonce="nonce", generation=1, root=wt,
                common_dir=target["common_dir"], session_key_value="session")
        self.assertEqual(clock.call_count, 1)
        self.assertEqual(generation["created_at"], FIN._iso_from_epoch(epoch + 5))
        generation_path = Path(FIN.generation_state_path(
            "canonical-generation", "nonce", 1))
        FIN._write_private(str(generation_path), json.dumps({
            **generation,
            "created_at": FIN._iso_from_epoch(generation["created_at_epoch"] - 1),
        }))
        migrated_generation, generation_status = FIN.read_generation_state(
            "canonical-generation", "nonce", 1)
        self.assertEqual(generation_status, "ok")
        self.assertEqual(
            migrated_generation["created_at"],
            FIN._iso_from_epoch(generation["created_at_epoch"]))
        malformed_generation = dict(migrated_generation)
        malformed_generation["created_at"] = FIN._iso_from_epoch(
            generation["created_at_epoch"] + 2)
        generation_path.write_text(
            json.dumps(malformed_generation), encoding="utf-8")
        generation_before = generation_path.read_bytes()
        self.assertEqual(
            FIN.read_generation_state(
                "canonical-generation", "nonce", 1)[1],
            "malformed")
        self.assertEqual(generation_path.read_bytes(), generation_before)

        malformed = dict(migrated)
        malformed["created_at"] = FIN._iso_from_epoch(epoch + 2)
        challenge_path.write_text(json.dumps(malformed), encoding="utf-8")
        before = challenge_path.read_bytes()
        self.assertEqual(FIN.read_challenge("canonical-times")[1], "malformed")
        self.assertEqual(challenge_path.read_bytes(), before)


# =====================================================================================
# (c) IDENTICAL-REFUSAL gate: every non-Close / stale / replayed / cross-* refuses + preserves
# =====================================================================================
class IdenticalRefusalGateTest(FinishBase):
    def _assert_preserved(self, wt: str, res: dict) -> None:
        self.assertEqual(res["outcome"], "refused", res)
        self.assertTrue(Path(wt).exists(), "a refusal MUST preserve the worktree")

    def test_non_close_variants_all_refuse(self) -> None:
        _, wt, _ = self.ephemeral_wt("nonclose", {"a": "1"})
        self.preview(wt)
        for ans in ("close", "CLOSE", "cLoSe", " Close ", "Close\n",
                    "Close please", "yes", "true", ""):
            res, _ = self.execute(wt, ans)
            self.assertEqual((res["outcome"], res["reason"]), ("refused", "not_close"), ans)
            self.assertTrue(Path(wt).exists())

    def test_no_challenge_refuses(self) -> None:
        _, wt, _ = self.ephemeral_wt("nochal", {"a": "1"})
        res, _ = self.execute(wt, "Close", conv="never-previewed")
        self._assert_preserved(wt, res)
        self.assertEqual(res["receipt_code"], "finish_no_challenge")

    def test_replay_once_challenge_consumed_on_removal(self) -> None:
        _, wt, _ = self.ephemeral_wt("replay2", {"a": "1"})
        self.preview(wt, conv="r2")
        res1, _ = self.execute(wt, "Close", conv="r2")
        self.assertEqual(res1["outcome"], "removed", res1)
        self.assertFalse(Path(wt).exists())
        # the challenge is consumed EXACTLY once on the terminal removal; a replay finds none.
        r = self.run_lib("challenge-read", "--conversation-id", "r2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("absent", r.stdout)

    def test_fingerprint_drift_refuses(self) -> None:
        _, wt, _ = self.ephemeral_wt("drift", {"a": "1"})
        self.preview(wt, conv="d1")
        Path(wt, "surprise.txt").write_text("new work appeared", encoding="utf-8")
        res, _ = self.execute(wt, "Close", conv="d1")
        self._assert_preserved(wt, res)
        self.assertEqual(res["receipt_code"], "finish_fingerprint_mismatch")

    def test_cross_root_challenge_refuses(self) -> None:
        # A challenge minted for worktree A must not authorize removing worktree B (same conv id).
        _, wt_a, _ = self.ephemeral_wt("rootA", {"a": "1"})
        _, wt_b, _ = self.ephemeral_wt("rootB", {"b": "1"})
        self.preview(wt_a, conv="shared")
        res, _ = self.execute(wt_b, "Close", conv="shared")
        self._assert_preserved(wt_b, res)
        self.assertEqual(res["receipt_code"], "finish_target_mismatch")
        self.assertTrue(Path(wt_a).exists())

    def test_boot_id_tamper_refuses_target_mismatch(self) -> None:
        # The challenge binds boot_id, so one minted before a reboot can NEVER authorize a removal
        # on a later boot (a reused pid/path could otherwise alias). Tamper the STORED boot_id ->
        # the target-match check refuses (challenge_target_mismatch -> finish_target_mismatch) and
        # preserves. boot_id is NOT in the fingerprint, so this proves the dedicated target bind.
        _, wt, _ = self.ephemeral_wt("bootid", {"a": "1"})
        self.preview(wt, conv="bi")
        cp = Path(FIN.challenge_path("bi"))
        rec = json.loads(cp.read_text(encoding="utf-8"))
        rec["boot_id"] = str(rec.get("boot_id", "")) + "-TAMPERED-NEXT-BOOT"
        cp.write_text(json.dumps(rec), encoding="utf-8")
        res, _ = self.execute(wt, "Close", conv="bi")
        self._assert_preserved(wt, res)
        self.assertEqual(res["receipt_code"], "finish_target_mismatch")

    def test_changed_or_empty_install_identity_refuses_under_execution_lock(self) -> None:
        for changed in ("different-install", ""):
            with self.subTest(changed=changed):
                _, wt, _ = self.ephemeral_wt(
                    "install-id-" + (changed or "empty"), {"a": "1"})
                conversation = "install-id-" + (changed or "empty")
                self.preview(wt, conv=conversation)
                challenge, status = FIN._read_challenge_raw(conversation)
                self.assertEqual(status, "ok")
                self.assertTrue(challenge["install_id"])
                target = self.targets(wt)
                with mock.patch.object(FIN, "install_id", return_value=changed):
                    res = FIN.finish_execute(
                        root=wt, **target, session_id="sess",
                        conversation_id=conversation,
                        answer="Close")
                self._assert_preserved(wt, res)
                self.assertEqual(res["receipt_code"], "finish_target_mismatch")
                current, status = FIN.read_challenge(
                    conversation)
                self.assertEqual(status, "ok")
                self.assertEqual(current["nonce"], challenge["nonce"])

    def test_cross_session_fresh_blocks(self) -> None:
        # Another fresh session (heartbeat present BEFORE preview so the fingerprint is stable)
        # blocks the finish via the per-session gate.
        _, wt, _ = self.ephemeral_wt("xsess", {"a": "1"})
        t = self.targets(wt)
        subprocess.run(["python3", str(_ROOTS_PY), "heartbeat", "--root", wt,
                        "--branch", t["branch"], "--common-dir", t["common_dir"],
                        "--session-id", "OTHER-LIVE-SESSION"],
                       env=self.env(), capture_output=True, text=True, check=True)
        self.preview(wt, conv="xs", session="CONFIRMING")
        res, _ = self.execute(wt, "Close", conv="xs", session="CONFIRMING")
        self._assert_preserved(wt, res)
        self.assertEqual(res["receipt_code"], "finish_session_blocked")


# =====================================================================================
# Per-session heartbeat gate (finish-only) — unit level on awa_roots
# =====================================================================================
class SessionGateTest(FinishBase):
    def _hb(self, root, session_id, branch="cursor/worktree/x", common="/c", pid=None, boot=None):
        AR.heartbeat(root, branch=branch, common_dir=common, session_id=session_id,
                     pid=pid, boot=boot)

    def test_confirming_pidless_fresh_is_waived(self) -> None:
        root = str(self.data_home / "wv"); os.makedirs(root, exist_ok=True)
        self._hb(root, "me", common="/c", branch="cursor/worktree/x")
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"),
                                   branch="cursor/worktree/x", common_dir="/c")
        self.assertFalse(v["blocked"], v)
        self.assertTrue(v.get("waived"))

    def test_other_fresh_session_blocks(self) -> None:
        root = str(self.data_home / "ot"); os.makedirs(root, exist_ok=True)
        self._hb(root, "other", common="/c", branch="cursor/worktree/x")
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"),
                                   branch="cursor/worktree/x", common_dir="/c")
        self.assertTrue(v["blocked"])
        self.assertEqual(v["reason"], "other_session_fresh")

    def test_any_live_pid_blocks_even_confirming(self) -> None:
        root = str(self.data_home / "lp"); os.makedirs(root, exist_ok=True)
        self._hb(root, "me", common="/c", branch="cursor/worktree/x",
                 pid=os.getpid(), boot=AR.boot_id())
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"),
                                   branch="cursor/worktree/x", common_dir="/c")
        self.assertTrue(v["blocked"])
        self.assertEqual(v["reason"], "pid_alive")

    def test_corrupt_record_blocks(self) -> None:
        root = str(self.data_home / "cor"); os.makedirs(root, exist_ok=True)
        self._hb(root, "me")
        Path(AR.record_path(root)).write_text("{ not json", encoding="utf-8")
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"))
        self.assertTrue(v["blocked"])
        self.assertEqual(v["reason"], "record_corrupt")

    def test_confirming_branch_mismatch_not_waived(self) -> None:
        root = str(self.data_home / "bm"); os.makedirs(root, exist_ok=True)
        self._hb(root, "me", common="/c", branch="cursor/worktree/x")
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"),
                                   branch="cursor/worktree/DIFFERENT", common_dir="/c")
        self.assertTrue(v["blocked"], "a confirming heartbeat on a different branch is not waivable")

    def test_stale_confirming_only_does_not_block(self) -> None:
        root = str(self.data_home / "st"); os.makedirs(root, exist_ok=True)
        self._hb(root, "me", common="/c", branch="cursor/worktree/x")
        # ttl=0 -> the confirming heartbeat is stale; a stale session neither blocks nor waives.
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"),
                                   branch="cursor/worktree/x", common_dir="/c", ttl=0)
        self.assertFalse(v["blocked"], v)

    def test_absent_record_does_not_block(self) -> None:
        root = str(self.data_home / "ab"); os.makedirs(root, exist_ok=True)
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("me"))
        self.assertFalse(v["blocked"])
        self.assertEqual(v["reason"], "no_record")

    def test_malformed_session_member_matrix_blocks_finish_only_as_malformed(self) -> None:
        def set_member(record, mutate):
            key = AR.session_key("me")
            mutate(record, key, record["sessions"][key])

        cases = {
            "pid_bool": lambda r, k, m: m.__setitem__("pid", True),
            "pid_string": lambda r, k, m: m.__setitem__("pid", "123"),
            "pid_zero": lambda r, k, m: m.__setitem__("pid", 0),
            "pid_negative": lambda r, k, m: m.__setitem__("pid", -1),
            "session_identity": lambda r, k, m: m.__setitem__("session_id", "other"),
            "boot": lambda r, k, m: m.__setitem__("boot_id", "different-boot"),
            "branch": lambda r, k, m: m.__setitem__("branch", "different-branch"),
            "common_dir": lambda r, k, m: m.__setitem__("git_common_dir", "/different"),
            "first_seen": lambda r, k, m: m.__setitem__("first_seen", "not-a-time"),
            "last_heartbeat": lambda r, k, m: m.__setitem__(
                "last_heartbeat", "not-a-time"),
            "epoch_bool": lambda r, k, m: m.__setitem__("last_heartbeat_epoch", True),
            "epoch_string": lambda r, k, m: m.__setitem__(
                "last_heartbeat_epoch", "123"),
            "epoch_zero": lambda r, k, m: m.__setitem__("last_heartbeat_epoch", 0),
            "non_object": lambda r, k, m: r["sessions"].__setitem__(k, "bad"),
            "bad_key": lambda r, k, m: (
                r["sessions"].pop(k), r["sessions"].__setitem__("wrong-key", m)),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                root = str(self.data_home / ("malformed-" + label))
                os.makedirs(root, exist_ok=True)
                record = AR.heartbeat(
                    root, session_id="me", branch="cursor/worktree/x",
                    common_dir="/c")
                set_member(record, mutate)
                Path(AR.record_path(root)).write_text(
                    json.dumps(record), encoding="utf-8")
                verdict = AR.finish_session_gate(
                    root, confirming_session_key=AR.session_key("me"),
                    branch="cursor/worktree/x", common_dir="/c")
                self.assertTrue(verdict["blocked"], verdict)
                self.assertEqual(verdict["reason"], "session_malformed", verdict)

    def test_missing_confirming_member_blocks_when_no_other_live_blocker(self) -> None:
        root = str(self.data_home / "confirming-missing")
        os.makedirs(root, exist_ok=True)
        record = AR.heartbeat(
            root, session_id="other", branch="cursor/worktree/x", common_dir="/c")
        member = record["sessions"][AR.session_key("other")]
        member["last_heartbeat_epoch"] -= 100000
        member["last_heartbeat"] = "2000-01-01T00:00:00Z"
        # Keep exact timestamp equality while making the evidence stale.
        member["last_heartbeat_epoch"] = 946684800
        member["first_seen"] = "2000-01-01T00:00:00Z"
        record["last_heartbeat_epoch"] = 946684800
        record["last_heartbeat"] = "2000-01-01T00:00:00Z"
        record["first_seen"] = "2000-01-01T00:00:00Z"
        Path(AR.record_path(root)).write_text(json.dumps(record), encoding="utf-8")
        verdict = AR.finish_session_gate(
            root, confirming_session_key=AR.session_key("me"),
            branch="cursor/worktree/x", common_dir="/c")
        self.assertTrue(verdict["blocked"], verdict)
        self.assertEqual(verdict["reason"], "session_malformed")
        self.assertEqual(verdict["detail"], "confirming_session_missing")

    def test_semantically_malformed_member_does_not_change_ordinary_disposition(self) -> None:
        root = str(self.data_home / "ordinary-compat")
        os.makedirs(root, exist_ok=True)
        record = AR.heartbeat(
            root, session_id="me", branch="cursor/worktree/x", common_dir="/c")
        record["sessions"][AR.session_key("me")]["pid"] = "not-an-int"
        Path(AR.record_path(root)).write_text(json.dumps(record), encoding="utf-8")
        ordinary = AR.disposition(root)
        self.assertEqual(ordinary["disposition"], "active")
        self.assertTrue(ordinary["blocks_removal"])
        finish = AR.finish_session_gate(
            root, confirming_session_key=AR.session_key("me"),
            branch="cursor/worktree/x", common_dir="/c")
        self.assertEqual((finish["blocked"], finish["reason"]),
                         (True, "session_malformed"))

    def test_malformed_member_after_preview_preserves_worktree_end_to_end(self) -> None:
        _, wt, _ = self.ephemeral_wt("malformed-e2e", {"draft": "keep"})
        target = self.targets(wt)
        AR.heartbeat(
            wt, session_id="me", branch=target["branch"],
            common_dir=target["common_dir"])
        preview = FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="me",
            conversation_id="malformed-e2e")
        self.assertTrue(preview["ok"])
        record_path = Path(AR.record_path(wt))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["sessions"][AR.session_key("me")]["pid"] = False
        record_path.write_text(json.dumps(record), encoding="utf-8")
        result = FIN.finish_execute(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="me",
            conversation_id="malformed-e2e", answer="Close")
        self.assertEqual(result["reason"], "session_malformed", result)
        self.assertTrue(Path(wt).exists())
        self.assertEqual(Path(wt, "draft").read_text(encoding="utf-8"), "keep")


# =====================================================================================
# Backward-compatible heartbeat migration (disposition() unchanged)
# =====================================================================================
class HeartbeatMigrationTest(FinishBase):
    def test_sessions_map_added_top_level_frozen(self) -> None:
        root = str(self.data_home / "mig"); os.makedirs(root, exist_ok=True)
        rec = AR.heartbeat(root, session_id="s1", branch="b", common_dir="/c")
        for k in ("schema", "root_path", "git_common_dir", "boot_id", "first_seen",
                  "last_heartbeat", "last_heartbeat_epoch"):
            self.assertIn(k, rec)
        self.assertIn("sessions", rec)
        self.assertIn(AR.session_key("s1"), rec["sessions"])

    def test_two_sessions_tracked_independently(self) -> None:
        root = str(self.data_home / "two"); os.makedirs(root, exist_ok=True)
        AR.heartbeat(root, session_id="s1", branch="b", common_dir="/c")
        rec = AR.heartbeat(root, session_id="s2", branch="b", common_dir="/c")
        self.assertEqual(set(rec["sessions"]), {AR.session_key("s1"), AR.session_key("s2")})

    def test_legacy_record_without_sessions_still_dispositions_active(self) -> None:
        # A pre-migration record (no `sessions`) must still classify + normalize safely.
        root = str(self.data_home / "leg"); os.makedirs(root, exist_ok=True)
        rec = AR.heartbeat(root, session_id="old", branch="b", common_dir="/c")
        rec.pop("sessions", None)
        Path(AR.record_path(root)).write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(AR.disposition(root)["disposition"], "active")
        # the finish gate synthesizes a legacy entry (keyed by the old session id) and waives it.
        v = AR.finish_session_gate(root, confirming_session_key=AR.session_key("old"),
                                   branch="b", common_dir="/c")
        self.assertFalse(v["blocked"], v)

    def test_corrupt_and_malformed_evidence_is_byte_preserved_and_mints_no_challenge(self) -> None:
        mutations = {
            "corrupt_json": lambda rec: b'{"schema":',
            "aggregate_epoch": lambda rec: json.dumps(
                {**rec, "last_heartbeat_epoch": "bad"}).encode(),
            "sessions_null": lambda rec: json.dumps(
                {**rec, "sessions": None}).encode(),
            "sessions_shape": lambda rec: json.dumps({**rec, "sessions": []}).encode(),
            "member_pid": lambda rec: json.dumps({
                **rec,
                "sessions": {
                    key: ({**member, "pid": "bad"} if key == AR.session_key("me")
                          else member)
                    for key, member in rec["sessions"].items()
                },
            }).encode(),
            "projection_mismatch": lambda rec: json.dumps({
                **rec, "branch": "different",
            }).encode(),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                _, wt, _ = self.ephemeral_wt("evidence-" + label)
                target = self.targets(wt)
                valid = AR.heartbeat(
                    wt, session_id="me", branch=target["branch"],
                    common_dir=target["common_dir"])
                record = Path(AR.record_path(wt))
                raw = mutate(valid)
                record.write_bytes(raw)
                heartbeat = AR.heartbeat(
                    wt, session_id="new", branch=target["branch"],
                    common_dir=target["common_dir"])
                self.assertFalse(heartbeat.get("ok", True), heartbeat)
                self.assertEqual(record.read_bytes(), raw)
                conversation = "malformed-" + label
                preview = FIN.preview(
                    root=wt, git_dir=target["git_dir"],
                    common_dir=target["common_dir"], branch=target["branch"],
                    head=target["head"], session_id="me",
                    conversation_id=conversation)
                self.assertFalse(preview["ok"], preview)
                self.assertEqual(preview["reason"], "session_malformed")
                self.assertEqual(record.read_bytes(), raw)
                self.assertEqual(FIN._read_challenge_raw(conversation)[1], "absent")

    def test_valid_legacy_record_migrates_only_during_locked_merge(self) -> None:
        _, wt, _ = self.ephemeral_wt("legacy-merge")
        target = self.targets(wt)
        legacy = AR.heartbeat(
            wt, session_id="old", branch=target["branch"],
            common_dir=target["common_dir"])
        legacy.pop("sessions")
        record = Path(AR.record_path(wt))
        record.write_text(json.dumps(legacy), encoding="utf-8")
        merged = AR.heartbeat(
            wt, session_id="new", branch=target["branch"],
            common_dir=target["common_dir"])
        self.assertEqual(
            set(merged["sessions"]),
            {AR.session_key("old"), AR.session_key("new")})
        evidence = AR.finish_session_evidence(
            wt, confirming_session_key=AR.session_key("new"),
            branch=target["branch"], common_dir=target["common_dir"])
        self.assertTrue(evidence["ok"], evidence)

    def test_concurrent_heartbeat_merges_never_lose_membership(self) -> None:
        _, wt, _ = self.ephemeral_wt("heartbeat-barrier")
        target = self.targets(wt)
        barrier = threading.Barrier(3)
        results: list[dict] = []

        def beat(session_id: str) -> None:
            barrier.wait()
            results.append(AR.heartbeat(
                wt, session_id=session_id, branch=target["branch"],
                common_dir=target["common_dir"]))

        threads = [
            threading.Thread(target=beat, args=("session-a",)),
            threading.Thread(target=beat, args=("session-b",)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertTrue(all(result.get("ok", True) for result in results), results)
        record = json.loads(Path(AR.record_path(wt)).read_text(encoding="utf-8"))
        self.assertEqual(
            set(record["sessions"]),
            {AR.session_key("session-a"), AR.session_key("session-b")})

    def test_heartbeat_before_finish_blocks_and_delayed_after_finish_cannot_recreate(self) -> None:
        _, blocked_wt, _ = self.ephemeral_wt("heartbeat-before", {"draft": "keep"})
        blocked_target = self.targets(blocked_wt)
        FIN.preview(
            root=blocked_wt, git_dir=blocked_target["git_dir"],
            common_dir=blocked_target["common_dir"], branch=blocked_target["branch"],
            head=blocked_target["head"], session_id="finisher",
            conversation_id="heartbeat-before")
        AR.heartbeat(
            blocked_wt, session_id="other", branch=blocked_target["branch"],
            common_dir=blocked_target["common_dir"])
        blocked = FIN.finish_execute(
            root=blocked_wt, git_dir=blocked_target["git_dir"],
            common_dir=blocked_target["common_dir"], branch=blocked_target["branch"],
            head=blocked_target["head"], session_id="finisher",
            conversation_id="heartbeat-before", answer="Close")
        self.assertEqual(blocked["outcome"], "refused", blocked)
        self.assertTrue(Path(blocked_wt).exists())

        _, removed_wt, _ = self.ephemeral_wt("finish-before-heartbeat", {"draft": "drop"})
        removed_target = self.targets(removed_wt)
        FIN.preview(
            root=removed_wt, git_dir=removed_target["git_dir"],
            common_dir=removed_target["common_dir"], branch=removed_target["branch"],
            head=removed_target["head"], session_id="finisher",
            conversation_id="finish-before-heartbeat")
        release = threading.Event()
        delayed_result: list[dict] = []

        def delayed_heartbeat() -> None:
            release.wait(10)
            delayed_result.append(AR.heartbeat(
                removed_wt, session_id="late", branch=removed_target["branch"],
                common_dir=removed_target["common_dir"]))

        thread = threading.Thread(target=delayed_heartbeat)
        thread.start()
        removed = FIN.finish_execute(
            root=removed_wt, git_dir=removed_target["git_dir"],
            common_dir=removed_target["common_dir"], branch=removed_target["branch"],
            head=removed_target["head"], session_id="finisher",
            conversation_id="finish-before-heartbeat", answer="Close")
        release.set()
        thread.join(timeout=10)
        self.assertEqual(removed["outcome"], "removed", removed)
        self.assertFalse(delayed_result[0].get("ok", True), delayed_result)
        self.assertEqual(delayed_result[0]["reason"], "heartbeat_target_root_absent")
        self.assertFalse(Path(AR.record_path(removed_wt)).exists())


# =====================================================================================
# Branch disposition (network-free, local refs only)
# =====================================================================================
class BranchDispositionTest(FinishBase):
    def _disp(self, wt: str, env: dict | None = None) -> dict:
        t = self.targets(wt)
        r = self.run_lib("branch-disposition", "--root", wt, "--branch", t["branch"],
                         "--head", t["head"], "--common-dir", t["common_dir"], env=env)
        return json.loads(r.stdout)

    def test_ephemeral_no_local_only_is_delete_eligible(self) -> None:
        _, wt, _ = self.ephemeral_wt("eph")
        self.assertEqual(self._disp(wt)["action"], "delete_eligible")

    def test_local_only_commits_retained(self) -> None:
        _, wt, _ = self.ephemeral_wt("lo")
        Path(wt, "work.txt").write_text("local\n", encoding="utf-8")
        commit_all(wt, "local only")
        self.assertEqual(self._disp(wt)["action"], "retain_local_only")

    def test_non_ephemeral_branch_retained(self) -> None:
        repo = self.make_repo("nonephem")
        wt = repo + ".wt"
        git(repo, "worktree", "add", "-q", "-b", "feature/keep", wt, "main")
        self.assertEqual(self._disp(wt)["action"], "retain")

    def test_protected_branch_never_deleted(self) -> None:
        self.assertFalse(FIN._is_ephemeral_branch("/x", "main", "/c"))
        self.assertFalse(FIN._is_ephemeral_branch("/x", "master", "/c"))


# =====================================================================================
# Durable removed-state transaction + exact current-session cleanup
# =====================================================================================
class RemovalJournalTest(FinishBase):
    def _prepare_only(self, wt: str, conversation: str, session: str = "sess") -> tuple[dict, dict]:
        target = self.targets(wt)
        preview = FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id=session,
            conversation_id=conversation)
        self.assertTrue(preview["ok"], preview)
        challenge, status = FIN._read_challenge_raw(conversation)
        self.assertEqual(status, "ok")
        inventory = FIN.build_inventory(wt, target["git_dir"])
        disposition = FIN.branch_disposition(
            wt, target["branch"], target["head"], target["common_dir"])
        identity = FIN._operation_identity_payload(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=conversation, nonce=challenge["nonce"],
            generation=challenge["generation"], session_id=session,
            session_key_value=AR.session_key(session), boot_id_value=challenge["boot_id"],
            install_id_value=challenge["install_id"],
            root_incarnation_value=challenge["root_incarnation"],
            git_dir_incarnation_value=challenge["git_dir_incarnation"],
            fingerprint=challenge["fingerprint"],
            execution_fingerprint=challenge["fingerprint"], claim="direct",
            branch_disposition_value=disposition,
            discard_count=len(inventory["entries"]))
        with FIN.common_dir_lock(target["common_dir"]):
            journal = FIN._prepare_removal_journal_locked(identity=identity)
        return target, journal

    def _downgrade_journal_to_legacy(self, journal: dict) -> dict:
        legacy = dict(journal)
        old_path = Path(FIN.removal_journal_path(legacy["operation_id"]))
        for key in (
                "install_id", "root_incarnation", "git_dir_incarnation",
                "execution_fingerprint"):
            legacy.pop(key)
        legacy["operation_id"] = FIN.finish_operation_id(
            **FIN._journal_identity(legacy))
        old_path.unlink()
        FIN._write_removal_journal(legacy)
        return legacy

    def test_pre_removal_interruption_never_reports_removed(self) -> None:
        _, wt, _ = self.ephemeral_wt("prepared-only", {"draft": "keep"})
        target, journal = self._prepare_only(wt, "prepared-only")
        contract = json.loads((_REPO_ROOT / "contracts" / "awa-contract.v1.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(
            set(journal), set(contract["awa_finish_removal"]["declared_keys"]))
        self.assertEqual(
            set(FIN.REMOVAL_PHASES),
            set(contract["awa_finish_removal"]["phase_values"]))
        self.assertEqual(
            Path(FIN.removal_journal_path(journal["operation_id"])).stat().st_mode & 0o777,
            0o600)
        changed_identity = FIN._journal_identity(journal)
        changed_identity["root_incarnation"] = dict(
            changed_identity["root_incarnation"])
        changed_identity["root_incarnation"]["ctime_ns"] += 1
        self.assertNotEqual(
            FIN.finish_operation_id(**changed_identity), journal["operation_id"])
        result = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="prepared-only", session_id="sess")
        self.assertEqual(result["outcome"], "not_removed", result)
        self.assertEqual(result["reason"], "pre_removal_interrupted")
        self.assertEqual(result["operation_id"], journal["operation_id"])
        self.assertTrue(Path(wt, "draft").exists())
        self.assertEqual(self.receipts(), [])

    def test_pre_execution_fingerprint_journal_remains_compatible(self) -> None:
        _, wt, _ = self.ephemeral_wt("prepared-pre-execution", {"draft": "keep"})
        target, journal = self._prepare_only(wt, "prepared-pre-execution")
        old_path = Path(FIN.removal_journal_path(journal["operation_id"]))
        prior = dict(journal)
        prior.pop("execution_fingerprint")
        prior["operation_id"] = FIN.finish_operation_id(
            **FIN._journal_identity(prior))
        old_path.unlink()
        FIN._write_removal_journal(prior)
        read_back, status = FIN.read_removal_journal(prior["operation_id"])
        self.assertEqual(status, "ok")
        self.assertEqual(read_back, prior)
        result = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="prepared-pre-execution", session_id="sess")
        self.assertEqual(result["outcome"], "not_removed", result)
        self.assertEqual(result["reason"], "pre_removal_interrupted")
        self.assertTrue(Path(wt, "draft").exists())

    def test_same_path_replacement_is_uncertain_and_preserves_journal(self) -> None:
        repo, wt, _ = self.ephemeral_wt("same-path-replacement", {"draft": "discard"})
        target, journal = self._prepare_only(wt, "same-path-replacement")
        removed = git(repo, "worktree", "remove", "--force", wt)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        recreated = git(repo, "worktree", "add", "-q", wt, target["branch"])
        self.assertEqual(recreated.returncode, 0, recreated.stderr)
        self.assertEqual(git(wt, "rev-parse", "HEAD").stdout.strip(), target["head"])
        result = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="same-path-replacement", session_id="sess")
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertEqual(result["reason"], "physical_incarnation_changed")
        self.assertTrue(Path(FIN.removal_journal_path(journal["operation_id"])).exists())
        self.assertTrue(Path(wt).exists())

    def test_legacy_journal_present_is_uncertain_but_absent_can_finalize(self) -> None:
        _, present_wt, _ = self.ephemeral_wt("legacy-present", {"draft": "keep"})
        present_target, present_journal = self._prepare_only(
            present_wt, "legacy-present")
        legacy_present = self._downgrade_journal_to_legacy(present_journal)
        present = FIN.reconcile_removal(
            root=present_wt, git_dir=present_target["git_dir"],
            common_dir=present_target["common_dir"],
            branch=present_target["branch"], head=present_target["head"],
            conversation_id="legacy-present", session_id="sess")
        self.assertEqual(present["outcome"], "uncertain", present)
        self.assertEqual(present["reason"], "legacy_present_identity_unavailable")
        self.assertTrue(
            Path(FIN.removal_journal_path(legacy_present["operation_id"])).exists())

        repo, absent_wt, _ = self.ephemeral_wt("legacy-absent", {"draft": "discard"})
        absent_target, absent_journal = self._prepare_only(
            absent_wt, "legacy-absent")
        legacy_absent = self._downgrade_journal_to_legacy(absent_journal)
        git(repo, "worktree", "remove", "--force", absent_wt)
        absent = FIN.reconcile_removal(
            root=absent_wt, git_dir=absent_target["git_dir"],
            common_dir=absent_target["common_dir"],
            branch=absent_target["branch"], head=absent_target["head"],
            conversation_id="legacy-absent", session_id="sess")
        self.assertEqual(absent["outcome"], "removed", absent)
        finalized, status = FIN.read_removal_journal(legacy_absent["operation_id"])
        self.assertEqual(status, "ok")
        self.assertEqual(finalized["phase"], "finalized")

    def test_prepared_state_write_failure_preserves_root_and_reports_no_removal(self) -> None:
        _, wt, _ = self.ephemeral_wt("prepared-write-fault", {"draft": "keep"})
        target = self.targets(wt)
        FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="sess",
            conversation_id="prepared-write-fault")
        real_write = FIN._write_removal_journal

        def fault(record: dict) -> None:
            if record.get("phase") == "prepared":
                raise OSError("injected prepared write failure")
            real_write(record)

        FIN._write_removal_journal = fault
        try:
            result = FIN.finish_execute(
                root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
                branch=target["branch"], head=target["head"], session_id="sess",
                conversation_id="prepared-write-fault", answer="Close")
        finally:
            FIN._write_removal_journal = real_write
        self.assertNotEqual(result["outcome"], "removed", result)
        self.assertTrue(Path(wt, "draft").exists())
        self.assertEqual(self.receipts(), [])

    def test_physical_and_registration_disagreement_preserves_uncertainty(self) -> None:
        import shutil
        _, wt, _ = self.ephemeral_wt("signal-disagreement", {"draft": "keep"})
        target, _journal = self._prepare_only(wt, "signal-disagreement")
        shutil.rmtree(wt)
        result = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="signal-disagreement", session_id="sess")
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertEqual(result["reason"], "physical_registration_disagree")
        self.assertEqual(self.receipts(), [])

    def test_malformed_journal_after_physical_removal_preserves_uncertainty(self) -> None:
        _, wt, _ = self.ephemeral_wt("malformed-journal", {"draft": "discard"})
        target, journal = self._prepare_only(wt, "malformed-journal")
        Path(FIN.removal_journal_path(journal["operation_id"])).write_bytes(b'{"schema":')
        removed = subprocess.run(
            ["git", "--git-dir=" + target["common_dir"], "worktree", "remove", "--force", wt],
            capture_output=True, text=True)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        result = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="malformed-journal", session_id="sess")
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertEqual(result["reason"], "removal_journal_malformed")
        self.assertEqual(self.receipts(), [])

    def test_abrupt_exit_after_real_remove_is_reconciled_by_shell_immediately(self) -> None:
        _, wt, _ = self.ephemeral_wt("crash-after-remove", {"draft": "discard"})
        self.preview(wt, conv="crash-after-remove")
        wrapper = self.data_home / "crash-finish.py"
        wrapper.write_text(
            "import importlib.util, os, sys\n"
            f"p={str(_FINISH_PY)!r}\n"
            "s=importlib.util.spec_from_file_location('crash_finish',p)\n"
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
            "real=m.subprocess.run\n"
            "def crash_run(*args, **kwargs):\n"
            "    result=real(*args, **kwargs)\n"
            "    argv=args[0] if args else kwargs.get('args', [])\n"
            "    if result.returncode == 0 and 'worktree' in argv and 'remove' in argv:\n"
            "        os._exit(86)\n"
            "    return result\n"
            "if len(sys.argv) > 1 and sys.argv[1] == 'finish-execute':\n"
            "    m.subprocess.run=crash_run\n"
            "raise SystemExit(m.main(sys.argv[1:]))\n",
            encoding="utf-8")
        result = self.run_dev_finish(
            "--authorization", "Close", "--conversation-id", "crash-after-remove",
            cwd=wt, env=self.env(extra={
                "AWA_FINISH_LIB": str(wrapper), "DEV_SESSION_ID": "sess",
            }))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(Path(wt).exists())
        self.assertIn("removed the current worktree", result.stdout + result.stderr)
        receipts = [r for r in self.receipts() if r.get("operation_id")]
        self.assertEqual(len(receipts), 1, receipts)
        self.assertEqual(receipts[0]["disposition"], "removed")

    def test_shell_reconciles_valid_removed_result_before_deferred_receipt(self) -> None:
        _, wt, _ = self.ephemeral_wt("deferred-shell", {"draft": "discard"})
        self.preview(wt, conv="deferred-shell")
        wrapper = self.data_home / "deferred-finish.py"
        wrapper.write_text(
            "import importlib.util, sys\n"
            f"p={str(_FINISH_PY)!r}\n"
            "s=importlib.util.spec_from_file_location('deferred_finish',p)\n"
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
            "if len(sys.argv) > 1 and sys.argv[1] == 'finish-execute':\n"
            "    real=m._write_removal_journal\n"
            "    def fault(record):\n"
            "        if record.get('phase') == 'removed':\n"
            "            raise OSError('injected persistent removed-state failure')\n"
            "        return real(record)\n"
            "    m._write_removal_journal=fault\n"
            "raise SystemExit(m.main(sys.argv[1:]))\n",
            encoding="utf-8")
        result = self.run_dev_finish(
            "--authorization", "Close", "--conversation-id", "deferred-shell",
            cwd=wt, env=self.env(extra={
                "AWA_FINISH_LIB": str(wrapper), "DEV_SESSION_ID": "sess",
            }))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(Path(wt).exists())
        receipts = [r for r in self.receipts() if r.get("operation_id")]
        self.assertEqual(len(receipts), 1, receipts)
        journal, status = FIN.read_removal_journal(receipts[0]["operation_id"])
        self.assertEqual(status, "ok")
        self.assertEqual(journal["phase"], "finalized")

    def test_removed_and_finalized_state_write_faults_reconcile_idempotently(self) -> None:
        for failed_phase, warning in (
                ("removed", "removed_state_write_failed"),
                ("finalized", "finalized_state_write_failed")):
            with self.subTest(failed_phase=failed_phase):
                _, wt, _ = self.ephemeral_wt(
                    "journal-" + failed_phase, {"draft": "discard"})
                target = self.targets(wt)
                FIN.preview(
                    root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
                    branch=target["branch"], head=target["head"], session_id="sess",
                    conversation_id="journal-" + failed_phase)
                real_write = FIN._write_removal_journal
                failed = {"done": False}

                def fault(record: dict) -> None:
                    if record.get("phase") == failed_phase and not failed["done"]:
                        failed["done"] = True
                        raise OSError("injected state write failure")
                    real_write(record)

                FIN._write_removal_journal = fault
                try:
                    removed = FIN.finish_execute(
                        root=wt, git_dir=target["git_dir"],
                        common_dir=target["common_dir"], branch=target["branch"],
                        head=target["head"], session_id="sess",
                        conversation_id="journal-" + failed_phase, answer="Close")
                finally:
                    FIN._write_removal_journal = real_write
                if failed_phase == "removed":
                    self.assertEqual(removed["outcome"], "uncertain", removed)
                    self.assertEqual(removed["reason"], warning)
                    self.assertEqual(self.receipts(), [])
                else:
                    self.assertEqual(removed["outcome"], "removed", removed)
                    self.assertIn(warning, removed["state_cleanup_warnings"])
                    durable, status = FIN.read_removal_journal(removed["operation_id"])
                    self.assertEqual(status, "ok")
                    self.assertEqual(durable["phase"], "removed")
                    self.assertEqual(durable["branch_action"], removed["branch_action"])
                    self.assertTrue(durable["branch_action"])
                again = FIN.reconcile_removal(
                    root=wt, git_dir=target["git_dir"],
                    common_dir=target["common_dir"], branch=target["branch"],
                    head=target["head"], conversation_id="journal-" + failed_phase,
                    session_id="sess")
                self.assertEqual(again["outcome"], "removed", again)
                operation = removed["operation_id"]
                self.assertEqual(
                    len([r for r in self.receipts() if r.get("operation_id") == operation]), 1)

    def test_receipt_failure_keeps_removed_latched_and_next_reconcile_repairs(self) -> None:
        _, wt, _ = self.ephemeral_wt("receipt-repair", {"draft": "discard"})
        target = self.targets(wt)
        FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="sess",
            conversation_id="receipt-repair")
        roots = FIN._roots_module()
        real_write = roots.write_receipt
        roots.write_receipt = lambda **kwargs: (_ for _ in ()).throw(
            OSError("injected receipt failure"))
        try:
            removed = FIN.finish_execute(
                root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
                branch=target["branch"], head=target["head"], session_id="sess",
                conversation_id="receipt-repair", answer="Close")
        finally:
            roots.write_receipt = real_write
        self.assertEqual(removed["outcome"], "removed", removed)
        self.assertFalse(removed["receipt_committed"])
        self.assertIn("receipt_write_failed", removed["state_cleanup_warnings"])
        repaired = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="receipt-repair", session_id="sess")
        self.assertEqual(repaired["outcome"], "removed", repaired)
        self.assertTrue(repaired["receipt_committed"])
        self.assertEqual(
            len([r for r in self.receipts()
                 if r.get("operation_id") == removed["operation_id"]]), 1)

    def test_unpersisted_removed_branch_state_defers_receipt_until_recovery(self) -> None:
        _, wt, _ = self.ephemeral_wt("removed-state-repair", {"draft": "discard"})
        target = self.targets(wt)
        FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="sess",
            conversation_id="removed-state-repair")
        real_write = FIN._write_removal_journal

        def fault(record: dict) -> None:
            if record.get("phase") == "removed":
                raise OSError("injected persistent removed-state failure")
            real_write(record)

        FIN._write_removal_journal = fault
        try:
            removed = FIN.finish_execute(
                root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
                branch=target["branch"], head=target["head"], session_id="sess",
                conversation_id="removed-state-repair", answer="Close")
        finally:
            FIN._write_removal_journal = real_write
        self.assertEqual(removed["outcome"], "uncertain", removed)
        self.assertEqual(removed["reason"], "removed_state_write_failed")
        self.assertEqual(
            [r for r in self.receipts()
             if r.get("operation_id") == removed["operation_id"]], [])
        repaired = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id="removed-state-repair", session_id="sess")
        self.assertEqual(repaired["outcome"], "removed", repaired)
        self.assertTrue(repaired["receipt_committed"], repaired)
        self.assertEqual(
            len([r for r in self.receipts()
                 if r.get("operation_id") == removed["operation_id"]]), 1)

    def test_current_session_cas_preserves_superseding_and_failed_finish_state(self) -> None:
        _, wt, _ = self.ephemeral_wt("current-cas", {"draft": "one"})
        target = self.targets(wt)
        roots = FIN._roots_module()
        roots.write_current_session(
            wt, session_id="old", conversation_id="old-conversation",
            branch=target["branch"], common_dir=target["common_dir"])
        roots.write_current_session(
            wt, session_id="new", conversation_id="new-conversation",
            branch=target["branch"], common_dir=target["common_dir"])
        superseded = roots.remove_current_session_cas(
            wt, session_id="old", conversation_id="old-conversation",
            branch=target["branch"], common_dir=target["common_dir"])
        self.assertEqual(superseded["reason"], "superseded")
        current, status = roots.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(current["session_id"], "new")

        FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="new",
            conversation_id="new-conversation")
        # A new row is structural drift and must still refuse; content-only drift within the
        # already displayed draft path is intentionally allowed by path-granularity Close.
        Path(wt, "new-after-preview").write_text("two", encoding="utf-8")
        refused = FIN.finish_execute(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="new",
            conversation_id="new-conversation", answer="Close")
        self.assertEqual(refused["outcome"], "refused", refused)
        self.assertEqual(roots.read_current_session(wt)[1], "ok")

    def test_current_session_reconciliation_clears_exact_pre_reboot_identity(self) -> None:
        _, wt, _ = self.ephemeral_wt("current-cas-reboot")
        target = self.targets(wt)
        roots = FIN._roots_module()
        current = roots.write_current_session(
            wt, session_id="sess", conversation_id="conversation",
            branch=target["branch"], common_dir=target["common_dir"])
        real_boot_id = roots.boot_id
        roots.boot_id = lambda: "simulated-new-boot"
        try:
            cleared = roots.remove_current_session_cas(
                wt, session_id="sess", conversation_id="conversation",
                branch=target["branch"], common_dir=target["common_dir"],
                expected_boot_id=current["boot_id"])
        finally:
            roots.boot_id = real_boot_id
        self.assertTrue(cleared["ok"], cleared)
        self.assertTrue(cleared["removed"], cleared)

    def test_removal_clears_exact_current_session_and_surfaces_cleanup_failure(self) -> None:
        for inject_failure in (False, True):
            with self.subTest(inject_failure=inject_failure):
                _, wt, _ = self.ephemeral_wt(
                    "current-clean-" + str(inject_failure), {"draft": "discard"})
                target = self.targets(wt)
                roots = FIN._roots_module()
                roots.write_current_session(
                    wt, session_id="sess", conversation_id="current-clean",
                    branch=target["branch"], common_dir=target["common_dir"])
                FIN.preview(
                    root=wt, git_dir=target["git_dir"],
                    common_dir=target["common_dir"], branch=target["branch"],
                    head=target["head"], session_id="sess",
                    conversation_id="current-clean")
                real_remove = roots.remove_current_session_cas
                if inject_failure:
                    roots.remove_current_session_cas = lambda *args, **kwargs: {
                        "ok": False, "reason": "current_session_unlink_failed",
                        "removed": False,
                    }
                try:
                    removed = FIN.finish_execute(
                        root=wt, git_dir=target["git_dir"],
                        common_dir=target["common_dir"], branch=target["branch"],
                        head=target["head"], session_id="sess",
                        conversation_id="current-clean", answer="Close")
                finally:
                    roots.remove_current_session_cas = real_remove
                self.assertEqual(removed["outcome"], "removed", removed)
                if inject_failure:
                    self.assertIn(
                        "current_session_unlink_failed",
                        removed["state_cleanup_warnings"])
                    self.assertTrue(
                        Path(roots.current_session_path(wt)).exists())
                    repaired = FIN.reconcile_removal(
                        root=wt, git_dir=target["git_dir"],
                        common_dir=target["common_dir"], branch=target["branch"],
                        head=target["head"], conversation_id="current-clean",
                        session_id="sess")
                    self.assertEqual(repaired["outcome"], "removed", repaired)
                    self.assertFalse(
                        any(item.startswith("current_session_")
                            for item in repaired["state_cleanup_warnings"]),
                        repaired)
                    self.assertEqual(roots.read_current_session(wt)[1], "absent")
                else:
                    self.assertEqual(roots.read_current_session(wt)[1], "absent")


# =====================================================================================
# (b) NO-NETWORK gate: removal + branch decision with fetch/ls-remote/push/gh made bombs
# =====================================================================================
class NoNetworkGateTest(FinishBase):
    def _net_bomb_path(self) -> tuple[str, Path]:
        """A PATH whose `git` rejects network verbs (fetch/ls-remote/push/clone) and whose `gh` is
        a bomb that touches a sentinel. Proves the removal path performs ZERO network."""
        import shutil
        real_git = shutil.which("git")
        self.assertTrue(real_git)
        shim = self.data_home / "netbomb"
        shim.mkdir(parents=True, exist_ok=True)
        sentinel = shim / "NETWORK_WAS_CALLED"
        (shim / "git").write_text(
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do case "$a" in\n'
            "  fetch|ls-remote|push|clone|remote-https|remote-http)\n"
            f'    echo net >> "{sentinel}"; echo "NETWORK GIT: $a" >&2; exit 97 ;;\n'
            "esac; done\n"
            f'exec "{real_git}" "$@"\n', encoding="utf-8")
        (shim / "git").chmod(0o755)
        (shim / "gh").write_text(
            "#!/usr/bin/env bash\n"
            f'echo gh >> "{sentinel}"; echo "NETWORK GH: $*" >&2; exit 98\n', encoding="utf-8")
        (shim / "gh").chmod(0o755)
        return f"{shim}:{os.environ.get('PATH', '')}", sentinel

    def test_removal_and_branch_delete_perform_no_network(self) -> None:
        path, sentinel = self._net_bomb_path()
        env = self.env(path=path)
        _, wt, _ = self.ephemeral_wt("nonet", {"draft.txt": "x"})
        self.preview(wt, conv="nn")
        res, _ = self.execute(wt, "Close", conv="nn", env=env)
        self.assertEqual(res["outcome"], "removed", res)
        self.assertEqual(res["branch_action"], "deleted")
        self.assertFalse(Path(wt).exists())
        self.assertFalse(sentinel.exists(),
                         "a network verb was invoked on the removal path: "
                         + (sentinel.read_text() if sentinel.exists() else ""))


# =====================================================================================
# (d) HOOK-INDEPENDENT gate + target spoofing + branch-delete fallback (via dev-worktree.sh)
# =====================================================================================
class HookIndependentGateTest(FinishBase):
    def test_prompt_hook_is_not_imported_by_kernel(self) -> None:
        # Phase 2 may ship a recall hook, but the Phase-1 kernel must not import/read it.
        hooks = _REPO_ROOT / "kernel" / "hooks"
        self.assertTrue((hooks / "before-submit-prompt.sh").is_file())
        for p in (_FINISH_PY, _DEV_WORKTREE):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("before-submit-prompt.sh", text)
            self.assertNotIn("beforeSubmitPrompt", text)

    def test_flag_alone_is_not_authorization(self) -> None:
        _, wt, _ = self.ephemeral_wt("noauth", {"a": "1"})
        r = self.run_dev_finish(cwd=wt)  # --finish-current with NO --authorization
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(Path(wt).exists(), "the flag alone must never remove a worktree")
        self.assertEqual(self.last_receipt()["reason_code"], "finish_no_authorization")

    def test_cli_requires_explicit_close_to_remove(self) -> None:
        _, wt, _ = self.ephemeral_wt("cliclose", {"a": "1"})
        # a preview creates the pending challenge...
        pv = self.run_dev_finish("--preview", cwd=wt)
        self.assertEqual(pv.returncode, 0, pv.stdout + pv.stderr)
        self.assertTrue(Path(wt).exists())
        self.assertEqual(self.last_receipt()["reason_code"], "finish_preview")
        # ...and only an explicit literal Close consumes it and removes.
        rm = self.run_dev_finish("--authorization", "Close", cwd=wt)
        self.assertEqual(rm.returncode, 0, rm.stdout + rm.stderr)
        self.assertFalse(Path(wt).exists())
        rec = self.last_receipt()
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("removed", "finish_removed"))
        self.assertTrue(rec["finish_current"])

    def test_env_authorization_accepted(self) -> None:
        _, wt, _ = self.ephemeral_wt("envauth", {"a": "1"})
        self.run_dev_finish("--preview", cwd=wt)
        rm = self.run_dev_finish(cwd=wt, env=self.env(extra={"AWA_FINISH_AUTHORIZATION": "Close"}))
        self.assertEqual(rm.returncode, 0, rm.stdout + rm.stderr)
        self.assertFalse(Path(wt).exists())

    def test_target_spoof_primary_checkout_refused(self) -> None:
        repo = self.make_repo("primary")
        r = self.run_dev_finish("--authorization", "Close", cwd=repo)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(Path(repo).exists())
        self.assertEqual(self.last_receipt()["reason_code"], "finish_not_linked")

    def test_target_spoof_subdir_not_toplevel_refused(self) -> None:
        _, wt, _ = self.ephemeral_wt("subdir")
        sub = Path(wt, "nested"); sub.mkdir()
        r = self.run_dev_finish("--authorization", "Close", cwd=str(sub))
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(Path(wt).exists())
        self.assertEqual(self.last_receipt()["reason_code"], "finish_not_linked")

    def test_finish_current_rejects_path_arg(self) -> None:
        _, wt, _ = self.ephemeral_wt("pathrej")
        r = self.run_dev_finish("--path", wt, "--authorization", "Close", cwd=wt)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(Path(wt).exists())
        self.assertEqual(self.last_receipt()["reason_code"], "finish_bad_args")

    def test_removed_receipt_carries_finish_fields(self) -> None:
        _, wt, _ = self.ephemeral_wt("fields", {"a.txt": "1", "b.txt": "2"})
        self.run_dev_finish("--preview", cwd=wt)
        self.run_dev_finish("--authorization", "Close", cwd=wt)
        rec = self.last_receipt()
        self.assertEqual(rec["disposition"], "removed")
        self.assertTrue(rec["finish_current"])
        self.assertEqual(rec["branch_action"], "deleted")
        self.assertGreaterEqual(int(rec["discard_count"]), 2)
        self.assertTrue(rec["challenge_fingerprint"])
        self.assertTrue(rec["authorization_nonce"])

    def test_branch_delete_fallback_still_reports_removed(self) -> None:
        """A branch-cleanup failure (branch moved off captured HEAD, simulated by a git shim that
        fails update-ref) MUST NOT misreport the already-removed root as surviving."""
        import shutil
        real_git = shutil.which("git")
        shim = self.data_home / "urefbomb"
        shim.mkdir(parents=True, exist_ok=True)
        (shim / "git").write_text(
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do [ "$a" = "update-ref" ] && { echo "shim: no update-ref" >&2; exit 1; }; done\n'
            f'exec "{real_git}" "$@"\n', encoding="utf-8")
        (shim / "git").chmod(0o755)
        env = self.env(path=f"{shim}:{os.environ.get('PATH', '')}")
        repo, wt, br = self.ephemeral_wt("fallback", {"a": "1"})
        self.run_dev_finish("--preview", cwd=wt, env=env)
        r = self.run_dev_finish("--authorization", "Close", cwd=wt, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists(), "the worktree was removed")
        rec = self.last_receipt()
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("removed", "finish_removed"))
        self.assertEqual(rec["branch_action"], "delete_failed")
        # the branch survives — compare-and-delete never force-deleted it.
        self.assertEqual(git(repo, "show-ref", "--verify", "--quiet",
                             f"refs/heads/{br}", check=False).returncode, 0)

    def test_dirty_state_is_discarded_on_close(self) -> None:
        # finish deliberately discards uncommitted work (dirty tree) once authorized.
        _, wt, _ = self.ephemeral_wt("dirty", {"tracked.txt": "v1"})
        commit_all(wt, "base")
        Path(wt, "tracked.txt").write_text("v2-uncommitted", encoding="utf-8")
        Path(wt, "new.txt").write_text("new", encoding="utf-8")
        self.run_dev_finish("--preview", cwd=wt)
        r = self.run_dev_finish("--authorization", "Close", cwd=wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists())


# =====================================================================================
# ENGINE-OFF proof + lock ABI parity
# =====================================================================================
class EngineOffAndLockAbiTest(FinishBase):
    def test_finish_execute_removes_with_engine_unimportable(self) -> None:
        # sanity: the engine-off env makes `import engine` fail...
        chk = subprocess.run(["python3", "-c", "import engine"], env=self.env(engine_off=True),
                             capture_output=True, text=True, cwd=str(self.data_home))
        self.assertNotEqual(chk.returncode, 0, "engine must be UNIMPORTABLE for this proof")
        # ...and the destructive path still works fully engine-OFF, run from a non-repo cwd.
        _, wt, _ = self.ephemeral_wt("engoff", {"a": "1"})
        self.preview(wt, conv="eo")
        res, _ = self.execute(wt, "Close", conv="eo",
                              env=self.env(engine_off=True), cwd=str(self.data_home))
        self.assertEqual(res["outcome"], "removed", res)
        self.assertFalse(Path(wt).exists())

    def test_lock_path_is_byte_identical_to_engine_abi(self) -> None:
        # kernel finish + engine maintenance MUST hash to the SAME lockfile so they mutually
        # exclude. Compare awa_finish's derivation to the engine's identity/paths ABI.
        from engine import identity, paths  # engine importable in the normal test env
        common = str(self.data_home / "some" / ".git")
        key = FIN.common_dir_key(common)
        self.assertEqual(key, identity.common_dir_key(common), "common_dir_key ABI drifted")
        self.assertEqual(Path(FIN.lockfile_for(common)), paths.locks_dir() / f"common-{key}.lock",
                         "lockfile path ABI drifted from engine/lock.py")

    def test_lock_path_cli(self) -> None:
        common = str(self.data_home / "x" / ".git")
        r = self.run_lib("lock-path", "--common-dir", common)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.strip().endswith(f"common-{FIN.common_dir_key(common)}.lock"))


# =====================================================================================
# Ordinary `clean --path` is UNCHANGED by the finish additions
# =====================================================================================
class OrdinaryCleanUnchangedTest(FinishBase):
    def test_ordinary_clean_path_still_removes_merged_worktree(self) -> None:
        repo = self.make_repo("ord")
        wt = self.add_worktree(repo, "feat/ord")
        Path(wt, "f.txt").write_text("x\n", encoding="utf-8")
        commit_all(wt, "f")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", "feat/ord")
        commit_all(repo, "squash")
        r = subprocess.run([str(_DEV_WORKTREE), "clean", "--path", wt],
                           cwd=str(_REPO_ROOT), env=self.env(engine_off=False),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists())
        rec = self.last_receipt()
        self.assertEqual(rec["reason_code"], "removed_kept_branch")
        # finish fields default to empty/false on the ordinary path (additive-within-v1).
        self.assertFalse(rec["finish_current"])

    def test_preview_without_finish_current_refuses(self) -> None:
        r = subprocess.run([str(_DEV_WORKTREE), "clean", "--preview", "--path", "/x"],
                           cwd=str(_REPO_ROOT), env=self.env(), capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.last_receipt()["reason_code"], "finish_bad_args")


# =====================================================================================
# Folded best-of-breed hardening (2026-07-10): the removed-latch, the final re-fingerprint
# gate, the lock-busy refusal, and the contract key-set PINS. Driven IN-PROCESS where fault
# injection (a post-removal raise, a mid-window file, a held lock) is required.
# =====================================================================================
class FoldedHardeningTest(FinishBase):
    def _restore_cwd(self) -> None:
        # finish_execute chdir's OUT of the (to-be-removed) worktree before removal; make sure a
        # test that reaches removal restores the process cwd afterwards.
        self.addCleanup(os.chdir, os.getcwd())

    def test_post_removal_branch_step_raise_still_reports_removed(self) -> None:
        # Fix 1 (MAJOR): once the worktree is physically GONE, a RAISING branch-delete must NOT
        # misreport the removed root as surviving/error. `removed` LATCHES: outcome stays `removed`
        # (branch_action=delete_error) and consume+remove_root STILL run (no phantom heartbeat).
        self._restore_cwd()
        _, wt, _ = self.ephemeral_wt("postrm", {"a": "1"})
        t = self.targets(wt)
        AR.heartbeat(wt, session_id="sess", branch=t["branch"], common_dir=t["common_dir"])
        self.assertTrue(Path(AR.record_path(wt)).exists(), "precondition: a heartbeat record exists")
        FIN.preview(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                    branch=t["branch"], head=t["head"], session_id="sess", conversation_id="pr")
        real_run = FIN.subprocess.run

        def bomb(cmd, *a, **k):
            if isinstance(cmd, (list, tuple)) and "update-ref" in cmd:
                raise RuntimeError("post-removal branch-delete boom")
            return real_run(cmd, *a, **k)

        FIN.subprocess.run = bomb
        try:
            res = FIN.finish_execute(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                                     branch=t["branch"], head=t["head"], session_id="sess",
                                     conversation_id="pr", answer="Close")
        finally:
            FIN.subprocess.run = real_run
        self.assertEqual(res["outcome"], "removed", res)
        self.assertEqual(res["receipt_code"], "finish_removed", res)
        self.assertEqual(res["branch_action"], "delete_error", res)
        self.assertFalse(Path(wt).exists(), "the worktree is GONE despite the branch-step raise")
        _, status = FIN.read_challenge("pr")
        self.assertEqual(status, "absent", "the challenge is consumed after terminal removal")
        self.assertFalse(Path(AR.record_path(wt)).exists(),
                         "the heartbeat record is cleared (no phantom 'dead' record)")

    def test_post_removal_consume_cas_preserves_concurrent_new_generation(self) -> None:
        self._restore_cwd()
        _, wt, _ = self.ephemeral_wt("postrm-consume-race", {"a": "1"})
        t = self.targets(wt)
        FIN.preview(
            root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
            branch=t["branch"], head=t["head"], session_id="sess",
            conversation_id="postrm-consume-race")
        cp = Path(FIN.challenge_path("postrm-consume-race"))
        challenge, status = FIN._read_challenge_raw("postrm-consume-race")
        self.assertEqual(status, "ok")
        newer = copy.deepcopy(challenge)
        newer["nonce"] = "post-removal-new-generation"
        newer["generation"] += 1
        newer["created_at_epoch"] = FIN._now_epoch()
        newer["created_at"] = FIN._iso_from_epoch(newer["created_at_epoch"])
        real_delete = FIN._delete_challenge_raw_cas

        def replace_then_delete(*args, **kwargs):
            self.assertFalse(Path(wt).exists(), "replacement must occur after physical removal")
            FIN._write_private(str(cp), json.dumps(newer))
            return real_delete(*args, **kwargs)

        FIN._delete_challenge_raw_cas = replace_then_delete
        try:
            result = FIN.finish_execute(
                root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                branch=t["branch"], head=t["head"], session_id="sess",
                conversation_id="postrm-consume-race", answer="Close")
        finally:
            FIN._delete_challenge_raw_cas = real_delete
        self.assertEqual(result["outcome"], "removed", result)
        self.assertFalse(Path(wt).exists())
        surviving, status = FIN.read_challenge("postrm-consume-race")
        self.assertEqual(status, "ok")
        self.assertEqual(surviving["nonce"], newer["nonce"])
        self.assertEqual(surviving["generation"], newer["generation"])

    def test_new_file_in_window_refused_by_final_regate(self) -> None:
        # Fix 2: a file created AFTER authorization but BEFORE the remove (injected via a
        # branch_disposition side effect — branch_disposition runs in exactly that window) is caught
        # by the FINAL re-fingerprint gate -> refuse fingerprint_mismatch + preserve. It was never
        # authorized for discard, so the fail-safe keeps the whole worktree.
        self._restore_cwd()
        _, wt, _ = self.ephemeral_wt("window", {"a": "1"})
        t = self.targets(wt)
        FIN.preview(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                    branch=t["branch"], head=t["head"], session_id="sess", conversation_id="wn")
        real_bd = FIN.branch_disposition

        def bd_side_effect(root, branch, head, common_dir):
            Path(root, "sneaked-in.txt").write_text("appeared after auth", encoding="utf-8")
            return real_bd(root, branch, head, common_dir)

        FIN.branch_disposition = bd_side_effect
        try:
            res = FIN.finish_execute(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                                     branch=t["branch"], head=t["head"], session_id="sess",
                                     conversation_id="wn", answer="Close")
        finally:
            FIN.branch_disposition = real_bd
        self.assertEqual((res["outcome"], res["receipt_code"]),
                         ("refused", "finish_fingerprint_mismatch"), res)
        self.assertTrue(Path(wt).exists(), "the worktree is preserved on the final-gate refusal")
        self.assertTrue(Path(wt, "sneaked-in.txt").exists(), "nothing was discarded")

    def test_finish_refuses_when_common_dir_lock_held(self) -> None:
        # Fix 7: a held per-common-dir lock (acquired here via a SECOND open of the SAME lockfile)
        # makes finish-execute refuse (finish_lock_busy) within a short timeout, worktree preserved
        # (the destructive section never runs). Same-process two-fd flock contends by design.
        self._restore_cwd()
        _, wt, _ = self.ephemeral_wt("lockbusy", {"a": "1"})
        t = self.targets(wt)
        FIN.preview(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                    branch=t["branch"], head=t["head"], session_id="sess", conversation_id="lb")
        with FIN.common_dir_lock(t["common_dir"], blocking=True, timeout=5.0):
            res = FIN.finish_execute(root=wt, git_dir=t["git_dir"], common_dir=t["common_dir"],
                                     branch=t["branch"], head=t["head"], session_id="sess",
                                     conversation_id="lb", answer="Close", lock_timeout=0.5)
        self.assertEqual((res["outcome"], res["receipt_code"]),
                         ("refused", "finish_lock_busy"), res)
        self.assertTrue(Path(wt).exists(), "a lock-busy refusal preserves the worktree")

    def test_challenge_declared_keys_pinned_to_contract(self) -> None:
        # Fix 6: the contract's declared_keys must EQUAL the live create_challenge() key-set (closes
        # the silent-drift gap that was previously documentation-only).
        contract = json.loads((_REPO_ROOT / "contracts" / "awa-contract.v1.json")
                              .read_text(encoding="utf-8"))
        declared = set(contract["awa_finish_challenge"]["declared_keys"])
        _, wt, _ = self.ephemeral_wt("keys", {"a": "1"})
        t = self.targets(wt)
        ch = FIN.create_challenge(conversation_id="k", root=wt, git_dir=t["git_dir"],
                                  common_dir=t["common_dir"], branch=t["branch"], head=t["head"],
                                  fingerprint="fp", markers=[], membership=[])
        self.assertEqual(declared, set(ch.keys()),
                         "contract awa_finish_challenge.declared_keys drifted from create_challenge()")

    def test_generation_state_declared_keys_pin_persisted_record(self) -> None:
        contract = json.loads((_REPO_ROOT / "contracts" / "awa-contract.v1.json")
                              .read_text(encoding="utf-8"))
        declared = set(contract["awa_finish_generation_state"]["declared_keys"])
        _, wt, _ = self.ephemeral_wt("generation-keys", {"a": "1"})
        target = self.targets(wt)
        transitioned = FIN._transition_generation(
            transition="close_claimed", conversation_id="generation-keys",
            nonce="nonce-keys", generation=1, root=wt,
            common_dir=target["common_dir"],
            session_key_value=AR.session_key("session-keys"))
        self.assertTrue(transitioned["created"], transitioned)
        persisted, status = FIN.read_generation_state(
            "generation-keys", "nonce-keys", 1)
        self.assertEqual(status, "ok")
        self.assertEqual(set(persisted), declared)

    def test_receipt_finish_fields_pinned_subset_of_receipt(self) -> None:
        # Fix 6: every contract clean_receipt.finish_fields.key must actually appear on a written
        # finish receipt (subset pin — the receipt MAY carry more, never fewer).
        contract = json.loads((_REPO_ROOT / "contracts" / "awa-contract.v1.json")
                              .read_text(encoding="utf-8"))
        finish_keys = set(contract["clean_receipt"]["finish_fields"]["keys"])
        _, wt, _ = self.ephemeral_wt("rfields", {"a": "1"})
        self.run_dev_finish("--preview", cwd=wt)
        self.run_dev_finish("--authorization", "Close", cwd=wt)
        rec = self.last_receipt()
        missing = finish_keys - set(rec.keys())
        self.assertEqual(missing, set(),
                         f"contract finish_fields.keys not all present on the receipt: {missing}")


if __name__ == "__main__":
    import unittest
    unittest.main()
