---
id: domain-data-flow-and-truth
kind: domain
completeness: operational
tags: [domain, sor, derived]
related: [sor-vs-derived, materialized-views-and-caches, batch-vs-stream-derived-state, rel-sor-feeds-views]
last_refined: 2026-07-30
---

# Domain 01 — Data flow and truth

**Job.** Decide what is authoritative, what is recomputable, how views are served, and how batch vs stream derivation trade freshness for cost.

## Concepts

| id | Page |
|----|------|
| `sor-vs-derived` | [concepts/system-of-record-vs-derived.md](concepts/system-of-record-vs-derived.md) |
| `materialized-views-and-caches` | [concepts/materialized-views-and-caches.md](concepts/materialized-views-and-caches.md) |
| `batch-vs-stream-derived-state` | [concepts/batch-vs-stream-derived-state.md](concepts/batch-vs-stream-derived-state.md) |

## Relationships

| id | Page |
|----|------|
| `rel-sor-feeds-views` | [relationships/sor-feeds-views.md](relationships/sor-feeds-views.md) |

## Chapters

`ch01`, `ch10`–`ch12` (see [../../chapters/](../../chapters/))

## Deviations that touch this domain

`dev-certification-derived-view`, `dev-coverage-denominator-codeql`
