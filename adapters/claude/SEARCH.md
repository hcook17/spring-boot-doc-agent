# Agent search playbook (Claude Code adapter)

This repo **mandates structural search for code citations**. Text search (`grep`, `rg`, Grep tool) matches strings and comments and has produced wrong `[Evidenced — path:line]` tags in production.

## Runtime scope

| Runtime | Grep / rg | ast-grep | Glob + Read |
|---------|-----------|----------|-------------|
| **Claude Code agents** (this adapter) | **Denied** — tool, settings.json, `deny_text_search.py` hook | **Allowed** — scoped `Bash(ast-grep:*)` in `.claude/settings.json` | **Allowed** |
| **Cursor IDE** | Available — not governed by Claude hooks | Available via Shell | Available |
| **CI / Python scripts** | Checker scripts only | Primary for structural claims | N/A |

Do not debate which tool to use inside Claude agents — follow this table.

## Decision tree (Claude agents)

1. **Structural Java/Spring claim** (`@Entity`, `@Query`, class shape) → `ast-grep run -l java -p '...' <path>`
   - Always try **both** `@Name` and `@Name($$$)` — marker-only and argument-bearing annotations are disjoint shapes.
   - Zero matches means **unproven**, not absent.
2. **Find files by name/path** → `Glob`, not grep.
3. **Prose, logs, steering prompts, markdown** → `Glob` to narrow, then `Read`.
4. **Cross-cutting multi-line patterns** → `semgrep` (see `software-architect-and-testing` agent).

## Benchmark

See [`docs/search-methodology-benchmark.md`](../../docs/search-methodology-benchmark.md) and `tests/doc_engine/test_search_methodology.py` for fixture-backed proof that ast-grep beats text grep on citation precision for this corpus.
