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

Registration in `mcp.json` requires a live Desktop check. AWA does not currently install
a `beforeMCPExecution` confirmation gate, and the contract-only ``consent_prompt`` copy
below is neither rendered nor enforced by this server. The server + protocol are verified
headlessly by the MCP contract tests.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from . import __version__
from . import (
    guard as guard_mod,
    lease as lease_mod,
    mcp_resources,
    modes as modes_mod,
    redact,
    state as state_mod,
)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "awa", "version": __version__}

# Policy resolution parity with engine/cli.py + kernel/hooks/worktree-guard.sh: honor
# AWA_POLICY from the MCP server's env (set in mcp.json at install time), else the installed
# kernel's generic default template — never a nonexistent repo-relative guess.
_AWA_HOME = os.environ.get("AWA_HOME") or str(Path(__file__).resolve().parent.parent)
_DEFAULT_POLICY = os.environ.get("AWA_POLICY") or str(
    Path(_AWA_HOME) / "kernel" / "policy" / "default-worktree-policy.yml"
)


def _policy_path() -> str:
    """Resolved host policy path (honors AWA_POLICY even if set after import)."""
    return os.environ.get("AWA_POLICY") or _DEFAULT_POLICY


# ---- tool implementations (all read-only) -----------------------------------
def _tool_failure(message: str) -> dict:
    """Return a tool-originated error payload (redacted; sets MCP isError)."""
    return {"ok": False, "error": redact.redact(message)}


def _tool_status(args: dict) -> dict:
    try:
        with state_mod.State(assert_local=False) as st:
            return {"wal": st.wal_mode(), "active_leases": st.list_leases("active"),
                    "detections": st.detections(limit=10)}
    except Exception:  # noqa: BLE001
        return _tool_failure("Engine status unavailable")


def _tool_lease_read(args: dict) -> dict:
    wt = args.get("worktree", ".")
    lz = lease_mod.read_lease(wt)
    if not lz:
        return {"found": False}
    return {"found": True, "lease": lz, "valid": not lease_mod.validate(lz)}


def _tool_guard_shell(args: dict) -> dict:
    d = guard_mod.decide_shell(args.get("cwd", "."), args.get("command", ""),
                               _policy_path())
    return {"permission": d.permission, "reason": d.reason, "classification": d.classification}


# ---- mode config tools (path-scoped mutations; reuse engine/modes.py) --------
def _resolve_modes_path() -> str:
    """Locate the host-configured modes file (zero-link; path is never caller-supplied).

    Path-scoping the write tools: the modes file is derived server-side from the host
    policy's ``modes_file:`` pointer, so an agent can only ever mutate that one file.
    """
    mf = modes_mod.resolve_modes_file(_policy_path())
    if not mf:
        raise modes_mod.ModesError(
            "no modes_file configured in the host policy; cannot manage modes"
        )
    return mf


def _tool_mode_list(args: dict) -> dict:
    try:
        return modes_mod.list_modes(_resolve_modes_path())
    except modes_mod.ModesError as exc:
        return _tool_failure(str(exc))


def _tool_mode_get(args: dict) -> dict:
    try:
        return modes_mod.get_mode(_resolve_modes_path(), args.get("rel", ""))
    except modes_mod.ModesError as exc:
        return _tool_failure(str(exc))


def _tool_mode_set(args: dict) -> dict:
    try:
        return modes_mod.set_mode(_resolve_modes_path(), args.get("rel", ""), args.get("mode"))
    except modes_mod.ModesError as exc:
        return _tool_failure(str(exc))


def _tool_mode_remove(args: dict) -> dict:
    try:
        return modes_mod.remove_mode(_resolve_modes_path(), args.get("rel", ""))
    except modes_mod.ModesError as exc:
        return _tool_failure(str(exc))


def _tool_mode_repair(args: dict) -> dict:
    try:
        return modes_mod.repair(_resolve_modes_path())
    except modes_mod.ModesError as exc:
        return _tool_failure(str(exc))


def _tool_mode_sync(args: dict) -> dict:
    try:
        return modes_mod.sync(_resolve_modes_path(), default_mode=args.get("default_mode"))
    except modes_mod.ModesError as exc:
        return _tool_failure(str(exc))


