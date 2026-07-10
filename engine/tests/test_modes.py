"""Tests for engine/modes.py (RECORD tooling) + the mutating MCP mode tools.

Covers: set/get/remove/list round-trip, atomic write (no temp residue), invalid-value
rejection (only on|off accepted), default_mode preservation, repair (fail-safe: coerce any
non-`off` VALUE to `on`, drop only an invalid KEY; normalize a legacy default_mode to `on`),
sync (create + idempotent + non-destructive), and a cross-check that a written file parses
identically through the classifier's own modes loader (PolicyConfig.load / mode_for). Also
asserts the new mutating MCP tools are registered and dispatch into modes.py, path-scoped to
the host modes file.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from engine import mcp_server, modes, policy


class ModesTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-modes-test.")
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "worktree-modes.yml"

    def tearDown(self):
        self._tmp.cleanup()

    def _temp_files(self) -> list[str]:
        # Atomic-write residue only (`.worktree-modes.<rand>.tmp`). The persistent flock lock
        # file (`.worktree-modes.yml.lock`) is expected and is NOT temp residue.
        return [n for n in os.listdir(self.dir)
                if n.startswith(".worktree-modes.") and n.endswith(".tmp")]


class TestSetGetRemoveList(ModesTestCase):
    def test_set_then_get_and_list(self):
        out = modes.set_mode(self.path, "capabilities/awa", "on")
        self.assertEqual(out["mode"], "on")
        self.assertIsNone(out["previous"])
        self.assertEqual(modes.get_mode(self.path, "capabilities/awa")["mode"], "on")

        modes.set_mode(self.path, "personal/legacy", "off")
        listed = modes.list_modes(self.path)
        self.assertTrue(listed["exists"])
        self.assertEqual(listed["schema"], modes.SCHEMA)
        self.assertEqual(listed["modes"],
                         {"capabilities/awa": "on", "personal/legacy": "off"})

    def test_set_updates_existing(self):
        modes.set_mode(self.path, "proj", "on")
        out = modes.set_mode(self.path, "proj", "off")
        self.assertEqual(out["previous"], "on")
        self.assertEqual(out["mode"], "off")
        self.assertEqual(modes.get_mode(self.path, "proj")["mode"], "off")

    def test_set_normalizes_case(self):
        modes.set_mode(self.path, "proj", "ON")
        self.assertEqual(modes.get_mode(self.path, "proj")["mode"], "on")
        modes.set_mode(self.path, "other", "OFF")
        self.assertEqual(modes.get_mode(self.path, "other")["mode"], "off")

    def test_get_absent(self):
        modes.sync(self.path)
        g = modes.get_mode(self.path, "nope")
        self.assertFalse(g["present"])
        self.assertEqual(g["mode"], "")

    def test_get_reports_invalid_legacy_value(self):
        self.path.write_text(
            "schema: awa-modes/v1\n"
            "default_mode: on\n"
            "modes:\n"
            "  proj: ask_on\n",
            encoding="utf-8",
        )
        g = modes.get_mode(self.path, "proj")
        self.assertTrue(g["present"])
        self.assertEqual(g["mode"], "invalid")
        self.assertIn("mode_error", g)
        self.assertIn("ask_on", g["mode_error"])

    def test_list_reports_invalid_legacy_values(self):
        self.path.write_text(
            "schema: awa-modes/v1\n"
            "default_mode: ask_on\n"
            "modes:\n"
            "  good: on\n"
            "  legacy: ask_on\n",
            encoding="utf-8",
        )
        listed = modes.list_modes(self.path)
        self.assertEqual(listed["modes"], {"good": "on", "legacy": "invalid"})
        self.assertEqual(listed["default_mode"], "invalid")
        self.assertIn("default_mode_error", listed)

    def test_remove(self):
        modes.set_mode(self.path, "a", "on")
        modes.set_mode(self.path, "b", "off")
        out = modes.remove_mode(self.path, "a")
        self.assertTrue(out["removed"])
        self.assertEqual(out["previous"], "on")
        self.assertEqual(modes.list_modes(self.path)["modes"], {"b": "off"})

    def test_remove_absent_is_noop(self):
        modes.set_mode(self.path, "a", "on")
        out = modes.remove_mode(self.path, "missing")
        self.assertFalse(out["removed"])
        self.assertEqual(modes.list_modes(self.path)["modes"], {"a": "on"})

    def test_list_nonexistent(self):
        listed = modes.list_modes(self.path)
        self.assertFalse(listed["exists"])
        self.assertEqual(listed["modes"], {})
        self.assertIsNone(listed["default_mode"])

    def test_set_off_warns(self):
        out = modes.set_mode(self.path, "proj", "off")
        self.assertIsNotNone(out["warning"])


class TestValidation(ModesTestCase):
    def test_set_rejects_invalid_value(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "proj", "bogus")
        # no file written on rejection
        self.assertFalse(self.path.exists())

    def test_set_rejects_legacy_ask_on(self):
        # `ask_on` is a REMOVED value: `set` validates against the 2-value set and rejects it
        # (no third mode). Migration of a pre-existing legacy value is repair()'s job.
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "proj", "ask_on")
        self.assertFalse(self.path.exists())

    def test_set_rejects_empty_rel(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "  ", "on")

    def test_sync_rejects_invalid_default(self):
        with self.assertRaises(modes.ModesError):
            modes.sync(self.path, default_mode="bogus")

    def test_sync_rejects_legacy_ask_on_default(self):
        # A caller can no longer SEED a legacy default via sync (it validates on|off). The
        # install/overlay migration path uses `repair`, which normalizes it instead.
        with self.assertRaises(modes.ModesError):
            modes.sync(self.path, default_mode="ask_on")


class TestRelInjection(ModesTestCase):
    """A `rel` is written as a raw YAML key; a hostile rel must not inject a second key."""

    def test_injecting_rel_rejected_and_default_unchanged(self):
        # A newline-bearing rel that would inject `default_mode: off` must be rejected AND
        # leave the modes file (incl. its default_mode) completely untouched.
        modes.sync(self.path, default_mode="off")
        before = self.path.read_text(encoding="utf-8")
        evil = "proj\ndefault_mode: off"
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, evil, "on")
        after = self.path.read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertEqual(modes.list_modes(self.path)["default_mode"], "off")

    def test_rel_with_colon_rejected(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "evil: off", "on")

    def test_rel_with_leading_trailing_ws_rejected(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, " proj ", "on")

    def test_rel_control_char_rejected(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "proj\tx", "on")

    def test_rel_absolute_path_rejected(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "/absolute/path", "on")

    def test_rel_dotdot_segment_rejected(self):
        with self.assertRaises(modes.ModesError):
            modes.set_mode(self.path, "foo/../bar", "on")

    def test_broad_off_rel_rejected(self):
        for rel in (".", "*", "**", "?"):
            with self.assertRaises(modes.ModesError, msg=rel):
                modes.set_mode(self.path, rel, "off")

    def test_glob_off_with_path_chars_allowed(self):
        modes.set_mode(self.path, "personal/*", "off")
        self.assertEqual(modes.list_modes(self.path)["modes"], {"personal/*": "off"})

    def test_get_and_remove_reject_injection(self):
        with self.assertRaises(modes.ModesError):
            modes.get_mode(self.path, "x\ny")
        with self.assertRaises(modes.ModesError):
            modes.remove_mode(self.path, "x:y")

    def test_valid_path_and_glob_rels_allowed(self):
        modes.set_mode(self.path, "capabilities/awa", "on")
        modes.set_mode(self.path, "personal/*", "off")
        modes.set_mode(self.path, "a/b_c.d-e", "on")
        self.assertEqual(
            modes.list_modes(self.path)["modes"],
            {"capabilities/awa": "on", "personal/*": "off", "a/b_c.d-e": "on"},
        )


class TestRelNormalization(ModesTestCase):
    """#3: operator entries like `foo/` or `./foo` must canonicalize to `foo` so they match
    the classifier's rel (which carries no leading `./` or trailing `/`)."""

    def test_trailing_slash_canonicalized(self):
        out = modes.set_mode(self.path, "capabilities/awa/", "off")
        self.assertEqual(out["rel"], "capabilities/awa")
        self.assertEqual(modes.list_modes(self.path)["modes"], {"capabilities/awa": "off"})

    def test_leading_dotslash_canonicalized(self):
        out = modes.set_mode(self.path, "./capabilities/awa", "on")
        self.assertEqual(out["rel"], "capabilities/awa")
        self.assertEqual(modes.list_modes(self.path)["modes"], {"capabilities/awa": "on"})

    def test_get_and_remove_use_canonical_form(self):
        modes.set_mode(self.path, "foo", "off")
        self.assertEqual(modes.get_mode(self.path, "foo/")["mode"], "off")
        self.assertEqual(modes.get_mode(self.path, "./foo")["mode"], "off")
        rm = modes.remove_mode(self.path, "./foo/")
        self.assertTrue(rm["removed"])
        self.assertEqual(modes.list_modes(self.path)["modes"], {})

    def test_canonical_entry_takes_effect_via_mode_for_and_classify(self):
        # `set off` on `foo/` and `./foo` must actually turn the guard OFF for rel `foo`.
        modes.set_mode(self.path, "foo/", "off")
        pol_path = self.dir / "worktree-policy.yml"
        pol_path.write_text(
            "version: 1\ndefault: include\nmodes_file: worktree-modes.yml\n",
            encoding="utf-8",
        )
        cfg = policy.PolicyConfig.load(pol_path)
        self.assertEqual(policy.mode_for("foo", cfg), "off")
        c = policy.classify("foo", str(self.dir), cfg, has_origin=True)
        self.assertEqual(c.classification, policy.EXCLUDE)
        self.assertEqual(c.reason, "explicit mode: off")


