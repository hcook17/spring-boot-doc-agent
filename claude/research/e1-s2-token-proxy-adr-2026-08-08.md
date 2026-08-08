# E1-S2 token proxy ADR — Option A (2026-08-08)

**Status:** Accepted  
**Context:** PR #94 / query `context_packet` budget honesty (review C2)  
**Decision:** **Option A** — emit index-style items (`row_ref`) and count the full serialized emission.

## Problem

The Stage-0 spike said the token proxy is `chars // 4` over **JSON serialization of kept items**. The first implementation deliberately excluded `payload` from `estimate_tokens` while still attaching full `payload` on emit. Probes showed ~30× under-reporting (`tokensUsed` vs real serialized size).

## Options

| Option | Shape | Trade-off |
|--------|--------|-----------|
| **A (chosen)** | Drop bulky `payload` before trim; emit `row_ref` `{path, line, provider}`; `estimate_tokens` counts full JSON of what agents receive | Packet stays an index; agents expand via `query_*` |
| B | Keep full `payload` on emit and count it in the budget | Honest but burns the budget on row dumps (anti-Mako) |

## Decision

**Option A.** Context packets are ranked **pointers**, not artifact dumps:

1. `to_emission_item` replaces `payload` with `row_ref` before `trim_to_budget`.
2. `estimate_tokens(obj) = len(json.dumps(obj)) // 4` with **no** silent field exclusion.
3. `partition_budget` splits primary/finding/risk with integer arithmetic that **sums exactly** to the budget (no `max(1, …)` overshoot for budgets 0–4).

## Consequences

- `tokensUsed` is a truthful upper bound on serialized kept items (modulo the single oversize lead-item exception already documented on `trim_to_budget`).
- Nested fan-out (`guards`, `candidates`) is capped separately via `apply_nested_cap` on query envelopes.
- Agents that need the full row call the specialized `query_*` tools with the `row_ref` coordinates.
