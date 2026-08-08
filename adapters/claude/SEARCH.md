# Agent search playbook (Claude Code adapter)

This repo **mandates structural search for code citations**. Text search (`grep`, `rg`, Grep tool) matches strings and comments and has produced wrong `[Evidenced — path:line]` tags in production.

## Runtime scope

| Runtime | Grep / rg | ast-grep | Glob + Read | Stage-0 query / packet | MCP |
|---------|-----------|----------|-------------|------------------------|-----|
| **Claude Code agents** | **Denied** | **Allowed** (`Bash(ast-grep:*)`) | **Allowed** | **Allowed** — `doc-engine query` / `query_artifacts` | Parallel — `adapters/mcp/server.py` |
| **Cursor IDE** | Available | Shell | Available | Prefer query/packet when run dir exists | Prefer MCP when configured |
| **CI / Python scripts** | Checker only | Structural claims | N/A | Product CLI | N/A |

## Decision tree (Claude agents)

1. **Vague task / “what’s relevant?”** when a Stage-0 `--run-dir` exists → **`context-packet` first**:
   - `doc-engine query context-packet --run-dir <run> --request "…" --budget-tokens 4000`
   - Or MCP tool `context_packet` (same library). **Containment:** set `DOC_ENGINE_ROOT` / `DOC_ENGINE_RUN_DIR`; MCP never accepts caller `root`. Items may carry `freshness` (`live` / `fresh_indexed` / `stale` / `unknown`); without a repo path the label is **`unknown`** (never a lying `fresh_indexed`). **stale ≠ delete** — re-verify with ast-grep or re-scan. Packet emission uses **row_ref** (Option A); `tokensUsed` is chars/4 over serialized emission.
2. **Navigational / evidence assembly** → specialized query:
   - `doc-engine query evidence|routes|facts|entity|dependents|route-trace …`
   - Prefer query over `Read`-ing whole `spring_signals.json`. Output is capped (`truncated`).
3. **Structural Java/Spring claim** not already in signals → `ast-grep run -l java -p '...' <path>`
   - Always try **both** `@Name` and `@Name($$$)`.
   - Zero matches means **unproven**, not absent.
4. **Find files by name/path** → `Glob`.
5. **Prose / markdown** → `Glob` then `Read`.
6. **Cross-cutting multi-line** → `semgrep` (architect-testing).
7. **TODO / FIXME candidates** → structural `ast-grep` or summarizer evidence — **not** text grep.

## Benchmark

See [`docs/search-methodology-benchmark.md`](../../docs/search-methodology-benchmark.md) and `tests/doc_engine/test_search_methodology.py`.