_TOOLS: dict[str, dict[str, Any]] = {
    "awa_status": {
        "description": (
            "Inspect engine bookkeeping: availability, leases, and detections—not full AWA "
            "health. Use CLI `dev-worktree.sh status` for current-repo classification/root/"
            "worktree state and `doctor` for policy/worktree health."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_status,
    },
    "awa_lease_read": {
        "description": (
            "Check one lease's required contract fields and identity hash only. found:false "
            "combines absent/unreadable/malformed; it proves neither liveness nor safety and "
            "never authorizes cleanup. CLI `dev-worktree.sh clean` instead uses active-root, "
            "git, and content checks."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"worktree": {"type": "string"}},
                        "required": ["worktree"]},
        "fn": _tool_lease_read,
    },
    "awa_guard_shell": {
        "description": (
            "Diagnose the guard decision for a command and cwd using the server-configured policy. "
            "The result is advisory, not execution or cleanup authorization; the live hook governs."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"cwd": {"type": "string"}, "command": {"type": "string"}},
                        "required": ["cwd", "command"]},
        "fn": _tool_guard_shell,
    },
    "awa_mode_list": {
        "description": (
            "List only referenced modes file exact/glob entries and default_mode. Runtime merges "
            "inline host-policy modes (file wins identical keys), then exact combined key, first "
            "matching combined glob, and default_mode only at final eligibility. Stored config "
            "is not proof of effective protection."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_mode_list,
    },
    "awa_mode_get": {
        "description": (
            "Get one exact referenced-file key; this does not inspect inline host-policy modes "
            "or resolve globs. Runtime may still use an inline exact or inline/file glob; "
            "default_mode applies only at final eligibility with no combined match."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"rel": {"type": "string",
                                               "description": "repo path/glob rel to governed root"}},
                        "required": ["rel"]},
        "fn": _tool_mode_get,
    },
    "awa_mode_set": {
        "description": (
            "Persist one exact path or glob referenced-file key as on|off. `off` excludes "
            "matches; `on` includes matches only after higher-priority safety exclusions and is "
            "not proof of protection. Runtime also merges inline host-policy modes."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"rel": {"type": "string",
                                               "description": "repo path/glob rel to governed root"},
                                       "mode": {"type": "string", "enum": ["on", "off"]}},
                        "required": ["rel", "mode"]},
        "fn": _tool_mode_set,
    },
    "awa_mode_remove": {
        "description": (
            "Persistently remove one exact referenced-file key. Runtime may reveal another "
            "inline/file exact or matching glob; default_mode applies only at final eligibility "
            "with no combined match, so removal does not guarantee a mode."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"rel": {"type": "string",
                                               "description": "repo path/glob rel to governed root"}},
                        "required": ["rel"]},
        "fn": _tool_mode_remove,
    },
    "awa_mode_repair": {
        "description": (
            "Persistently repair only an existing referenced modes file: drop unsafe/empty keys, "
            "coerce invalid/legacy values and default_mode to on. Does not inspect inline policy "
            "or scan repos; use sync if missing."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "fn": _tool_mode_repair,
    },
    "awa_mode_sync": {
        "description": (
            "Persistently ensure/normalize only the referenced modes file, without scanning repos "
            "or inline policy. Preserve entries/valid default; coerce invalid values to on and "
            "drop unsafe keys. Optional default_mode seeds only a missing/invalid file default; "
            "off excludes eligible repos with no combined inline/file exact or matching glob."
        ),
        "inputSchema": {"type": "object",
                        "properties": {"default_mode": {"type": "string",
                                                        "enum": ["on", "off"],
                                                        "description": (
                                                            "Seed only a missing or invalid default; "
                                                            "off leaves unmatched eligible repos "
                                                            "unprotected"
                                                        )}}},
        "fn": _tool_mode_sync,
    },
}


# ---- candidate consent copy (not wired into MCP execution) ------------------
# These strings are an egress-copy contract for a future host approval integration. The stdio
# server does not render or enforce them, and no production beforeMCPExecution wiring is claimed.
# Keep them honest so a future host can adopt them without understating persistent mode changes.
MUTATING_TOOLS = frozenset({"awa_mode_set", "awa_mode_remove", "awa_mode_repair", "awa_mode_sync"})


def _is_glob_key(value: Any) -> bool:
    return any(char in str(value) for char in "*?[")


