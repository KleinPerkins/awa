"""Phase 7: MCP stdio server contract (initialize / tools.list / tools.call)."""

from __future__ import annotations

import io
import json
import unittest

from engine import lifecycle, mcp_server
from engine.tests.helpers import EngineTestCase


def _drive(lines: list[dict]) -> list[dict]:
    """Feed JSON-RPC messages through the server; collect newline-delimited responses."""
    stdin = io.StringIO("\n".join(json.dumps(m) for m in lines) + "\n")
    stdout = io.StringIO()
    mcp_server.serve(stdin, stdout)
    return [json.loads(ln) for ln in stdout.getvalue().splitlines() if ln.strip()]


class TestMcpContract(EngineTestCase):
    def test_initialize_advertises_tools_capability(self):
        resp = _drive([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
        self.assertEqual(resp[0]["id"], 1)
        r = resp[0]["result"]
        self.assertIn("protocolVersion", r)
        self.assertEqual(r["serverInfo"]["name"], "awa")
        self.assertIn("tools", r["capabilities"])

    def test_tools_list_exposes_readonly_and_mode_tools(self):
        resp = _drive([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        names = {t["name"] for t in resp[0]["result"]["tools"]}
        self.assertTrue({"awa_status", "awa_lease_read", "awa_guard_shell"} <= names)
        self.assertTrue(
            {"awa_mode_list", "awa_mode_get", "awa_mode_set", "awa_mode_remove",
             "awa_mode_repair", "awa_mode_sync"} <= names)

    def test_notification_produces_no_response(self):
        resp = _drive([{"jsonrpc": "2.0", "method": "notifications/initialized"}])
        self.assertEqual(resp, [])

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

    def test_unknown_tool_errors(self):
        resp = _drive([{"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "nope", "arguments": {}}}])
        self.assertIn("error", resp[0])

    def test_parse_error_reported(self):
        stdin = io.StringIO("{not json\n")
        stdout = io.StringIO()
        mcp_server.serve(stdin, stdout)
        resp = json.loads(stdout.getvalue().splitlines()[0])
        self.assertEqual(resp["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