class TestCorruptFileRecovery(ModesTestCase):
    """#4: a non-regular / unreadable modes file raises an ACTIONABLE ModesError, not a raw
    traceback."""

    def test_read_directory_raises_actionable(self):
        self.path.mkdir()  # a directory where a file is expected
        with self.assertRaises(modes.ModesError) as ctx:
            modes.list_modes(self.path)
        self.assertIn("not a readable regular file", str(ctx.exception))
        self.assertIn("mode sync", str(ctx.exception))

    def test_sync_on_directory_raises_actionable(self):
        self.path.mkdir()
        with self.assertRaises(modes.ModesError):
            modes.sync(self.path)

    def test_read_fifo_raises_actionable_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO support unavailable")
        os.mkfifo(self.path)
        with self.assertRaises(modes.ModesError) as ctx:
            modes.list_modes(self.path)
        self.assertIn("not a readable regular file", str(ctx.exception))


class TestSerializeChokePoint(ModesTestCase):
    """#10: repair/sync must NOT persist an unsafe key introduced by a hand-edit."""

    def test_repair_drops_unsafe_handedited_key(self):
        self.path.write_text(
            "schema: awa-modes/v1\n"
            "default_mode: on\n"
            "modes:\n"
            "  foo bar: on\n"   # a space-bearing key a hand-edit could introduce
            "  good: on\n",
            encoding="utf-8",
        )
        out = modes.repair(self.path)
        self.assertEqual(out["modes"], {"good": "on"})
        self.assertIn("foo bar", out["dropped"])


