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


def _jsonrpc_error(code: int, message: str, *, msg_id: Any = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj), flush=True)


def _line_byte_len(line: str) -> int:
    if isinstance(line, str):
        return len(line.encode("utf-8", errors="replace"))
    return len(line)


def _reject_oversized(line: str) -> bool:
    if _line_byte_len(line) <= MAX_LINE_BYTES:
        return False
    _emit(
        _jsonrpc_error(
            -32600,
            f"line exceeds MAX_LINE_BYTES ({MAX_LINE_BYTES})",
        )
    )
    return True


def _parse_message(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        _emit(_jsonrpc_error(-32700, "parse error"))
        return None


def _handle_or_bulkhead(msg: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return handle_message(msg)
    except Exception as exc:  # noqa: BLE001 — bulkhead: keep stdin loop alive
        msg_id = msg.get("id") if isinstance(msg, dict) else None
        _emit(_jsonrpc_error(-32603, f"internal error: {exc}", msg_id=msg_id))
        return None


def _process_stdin_line(line: str) -> None:
    if _reject_oversized(line):
        return
    line = line.strip()
    if not line:
        return
    msg = _parse_message(line)
    if msg is None:
        return
    resp = _handle_or_bulkhead(msg)
    if resp is not None:
        _emit(resp)


def main() -> int:
    try:
        require_server_root()
    except QueryPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for line in sys.stdin:
        _process_stdin_line(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
