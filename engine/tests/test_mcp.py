"""MCP stdio contract: tools, fixed guidance resource, and bounded hardening."""

from __future__ import annotations

import ast
import contextlib
import io
import inspect
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import engine
from engine import lifecycle, mcp_resources, mcp_server, modes, policy, redact
from engine.tests.helpers import EngineTestCase


def _drive(lines: list[dict]) -> list[dict]:
    """Feed JSON-RPC messages through the server; collect newline-delimited responses."""
    stdin = io.StringIO("\n".join(json.dumps(m) for m in lines) + "\n")
    stdout = io.StringIO()
    mcp_server.serve(stdin, stdout)
    return [json.loads(ln) for ln in stdout.getvalue().splitlines() if ln.strip()]


def _initialize_request(rid: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "awa-test-client", "version": "1.0.0"},
        },
    }


def _drive_initialized(request: dict) -> list[dict]:
    """Run one operation after the required initialize/initialized sequence."""
    return _drive([
        _initialize_request(900),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        request,
    ])


class _NoEnvironmentAccess(dict):
    def _deny(self, *args, **kwargs):
        raise AssertionError("resource must not read the environment")

    __getitem__ = _deny
    __iter__ = _deny
    __len__ = _deny
    get = _deny
    items = _deny
    keys = _deny
    values = _deny
    copy = _deny
    __contains__ = _deny