class TestConcurrencyLock(ModesTestCase):
    """#5: mutating verbs take an flock; concurrent writers don't lose updates. Also asserts
    the lock file is a hidden sibling (so the host .gitignore covers it)."""

    def test_lock_file_is_hidden_sibling(self):
        modes.set_mode(self.path, "a", "on")
        lock = self.dir / (".worktree-modes.yml.lock")
        # lock file may or may not persist after release, but if present it must be hidden.
        stray = [n for n in os.listdir(self.dir) if not n.startswith(".") and n != "worktree-modes.yml"]
        self.assertEqual(stray, [])

    def test_serialized_writes_all_land(self):
        import threading
        modes.sync(self.path, default_mode="on")
        keys = [f"r{i}" for i in range(12)]

        def worker(k):
            modes.set_mode(self.path, k, "on")

        threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        got = modes.list_modes(self.path)["modes"]
        for k in keys:
            self.assertEqual(got.get(k), "on", k)


class TestSerializerHeader(ModesTestCase):
    """`_serialize` emits a fixed canonical header so tool round-trips are byte-stable."""

    def test_header_present_after_sync(self):
        modes.sync(self.path, default_mode="off")
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# AWA per-repo MODE file"))
        self.assertIn("DO NOT HAND-EDIT", text)
        self.assertIn(
            "# default_mode governs eligible repos with no explicit entry; "
            "modes is a tool-managed map.\n",
            text,
        )
        self.assertIn("schema: awa-modes/v1", text)
        self.assertIn("default_mode: off", text)

    def test_resync_byte_identical(self):
        modes.sync(self.path, default_mode="off")
        modes.set_mode(self.path, "proj", "on")
        text1 = self.path.read_text(encoding="utf-8")
        modes.sync(self.path)
        text2 = self.path.read_text(encoding="utf-8")
        self.assertEqual(text1, text2)

    def test_sync_on_canonical_file_does_not_rewrite(self):
        modes.sync(self.path, default_mode="off")
        mtime_before = self.path.stat().st_mtime_ns
        out = modes.sync(self.path)
        self.assertFalse(out["rewritten"])
        self.assertEqual(self.path.stat().st_mtime_ns, mtime_before)
        self.assertEqual(self._temp_files(), [])


