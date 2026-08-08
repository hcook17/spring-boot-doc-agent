# Cursor adapter

Use **doc-engine** as the orchestrator from Cursor automations or agent rules:

```bash
pip install -e /path/to/spring-boot-doc-agent
doc-engine pipeline run /path/to/target-repo \
  --compliance-profile certified \
  --out-dir /tmp/doc-run
doc-engine certification verify /tmp/doc-run/certification.json
# equivalent: python -m doc_engine.tools.certification /tmp/doc-run/certification.json
```

Gate merges on `certified: true` in `certification.json`. Do not reimplement stage bash sequences in `.cursor` rules — call the CLI.

## Typed query + context_packet

After Stage 0, prefer bounded lookups:

```bash
doc-engine query context-packet --run-dir /tmp/doc-run --request "authorization gaps" --budget-tokens 4000
doc-engine query evidence --signals /tmp/doc-run/spring_signals.json --bucket security --limit 25
```

## MCP (optional)

Read-only MCP stdio server wrapping the same library (`adapters/mcp/`):

```json
{
  "mcpServers": {
    "doc-engine-query": {
      "command": "python",
      "args": ["adapters/mcp/server.py"],
      "env": {
        "DOC_ENGINE_RUN_DIR": "/tmp/doc-run"
      }
    }
  }
}
```

Tools: `context_packet`, `query_evidence`, `query_facts`, `query_entity`, `query_dependents`, `query_routes`, `query_route_trace`, `doc_engine_help`. All read-only; SoR remains Stage-0 JSON on disk.

