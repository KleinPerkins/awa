"""mcp_server.py — local stdio MCP server exposing AWA tools (Phase 7).

A minimal, dependency-free MCP server over the stdio transport (newline-delimited
JSON-RPC 2.0). It exposes AWA tools so a Desktop agent can query worktree safety/state
without shelling out. It is Desktop-only (cloud omits MCP + user hooks, per the
doc-derived L9/L10 facts).

Read-only invariant (amended): the server is read-only for SAFETY STATE (leases,
detections, guard decisions). The ONLY mutating tools are the ``awa_mode_*`` config
verbs, which are strictly PATH-SCOPED to the host-configured modes file (resolved from
the host policy's ``modes_file:`` pointer, never a caller-supplied path) and reuse
``engine/modes.py`` (no logic duplication). They never touch a repo, git, or a primary
checkout. Non-technical owners change per-repo modes through these tools in plain language.

Registration in `mcp.json` + the paired `beforeMCPExecution` gate (whether Cursor
honors a returned permission on an MCP call) require a LIVE Desktop agent to confirm;
that live check is a documented operator step for the write tools. The server + its
protocol are verified headlessly by the MCP contract test (drives
initialize/tools.list/tools.call).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from . import guard as guard_mod, lease as lease_mod, modes as modes_mod, state as state_mod

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


# ---- mode config tools (path-scoped mutations; reuse engine/modes.py) --------
def _resolve_modes_path() -> str:
    """Locate the host-configured modes file (zero-link; path is never caller-supplied).

    Path-scoping the write tools: the modes file is derived server-side from the host
    policy's ``modes_file:`` pointer, so an agent can only ever mutate that one file.
    """
    mf = modes_mod.resolve_modes_file(_DEFAULT_POLICY)
    if not mf:
        raise modes_mod.ModesError(
            "no modes_file configured in the host policy; cannot manage modes"
        )
    return mf


def _tool_mode_list(args: dict) -> dict:
    try:
        return modes_mod.list_modes(_resolve_modes_path())
    except modes_mod.ModesError as exc:
        return {"ok": False, "error": str(exc)}


def _tool_mode_get(args: dict) -> dict:
    try:
        return modes_mod.get_mode(_resolve_modes_path(), args.get("rel", ""))
    except modes_mod.ModesError as exc:
        return {"ok": False, "error": str(exc)}


def _tool_mode_set(args: dict) -> dict:
    try:
        return modes_mod.set_mode(_resolve_modes_path(), args.get("rel", ""), args.get("mode"))
    except modes_mod.ModesError as exc:
        return {"ok": False, "error": str(exc)}


def _tool_mode_remove(args: dict) -> dict:
    try:
        return modes_mod.remove_mode(_resolve_modes_path(), args.get("rel", ""))
    except modes_mod.ModesError as exc:
        return {"ok": False, "error": str(exc)}


def _tool_mode_repair(args: dict) -> dict:
    try:
        return modes_mod.repair(_resolve_modes_path())
    except modes_mod.ModesError as exc:
        return {"ok": False, "error": str(exc)}


def _tool_mode_sync(args: dict) -> dict:
    try:
        return modes_mod.sync(_resolve_modes_path(), default_mode=args.get("default_mode"))
    except modes_mod.ModesError as exc:
        return {"ok": False, "error": str(exc)}


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
    "awa_mode_list": {
        "description": ("List every explicit per-repo mode entry + the governing "
                        "default_mode from the host modes file (read-only)."),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_mode_list,
    },
    "awa_mode_get": {
        "description": "Get the explicit mode for a repo path/glob (read-only).",
        "inputSchema": {"type": "object",
                        "properties": {"rel": {"type": "string",
                                               "description": "repo path/glob rel to governed root"}},
                        "required": ["rel"]},
        "fn": _tool_mode_get,
    },
    "awa_mode_set": {
        "description": ("Set a repo's mode to on|ask_on|off in the host modes file "
                        "(path-scoped mutation; atomic; validated). `off` disables the "
                        "AWA guard for that path."),
        "inputSchema": {"type": "object",
                        "properties": {"rel": {"type": "string",
                                               "description": "repo path/glob rel to governed root"},
                                       "mode": {"type": "string", "enum": ["on", "ask_on", "off"]}},
                        "required": ["rel", "mode"]},
        "fn": _tool_mode_set,
    },
    "awa_mode_remove": {
        "description": ("Remove a repo's explicit mode entry from the host modes file "
                        "(path-scoped mutation; atomic)."),
        "inputSchema": {"type": "object",
                        "properties": {"rel": {"type": "string",
                                               "description": "repo path/glob rel to governed root"}},
                        "required": ["rel"]},
        "fn": _tool_mode_remove,
    },
    "awa_mode_repair": {
        "description": ("Normalize the host modes file: drop invalid mode values + empty "
                        "keys, normalize default_mode; report changes (idempotent)."),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_mode_repair,
    },
    "awa_mode_sync": {
        "description": ("Ensure the host modes file exists with schema awa-modes/v1 + a "
                        "default_mode (idempotent, non-destructive; preserves entries)."),
        "inputSchema": {"type": "object",
                        "properties": {"default_mode": {"type": "string",
                                                        "enum": ["on", "ask_on", "off"],
                                                        "description": "seed default_mode when creating the file"}}},
        "fn": _tool_mode_sync,
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