class TestAtomicWrite(ModesTestCase):
    def test_no_temp_residue(self):
        modes.set_mode(self.path, "a", "on")
        modes.set_mode(self.path, "b", "off")
        modes.remove_mode(self.path, "a")
        self.assertEqual(self._temp_files(), [])

    def test_write_creates_parent_dirs(self):
        nested = self.dir / "sub" / "dir" / "modes.yml"
        modes.sync(nested)
        self.assertTrue(nested.exists())


class TestDefaultModePreserved(ModesTestCase):
    def test_default_mode_preserved_across_set_and_remove(self):
        modes.sync(self.path, default_mode="off")
        modes.set_mode(self.path, "proj", "on")
        self.assertEqual(modes.list_modes(self.path)["default_mode"], "off")
        modes.remove_mode(self.path, "proj")
        self.assertEqual(modes.list_modes(self.path)["default_mode"], "off")

    def test_set_on_fresh_file_uses_backcompat_default(self):
        modes.set_mode(self.path, "proj", "on")
        self.assertEqual(modes.list_modes(self.path)["default_mode"],
                         modes.DEFAULT_DEFAULT_MODE)


class TestRepair(ModesTestCase):
    def test_repair_coerces_invalid_value_and_normalizes_default(self):
        # FAIL-SAFE migration: an invalid VALUE is coerced forward to `on` (kept + protected),
        # NOT dropped; a legacy/invalid default_mode normalizes to `on`. Only an invalid KEY
        # (tested separately) is dropped.
        self.path.write_text(
            "schema: awa-modes/v1\n"
            "default_mode: bogus\n"
            "modes:\n"
            "  good: on\n"
            "  bad: nonsense\n",
            encoding="utf-8",
        )
        out = modes.repair(self.path)
        self.assertEqual(out["modes"], {"good": "on", "bad": "on"})  # coerced, not dropped
        self.assertEqual(out["dropped"], {})
        self.assertTrue(out["default_mode_normalized"])
        self.assertEqual(out["default_mode"], modes.DEFAULT_DEFAULT_MODE)
        # persisted
        self.assertEqual(modes.list_modes(self.path)["modes"], {"good": "on", "bad": "on"})

    def test_repair_migrates_legacy_ask_on_to_on(self):
        # The install/overlay migration path: a pre-refactor file with default_mode: ask_on and
        # a per-repo ask_on entry self-heals to on (both), preserving `off`. This is the ONLY
        # sanctioned way a legacy `ask_on` migrates forward.
        self.path.write_text(
            "schema: awa-modes/v1\n"
            "default_mode: ask_on\n"
            "modes:\n"
            "  keepon: ask_on\n"
            "  disabled: off\n",
            encoding="utf-8",
        )
        out = modes.repair(self.path)
        self.assertEqual(out["default_mode"], "on")
        self.assertTrue(out["default_mode_normalized"])
        self.assertEqual(out["modes"], {"keepon": "on", "disabled": "off"})
        self.assertEqual(out["dropped"], {})
        # persisted + reads back through the classifier loader as on/off only
        self.assertEqual(modes.list_modes(self.path)["default_mode"], "on")
        self.assertEqual(modes.list_modes(self.path)["modes"], {"keepon": "on", "disabled": "off"})

    def test_repair_idempotent(self):
        modes.sync(self.path, default_mode="off")
        modes.set_mode(self.path, "proj", "on")
        first = modes.repair(self.path)
        text1 = self.path.read_text(encoding="utf-8")
        second = modes.repair(self.path)
        text2 = self.path.read_text(encoding="utf-8")
        self.assertEqual(text1, text2)
        self.assertEqual(first["modes"], second["modes"])

    def test_repair_missing_file_raises(self):
        with self.assertRaises(modes.ModesError):
            modes.repair(self.path)