def consent_prompt(name: str, args: dict | None = None) -> str | None:
    """Return contract-only candidate approval copy for a mutating tool.

    This function is not called by ``handle`` and is not production-wired. It states the lasting
    scope in plain language for a future host integration and is scanned by the egress gate.
    """
    args = args or {}
    if name == "awa_mode_set":
        want = str(args.get("mode", "")).strip().lower()
        many = _is_glob_key(args.get("rel", ""))
        if want == "off":
            if many:
                return (
                    "Save a lasting setting that stops protection for every eligible repo "
                    "matching this path pattern until the setting is changed or removed?"
                )
            return (
                "Save a lasting setting that stops protection for this eligible repo until "
                "the setting is changed or removed?"
            )
        if want == "on":
            if many:
                return (
                    "Save a lasting setting that turns protection on for matching repos when "
                    "higher-priority safety rules allow it?"
                )
            return (
                "Save a lasting setting that turns protection on for this repo when "
                "higher-priority safety rules allow it?"
            )
        return "Save a lasting protection setting for this path or path pattern?"
    if name == "awa_mode_remove":
        if _is_glob_key(args.get("rel", "")):
            return (
                "Remove this saved path-pattern setting for matching repos, knowing other saved "
                "settings may apply before the eligible-repo default?"
            )
        return (
            "Remove this saved path setting, knowing another exact setting or path pattern may "
            "apply before the eligible-repo default?"
        )
    if name == "awa_mode_repair":
        return "Tidy up your saved protection settings?"
    if name == "awa_mode_sync":
        want = str(args.get("default_mode", "")).strip().lower()
        if want == "off":
            return (
                "If the saved default is missing or invalid, save a lasting choice that stops "
                "protection for eligible repos with no exact or matching saved setting?"
            )
        return "Set up or tidy your saved protection settings while preserving a valid default?"
    return None


def _result(rid: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str, *, data: dict | None = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def _tool_result_is_error(out: Any) -> bool:
    if not isinstance(out, dict):
        return False
    if out.get("ok") is False:
        return True
    return "error" in out and out.get("ok") is not True


def _validate_tool_arguments(schema: dict, arguments: dict) -> str | None:
    """Validate tools/call arguments against the advertised inputSchema."""
    if schema.get("type", "object") != "object":
        return "invalid tool schema"
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        return "invalid tool schema"
    required = schema.get("required", [])
    if not isinstance(required, list):
        return "invalid tool schema"
    for key in required:
        if key not in arguments:
            return f"missing required argument: {key}"
    for key, value in arguments.items():
        prop = props.get(key)
        if not isinstance(prop, dict):
            continue
        expected_type = prop.get("type")
        if expected_type == "string" and not isinstance(value, str):
            return f"argument {key} must be a string"
        enum_vals = prop.get("enum")
        if isinstance(enum_vals, list) and value not in enum_vals:
            return f"argument {key} has invalid value"
    return None


def _params(msg: dict) -> dict | None:
    if "params" not in msg:
        return {}
    params = msg.get("params", {})
    return params if isinstance(params, dict) else None


def _valid_request_id(value: Any) -> bool:
    """MCP RequestId is a string or integer (never null, bool, float, array, or object)."""
    return isinstance(value, str) or (
        isinstance(value, int) and not isinstance(value, bool)
    )


def _valid_initialize_params(params: dict) -> bool:
    """Validate the required 2024-11-05 InitializeRequest fields without a schema engine."""
    if not isinstance(params.get("protocolVersion"), str):
        return False
    if not isinstance(params.get("capabilities"), dict):
        return False
    client_info = params.get("clientInfo")
    return (
        isinstance(client_info, dict)
        and isinstance(client_info.get("name"), str)
        and isinstance(client_info.get("version"), str)
    )


_URI_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9+.-]*:[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*\Z"
)
_BAD_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _looks_like_uri(value: str) -> bool:
    """Validate an absolute RFC-3986-style URI; exact matching remains registry-owned."""
    if not value or _URI_RE.fullmatch(value) is None:
        return False
    if _BAD_PERCENT_ESCAPE_RE.search(value):
        return False
    if value.count("#") > 1:
        return False
    try:
        parsed = urlsplit(value)
        if parsed.netloc:
            parsed.port
    except ValueError:
        return False
    # RFC 3986 reserves square brackets for IP literals in an authority. They are not valid
    # unescaped in a URN/path/query/fragment, even though urllib accepts those forms.
    if any("[" in part or "]" in part
           for part in (parsed.path, parsed.query, parsed.fragment)):
        return False
    return True


_MAX_JSON_NESTING = 128
_MAX_MESSAGE_SIZE = 1_048_576


def _json_nesting_within_limit(text: str) -> bool:
    """Bound object/array nesting before json.loads so parser recursion cannot kill stdio."""
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > _MAX_JSON_NESTING:
                return False
        elif char in "]}":
            depth -= 1
    return True


def _reject_json_constant(value: str) -> None:
    """Reject Python's non-standard NaN/Infinity JSON extensions."""
    raise ValueError(f"non-finite JSON number: {value}")


