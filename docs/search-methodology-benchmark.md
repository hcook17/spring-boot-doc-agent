# Search methodology benchmark

Recorded expectations for `tests/doc_engine/test_search_methodology.py`. The goal is **citation precision**, not search speed.

## Fixture

`scripts/fixtures/spring_signals/` — billing demo service used by `tests/doc_engine/test_spring_signal_scan.py`.

## Cases

| Case | Tool | Expected |
|------|------|----------|
| Java sources present | Glob / filesystem | At least one `.java` file under fixture |
| Argument-bearing annotations | `ast-grep -p '@Table($$$)'` or `@Entity($$$)` | Non-empty match set on fixture |
| `@EntityScan` regression doc | `Misc.java` prose guard | Documents regex false-positive; scanner uses ast-grep rules |
| Claude hook policy | `deny_text_search.decide(Grep)` | Denied |
| ast-grep via Bash | `deny_text_search.decide(Bash, ast-grep ...)` | Allowed |

## Agent playbook

See [`adapters/claude/SEARCH.md`](../adapters/claude/SEARCH.md) — artifact query first when Stage-0 outputs exist, then ast-grep for live structural claims.

## Why not grep

Text grep matches `@Entity` inside comments/strings and cannot distinguish `@EntityScan` from `@Entity` reliably — see README drift section and `CONSTRAINTS.md` precision tradeoffs.