class TestSync(ModesTestCase):
    def test_sync_creates_with_schema_and_default(self):
        out = modes.sync(self.path, default_mode="off")
        self.assertTrue(out["created"])
        self.assertEqual(out["default_mode"], "off")
        self.assertEqual(out["schema"], modes.SCHEMA)
        self.assertTrue(self.path.exists())

    def test_sync_default_backcompat_on(self):
        out = modes.sync(self.path)
        self.assertEqual(out["default_mode"], "on")

    def test_sync_idempotent_and_nondestructive(self):
        modes.sync(self.path, default_mode="off")
        modes.set_mode(self.path, "proj", "off")
        before = self.path.read_text(encoding="utf-8")
        out = modes.sync(self.path, default_mode="on")  # must NOT clobber existing
        after = self.path.read_text(encoding="utf-8")
        self.assertFalse(out["created"])
        self.assertEqual(before, after)  # preserved default_mode + entry
        self.assertEqual(modes.list_modes(self.path)["default_mode"], "off")
        self.assertEqual(modes.list_modes(self.path)["modes"], {"proj": "off"})


class TestClassifierRoundTrip(ModesTestCase):
    """A file written by modes.py must parse identically through the classifier loader."""

    def test_roundtrip_via_policyconfig(self):
        modes.sync(self.path, default_mode="off")
        modes.set_mode(self.path, "capabilities/awa", "on")
        modes.set_mode(self.path, "personal/*", "off")

        policy_path = self.dir / "worktree-policy.yml"
        policy_path.write_text(
            "version: 1\n"
            "default: include\n"
            "modes_file: worktree-modes.yml\n",
            encoding="utf-8",
        )
        cfg = policy.PolicyConfig.load(policy_path)
        self.assertEqual(cfg.default_mode, "off")
        self.assertEqual(cfg.modes["capabilities/awa"], "on")
        self.assertEqual(cfg.modes["personal/*"], "off")
        # mode_for agrees with what the tool set (glob first-match).
        self.assertEqual(policy.mode_for("capabilities/awa", cfg), "on")
        self.assertEqual(policy.mode_for("personal/legacy", cfg), "off")
        self.assertEqual(policy.mode_for("unmatched", cfg), "")


class TestResolveModesFile(ModesTestCase):
    def test_resolve_relative_to_policy_dir(self):
        policy_path = self.dir / "worktree-policy.yml"
        policy_path.write_text("modes_file: worktree-modes.yml\n", encoding="utf-8")
        resolved = modes.resolve_modes_file(policy_path)
        self.assertEqual(Path(resolved).resolve(), self.path.resolve())

    def test_resolve_none_when_no_pointer(self):
        policy_path = self.dir / "worktree-policy.yml"
        policy_path.write_text("version: 1\n", encoding="utf-8")
        self.assertIsNone(modes.resolve_modes_file(policy_path))

    def test_resolve_none_when_policy_missing(self):
        self.assertIsNone(modes.resolve_modes_file(self.dir / "nope.yml"))


class TestCliRemoveIdempotent(ModesTestCase):
    """`mode remove` on an absent entry is idempotent: exit 0 with removed=False."""

    def test_cli_remove_absent_exit_zero(self):
        import contextlib
        from engine import cli

        modes.sync(self.path, default_mode="on")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["mode", "remove", "nope", "--modes-file", str(self.path)])
        self.assertEqual(rc, 0)
        self.assertFalse(json.loads(buf.getvalue())["removed"])

    def test_cli_remove_present_exit_zero(self):
        import contextlib
        from engine import cli

        modes.set_mode(self.path, "proj", "on")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["mode", "remove", "proj", "--modes-file", str(self.path)])
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(buf.getvalue())["removed"])


