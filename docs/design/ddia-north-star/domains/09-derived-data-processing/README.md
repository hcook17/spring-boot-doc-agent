---
id: domain-derived-data-processing
kind: domain
completeness: operational
tags: [domain, batch, stream, derived, etl]
related: [batch-vs-stream-derived-state, rel-batch-feeds-serving, materialized-views-and-caches, sor-vs-derived, ch10, ch11, ch12]
last_refined: 2026-07-30
---

# Domain 09 — Derived data processing

**Job.** Own batch vs stream derivation mechanics and serving-layer loads. Domain `01` still owns SoR-vs-derived *truth*; this domain owns *how* views are computed and served.

## Owns

- Batch offline derivation, immutable inputs, stage+load serving.
- Stream/event-log continuous views and freshness tradeoffs.
- Choosing batch vs stream for a control (CI fixture vs incremental).

## Defers

- SoR vs derived *identity* → domain `01` (`sor-vs-derived`, `rel-sor-feeds-views`).
- Partition/skew of workers → domain `07`.
- Encoding of batch/stream payloads → domain `02`.

## Concepts

| id | Page |
|----|------|
| `batch-vs-stream-derived-state` | [concepts/batch-vs-stream-derived-state.md](concepts/batch-vs-stream-derived-state.md) |

## Relationships

| id | Page |
|----|------|
| `rel-batch-feeds-serving` | [relationships/batch-feeds-serving.md](relationships/batch-feeds-serving.md) |

## Chapters

`ch10` (bridge), `ch11` (batch), `ch12` (stream)

## Anti-band-aids

- Fail if a batch or stream job writes the SoR live without stage+load or a filed deviation.
- Fail if “real-time” is used to justify a second writer.

## Repo path witness

- [Repo] `docs/design/ddia-north-star/_build_catalog.py`
- [Repo] `src/doc_engine/tools/capacity_preflight.py`
