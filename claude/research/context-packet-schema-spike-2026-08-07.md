# Spike: context_packet schema + ranking (E1-S1 / E1-S2)

Date: 2026-08-07  
Status: decided for implementation

## E1-S1 — Schema vs agentmako

Mako `context_packet` includes: primary/related context, active findings, risks,
mode policy, freshness gate, scoped instructions, `_hints`, expandable tools.
Postgres/RLS/auth_path fields are **out** — our SoR is Stage-0 Spring artifacts.

**Adopted subset** (`scripts/schemas/context_packet.schema.json`):

| Field | Source |
|-------|--------|
| `schema_version` | const 1 |
| `kind` | `"context-packet"` |
| `request` | echo of input |
| `budgetTokens` | requested budget (chars/4 proxy) |
| `tokensUsed` | estimated tokens after trim |
| `truncated` | budget or provider caps hit |
| `primaryContext` | top-ranked `ContextItem`s |
| `relatedContext` | next tier |
| `activeFindings` | contested MAPS_TO / UNPROVEN facts |
| `risks` | `redaction_zones` rows |
| `providersUsed` | which providers ran |
| `_hints` | next `doc-engine query …` kinds |
| `empty` | true when no items |

No SQLite index; providers read `spring_signals.json` / `facts.jsonl` from `--run-dir`.

## E1-S2 — Ranking formula (falsifiable)

Score for item with path `P`, text `T`, bucket/provider `B`:

```
score = 0.50 * token_overlap(request_tokens, tokenize(P) ∪ tokenize(T))
      + 0.30 * bucket_priority(B)
      + 0.20 * contested_boost  # 1.0 if MAPS_TO contested / status contested else 0
```

`bucket_priority`: security=1.0, api_surface/route-trace=0.9, persistence/entity=0.8,
facts=0.7, dependents=0.6, references=0.3, other=0.4.

`token_overlap` = |A∩B| / max(1, |A|). Stable sort: (−score, path, provider).

Token proxy for budget: `chars // 4` over JSON serialization of kept items
(same heuristic as partition_repo chars/N).
