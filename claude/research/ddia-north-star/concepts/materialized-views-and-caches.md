---
id: materialized-views-and-caches
kind: concept
completeness: operational
tags: [materialized-view, cache, fan-out, read-model]
epub_anchors:
  - { chapter: 2, fragment: sec_introduction_materializing, title: "Materializing and Updating Timelines" }
  - { chapter: 12, title: "Maintaining materialized views" }
related: [sor-vs-derived, batch-vs-stream-derived-state, coverage-gates]
last_refined: 2026-07-30
---

# Materialized views and caches

## In one sentence

A materialized view is a stored query result kept in sync with underlying facts so reads avoid recomputing the join or scan every time.

## When to open

- Multiple consumers need different shapes of the same facts.
- A gate “view” over a ruleset (non-vacuity vs FP vs recall).
- Caching / dual indexes / fan-out on write.

## Core claims

- Materialization trades write amplification (update each follower/view) for read latency.
- One immutable fact log (or SoR) can feed several read-optimized views without changing producers.
- Caches and denormalized timelines are derived; they must be invalidate/rebuild-safe.
- Serving derived data should stage then load/swap — not hammer live SoR row-by-row from batch.

## Tradeoffs

- More views → more sync/lag surface.
- Stale view without monitoring → operators think SoR is wrong.
- One helper with two polarities (recall vs FP) → silent wrong gate.

## Repo analogues

- Positive non-vacuity, FP ratchet, and recall ratchet = three materialized checks over one ruleset.
- `certification.json` fold over stage/gate facts.
- `entity_table_map` / edges as derived joins (historically LLM-inferred → deterministic).

## Review checks

1. Is each view’s input set and refresh rule stated?
2. Are polarities separate (e.g. drop-to-zero vs rise-above-baseline)?
3. On failure, can you tell “view lag” from “SoR corruption”?

## Refactor signals

- Collapsing two ratchets into one function “with a flag”.
- Writing production artifacts from a batch/scan without a staging step.

## Anti-patterns seen

- Semgrep recall `check_ratchet` is not an FP ratchet; L1 adds `check_fp_ratchet`.

## See also

- `coverage-gates`, `batch-vs-stream-derived-state`, `sor-vs-derived`