def _contains_non_finite(value: Any) -> bool:
    """Catch finite-looking JSON numbers such as 1e400 that decode to infinity."""
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_non_finite(k) or _contains_non_finite(v)
                   for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_non_finite(item) for item in value)
    return False


def _write_response(stdout, resp: dict) -> None:
    """Write one valid JSON response; sanitize unserializable/non-finite tool output."""
    try:
        encoded = json.dumps(resp, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        rid = resp.get("id") if _valid_request_id(resp.get("id")) else None
        encoded = json.dumps(_error(rid, -32603, "Internal error"), allow_nan=False)
    stdout.write(encoded + "\n")
    stdout.flush()


def handle(msg: Any) -> dict | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for notifications."""
    if not isinstance(msg, dict):
        return _error(None, -32600, "Invalid Request")
    rid = msg.get("id")
    method = msg.get("method")
    if msg.get("jsonrpc") != "2.0" or not isinstance(method, str):
        safe_rid = rid if _valid_request_id(rid) else None
        return _error(safe_rid, -32600, "Invalid Request")
    # MCP defines specific notifications; request methods sent without an id are ignored and
    # never executed (important for path-scoped mutating tools).
    if "id" not in msg:
        return None
    if not _valid_request_id(rid):
        return _error(None, -32600, "Invalid Request")
    params = _params(msg)
    if params is None:
        return _error(rid, -32602, "Invalid params")
    if method == "initialize":
        if not _valid_initialize_params(params):
            return _error(rid, -32602, "Invalid params")
        return _result(rid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": SERVER_INFO,
            "instructions": mcp_resources.render_guidance(_TOOLS),
        })
    if method == "tools/list":
        tools = [{"name": name, "description": spec["description"],
                  "inputSchema": spec["inputSchema"]}
                 for name, spec in _TOOLS.items()]
        return _result(rid, {"tools": tools})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(rid, -32602, "Invalid params")
        spec = _TOOLS.get(name)
        if not spec:
            return _error(rid, -32602, "Invalid tool name")
        schema_err = _validate_tool_arguments(spec["inputSchema"], arguments)
        if schema_err is not None:
            return _error(rid, -32602, "Invalid params")
        fn: Callable[[dict], dict] = spec["fn"]
        try:
            out = fn(arguments)
        except Exception:  # noqa: BLE001
            return _error(rid, -32603, "Tool execution failed")
        is_error = _tool_result_is_error(out)
        try:
            text = json.dumps(out, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            return _error(rid, -32603, "Tool execution failed")
        return _result(rid, {"content": [{"type": "text", "text": text}],
                             "isError": is_error})
    if method == "resources/list":
        return _result(rid, {"resources": mcp_resources.list_resources()})
    if method == "resources/templates/list":
        return _result(rid, {"resourceTemplates": []})
    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str) or not _looks_like_uri(uri):
            return _error(rid, -32602, "Invalid params")
        content = mcp_resources.read_resource(uri, _TOOLS)
        if content is None:
            return _error(rid, -32002, "Resource not found", data={"uri": uri})
        return _result(rid, {"contents": [content]})
    if method == "ping":
        return _result(rid, {})
    return _error(rid, -32601, "Method not found")


def serve(stdin=None, stdout=None) -> int:
    """Newline-delimited JSON-RPC loop over stdio (MCP stdio transport)."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    while True:
        line = stdin.readline(_MAX_MESSAGE_SIZE + 1)
        if line == "":
            break
        if len(line) > _MAX_MESSAGE_SIZE:
            # Drain only this oversized newline-delimited message in bounded chunks so the next
            # valid request is still processed.
            while line and not line.endswith("\n"):
                line = stdin.readline(_MAX_MESSAGE_SIZE + 1)
            _write_response(stdout, _error(None, -32700, "parse error"))
            continue
        line = line.strip()
        if not line:
            continue
        try:
            if not _json_nesting_within_limit(line):
                raise ValueError("JSON nesting limit exceeded")
            msg = json.loads(line, parse_constant=_reject_json_constant)
            if _contains_non_finite(msg):
                raise ValueError("non-finite JSON number")
        except (json.JSONDecodeError, RecursionError, ValueError):
            _write_response(stdout, _error(None, -32700, "parse error"))
            continue
        try:
            resp = handle(msg)
        except Exception:  # noqa: BLE001
            rid = msg.get("id") if isinstance(msg, dict) else None
            rid = rid if _valid_request_id(rid) else None
            resp = _error(rid, -32603, "Internal error")
        if resp is not None:
            _write_response(stdout, resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
