#!/usr/bin/env python3
"""Interactive installed MCP lifecycle smoke for ``make verify-install``."""

from __future__ import annotations

import json
import select
import subprocess
import sys
from pathlib import Path

# Source tree is on PYTHONPATH when invoked from Makefile verify-install.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine import mcp_resources  # noqa: E402


def _send(proc: subprocess.Popen, message: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _read(proc: subprocess.Popen) -> dict:
    assert proc.stdout is not None
    ready, _, _ = select.select([proc.stdout], [], [], 10)
    if not ready:
        raise AssertionError("MCP server did not respond within 10 seconds")
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise AssertionError(f"MCP server exited before responding: {stderr}")
    return json.loads(line)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: install_mcp_smoke.py LAUNCHER EXPECTED_VERSION")
    launcher, expected_version = argv
    proc = subprocess.Popen(
        [launcher, "mcp-serve"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        _send(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "awa-install-smoke", "version": "1.0.0"},
            },
        })
        init = _read(proc)
        assert init["id"] == 1
        result = init["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert result["capabilities"]["resources"] == {}
        assert result["serverInfo"] == {"name": "awa", "version": expected_version}
        instructions = result["instructions"]
        assert isinstance(instructions, str) and instructions.strip()

        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/list",
            "params": {},
        })
        resources = _read(proc)
        assert resources["id"] == 2
        descriptors = resources["result"]["resources"]
        assert len(descriptors) == 1
        assert descriptors[0]["uri"] == mcp_resources.OPERATOR_GUIDE_URI

        _send(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": mcp_resources.OPERATOR_GUIDE_URI},
        })
        read = _read(proc)
        assert read["id"] == 3
        contents = read["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["mimeType"] == "text/markdown"
        assert contents[0]["text"] == (
            "# AWA operator guide (v1)\n\n" + instructions
        )
        assert len(contents[0]["text"].split()) <= 500

        _send(proc, {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/list",
            "params": {},
        })
        tools = _read(proc)
        assert tools["id"] == 4
        names = {tool["name"] for tool in tools["result"]["tools"]}
        assert names == {
            "awa_status",
            "awa_lease_read",
            "awa_guard_shell",
            "awa_mode_list",
            "awa_mode_get",
            "awa_mode_set",
            "awa_mode_remove",
            "awa_mode_repair",
            "awa_mode_sync",
        }

        assert proc.stdin is not None
        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
