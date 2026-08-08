"""Thin MCP stdio adapter over doc_engine.query (E3).

Decision (E3-S1): **minimal JSON-RPC stdio**, not the official MCP Python SDK.
Rationale: keep kernel deps slim (no new pin for stdio transport); dispatch
logic lives in ``doc_engine.query.mcp_tools`` so the adapter cannot fork SoR.
Upgrade path: swap this shell for the SDK while keeping ``dispatch_tool``.

Run::

    python -m adapters.mcp.server
    # or: python adapters/mcp/server.py

Env (required at startup):
    DOC_ENGINE_ROOT or DOC_ENGINE_RUN_DIR — containment root; never caller-overridable.
    DOC_ENGINE_RUN_DIR — also used as default run_dir when tools omit it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow `python adapters/mcp/server.py` from repo root
_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from doc_engine.query.load import QueryError, QueryPathError, require_server_root  # noqa: E402
from doc_engine.query.mcp_tools import TOOL_NAMES, dispatch_tool  # noqa: E402

MAX_LINE_BYTES = 8 * 1024 * 1024  # 8 MiB stdin line cap (H4 / Q1-1)


def _default_run_dir(arguments: dict[str, Any]) -> dict[str, Any]:
    args = dict(arguments)
    if "run_dir" not in args and "runDir" not in args:
        env = os.environ.get("DOC_ENGINE_RUN_DIR")
        if env:
            args["run_dir"] = env
    return args


def handle_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC-ish message; return response or None for notifications."""
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "doc-engine-query", "version": "0.1.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        tools = [
            {
                "name": n,
                "description": f"doc-engine read-only tool {n}",
                "inputSchema": {"type": "object", "additionalProperties": True},
                "annotations": {"readOnlyHint": True},
            }
            for n in TOOL_NAMES
        ]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        arguments = _default_run_dir(params.get("arguments") or {})
        try:
            result = dispatch_tool(str(name), arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "structuredContent": result,
                    "isError": False,
                },
            }
        except (QueryError, KeyError, TypeError, ValueError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                },
            }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main() -> int:
    try:
        require_server_root()
    except QueryPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for line in sys.stdin:
        # Size gate before strip/parse (H4 / Q1-1).
        raw_len = len(line.encode("utf-8", errors="replace")) if isinstance(line, str) else len(line)
        if raw_len > MAX_LINE_BYTES:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": f"line exceeds MAX_LINE_BYTES ({MAX_LINE_BYTES})",
                },
            }
            print(json.dumps(err), flush=True)
            continue
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "parse error"},
            }
            print(json.dumps(err), flush=True)
            continue
        try:
            resp = handle_message(msg)
        except Exception as exc:  # noqa: BLE001 — bulkhead: keep stdin loop alive
            err = {
                "jsonrpc": "2.0",
                "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32603, "message": f"internal error: {exc}"},
            }
            print(json.dumps(err), flush=True)
            continue
        if resp is not None:
            print(json.dumps(resp), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
