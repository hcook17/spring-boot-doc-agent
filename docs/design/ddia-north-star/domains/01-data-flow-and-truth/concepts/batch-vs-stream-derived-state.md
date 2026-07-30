---
id: batch-vs-stream-derived-state
kind: concept
completeness: operational
tags: [batch, stream, etl, event-log, immutability]
epub_anchors:
  - { chapter: 11, title: "Serving Derived Data" }
  - { chapter: 12, title: "State, Streams, and Immutability" }
related: [materialized-views-and-caches, sor-vs-derived, trust-but-verify-and-auditability]
last_refined: 2026-07-30
path: domains/01-data-flow-and-truth/concepts/batch-vs-stream-derived-state.md

---

# Batch vs stream derived state

## In one sentence

Batch derives large views when freshness can lag; streams keep views continuously updated from an append-only log of facts.

## When to open

- Offline backtests vs hermetic CI fixtures.
- Whether a control should be periodic recompute or incremental.
- Immutable inputs for safe reprocessing.

## Core claims

- Batch fits ETL, training, reconciliation — high volume, delayed freshness.
- Serving derived data: stage then load; avoid live row-at-a-time writes from batch into production SoR.
- State is the fold of events; immutability of the log enables rebuild and audit.
- One log, many consumers/views — evolution without rewriting producers.

## Tradeoffs

- Batch-only → stale operational truth.
- Stream-only everywhere → operational complexity where overnight jobs suffice.
- Mutable “fixups” of history without a log → unauditable.

## Repo analogues

- Hermetic fixture non-vacuity/FP = small batch over committed corpus (CI).
- Real-corpus recall backtest = large batch on a dev machine; commit baseline not corpus.
- Dual-emit `facts.jsonl` beside signals = ledger-friendly SoR for later folds.

## Review checks

1. Is freshness requirement stated?
2. Can the derivation be replayed from immutable inputs?
3. Does the pipeline write SoR directly from a bulk job?

## Refactor signals

- CI depending on an untracked client checkout name.
- Mixing recall and precision into one batch without separate baselines.

## Anti-patterns seen

- Inventing a client-named recall baseline instead of hermetic FP fixtures (L1).

## See also

- `coverage-gates`, `materialized-views-and-caches`
