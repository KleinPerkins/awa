"""mcp_server.py — local stdio MCP server exposing READ-ONLY AWA tools (Phase 7).

A minimal, dependency-free MCP server over the stdio transport (newline-delimited
JSON-RPC 2.0). It exposes read-only AWA tools so a Desktop agent can query worktree
safety/state without shelling out. It is Desktop-only (cloud omits MCP + user hooks,
per the doc-derived L9/L10 facts) and NEVER mutates: every tool here is inspection.

Registration in `mcp.json` + the paired `beforeMCPExecution` gate (whether Cursor
honors a returned permission on an MCP call) require a LIVE Desktop agent to confirm;
that live check is a documented operator step. The server + its protocol are verified
headlessly by the MCP contract test (drives initialize/tools.list/tools.call).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from . import guard as guard_mod, lease as lease_mod, state as state_mod

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "awa", "version": "1.0.0"}

_DEFAULT_POLICY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "policy", "worktree-policy.yml",
)


# ---- tool implementations (all read-only) -----------------------------------
def _tool_status(args: dict) -> dict:
    try:
        with state_mod.State(assert_local=False) as st:
            return {"wal": st.wal_mode(), "active_leases": st.list_leases("active"),
                    "detections": st.detections(limit=10)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _tool_lease_read(args: dict) -> dict:
    wt = args.get("worktree", ".")
    lz = lease_mod.read_lease(wt)
    if not lz:
        return {"found": False}
    return {"found": True, "lease": lz, "valid": not lease_mod.validate(lz)}


def _tool_guard_shell(args: dict) -> dict:
    d = guard_mod.decide_shell(args.get("cwd", "."), args.get("command", ""),
                               args.get("policy", _DEFAULT_POLICY))
    return {"permission": d.permission, "reason": d.reason, "classification": d.classification}


_TOOLS: dict[str, dict[str, Any]] = {
    "awa_status": {
        "description": "Read-only AWA engine status: WAL mode, active leases, recent detections.",
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_status,
    },
    "awa_lease_read": {
        "description": "Read + validate a worktree's .awa/lease.json.",
        "inputSchema": {"type": "object",
                        "properties": {"worktree": {"type": "string"}},
                        "required": ["worktree"]},
        "fn": _tool_lease_read,
    },
    "awa_guard_shell": {
        "description": "Decide allow/ask/deny for a shell command in a cwd (engine-off kernel guard).",
        "inputSchema": {"type": "object",
                        "properties": {"cwd": {"type": "string"}, "command": {"type": "string"}},
                        "required": ["cwd", "command"]},
        "fn": _tool_guard_shell,
    },
}


def _result(rid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def handle(msg: dict) -> dict | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    method = msg.get("method")
    rid = msg.get("id")
    if method == "initialize":
        return _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        tools = [{"name": name, "description": spec["description"],
                  "inputSchema": spec["inputSchema"]}
                 for name, spec in _TOOLS.items()]
        return _result(rid, {"tools": tools})
    if method == "tools/call":
        params = msg.get("params", {}) or {}
        name = params.get("name")
        spec = _TOOLS.get(name)
        if not spec:
            return _error(rid, -32602, f"unknown tool: {name}")
        fn: Callable[[dict], dict] = spec["fn"]
        try:
            out = fn(params.get("arguments", {}) or {})
        except Exception as exc:  # noqa: BLE001
            return _error(rid, -32603, f"tool error: {exc}")
        return _result(rid, {"content": [{"type": "text", "text": json.dumps(out)}],
                             "isError": False})
    if method == "ping":
        return _result(rid, {})
    if rid is not None:
        return _error(rid, -32601, f"method not found: {method}")
    return None


def serve(stdin=None, stdout=None) -> int:
    """Newline-delimited JSON-RPC loop over stdio (MCP stdio transport)."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