class TestMcpContract(EngineTestCase):
    def test_initialize_advertises_tools_resources_and_shared_instructions(self):
        resp = _drive([_initialize_request()])
        self.assertEqual(resp[0]["id"], 1)
        r = resp[0]["result"]
        self.assertEqual(r["protocolVersion"], "2024-11-05")
        self.assertEqual(r["serverInfo"]["name"], "awa")
        self.assertIn("tools", r["capabilities"])
        self.assertEqual(r["capabilities"]["resources"], {})
        instructions = r["instructions"]
        for phrase in (
            "engine is off",
            "host-driven secondary context",
            "diagnostic, not authorization",
            "Lease reads check contract fields/hash only",
            "merges inline policy and referenced-file modes",
            "`default_mode` applies only at the final eligibility step",
            "sync can seed `off` only for a missing or invalid file default",
            "`list` lists git worktrees",
        ):
            self.assertIn(phrase, instructions)

    def test_release_identity_matches_engine_and_pyproject(self):
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        match = re.search(
            r'(?m)^version = "([^"]+)"$',
            pyproject.read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(match)
        self.assertEqual(mcp_server.SERVER_INFO["version"], engine.__version__)
        self.assertEqual(match.group(1), engine.__version__)

    def test_conformant_initialize_initialized_operation_sequence(self):
        responses = _drive_initialized({
            "jsonrpc": "2.0",
            "id": 901,
            "method": "resources/list",
            "params": {},
        })
        self.assertEqual([row["id"] for row in responses], [900, 901])
        self.assertIn("resources", responses[1]["result"])

    def test_tools_list_exposes_exact_catalog_without_internal_usage_metadata(self):
        resp = _drive([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        tools = resp[0]["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertTrue({"awa_status", "awa_lease_read", "awa_guard_shell"} <= names)
        self.assertTrue(
            {"awa_mode_list", "awa_mode_get", "awa_mode_set", "awa_mode_remove",
             "awa_mode_repair", "awa_mode_sync"} <= names)
        self.assertEqual(names, set(mcp_server._TOOLS))
        for tool in tools:
            self.assertNotIn("usage", tool)
        self.assertTrue(all("usage" not in spec for spec in mcp_server._TOOLS.values()))

    def test_public_guidance_encodes_independent_routing_semantics(self):
        tools = _drive([
            {"jsonrpc": "2.0", "id": 30, "method": "tools/list"}
        ])[0]["result"]["tools"]
        descriptions = {tool["name"]: tool["description"].lower() for tool in tools}
        expected = {
            "awa_status": ("classification", "root/worktree state", "not full awa health"),
            "awa_lease_read": ("required contract fields", "found:false", "never authorizes cleanup"),
            "awa_guard_shell": ("advisory", "live hook governs"),
            "awa_mode_list": ("referenced modes file", "inline host-policy", "final eligibility"),
            "awa_mode_get": ("exact referenced-file", "does not inspect inline", "final eligibility"),
            "awa_mode_set": ("persist one exact path or glob", "safety exclusions", "not proof"),
            "awa_mode_remove": ("inline/file", "matching glob", "does not guarantee"),
            "awa_mode_repair": ("existing referenced modes file", "unsafe/empty", "use sync"),
            "awa_mode_sync": (
                "referenced modes file",
                "without scanning repos",
                "missing/invalid file default",
                "eligible repo",
                "combined inline/file exact",
            ),
        }
        self.assertEqual(set(descriptions), set(expected))
        for name, phrases in expected.items():
            with self.subTest(tool=name):
                for phrase in phrases:
                    self.assertIn(phrase, descriptions[name])
        instructions = _drive([_initialize_request(31)])[0]["result"]["instructions"]
        for description in descriptions.values():
            self.assertIn(description, instructions.lower())

    def test_guidance_discloses_inline_file_merge_and_safety_exclusions(self):
        with tempfile.TemporaryDirectory(prefix="awa-mcp-inline-semantics.") as td:
            root = Path(td)
            modes_path = root / "worktree-modes.yml"
            modes_path.write_text(
                "schema: awa-modes/v1\n"
                "default_mode: off\n"
                "modes:\n"
                "  personal/*: on\n",
                encoding="utf-8",
            )
            policy_path = root / "worktree-policy.yml"
            policy_path.write_text(
                "version: 1\n"
                "default: include\n"
                "modes_file: worktree-modes.yml\n"
                "modes:\n"
                "  personal/repo: off\n",
                encoding="utf-8",
            )
            cfg = policy.PolicyConfig.load(policy_path)
            self.assertEqual(modes.get_mode(modes_path, "personal/repo")["mode"], "")
            self.assertEqual(policy.mode_for("personal/repo", cfg), "off")

            safety_cfg = policy.PolicyConfig(
                default=policy.INCLUDE,
                read_only_paths=["personal/repo"],
                modes={"personal/repo": "on"},
            )
            classified = policy.classify(
                "personal/repo",
                str(root / "personal/repo"),
                safety_cfg,
                has_origin=True,
            )
            self.assertEqual(classified.classification, policy.EXCLUDE)

        descriptions = {
            tool["name"]: tool["description"].lower()
            for tool in _drive([{
                "jsonrpc": "2.0", "id": 902, "method": "tools/list",
            }])[0]["result"]["tools"]
        }
        self.assertIn("does not inspect inline", descriptions["awa_mode_get"])
        self.assertIn("higher-priority safety exclusions", descriptions["awa_mode_set"])

    def test_glob_precedes_default_after_exact_entry_removal(self):
        with tempfile.TemporaryDirectory(prefix="awa-mcp-mode-semantics.") as td:
            root = Path(td)
            modes_path = root / "worktree-modes.yml"
            policy_path = root / "worktree-policy.yml"
            policy_path.write_text(
                "version: 1\n"
                "default: include\n"
                "modes_file: worktree-modes.yml\n",
                encoding="utf-8",
            )
            modes.sync(modes_path, default_mode="on")
            modes.set_mode(modes_path, "personal/*", "off")
            modes.set_mode(modes_path, "personal/repo", "on")
            cfg = policy.PolicyConfig.load(policy_path)
            self.assertEqual(policy.mode_for("personal/repo", cfg), "on")
            modes.remove_mode(modes_path, "personal/repo")
            cfg = policy.PolicyConfig.load(policy_path)
            self.assertEqual(cfg.default_mode, "on")
            self.assertEqual(policy.mode_for("personal/repo", cfg), "off")
            classified = policy.classify(
                "personal/repo", str(root / "personal/repo"), cfg, has_origin=True
            )
            self.assertEqual(classified.classification, policy.EXCLUDE)

        guidance = _drive([_initialize_request(32)])[0]["result"]["instructions"]
        self.assertIn("exact combined key", guidance)
        self.assertIn("first matching glob", guidance)
        self.assertIn("final eligibility", guidance)

    def test_mode_sync_off_consequence_and_consent_are_explicit(self):
        description = next(
            tool["description"]
            for tool in _drive([
                {"jsonrpc": "2.0", "id": 33, "method": "tools/list"}
            ])[0]["result"]["tools"]
            if tool["name"] == "awa_mode_sync"
        )
        self.assertIn("off excludes eligible repos", description)
        self.assertIn("combined inline/file exact or matching glob", description)
        prompt = mcp_server.consent_prompt(
            "awa_mode_sync", {"default_mode": "off"}
        )
        self.assertIn("saved default is missing or invalid", prompt)
        self.assertIn("lasting choice", prompt)
        self.assertNotEqual(prompt, mcp_server.consent_prompt("awa_mode_sync", {}))

    def test_consent_copy_states_persistence_and_exact_or_glob_scope(self):
        exact_off = mcp_server.consent_prompt(
            "awa_mode_set", {"rel": "personal/repo", "mode": "off"}
        )
        glob_off = mcp_server.consent_prompt(
            "awa_mode_set", {"rel": "personal/*", "mode": "off"}
        )
        exact_remove = mcp_server.consent_prompt(
            "awa_mode_remove", {"rel": "personal/repo"}
        )
        glob_remove = mcp_server.consent_prompt(
            "awa_mode_remove", {"rel": "personal/*"}
        )
        self.assertIn("lasting", exact_off)
        self.assertIn("this eligible repo", exact_off)
        self.assertIn("every eligible repo", glob_off)
        self.assertIn("path pattern", glob_off)
        self.assertIn("another exact setting or path pattern", exact_remove)
        self.assertIn("other saved settings", glob_remove)
        self.assertIn("eligible-repo default", exact_remove)
        self.assertNotIn("Temporarily", exact_off)

    def test_notification_produces_no_response(self):
        resp = _drive([{"jsonrpc": "2.0", "method": "notifications/initialized"}])
        self.assertEqual(resp, [])

    def test_request_method_notification_is_not_executed(self):
        fn = mock.Mock()
        with mock.patch.dict(mcp_server._TOOLS["awa_mode_set"], {"fn": fn}):
            resp = _drive([
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "awa_mode_set",
                        "arguments": {"rel": "projects/foo", "mode": "off"},
                    },
                },
                {"jsonrpc": "2.0", "id": 99, "method": "ping"},
            ])
        fn.assert_not_called()
        self.assertEqual(resp, [{"jsonrpc": "2.0", "id": 99, "result": {}}])

    def test_tools_call_guard_shell(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        resp = _drive([{
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "awa_guard_shell",
                       "arguments": {"cwd": wt, "command": "git commit -am x"}},
        }])
        payload = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertEqual(payload["permission"], "allow")  # adopted worktree

    def test_guard_shell_ignores_undeclared_caller_policy(self):
        decision = SimpleNamespace(permission="allow", reason="test", classification="include")
        with mock.patch.object(mcp_server.guard_mod, "decide_shell", return_value=decision) as decide:
            resp = _drive([{
                "jsonrpc": "2.0", "id": 31, "method": "tools/call",
                "params": {
                    "name": "awa_guard_shell",
                    "arguments": {
                        "cwd": "/tmp/repo",
                        "command": "git status",
                        "policy": "/attacker/controlled.yml",
                    },
                },
            }])
        self.assertFalse(resp[0]["result"]["isError"])
        decide.assert_called_once_with(
            "/tmp/repo", "git status", mcp_server._policy_path()
        )

    def test_tools_call_lease_read(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        resp = _drive([{
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "awa_lease_read", "arguments": {"worktree": wt}},
        }])
        payload = json.loads(resp[0]["result"]["content"][0]["text"])
        self.assertTrue(payload["found"])
        self.assertTrue(payload["valid"])

    def test_tools_call_rejects_missing_required_arguments(self):
        resp = _drive([{
            "jsonrpc": "2.0",
            "id": 35,
            "method": "tools/call",
            "params": {"name": "awa_lease_read", "arguments": {}},
        }])
        self.assertEqual(
            resp[0]["error"], {"code": -32602, "message": "Invalid params"}
        )

    def test_tools_call_rejects_invalid_enum_arguments(self):
        resp = _drive([{
            "jsonrpc": "2.0",
            "id": 36,
            "method": "tools/call",
            "params": {
                "name": "awa_mode_set",
                "arguments": {"rel": "personal/repo", "mode": "maybe"},
            },
        }])
        self.assertEqual(
            resp[0]["error"], {"code": -32602, "message": "Invalid params"}
        )

    def test_status_tool_failure_sets_is_error_without_leaking_exception(self):
        with mock.patch.object(mcp_server.state_mod, "State", side_effect=OSError("/secret/path")):
            resp = _drive([{
                "jsonrpc": "2.0",
                "id": 37,
                "method": "tools/call",
                "params": {"name": "awa_status", "arguments": {}},
            }])
        result = resp[0]["result"]
        self.assertTrue(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload, {"ok": False, "error": "Engine status unavailable"})
        self.assertNotIn("/secret/path", json.dumps(resp[0]))

    def test_unknown_tool_errors(self):
        resp = _drive([{"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "secret-tool-name", "arguments": {}}}])
        self.assertEqual(resp[0]["error"]["code"], -32602)
        self.assertEqual(resp[0]["error"]["message"], "Invalid tool name")
        self.assertNotIn("secret-tool-name", json.dumps(resp[0]))

    def test_non_finite_tool_output_is_not_emitted(self):
        with mock.patch.dict(
            mcp_server._TOOLS["awa_status"],
            {"fn": mock.Mock(return_value={"metric": float("nan")})},
        ):
            resp = _drive([{
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {"name": "awa_status", "arguments": {}},
            }])
        self.assertEqual(
            resp[0]["error"], {"code": -32603, "message": "Tool execution failed"}
        )
        self.assertNotIn("NaN", json.dumps(resp[0]))

    def test_resources_list_is_single_fixed_descriptor(self):
        resp = _drive_initialized(
            {"jsonrpc": "2.0", "id": 6, "method": "resources/list", "params": {}}
        )
        resources = resp[-1]["result"]["resources"]
        self.assertEqual(resources, mcp_resources.list_resources())
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["uri"], mcp_resources.OPERATOR_GUIDE_URI)
        self.assertEqual(resources[0]["mimeType"], "text/markdown")
        self.assertEqual(
            set(resources[0]), {"uri", "name", "description", "mimeType"}
        )

    def test_resources_read_is_deterministic_bounded_and_matches_inline_guidance(self):
        request = {
            "jsonrpc": "2.0", "id": 7, "method": "resources/read",
            "params": {"uri": mcp_resources.OPERATOR_GUIDE_URI},
        }
        first = _drive_initialized(request)[-1]["result"]["contents"]
        second = _drive_initialized(request)[-1]["result"]["contents"]
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        content = first[0]
        self.assertEqual(content["uri"], mcp_resources.OPERATOR_GUIDE_URI)
        self.assertEqual(content["mimeType"], "text/markdown")
        self.assertLessEqual(len(content["text"].split()), 500)
        initialize = _drive([_initialize_request(8)])[0]["result"]
        self.assertEqual(
            content["text"],
            "# AWA operator guide (v1)\n\n" + initialize["instructions"],
        )

    def test_resource_module_has_only_pure_dependencies(self):
        tree = ast.parse(inspect.getsource(mcp_resources))
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module)
        self.assertEqual(imported_modules, {"__future__", "typing"})

    def test_resource_read_performs_no_io_or_live_reads_and_emits_no_secrets(self):
        secret = "ghp_not-a-real-secret-value"
        host_path = "/Users/example/private/awa-policy.yml"
        request = {
            "jsonrpc": "2.0", "id": 9, "method": "resources/read",
            "params": {"uri": mcp_resources.OPERATOR_GUIDE_URI},
        }
        forbidden = AssertionError("resource must not perform external reads")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                os,
                "environ",
                _NoEnvironmentAccess({"AWA_POLICY": host_path, "TEST_SECRET": secret}),
            ))
            stack.enter_context(mock.patch("builtins.open", side_effect=forbidden))
            for method in ("exists", "open", "read_bytes", "read_text"):
                stack.enter_context(mock.patch.object(Path, method, side_effect=forbidden))
            for target, attribute in (
                (mcp_server.state_mod, "State"),
                (mcp_server.lease_mod, "read_lease"),
                (mcp_server.guard_mod, "decide_shell"),
                (mcp_server.modes_mod, "list_modes"),
                (mcp_server.modes_mod, "get_mode"),
                (mcp_server.modes_mod, "set_mode"),
                (mcp_server.modes_mod, "remove_mode"),
                (mcp_server.modes_mod, "repair"),
                (mcp_server.modes_mod, "sync"),
                (mcp_server.modes_mod, "resolve_modes_file"),
            ):
                stack.enter_context(mock.patch.object(target, attribute, side_effect=forbidden))
            payload = mcp_resources.read_resource(
                mcp_resources.OPERATOR_GUIDE_URI, mcp_server._TOOLS
            )
            self.assertIsNotNone(payload)
        serialized = json.dumps(payload)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(host_path, serialized)
        self.assertEqual(redact.redact(serialized), serialized)
        for live_field in (
            '"active_leases":',
            '"detections":',
            '"wal"',
            "SQLite",
            ".awa/lease.json",
            "/Users/",
            "/home/",
            ".local/state",
        ):
            self.assertNotIn(live_field, serialized)

    def test_resource_templates_are_explicitly_empty(self):
        resp = _drive_initialized([
            {"jsonrpc": "2.0", "id": 10, "method": "resources/templates/list"}
        ][0])
        self.assertEqual(resp[-1]["result"], {"resourceTemplates": []})

    def test_resource_read_rejects_malformed_and_unknown_uris(self):
        malformed = (
            None,
            "",
            7,
            "not a uri",
            "://missing-scheme",
            "awa://assistant/operator guide/v1",
            "awa://assistant/operator-guide/%ZZ",
            "awa://[malformed-authority",
            "urn:[foo]",
            "urn:foo#bar#baz",
            "awa://assistant/path[segment]",
            "relative/path",
        )
        for index, uri in enumerate(malformed, start=11):
            with self.subTest(uri=uri):
                resp = _drive_initialized({
                    "jsonrpc": "2.0", "id": index, "method": "resources/read",
                    "params": {"uri": uri},
                })
                self.assertEqual(resp[-1]["error"]["code"], -32602)
                self.assertEqual(resp[-1]["error"]["message"], "Invalid params")
        for uri in (
            "awa://assistant/operator-guide/v2",
            mcp_resources.OPERATOR_GUIDE_URI + "?live=true",
            "urn:awa:operator-guide:v1",
            "mailto:operator@example.com",
            "custom:",
            "http://[2001:db8::1]/guide",
        ):
            with self.subTest(uri=uri):
                resp = _drive_initialized({
                    "jsonrpc": "2.0", "id": 20, "method": "resources/read",
                    "params": {"uri": uri},
                })
                self.assertEqual(resp[-1]["error"]["code"], -32002)
                self.assertEqual(resp[-1]["error"]["message"], "Resource not found")
                self.assertEqual(resp[-1]["error"]["data"], {"uri": uri})

    def test_invalid_requests_and_params_use_standard_sanitized_errors(self):
        invalid = mcp_server.handle([])
        self.assertEqual(invalid["error"], {"code": -32600, "message": "Invalid Request"})
        invalid_version = mcp_server.handle(
            {"jsonrpc": "1.0", "id": 21, "method": "ping"}
        )
        self.assertEqual(
            invalid_version["error"], {"code": -32600, "message": "Invalid Request"}
        )
        bad_params = _drive([{
            "jsonrpc": "2.0", "id": 22, "method": "resources/list", "params": [],
        }])
        self.assertEqual(
            bad_params[0]["error"], {"code": -32602, "message": "Invalid params"}
        )
        null_params = _drive([{
            "jsonrpc": "2.0", "id": 23, "method": "ping", "params": None,
        }])
        self.assertEqual(
            null_params[0]["error"], {"code": -32602, "message": "Invalid params"}
        )

    def test_request_ids_must_be_string_or_integer(self):
        invalid_ids = (None, True, False, 1.0, 1.5, -2.5, [], {}, ["nested"])
        for rid in invalid_ids:
            with self.subTest(id=rid):
                resp = _drive([{
                    "jsonrpc": "2.0", "id": rid, "method": "ping",
                }])
                self.assertEqual(
                    resp[0],
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request"},
                    },
                )
        valid = _drive([
            {"jsonrpc": "2.0", "id": "request-id", "method": "ping"},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
            {"jsonrpc": "2.0", "id": -3, "method": "ping"},
        ])
        self.assertEqual([row["id"] for row in valid], ["request-id", 7, -3])

    def test_initialize_requires_2024_11_05_client_fields(self):
        valid_params = _initialize_request()["params"]
        invalid_params = [
            {},
            {k: v for k, v in valid_params.items() if k != "protocolVersion"},
            {k: v for k, v in valid_params.items() if k != "capabilities"},
            {k: v for k, v in valid_params.items() if k != "clientInfo"},
            {**valid_params, "protocolVersion": 20241105},
            {**valid_params, "capabilities": []},
            {**valid_params, "clientInfo": {"name": "client"}},
            {**valid_params, "clientInfo": {"name": "client", "version": 1}},
        ]
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 40 + index,
                "method": "initialize",
                "params": params,
            }
            for index, params in enumerate(invalid_params)
        ]
        responses = _drive(requests)
        self.assertEqual(
            [response["error"] for response in responses],
            [{"code": -32602, "message": "Invalid params"}] * len(invalid_params),
        )

    def test_parse_error_reported(self):
        stdin = io.StringIO("{not json\n")
        stdout = io.StringIO()
        mcp_server.serve(stdin, stdout)
        resp = json.loads(stdout.getvalue().splitlines()[0])
        self.assertEqual(resp["error"]["code"], -32700)

    def test_stdio_loop_recovers_after_malformed_input(self):
        stdin = io.StringIO(
            "{not json\n"
            "[]\n"
            '{"jsonrpc":"2.0","id":23,"method":"tools/list","params":[]}\n'
            '{"jsonrpc":"2.0","id":24,"method":"ping"}\n'
        )
        stdout = io.StringIO()
        self.assertEqual(mcp_server.serve(stdin, stdout), 0)
        responses = [
            json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()
        ]
        self.assertEqual(
            [response.get("error", {}).get("code") for response in responses[:3]],
            [-32700, -32600, -32602],
        )
        self.assertEqual(responses[3], {"jsonrpc": "2.0", "id": 24, "result": {}})

    def test_stdio_rejects_deep_json_and_continues(self):
        deep = (
            '{"jsonrpc":"2.0","id":25,"method":"ping","params":{"value":'
            + "[" * (mcp_server._MAX_JSON_NESTING + 1)
            + "0"
            + "]" * (mcp_server._MAX_JSON_NESTING + 1)
            + "}}\n"
        )
        stdin = io.StringIO(
            deep + '{"jsonrpc":"2.0","id":26,"method":"ping"}\n'
        )
        stdout = io.StringIO()
        self.assertEqual(mcp_server.serve(stdin, stdout), 0)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1], {"jsonrpc": "2.0", "id": 26, "result": {}})

    def test_stdio_rejects_non_finite_json_and_continues(self):
        stdin = io.StringIO(
            '{"jsonrpc":"2.0","id":27,"method":"ping","params":{"value":NaN}}\n'
            '{"jsonrpc":"2.0","id":1e400,"method":"ping"}\n'
            '{"jsonrpc":"2.0","id":28,"method":"ping"}\n'
        )
        stdout = io.StringIO()
        self.assertEqual(mcp_server.serve(stdin, stdout), 0)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(
            [response.get("error", {}).get("code") for response in responses[:2]],
            [-32700, -32700],
        )
        self.assertEqual(responses[2], {"jsonrpc": "2.0", "id": 28, "result": {}})

    def test_stdio_rejects_oversized_message_and_continues(self):
        oversized = (
            '{"jsonrpc":"2.0","id":29,"method":"ping","params":{"padding":"'
            + "x" * mcp_server._MAX_MESSAGE_SIZE
            + '"}}\n'
        )
        stdin = io.StringIO(
            oversized + '{"jsonrpc":"2.0","id":30,"method":"ping"}\n'
        )
        stdout = io.StringIO()
        self.assertEqual(mcp_server.serve(stdin, stdout), 0)
        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1], {"jsonrpc": "2.0", "id": 30, "result": {}})


    def test_operator_guide_word_limit_is_enforced(self):
        inflated = {
            "awa_status": {
                "description": " ".join(["routing"] * 600),
                "inputSchema": {"type": "object", "properties": {}},
            }
        }
        with self.assertRaises(ValueError):
            mcp_resources.render_operator_guide(inflated)


if __name__ == "__main__":
    unittest.main()
