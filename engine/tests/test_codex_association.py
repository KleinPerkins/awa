"""ADR 0030 source qualification. Every Git/state write is disposable synthetic data."""
from __future__ import annotations

import copy
import errno
import fcntl
import io
import json
import os
import pathlib
import subprocess
import tempfile
import threading
import sys
import unittest
from unittest import mock

from engine import codex_association as abi
from engine import codex_association_files as files
from engine import codex_association_store as store
from engine.codex_association_files import Access
from engine.policy import HardNoTouchMatcher, hard_no_touch_matcher_from_data


class AssociationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-association-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        if sys.platform.startswith("linux"):
            # Linux is not a supported product host. gVisor rejects
            # RENAME_EXCHANGE with EINVAL, so these protocol fixtures model its
            # successful postcondition instead of claiming native qualification.
            # macOS runs every case against the real, unpatched kernel exchange.
            self.enterContext(mock.patch.object(store, "exchange_operation", return_value=self.fixture_exchange))
        self.state = self.root / "private-state" / "awa"
        self.enterContext(mock.patch.object(store.paths, "awa_state_dir", return_value=self.state))
        self.enterContext(mock.patch.object(store, "supported_host", return_value=True))
        self.now = 1000000
        self.clock = abi.Clock(self.now, "a" * 64, 1000000000000)
        self.matcher = HardNoTouchMatcher.empty()
        self.primary = self.root / "repo"
        self.git("init", str(self.primary))
        self.git("-C", str(self.primary), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "fixture")
        self.wt = self.root / "worktree"
        self.git("-C", str(self.primary), "worktree", "add", "-b", "fixture-one", str(self.wt))
        self.service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now)

    @staticmethod
    def fixture_exchange(directory, source, target):
        """Test-only name-swap model; deliberately not an atomic implementation.

        All names belong to this disposable fixture. The production publisher
        never imports this model or falls back to these three rename calls.
        """
        held = source + ".fixture-exchange"
        os.rename(target, held, src_dir_fd=directory, dst_dir_fd=directory)
        os.rename(source, target, src_dir_fd=directory, dst_dir_fd=directory)
        os.rename(held, source, src_dir_fd=directory, dst_dir_fd=directory)

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "DEV_SESSION_ID"}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        return subprocess.check_output(["git", *args], env=env, stderr=subprocess.DEVNULL).decode().strip()

    def request(self, chat="chat-one", *, action="record", revision=0, root=None, attachments=None):
        target = str(root or self.wt)
        snapshot = {"chat_id": chat, "current_workspace": target,
                    "attachments": attachments or [{"attachment_id": "attachment-one", "root": target, "workspace_root": target}]}
        return {"schema": "awa-codex-association-request/v1", "action": action, "expected_revision": revision,
                "host_scope": abi.HOST, "chat_id": chat, "trust": abi.TRUST, "adapter_revision": abi.ADAPTER,
                "outcome": "current", "reason": "none", "reported_started_ms": self.now - 10,
                "reported_completed_ms": self.now, "before": snapshot, "after": copy.deepcopy(snapshot)}

    def send(self, request, service=None):
        return (service or self.service).mutate(abi.canonical(request), request["action"])

    def record_path(self, chat="chat-one"):
        return self.state / "codex-associations" / "v1" / (self.service._name(chat) + ".json")

    def positive(self, chat="chat-one"):
        value, code = self.send(self.request(chat))
        self.assertEqual((code, value["outcome"], value["changed"], value["complete"]), (0, "recorded_as_observed", True, True), value)
        self.assertFalse(value["protection_claim"])
        self.assertFalse(value["writer_exclusion_granted"])
        self.assertFalse(value["cleanup_authorized"])
        return value

    def unknown(self, reason="archive_observed", revision=1):
        r = self.request(action="refresh", revision=revision)
        r.update(outcome="unknown", reason=reason, before=None, after=None)
        return r

    def test_parser_invalid_packets_do_not_access_or_create_state(self):
        base = self.request()
        cases = []
        for field, value in [("expected_revision", True), ("expected_revision", 1.0), ("expected_revision", -1),
                             ("chat_id", " x"), ("chat_id", "x\x7f"), ("chat_id", "a" * 257),
                             ("trust", "host-authenticated"), ("action", "refresh"), ("outcome", "arbitrary"),
                             ("reported_started_ms", True), ("reported_completed_ms", self.now - 60001),
                             ("reported_completed_ms", self.now + 5001)]:
            r = copy.deepcopy(base); r[field] = value; cases.append(abi.canonical(r))
        for path in ["relative", "/a/../b", "/a/./b", "/a//b", "/a/", "/~/b", "/a\x00b"]:
            r = copy.deepcopy(base); r["before"]["current_workspace"] = path; cases.append(abi.canonical(r))
        r = copy.deepcopy(base); r["before"]["extra"] = "secret"; cases.append(abi.canonical(r))
        r = copy.deepcopy(base); r["before"]["attachments"] *= 2; cases.append(abi.canonical(r))
        r = copy.deepcopy(base); r["before"]["chat_id"] = "other-chat"; cases.append(abi.canonical(r))
        r = copy.deepcopy(base); r["before"]["attachments"] *= 65; cases.append(abi.canonical(r))
        r = copy.deepcopy(base); r["outcome"] = "unknown"; r["reason"] = []; cases.append(abi.canonical(r))
        cases += [b'{"schema":1,"schema":2}', b'{"x":NaN}', b'"\\ud800"', b'\xff', b'[]', b'{' * 100,
                  b" " * (abi.REQUEST_CAP + 1)]
        with mock.patch.object(self.service, "physical_probe", side_effect=AssertionError("must not probe")), \
                mock.patch.object(self.service.access, "directory", side_effect=AssertionError("must not access state")):
            for raw in cases:
                with self.subTest(raw=raw[:70]):
                    value, code = self.service.mutate(raw, "record")
                    self.assertEqual(code, 2, value)
                    self.assertEqual(value["reason"], "invalid_input")
        self.assertFalse(self.state.exists())

    def test_depth_utf8_and_canonical_caps(self):
        self.assertEqual(abi.strict_json(b"[" * 8 + b"0" + b"]" * 8), [[[[[[[[0]]]]]]]])
        with self.assertRaises(abi.AssociationError):
            abi.strict_json(b"[" * 9 + b"0" + b"]" * 9)
        r = self.request(chat="chat-\u00e9")
        self.assertEqual(abi.parse_request(abi.canonical(r), "record", self.now)["chat_id"], "chat-\u00e9")
        r["chat_id"] = "\ud800"
        value, code = self.service.mutate(json.dumps(r).encode(), "record")
        self.assertEqual(code, 2)
        self.assertFalse(self.state.exists())

    def test_physical_probe_matches_git_and_ignores_dirty_detached_operation_state(self):
        r = abi.parse_request(abi.canonical(self.request()), "record", self.now)
        before = abi.probe(r, self.matcher)
        self.assertEqual(before["git_dir"], self.git("-C", str(self.wt), "rev-parse", "--absolute-git-dir"))
        self.assertEqual(before["common_dir"], str((self.wt / self.git("-C", str(self.wt), "rev-parse", "--git-common-dir")).resolve()))
        self.assertEqual(before["head"], self.git("-C", str(self.wt), "rev-parse", "HEAD"))
        (self.wt / "untracked-content").write_text("never read this content")
        self.git("-C", str(self.wt), "checkout", "--detach")
        (pathlib.Path(before["git_dir"]) / "MERGE_HEAD").write_text(before["head"] + "\n")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no subprocess in physical probe")):
            after = abi.probe(r, self.matcher)
        self.assertIsNone(after["branch"])
        self.assertEqual(abi.edge_key("chat-one", before), abi.edge_key("chat-one", after))

    def test_subdirectory_selection_and_noncurrent_paths_never_probed(self):
        sub = self.wt / "sub"; sub.mkdir()
        attachments = [{"attachment_id": "z", "root": str(self.wt), "workspace_root": str(sub)},
                       {"attachment_id": "a", "root": str(self.wt), "workspace_root": str(self.wt)},
                       {"attachment_id": "other", "root": "/unrelated/never-access", "workspace_root": "/unrelated/never-access"}]
        r = self.request(attachments=attachments)
        r["before"]["current_workspace"] = r["after"]["current_workspace"] = str(sub)
        reads = []
        original = Access.read
        def read(obj, path, *a, **kw):
            reads.append(path)
            self.assertFalse(path.startswith("/unrelated"))
            return original(obj, path, *a, **kw)
        with mock.patch.object(Access, "read", read):
            value, code = self.send(r)
        self.assertEqual(code, 0, value)
        rec = json.loads(self.record_path().read_bytes())
        self.assertEqual(rec["observation"]["selected_attachment_ids"], ["a", "z"])
        self.assertEqual(rec["observation"]["other_attachment_ids"], ["other"])
        self.assertNotIn(b"unrelated", self.record_path().read_bytes())
        self.assertEqual(rec["observation"]["attachment_set_sha256"], abi.digest(sorted(attachments, key=lambda x: x["attachment_id"])))

    def test_ambiguous_nested_candidates_and_bracket_change_clear_only_current(self):
        self.positive(); old_edge = json.loads(self.record_path().read_bytes())["edges"]
        r = self.request(action="refresh", revision=1)
        sub = self.wt / "nested"; sub.mkdir()
        for n in ("before", "after"):
            r[n]["current_workspace"] = str(sub)
            r[n]["attachments"].append({"attachment_id": "nested", "root": str(sub), "workspace_root": str(sub)})
        value, code = self.send(r)
        self.assertEqual((value["reason"], code, value["changed"]), ("association_conflict", 1, True))
        new = json.loads(self.record_path().read_bytes())
        self.assertIsNone(new["current_edge_key"]); self.assertEqual(new["edges"], old_edge)
        r = self.request(action="refresh", revision=2); r["after"]["attachments"] = []
        self.assertEqual(self.send(r)[0]["reason"], "association_conflict")

    def test_policy_root_and_derived_locator_refuse_before_forbidden_access(self):
        def matcher(path):
            return hard_no_touch_matcher_from_data({"version": 1, "hard_no_touch_paths": {"exact_roots": [str(path)], "managed_namespace_prefixes": []}})
        r = abi.parse_request(abi.canonical(self.request()), "record", self.now)
        with mock.patch("os.open", side_effect=AssertionError("no target access")):
            with self.assertRaisesRegex(abi.AssociationError, "policy_refused"):
                abi.probe(r, matcher(self.wt))
        forbidden = self.root / "forbidden-derived"
        (self.wt / ".git").write_text("gitdir: " + str(forbidden) + "\n")
        original = os.open
        fdpaths = {}
        def guarded(path, flags, *args, **kwargs):
            target = str(path) if os.path.isabs(path) else fdpaths[kwargs["dir_fd"]].rstrip("/") + "/" + path
            self.assertFalse(abi.inside(str(forbidden), target))
            fd = original(path, flags, *args, **kwargs); fdpaths[fd] = target
            return fd
        with mock.patch("os.open", side_effect=guarded):
            with self.assertRaisesRegex(abi.AssociationError, "policy_refused"):
                abi.probe(r, matcher(forbidden))

    def test_symlink_alias_backref_and_configuration_indirection_are_unsupported(self):
        r = abi.parse_request(abi.canonical(self.request()), "record", self.now)
        edge = abi.probe(r, self.matcher)
        alias = self.root / "alias"; alias.symlink_to(self.wt, target_is_directory=True)
        rr = self.request(root=alias)
        self.assertEqual(self.send(rr)[0]["reason"], "physical_identity_unavailable")
        config = pathlib.Path(edge["common_dir"]) / "config"; saved = config.read_bytes()
        for addition in ['\n[include]\n path = /unrelated/never-access\n', '\n[core]\n worktree = /unrelated/never-access\n', '\n[extensions]\n unsupported = true\n',
                         '\n[core]\n repositoryformatversion = 99\n', '\n[remote "fixture"]\n url = "unterminated\n', '\n[remote "fixture"]\n url = bad\x00value\n']:
            config.write_bytes(saved + addition.encode())
            with self.subTest(addition=addition):
                self.assertEqual(self.send(self.request())[0]["reason"], "physical_identity_unavailable")
        config.write_bytes(saved)
        back = pathlib.Path(edge["git_dir"]) / "gitdir"; back.write_text(str(self.primary / ".git") + "\n")
        self.assertEqual(self.send(self.request())[0]["reason"], "physical_identity_unavailable")
        self.assertFalse(self.record_path().exists())

    def worktree_config_fixture(self):
        request = abi.parse_request(abi.canonical(self.request()), "record", self.now)
        edge = abi.probe(request, self.matcher)
        common_config = pathlib.Path(edge["common_dir"]) / "config"
        common_config.write_bytes(common_config.read_bytes() + b"\n[extensions]\n worktreeConfig = true\n")
        return request, edge, pathlib.Path(edge["git_dir"]) / "config.worktree"

    def test_codex_worktree_config_matches_git_without_following_values_or_starting_helpers(self):
        request, expected, config = self.worktree_config_fixture()
        self.assertEqual(abi.probe(request, self.matcher), expected)  # Optional file absent.
        target = str(self.root / "never-read-environment.toml")
        for value in [target, '"' + target + '" # comment', '""']:
            config.write_text('[Codex]\n LocalEnvironmentConfigPath = ' + value + '\n')
            self.assertEqual(self.git("-C", str(self.wt), "rev-parse", "--show-toplevel"), str(self.wt))
            self.assertEqual(self.git("-C", str(self.wt), "rev-parse", "--absolute-git-dir"), expected["git_dir"])
            original = os.open
            def guarded(path, *args, **kwargs):
                self.assertNotEqual(str(path), target)
                self.assertNotEqual(str(path), os.path.basename(target))
                return original(path, *args, **kwargs)
            with mock.patch("os.open", side_effect=guarded), mock.patch("subprocess.Popen", side_effect=AssertionError("no helpers")):
                self.assertEqual(abi.probe(request, self.matcher), expected)
        self.positive()

    def test_worktree_config_rejects_identity_indirection_and_unknown_grammar(self):
        request, edge, config = self.worktree_config_fixture()
        for raw in [b'[core]\n worktree = /unrelated/never-access\n', b'[core]\n bare = false\n',
                    b'[extensions]\n objectFormat = sha256\n', b'[include]\n path = /unrelated/never-access\n',
                    b'[includeIf "gitdir:/x"]\n path = /unrelated/never-access\n', b'[core]\n',
                    b'[codex "subsection"]\n localEnvironmentConfigPath = x\n', b'[codex]\n unknown = x\n',
                    b'[codex]\n localEnvironmentConfigPath = "unterminated\n',
                    b'[codex]\n localEnvironmentConfigPath = x\\\ny\n', b'[codex]\n localEnvironmentConfigPath = x\x00y\n',
                    b'[codex]\n localEnvironmentConfigPath = \xff\n']:
            config.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                abi.probe(request, self.matcher)
        config.write_bytes(b'[codex]\n localEnvironmentConfigPath = /unrelated/never-access\n')
        common = pathlib.Path(edge["common_dir"]) / "config"
        original = common.read_bytes()
        for enabled in [b"false", b"invalid"]:
            common.write_bytes(original.replace(b"worktreeConfig = true", b"worktreeConfig = " + enabled))
            with self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                abi.probe(request, self.matcher)

    def test_worktree_config_rejects_unsafe_files_and_foreign_ownership(self):
        request, edge, config = self.worktree_config_fixture()
        benign = b'[codex]\n localEnvironmentConfigPath = /unrelated/never-access\n'
        for mode in [0o620, 0o602]:
            config.write_bytes(benign); config.chmod(mode)
            with self.subTest(mode=mode), self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                abi.probe(request, self.matcher)
        config.chmod(0o600)
        with mock.patch("os.getuid", return_value=os.getuid() + 1), self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
            abi.probe(request, self.matcher)
        config.write_bytes(b"#" * (abi.FILE_CAP + 1))
        with self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
            abi.probe(request, self.matcher)
        config.write_bytes(benign)
        held = config.with_name("held-config"); config.rename(held)
        for kind in ["symlink", "hardlink", "fifo", "directory"]:
            if kind == "symlink": config.symlink_to(held)
            elif kind == "hardlink": os.link(held, config)
            elif kind == "fifo": os.mkfifo(config)
            else: config.mkdir()
            with self.subTest(kind=kind), self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                abi.probe(request, self.matcher)
            if kind == "directory": config.rmdir()
            else: config.unlink()
        self.assertEqual(held.read_bytes(), benign)

    def test_worktree_extension_boolean_matches_git_quoted_whitespace_rejection(self):
        request, edge, config = self.worktree_config_fixture()
        common = pathlib.Path(edge["common_dir"]) / "config"
        original = common.read_bytes()
        for value in [b'" true "', b'"true\\t"', b'"true\\n"', b'\xc2\xa0true', b'true\xc2\xa0',
                      b'true ""', b'"true" ""', b'true\t"" # comment']:
            common.write_bytes(original.replace(b"worktreeConfig = true", b"worktreeConfig = " + value))
            with self.subTest(value=value):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.git("-C", str(self.wt), "rev-parse", "--absolute-git-dir")
                with self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                    abi.probe(request, self.matcher)
        for value in [b'"true"', b' true # comment', b'\ttrue\t']:
            common.write_bytes(original.replace(b"worktreeConfig = true", b"worktreeConfig = " + value))
            self.assertEqual(self.git("-C", str(self.wt), "rev-parse", "--absolute-git-dir"), edge["git_dir"])
            self.assertEqual(abi.probe(request, self.matcher), edge)
        # Differential coverage of concatenated/empty quoted fragments. The
        # supported subset may refuse valid Git values, but never accepts a
        # boolean that Git rejects or interprets differently.
        atoms = [b'true', b'false', b'"true"', b'"false"', b'""', b'" "']
        for left in atoms:
            for right in atoms:
                for separator in [b'', b' ', b'\t', b'\xc2\xa0']:
                    value = left + separator + right
                    raw = original.replace(b"worktreeConfig = true", b"worktreeConfig = " + value)
                    common.write_bytes(raw)
                    try:
                        oid_length, enabled = abi._config_supported(raw)
                    except abi.AssociationError:
                        continue
                    with self.subTest(concatenated=value):
                        self.assertEqual(self.git("config", "--file", str(common), "--bool", "extensions.worktreeConfig"),
                                         "true" if enabled else "false")

    def test_worktree_config_presence_bytes_and_inode_are_rechecked(self):
        request, edge, config = self.worktree_config_fixture()
        benign = b'[codex]\n localEnvironmentConfigPath = /unrelated/never-access\n'
        original = Access.read
        for change in ["appear", "disappear", "bytes", "inode"]:
            if config.exists(): config.unlink()
            if change != "appear": config.write_bytes(benign)
            count = 0
            def drift(access, path, *args, **kwargs):
                nonlocal count
                # Change once between the two physical configuration observations.
                if path == edge["common_dir"] + "/config" and kwargs.get("parent_fd") is None:
                    count += 1
                    if count == 2:
                        if change in ("disappear", "inode"): config.unlink()
                        if change != "disappear": config.write_bytes(benign + (b"# changed\n" if change == "bytes" else b""))
                return original(access, path, *args, **kwargs)
            with self.subTest(change=change), mock.patch.object(Access, "read", drift), self.assertRaisesRegex(abi.AssociationError, "identity_changed"):
                abi.probe(request, self.matcher)

    def test_worktree_config_policy_refuses_before_file_access(self):
        request, edge, config = self.worktree_config_fixture()
        config.write_text('[codex]\n localEnvironmentConfigPath = /unrelated/never-access\n')
        matcher = hard_no_touch_matcher_from_data({"version": 1, "hard_no_touch_paths": {"exact_roots": [str(config)], "managed_namespace_prefixes": []}})
        original = os.open
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(str(path), str(config))
            self.assertNotEqual(str(path), config.name)
            return original(path, *args, **kwargs)
        with mock.patch("os.open", side_effect=guarded), self.assertRaisesRegex(abi.AssociationError, "policy_refused"):
            abi.probe(request, matcher)

    def test_probe_rechecked_under_lock_binding_drift_never_promotes(self):
        self.positive()
        original = abi.probe(abi.parse_request(abi.canonical(self.request()), "record", self.now), self.matcher)
        altered = dict(original, root_ino=str(int(original["root_ino"]) + 1))
        with mock.patch.object(self.service, "physical_probe", side_effect=[original, altered]):
            value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["reason"], value["changed"]), (1, "identity_changed", True))
        self.assertIsNone(json.loads(self.record_path().read_bytes())["current_edge_key"])

    def test_two_chats_same_root_and_unknown_native_history_are_honest(self):
        self.positive(); self.positive("chat-two")
        self.assertEqual(self.send(self.unknown())[1], 0)
        value, code = self.service.inspect(worktree=str(self.wt))
        self.assertEqual((code, value["outcome"], value["complete"], value["revision"]), (0, "recorded_as_observed", False, None))
        self.assertEqual({x["chat_id"] for x in value["associations"]}, {"chat-one", "chat-two"})
        self.assertEqual([x["state"] for x in value["associations"]], ["historical", "recent_as_observed"])
        one, code = self.service.inspect(chat_id="chat-one")
        self.assertEqual((one["outcome"], one["reason"]), ("unknown", "cached_unknown"))
        self.assertNotEqual(one["reason"], "archive_observed")

    def test_revision_conflicts_preserve_exact_bytes_and_fork_needs_own_record(self):
        first = self.positive(); before = self.record_path().read_bytes()
        for r in [self.request(), self.request(action="refresh", revision=2)]:
            value, code = self.send(r)
            self.assertEqual((code, value["outcome"], value["revision"]), (1, "conflict", 1))
            self.assertEqual(self.record_path().read_bytes(), before)
        value, code = self.send(self.request("new-fork", action="refresh", revision=1))
        self.assertEqual((value["outcome"], value["revision"]), ("conflict", None))
        value, code = self.service.inspect(chat_id="new-fork")
        self.assertEqual(value["reason"], "no_record")

    def test_lock_contention_is_bounded_and_no_snapshot_change(self):
        self.positive(); old = self.record_path().read_bytes()
        lock = self.record_path().with_suffix(".lock")
        with lock.open("rb") as fp:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["reason"]), (1, "lock_busy"))
        self.assertEqual(self.record_path().read_bytes(), old)

    def test_fault_cuts_preserve_or_report_uncertain_and_never_blind_retry(self):
        self.positive()
        base = self.record_path().read_bytes()
        for stage in ["write", "file_fsync", "file_close", "before_replace", "replace_attempt", "replace",
                      "parent_fsync", "readback", "temp_cleanup", "lock_cleanup", "directory_cleanup"]:
            self.record_path().write_bytes(base)
            def fault(point):
                if point == stage:
                    raise OSError("private arbitrary failure must never escape")
            service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, fault=fault)
            value, code = self.send(self.request(action="refresh", revision=1), service)
            uncertain = stage in ["replace_attempt", "replace", "parent_fsync", "readback", "temp_cleanup", "lock_cleanup", "directory_cleanup"]
            with self.subTest(stage=stage):
                self.assertEqual(code, 1)
                self.assertEqual(value["outcome"], "durability_unconfirmed" if uncertain else "refused")
                self.assertEqual(value["reason"], "publication_failed")
                self.assertIs(value["changed"], None if uncertain else False)
                self.assertIsNone(value["revision"]); self.assertEqual(value["associations"], [])
                self.assertNotIn("arbitrary", json.dumps(value))
                if not uncertain:
                    self.assertEqual(self.record_path().read_bytes(), base)
                self.assertFalse(list(self.record_path().parent.glob(".*.tmp")))
        self.record_path().write_bytes(base)
        self.assertEqual(self.send(self.request(action="refresh", revision=1))[1], 0)
        value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((value["outcome"], value["revision"]), ("conflict", 2))

    def test_inspect_freshness_suspend_reboot_wall_rollback_and_clock_unavailable(self):
        self.positive(); original = self.record_path().read_bytes()
        for clock, reason in [(abi.Clock(self.now + 300001, self.clock.boot, self.clock.continuous_ns + 300001000000), "stale"),
                              (abi.Clock(self.now + 10, self.clock.boot, self.clock.continuous_ns + 300001000000), "stale"),
                              (abi.Clock(self.now, "b" * 64, self.clock.continuous_ns), "stale"),
                              (abi.Clock(self.now - 1, self.clock.boot, self.clock.continuous_ns + 1), "stale"),
                              (abi.Clock(self.now, None, None), "clock_unavailable")]:
            self.clock = clock
            value, code = self.service.inspect(chat_id="chat-one")
            with self.subTest(reason=reason, clock=clock):
                self.assertEqual((code, value["reason"], value["complete"]), (0, reason, False))
                self.assertTrue(all(x["state"] == "historical" for x in value["associations"]))
                self.assertEqual(self.record_path().read_bytes(), original)

    def test_unknown_create_and_absent_empty_inspection_never_create_state(self):
        r = self.request(); r.update(outcome="unknown", reason="native_unavailable", before=None, after=None)
        value, code = self.send(r)
        self.assertEqual((code, value["outcome"], value["changed"]), (1, "unknown", False))
        for kwargs in [{"chat_id": "chat-one"}, {"worktree": str(self.wt)}]:
            value, code = self.service.inspect(**kwargs)
            self.assertEqual((code, value["reason"], value["revision"], value["associations"]), (0, "no_record", None, []))
        self.assertFalse(self.state.exists())
        pathlib.Path(self.service.root).mkdir(mode=0o700, parents=True)
        os.chmod(self.state, 0o700); os.chmod(self.state / "codex-associations", 0o700)
        self.assertEqual(self.service.inspect(worktree=str(self.wt))[0]["reason"], "no_cached_match")

    def test_unsafe_modes_links_malformed_and_cross_chat_cache_refuse_without_repair(self):
        self.positive(); path = self.record_path(); original = path.read_bytes()
        os.chmod(path, 0o644)
        self.assertEqual(self.service.inspect(chat_id="chat-one")[0]["reason"], "unsafe_state")
        self.assertEqual(self.send(self.unknown())[0]["reason"], "unsafe_state")
        self.assertEqual(path.stat().st_mode & 0o777, 0o644); os.chmod(path, 0o600)
        path.write_bytes(original + b" ")
        self.assertEqual(self.service.inspect(chat_id="chat-one")[0]["reason"], "unsafe_state")
        path.write_bytes(original)
        other = path.with_name("kept-data"); path.rename(other); path.symlink_to(other)
        self.assertEqual(self.send(self.unknown())[0]["reason"], "unsafe_state")
        self.assertEqual(other.read_bytes(), original)
        path.unlink(); other.rename(path)
        data = json.loads(original); data["chat_id"] = "different-chat"; path.write_bytes(abi.canonical(data) + b"\n")
        self.assertEqual(self.service.inspect(chat_id="chat-one")[0]["reason"], "unsafe_state")

    def test_root_scan_caps_unexpected_entries_and_result_cap_are_closed(self):
        self.positive()
        directory = self.record_path().parent
        (directory / "unexpected").write_text("do not read")
        self.assertEqual(self.service.inspect(worktree=str(self.wt))[0]["reason"], "unsafe_state")
        (directory / "unexpected").unlink()
        for n in range(256):
            (directory / ("assoc-" + format(n, "064x") + ".json")).touch(mode=0o600)
        value, code = self.service.inspect(worktree=str(self.wt))
        self.assertEqual((code, value["reason"], value["associations"]), (1, "limit_exceeded", []))
        items = [{"chat_id": "x" * 256, "root": "/" + "x" * 4090, "edge_key": "a" * 64, "state": "historical", "as_of_ms": 0}] * 256
        value, code = abi.result("inspect", "historical", "stale", 0, associations=items)
        self.assertEqual((code, value["reason"], value["associations"]), (1, "limit_exceeded", []))

    def test_clock_failure_positive_create_and_refresh_do_not_claim_current(self):
        self.clock = abi.Clock(self.now, None, None)
        value, code = self.send(self.request())
        self.assertEqual((code, value["reason"], value["changed"]), (1, "clock_unavailable", False))
        self.assertFalse(self.record_path().exists())
        self.clock = abi.Clock(self.now, "a" * 64, 1000000000000); self.positive()
        self.clock = abi.Clock(self.now, None, None)
        value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["reason"], value["changed"]), (1, "clock_unavailable", True))
        self.assertIsNone(json.loads(self.record_path().read_bytes())["current_edge_key"])

    def test_inspect_never_probes_target_or_calls_lifecycle(self):
        self.positive()
        with mock.patch.object(self.service, "physical_probe", side_effect=AssertionError("not allowed")), \
                mock.patch("engine.lifecycle.adopt", side_effect=AssertionError("not allowed")), \
                mock.patch("engine.lifecycle.attest", side_effect=AssertionError("not allowed")):
            self.assertEqual(self.service.inspect(worktree=str(self.wt))[1], 0)
            self.assertEqual(self.service.inspect(chat_id="chat-one")[1], 0)

    def test_cli_closed_grammar_stdout_and_no_activation(self):
        from engine import cli
        for args in [["record", "--file", "/unrelated"], ["inspect"], ["inspect", "--chat-id", "x", "--worktree", "/unrelated"], ["unknown"]]:
            out = io.StringIO()
            with mock.patch("sys.stdout", out):
                code = cli.main(["codex-association"] + args)
            value = json.loads(out.getvalue())
            self.assertEqual((code, value["reason"]), (2, "invalid_input"))
        self.assertFalse(self.state.exists())

    def test_history_eviction_is_per_chat_deterministic_and_stays_truncated(self):
        physical = abi.probe(abi.parse_request(abi.canonical(self.request()), "record", self.now), self.matcher)
        def synthetic_probe(request, matcher):
            # Store-only synthetic identities. Physical verification is qualified
            # separately against real disposable linked repositories above.
            return dict(physical, root=request["selected_root"])
        service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, physical_probe=synthetic_probe)
        self.positive("independent-chat")
        independent = self.record_path("independent-chat").read_bytes()
        for n in range(18):
            self.now += 10
            self.clock = abi.Clock(self.now, "a" * 64, self.clock.continuous_ns + 10000000)
            r = self.request(root=self.wt / ("synthetic-" + str(n)), action="record" if n == 0 else "refresh", revision=n)
            self.assertEqual(self.send(r, service)[1], 0)
        rec = json.loads(self.record_path().read_bytes())
        self.assertEqual(len(rec["edges"]), 16)
        self.assertTrue(rec["history_truncated"])
        self.assertEqual({e["root"] for e in rec["edges"]}, {str(self.wt / ("synthetic-" + str(n))) for n in range(2, 18)})
        self.assertEqual(self.record_path("independent-chat").read_bytes(), independent)
        value, code = service.inspect(chat_id="chat-one")
        self.assertEqual((code, len(value["associations"]), value["complete"]), (0, 16, False))
        self.assertEqual(self.send(self.unknown(revision=18), service)[1], 0)
        self.assertTrue(json.loads(self.record_path().read_bytes())["history_truncated"])

    def test_path_reuse_has_new_physical_edge_and_keeps_old_history(self):
        self.positive(); old = json.loads(self.record_path().read_bytes())["current_edge_key"]
        second = self.root / "second-worktree"
        self.git("-C", str(self.primary), "worktree", "add", "-b", "fixture-two", str(second))
        self.wt.rename(self.root / "retained-old-root")
        second.rename(self.wt)
        self.git("-C", str(self.primary), "worktree", "repair", str(self.wt))
        value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual(code, 0, value)
        rec = json.loads(self.record_path().read_bytes())
        self.assertNotEqual(rec["current_edge_key"], old)
        self.assertEqual(len(rec["edges"]), 2)
        self.assertIn(old, {e["edge_key"] for e in rec["edges"]})

    def test_cooperating_concurrent_refreshes_have_one_winner_and_fresh_conflict(self):
        self.positive(); barrier = threading.Barrier(2); calls = threading.local()
        def physical(request, matcher):
            edge = abi.probe(request, matcher)
            calls.count = getattr(calls, "count", 0) + 1
            if calls.count == 1:
                barrier.wait(timeout=2)
            return edge
        service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, physical_probe=physical)
        results = []
        def work():
            results.append(self.send(self.request(action="refresh", revision=1), service))
        threads = [threading.Thread(target=work) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=5)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(sorted(code for value, code in results), [0, 1])
        self.assertEqual({value["outcome"] for value, code in results}, {"recorded_as_observed", "conflict"})
        self.assertEqual({value["revision"] for value, code in results}, {2})

    def test_revision_overflow_and_malformed_record_invariants_are_not_repaired(self):
        self.positive(); path = self.record_path(); original = path.read_bytes(); source = json.loads(original)
        edits = [lambda r:r.update(extra="forbidden"), lambda r:r.update(revision=True),
                 lambda r:r["observation"].update(attachment_set_sha256="bad"),
                 lambda r:r["observation"].update(other_attachment_ids=["attachment-one"]),
                 lambda r:r["observation"].update(continuous_ns=-1),
                 lambda r:r["edges"][0].update(root_ino="01"),
                 lambda r:r["edges"][0].update(edge_key="b" * 64),
                 lambda r:r["edges"].append(copy.deepcopy(r["edges"][0])),
                 lambda r:r.update(current_edge_key=None)]
        for edit in edits:
            r = copy.deepcopy(source); edit(r); encoded = abi.canonical(r) + b"\n"; path.write_bytes(encoded)
            value, code = self.service.inspect(chat_id="chat-one")
            self.assertEqual((code, value["reason"], value["associations"]), (1, "unsafe_state", []))
            self.assertEqual(path.read_bytes(), encoded)
        source["revision"] = abi.MAX_INT; path.write_bytes(abi.canonical(source) + b"\n"); before = path.read_bytes()
        value, code = self.send(self.request(action="refresh", revision=abi.MAX_INT))
        self.assertEqual((code, value["reason"]), (1, "limit_exceeded")); self.assertEqual(path.read_bytes(), before)

    def test_unsafe_lock_state_directory_and_hardlink_are_never_repaired(self):
        self.positive(); path = self.record_path(); before = path.read_bytes()
        lock = path.with_suffix(".lock"); lock.unlink(); victim = self.root / "lock-victim"; victim.write_text("untouched")
        lock.symlink_to(victim)
        value, code = self.send(self.unknown())
        self.assertEqual((code, value["reason"]), (1, "unsafe_state")); self.assertEqual(victim.read_text(), "untouched")
        lock.unlink(); lock.touch(mode=0o600)
        copy_path = self.root / "hardlink"; os.link(path, copy_path)
        self.assertEqual(self.service.inspect(chat_id="chat-one")[0]["reason"], "unsafe_state")
        self.assertEqual(copy_path.read_bytes(), before); copy_path.unlink()
        os.chmod(path.parent, 0o755)
        self.assertEqual(self.send(self.unknown())[0]["reason"], "unsafe_state")
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o755)

    def test_tampered_target_or_owned_temp_is_not_overwritten_and_primary_error_survives(self):
        self.positive(); path = self.record_path(); original = path.read_bytes()
        kept = self.root / "kept-snapshot"
        def replace_target(stage):
            if stage == "before_replace":
                path.rename(kept); path.symlink_to(kept)
        service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, fault=replace_target)
        value, code = self.send(self.request(action="refresh", revision=1), service)
        self.assertEqual((code, value["reason"], value["changed"]), (1, "unsafe_state", False))
        self.assertTrue(path.is_symlink()); self.assertEqual(kept.read_bytes(), original)
        path.unlink(); kept.rename(path)
        def tamper_temp(stage):
            if stage == "before_replace":
                temporary = next(path.parent.glob(".*.tmp")); temporary.write_bytes(b"different bytes")
        service.fault = tamper_temp
        value, code = self.send(self.request(action="refresh", revision=1), service)
        self.assertEqual((code, value["reason"], value["changed"]), (1, "publication_failed", False))
        self.assertEqual(path.read_bytes(), original)
        observed = []
        def primary_and_cleanup(stage):
            observed.append(stage)
            if stage == "write":raise OSError("primary-test-failure")
            if stage == "temp_cleanup":raise OSError("secondary-test-failure")
        service.fault = primary_and_cleanup
        with self.assertRaisesRegex(OSError, "primary-test-failure"):
            with service._transaction(False, service._name("chat-one") + ".lock") as fd:
                service._publish(fd, path.name, original, original, [False])
        self.assertIn("temp_cleanup", observed)
        self.assertFalse(list(path.parent.glob(".*.tmp")))

    def test_directory_cleanup_happens_while_chat_lock_is_held(self):
        self.positive(); lock = self.record_path().with_suffix(".lock"); observed = []
        def fault(stage):
            if stage in ("directory_cleanup", "lock_cleanup"):
                with lock.open("rb") as fp:
                    try:
                        fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        observed.append((stage, "held"))
                    else:
                        observed.append((stage, "released")); fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, fault=fault)
        self.assertEqual(self.send(self.request(action="refresh", revision=1), service)[1], 0)
        self.assertEqual(observed, [("directory_cleanup", "held"), ("lock_cleanup", "released")])

    def test_under_lock_expired_evidence_becomes_unknown_on_refresh(self):
        self.positive(); before = self.record_path().read_bytes()
        self.clock = abi.Clock(self.now + 60001, "a" * 64, self.clock.continuous_ns + 60001000000)
        value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["reason"], value["changed"]), (1, "source_unsupported", True))
        r = json.loads(self.record_path().read_bytes())
        self.assertIsNone(r["current_edge_key"])
        self.assertEqual(r["revision"], 2)
        self.assertEqual(r["edges"], json.loads(before)["edges"])

    def test_clock_boot_output_size_timeout_and_environment_are_bounded(self):
        real_popen = subprocess.Popen
        def sample(raw, delay=0):
            children = []
            def popen(argv, **kwargs):
                self.assertEqual(argv, ["/usr/sbin/sysctl", "-n", "kern.boottime"])
                self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
                child = real_popen([sys.executable, "-c", "import time,os;time.sleep(" + str(delay) + ");os.write(1," + repr(raw) + ")"], **kwargs)
                children.append(child); return child
            with mock.patch.object(abi.sys, "platform", "darwin"), mock.patch("subprocess.Popen", side_effect=popen), \
                    mock.patch("engine.registration_clock.mach_continuous_time_ns", return_value=123):
                value = abi.sample_clock()
            self.assertTrue(all(c.poll() is not None for c in children))
            return value
        good = sample(b"{ sec = 7, usec = 12 } fixture\n")
        self.assertEqual((good.boot, good.continuous_ns), (abi.digest([7, 12]), 123))
        for raw, delay in [(b"bad output", 0), (b"{ sec = 7, usec = 9999999 }\n", 0), (b"x" * 257, 0), (b"", 2)]:
            value = sample(raw, delay)
            self.assertIsNone(value.boot); self.assertIsNone(value.continuous_ns)

    def test_positive_cli_uses_only_stdin_and_fixture_state(self):
        from engine import cli
        class Input:
            buffer = io.BytesIO(abi.canonical(self.request()))
        output = io.StringIO()
        with mock.patch("sys.stdin", Input()), mock.patch("sys.stdout", output), \
                mock.patch.object(store, "Store", return_value=self.service), \
                mock.patch("engine.policy.load_hard_no_touch_matcher", return_value=self.matcher):
            code = cli.main(["codex-association", "record"])
        value = json.loads(output.getvalue())
        self.assertEqual((code, value["outcome"], value["verification_source"]), (0, "recorded_as_observed", abi.TRUST))
        self.assertTrue(self.record_path().exists())
        with mock.patch.object(store, "supported_host", return_value=False):
            before = self.record_path().read_bytes()
            value, code = self.send(self.request())
            self.assertEqual((code, value["reason"]), (2, "unsupported_host"))
            self.assertEqual(self.record_path().read_bytes(), before)

    def test_record_byte_cap_refuses_unchanged_without_extra_history_eviction(self):
        physical = abi.probe(abi.parse_request(abi.canonical(self.request()), "record", self.now), self.matcher)
        def synthetic_probe(request, matcher):
            return dict(physical, root=request["selected_root"], git_dir="/" + "g" * 4090, common_dir="/" + "c" * 4090)
        service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, physical_probe=synthetic_probe)
        previous, refused = None, False
        for n in range(16):
            root = str(self.wt / ("synthetic-" + str(n)))
            attachments = [{"attachment_id": format(i, "03d") + "x" * 252, "root": root, "workspace_root": root} for i in range(64)]
            r = self.request(root=pathlib.Path(root), attachments=attachments, action="record" if n == 0 else "refresh", revision=n)
            value, code = self.send(r, service)
            if code:
                self.assertEqual((value["reason"], value["changed"]), ("limit_exceeded", False))
                self.assertEqual(self.record_path().read_bytes(), previous)
                refused = True; break
            previous = self.record_path().read_bytes()
        self.assertTrue(refused)

    def test_scan_entry_cap_and_symlinked_private_ancestor_are_closed(self):
        self.positive(); directory = self.record_path().parent
        for n in range(1025):
            (directory / ("assoc-" + format(n, "064x") + ".lock")).touch(mode=0o600)
        value, code = self.service.inspect(worktree=str(self.wt))
        self.assertEqual((code, value["reason"], value["associations"]), (1, "limit_exceeded", []))
        kept = self.root / "retained-fixture-state"; directory.rename(kept); directory.symlink_to(kept, target_is_directory=True)
        value, code = self.service.inspect(chat_id="chat-one")
        self.assertEqual((code, value["reason"]), (1, "unsafe_state"))
        self.assertTrue(directory.is_symlink())

    def test_common_locator_policy_and_configured_helpers_never_execute_or_follow(self):
        request = abi.parse_request(abi.canonical(self.request()), "record", self.now)
        physical = abi.probe(request, self.matcher)
        config = pathlib.Path(physical["common_dir"]) / "config"
        config.write_bytes(config.read_bytes() + b"\n[core]\n fsmonitor = /unrelated/helper\n hooksPath = /unrelated/hooks\n")
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no Git/helper execution")):
            self.assertEqual(abi.probe(request, self.matcher)["root"], str(self.wt))
        forbidden = self.root / "forbidden-common"
        (pathlib.Path(physical["git_dir"]) / "commondir").write_text(str(forbidden) + "\n")
        matcher = hard_no_touch_matcher_from_data({"version": 1, "hard_no_touch_paths": {"exact_roots": [str(forbidden)], "managed_namespace_prefixes": []}})
        visited = []
        original = Access.directory_identity
        def identity(obj, path):
            visited.append(path)
            self.assertFalse(abi.inside(str(forbidden), path))
            return original(obj, path)
        with mock.patch.object(Access, "directory_identity", identity):
            with self.assertRaisesRegex(abi.AssociationError, "policy_refused"):
                abi.probe(request, matcher)
        self.assertNotIn(str(forbidden), visited)

    def test_nested_bare_discovery_refuses_parent_association_without_state(self):
        nested = self.wt / "nested-bare"
        self.git("init", "--bare", str(nested))
        r = self.request()
        r["before"]["current_workspace"] = r["after"]["current_workspace"] = str(nested)
        with self.assertRaises(subprocess.CalledProcessError):
            self.git("-C", str(nested), "rev-parse", "--show-toplevel")
        value, code = self.send(r)
        self.assertEqual((code, value["reason"], value["changed"]), (1, "association_conflict", False))
        self.assertFalse(self.record_path().exists())

    def test_unqualified_derived_layout_is_refused_before_directory_access(self):
        r = abi.parse_request(abi.canonical(self.request()), "record", self.now)
        unrelated = self.root / "not-a-gitdir"
        (self.wt / ".git").write_text("gitdir: " + str(unrelated) + "\n")
        original = Access.directory_identity
        def identity(obj, path):
            self.assertNotEqual(path, str(unrelated))
            return original(obj, path)
        with mock.patch.object(Access, "directory_identity", identity):
            with self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                abi.probe(r, self.matcher)
        gitdir = self.root / "metadata" / "worktrees" / "entry"; gitdir.mkdir(parents=True)
        (self.wt / ".git").write_text("gitdir: " + str(gitdir) + "\n")
        (gitdir / "commondir").write_text(str(unrelated) + "\n")
        with mock.patch.object(Access, "directory_identity", identity):
            with self.assertRaisesRegex(abi.AssociationError, "physical_identity_unavailable"):
                abi.probe(r, self.matcher)

    def test_historical_root_view_is_incomplete_when_chat_moved_elsewhere(self):
        self.positive()
        second = self.root / "second"
        self.git("-C", str(self.primary), "worktree", "add", "-b", "fixture-two", str(second))
        self.assertEqual(self.send(self.request(root=second, action="refresh", revision=1))[1], 0)
        value, code = self.service.inspect(worktree=str(self.wt))
        self.assertEqual((code, value["outcome"], value["reason"], value["complete"]), (0, "historical", "stale", False))
        self.assertEqual(value["associations"][0]["state"], "historical")
        self.assertTrue(self.service.inspect(worktree=str(second))[0]["complete"])

    def test_CLI_initialization_errors_are_closed_without_raw_exception(self):
        for args in [["inspect", "--chat-id", "fixture-chat"], ["record"]]:
            class Input:
                buffer = io.BytesIO(abi.canonical(self.request()))
            with mock.patch.object(store.paths, "awa_state_dir", side_effect=OSError("private-exception-data")), \
                    mock.patch("engine.policy.load_hard_no_touch_matcher", return_value=self.matcher), mock.patch("sys.stdin", Input()):
                value, code = store.cli(args, "/unused-synthetic-policy")
            self.assertEqual(code, 1)
            self.assertEqual(value["reason"], "state_unavailable" if args[0] == "inspect" else "unsafe_state")
            self.assertNotIn("private-exception-data", json.dumps(value))
        self.assertFalse(self.state.exists())

    def test_nonpublishing_creates_leave_no_chat_locks_in_existing_cache(self):
        self.positive("existing-chat")
        directory = self.record_path().parent; before = set(directory.iterdir())
        for n in range(12):
            r = self.request("unknown-new-" + str(n));r.update(outcome="unknown", reason="native_unavailable", before=None, after=None)
            value, code = self.send(r)
            self.assertEqual((code, value["reason"], value["changed"]), (1, "native_unavailable", False))
        self.assertEqual(set(directory.iterdir()), before)
        self.clock = abi.Clock(self.now, None, None)
        value, code = self.send(self.request("clock-unavailable-create"))
        self.assertEqual((code, value["reason"], value["changed"]), (1, "clock_unavailable", False))
        self.assertEqual(set(directory.iterdir()), before)

    def test_namespace_mode_rename_and_lock_replacement_prevent_success(self):
        self.positive(); path = self.record_path(); original = path.read_bytes()
        for kind in ["mode", "rename", "lock", "late-rename", "late-delete", "late-case"]:
            with self.subTest(kind=kind):
                directory = path.parent; lock = path.with_suffix(".lock")
                def fault(stage):
                    if kind == "late-case" and stage == "directory_cleanup":
                        path.rename(path.with_name(path.name.upper()))
                    if kind == "late-delete" and stage == "directory_cleanup":
                        path.unlink()
                    if kind == "late-rename" and stage == "directory_cleanup":
                        directory.rename(self.root / "retained-cache");directory.mkdir(mode=0o700)
                        (self.root / "retained-cache" / lock.name).rename(lock)
                    if stage == "replace_attempt":
                        if kind == "mode":os.chmod(directory, 0o755)
                        elif kind == "rename":
                            directory.rename(self.root / "retained-cache");directory.mkdir(mode=0o700)
                        elif kind == "lock":
                            lock.rename(lock.with_name("retained-lock"));lock.touch(mode=0o600)
                service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, fault=fault)
                value, code = self.send(self.request(action="refresh", revision=1), service)
                self.assertEqual((code, value["outcome"], value["changed"], value["associations"]), (1, "durability_unconfirmed", None, []))
                if kind == "late-rename":
                    lock.rename(self.root / "retained-cache" / lock.name)
                if kind in ("rename", "late-rename"):
                    directory.rmdir();(self.root / "retained-cache").rename(directory)
                if kind == "mode":os.chmod(directory, 0o700)
                if kind == "lock":
                    lock.unlink();lock.with_name("retained-lock").rename(lock)
                if kind == "late-case":
                    path.with_name(path.name.upper()).rename(path)
                path.write_bytes(original)
                path.chmod(0o600)

    def test_atomic_create_and_exchange_preserve_concurrently_inserted_foreign_data(self):
        for action in ["record", "refresh"]:
            if action == "refresh":
                # The create race left an intentionally invalid foreign target.
                self.record_path().unlink();self.positive()
            path = self.record_path(); payload = b"unrelated-owned-private-data"
            foreign_identity = []
            def race(stage):
                if stage == "replace_attempt":
                    replacement = self.root / "foreign-insertion"
                    replacement.write_bytes(payload); replacement.chmod(0o600)
                    foreign_identity.append((replacement.stat().st_dev, replacement.stat().st_ino))
                    os.replace(replacement, path)
            service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now, fault=race)
            value, code = self.send(self.request(action=action, revision=0 if action == "record" else 1), service)
            self.assertEqual((code, value["outcome"], value["changed"], value["associations"]), (1, "durability_unconfirmed", None, []))
            preserved = [p for p in path.parent.iterdir() if p.is_file() and (p.stat().st_dev, p.stat().st_ino) == foreign_identity[0]]
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0].read_bytes(), payload)
            if action == "record":self.assertEqual(preserved[0], path)
            else:
                self.assertNotEqual(preserved[0], path)
                self.assertEqual(self.service.inspect(worktree=str(self.wt))[0]["reason"], "unsafe_state")

    def test_wall_reversal_during_receive_commits_unknown_not_positive_or_stale_claim(self):
        self.positive()
        # Request was fresh at entry, but receiver wall time reverses before the
        # final sample. Preserve its reported times; publish only uncertainty.
        self.clock = abi.Clock(self.now - 10000, "a" * 64, self.clock.continuous_ns + 1000000)
        value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["reason"], value["changed"]), (1, "clock_unavailable", True))
        r = json.loads(self.record_path().read_bytes())
        self.assertIsNone(r["current_edge_key"])
        self.assertEqual(r["observation"]["recorded_ms"], self.now - 10000)
        self.assertEqual(r["observation"]["reported_completed_ms"], self.now)

    def test_invalid_configured_state_path_is_closed_and_never_accessed(self):
        edge = abi.probe(abi.parse_request(abi.canonical(self.request()), "record", self.now), self.matcher)
        with mock.patch.object(store.paths, "awa_state_dir", return_value=pathlib.Path("relative-state")):
            service = store.Store(self.matcher, clock=lambda: self.clock, wall=lambda: self.now,
                                  physical_probe=lambda request, matcher: dict(edge))
        with mock.patch("os.open", side_effect=AssertionError("invalid state path must not be opened")):
            value, code = self.send(self.request(), service)
        self.assertEqual((code, value["reason"], value["changed"]), (1, "unsafe_state", False))

    def test_under_lock_expired_evidence_cannot_create_first_snapshot(self):
        self.clock = abi.Clock(self.now + 60001, "a" * 64, self.clock.continuous_ns + 60001000000)
        value, code = self.send(self.request())
        self.assertEqual((code, value["outcome"], value["reason"], value["changed"], value["associations"]),
                         (1, "unknown", "source_unsupported", False, []))
        self.assertFalse(self.record_path().exists())
        self.assertFalse(list(pathlib.Path(self.service.root).glob("assoc-*")))

    def test_exact_UTF8_wire_serialization_matches_the_response_cap(self):
        from engine import cli
        items = [{"chat_id": "fixture", "root": "/" + "\u00e9" * 2000 + str(n), "edge_key": format(n, "064x"),
                  "state": "historical", "as_of_ms": self.now} for n in range(16)]
        value, code = abi.result("inspect", "historical", "stale", 0, associations=items)
        self.assertLess(len(abi.canonical(value)) + 1, abi.REQUEST_CAP)
        self.assertGreater(len(json.dumps(value, indent=2).encode()) + 1, abi.REQUEST_CAP)
        out = io.StringIO()
        fake_store = mock.Mock(); fake_store.inspect.return_value = (value, code)
        with mock.patch("sys.stdout", out), mock.patch.object(store, "Store", return_value=fake_store), \
                mock.patch("engine.policy.load_hard_no_touch_matcher", return_value=self.matcher):
            emitted = cli.main(["codex-association", "inspect", "--chat-id", "fixture"])
        wire = out.getvalue().encode("utf-8")
        self.assertEqual((emitted, wire), (0, abi.canonical(value) + b"\n"))
        self.assertLessEqual(len(wire), abi.REQUEST_CAP)

    def test_private_file_and_lock_case_variants_refuse_without_repair(self):
        self.positive(); path = self.record_path(); before = path.read_bytes()
        for original in [path, path.with_suffix(".lock")]:
            variant = original.with_name(original.name.upper())
            original.rename(variant)
            if not original.exists():
                variant.rename(original)
                self.skipTest("filesystem is case-sensitive; descriptor alias seam covered separately")
            if original == path:
                self.assertEqual(self.service.inspect(chat_id="chat-one")[0]["reason"], "unsafe_state")
            self.assertEqual(self.send(self.request(action="refresh", revision=1))[0]["reason"], "unsafe_state")
            self.assertIn(variant.name, [p.name for p in original.parent.iterdir()])
            variant.rename(original)
            self.assertEqual(path.read_bytes(), before)

    def test_private_descriptor_path_proof_is_enforced_on_every_platform(self):
        self.positive(); path = self.record_path(); before = path.read_bytes()
        original = Access._kernel_path
        def alias(fd):
            actual = original(fd)
            if actual.endswith((path.name, path.with_suffix(".lock").name)):
                return str(pathlib.Path(actual).with_name(pathlib.Path(actual).name.upper()))
            return actual
        with mock.patch.object(Access, "_kernel_path", side_effect=alias):
            self.assertEqual(self.service.inspect(chat_id="chat-one")[0]["reason"], "unsafe_state")
            self.assertEqual(self.send(self.request(action="refresh", revision=1))[0]["reason"], "unsafe_state")
        self.assertEqual(path.read_bytes(), before)

    def test_unavailable_exchange_refuses_refresh_before_publication(self):
        self.positive(); path = self.record_path(); before = path.read_bytes()
        names = set(path.parent.iterdir())
        with mock.patch.object(store, "exchange_operation", side_effect=OSError(errno.ENOTSUP, "unavailable")):
            value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["outcome"], value["reason"], value["changed"]),
                         (1, "refused", "publication_failed", False))
        self.assertEqual(value["associations"], [])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(set(path.parent.iterdir()), names)

    def test_rejected_exchange_is_uncertain_without_snapshot_loss_or_fallback(self):
        self.positive(); path = self.record_path(); before = path.read_bytes()
        names = set(path.parent.iterdir())
        rejected = mock.Mock(side_effect=OSError(errno.EINVAL, "unsupported exchange flags"))
        with mock.patch.object(store, "exchange_operation", return_value=rejected):
            value, code = self.send(self.request(action="refresh", revision=1))
        self.assertEqual((code, value["outcome"], value["reason"], value["changed"]),
                         (1, "durability_unconfirmed", "publication_failed", None))
        self.assertEqual(value["associations"], [])
        rejected.assert_called_once()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(set(path.parent.iterdir()), names)


class NativeExchangeTest(unittest.TestCase):
    def test_native_exchange_swaps_or_linux_refuses_without_mutation(self):
        # This uses the real helper, independently of the Linux protocol model.
        # An unsupported macOS primitive is a failure, never a skip or a model.
        with tempfile.TemporaryDirectory(prefix="awa-association-exchange-") as tmp:
            root = pathlib.Path(tmp).resolve()
            first, second = root / "first", root / "second"
            first.write_bytes(b"old"); second.write_bytes(b"new")
            identities = [p.stat().st_ino for p in (first, second)]
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                try:
                    files.exchange_operation()(fd, first.name, second.name)
                except OSError as exc:
                    self.assertTrue(sys.platform.startswith("linux"), exc)
                    self.assertIn(exc.errno, (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP))
                    self.assertEqual([p.read_bytes() for p in (first, second)], [b"old", b"new"])
                    self.assertEqual([p.stat().st_ino for p in (first, second)], identities)
                else:
                    self.assertEqual([p.read_bytes() for p in (first, second)], [b"new", b"old"])
                    self.assertEqual([p.stat().st_ino for p in (first, second)], identities[::-1])
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