def _drive(lines: list[dict]) -> list[dict]:
    stdin = io.StringIO("\n".join(json.dumps(m) for m in lines) + "\n")
    stdout = io.StringIO()
    mcp_server.serve(stdin, stdout)
    return [json.loads(ln) for ln in stdout.getvalue().splitlines() if ln.strip()]


class TestMcpModeTools(ModesTestCase):
    """The mutating MCP tools dispatch into modes.py, path-scoped to the host modes file."""

    def setUp(self):
        super().setUp()
        # Point the server's host policy at a temp policy whose modes_file is our scratch
        # file, so the write tools are scoped to it (zero-link: server-resolved, not caller).
        self._saved_policy = mcp_server._DEFAULT_POLICY
        self._saved_awa_policy = os.environ.get("AWA_POLICY")
        policy_path = self.dir / "worktree-policy.yml"
        policy_path.write_text("modes_file: worktree-modes.yml\n", encoding="utf-8")
        os.environ["AWA_POLICY"] = str(policy_path)
        mcp_server._DEFAULT_POLICY = os.environ["AWA_POLICY"]

    def tearDown(self):
        mcp_server._DEFAULT_POLICY = self._saved_policy
        if self._saved_awa_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = self._saved_awa_policy
        super().tearDown()

    def _call(self, name: str, arguments: dict | None = None) -> tuple[dict, dict]:
        resp = _drive([{
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }])
        result = resp[0]["result"]
        return result, json.loads(result["content"][0]["text"])

    def test_resolve_modes_path_via_awa_policy_env(self):
        """_resolve_modes_path() works when AWA_POLICY is set (no _DEFAULT_POLICY patch)."""
        policy_path = self.dir / "host-policy.yml"
        policy_path.write_text("modes_file: worktree-modes.yml\n", encoding="utf-8")
        saved = os.environ.get("AWA_POLICY")
        try:
            os.environ["AWA_POLICY"] = str(policy_path)
            self.assertEqual(
                Path(mcp_server._resolve_modes_path()).resolve(),
                self.path.resolve(),
            )
        finally:
            if saved is None:
                os.environ.pop("AWA_POLICY", None)
            else:
                os.environ["AWA_POLICY"] = saved

    def test_mode_tools_registered(self):
        resp = _drive([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        names = {t["name"] for t in resp[0]["result"]["tools"]}
        self.assertTrue(
            {"awa_mode_list", "awa_mode_get", "awa_mode_set", "awa_mode_remove",
             "awa_mode_repair", "awa_mode_sync"} <= names)

    def test_set_get_remove_via_mcp_mutates_only_modes_file(self):
        self._call("awa_mode_sync", {"default_mode": "off"})
        _, out = self._call("awa_mode_set", {"rel": "proj", "mode": "on"})
        self.assertEqual(out["mode"], "on")
        # written to exactly the configured modes file
        self.assertTrue(self.path.exists())
        self.assertEqual(modes.list_modes(self.path)["modes"], {"proj": "on"})
        _, got = self._call("awa_mode_get", {"rel": "proj"})
        self.assertEqual(got["mode"], "on")
        _, rm = self._call("awa_mode_remove", {"rel": "proj"})
        self.assertTrue(rm["removed"])
        self.assertEqual(modes.list_modes(self.path)["modes"], {})

    def test_set_invalid_returns_error_no_write(self):
        resp = _drive([{
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "awa_mode_set", "arguments": {"rel": "proj", "mode": "bogus"}},
        }])
        self.assertEqual(
            resp[0]["error"], {"code": -32602, "message": "Invalid params"}
        )
        self.assertFalse(self.path.exists())

    def test_broad_off_via_mcp_returns_is_error(self):
        result, out = self._call("awa_mode_set", {"rel": "*", "mode": "off"})
        self.assertTrue(result.get("isError"))
        self.assertFalse(out.get("ok", True))
        self.assertIn("broad/glob", out["error"])


if __name__ == "__main__":
    unittest.main()
