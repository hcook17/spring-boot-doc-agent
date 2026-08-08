# doc-engine MCP adapter (read-only Stage-0 query + context_packet)

This package is a **thin stdio facade**. Business logic lives in
`doc_engine.query.mcp_tools.dispatch_tool` — do not reimplement filters here.

## E3-S1 decision

Minimal JSON-RPC/MCP-shaped stdio (no official MCP SDK pin). Swap later if needed.

## Run

```bash
export DOC_ENGINE_RUN_DIR=/path/to/pipeline-run
python adapters/mcp/server.py
```

## Cursor

See [adapters/cursor/README.md](../cursor/README.md).
