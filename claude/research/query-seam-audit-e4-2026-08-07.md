"""Seam audit (E4-S1): call sites that still Read whole signals vs packet/query.

Status: snapshot after hybrid layer land (2026-08-07).

| Location | Still full Read? | Prefer |
|----------|------------------|--------|
| file-summarizer group slice | Orchestrator-fed slice | query / context-packet for extra lookups |
| doc-writer signals slice | Dispatch slice + query guidance | context-packet for vague nav |
| gap-analyzer | Prompt lists signals+facts | context-packet first |
| software-architect-and-testing | Read paths | query evidence buckets |
| capacity_preflight | Full JSON for metrics | OK (operator tool, not agent nav) |
| gap_probe | Full signals+facts | OK (measurement) |

Action: SEARCH.md + agent prompts updated to prefer context-packet / query.
No further mandatory code moves in E4 beyond FakeProvider test + schema_check.
"""
