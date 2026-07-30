---
id: domain-data-flow-and-truth
kind: domain
completeness: operational
tags: [domain, sor, derived]
related: [sor-vs-derived, materialized-views-and-caches, rel-sor-feeds-views, domain-derived-data-processing]
last_refined: 2026-07-30
---

# Domain 01 — Data flow and truth

**Job.** Decide what is authoritative, what is recomputable, how views relate to SoR, and when batch vs stream *truth* questions arise. Mechanics of batch/stream jobs live in domain `09`.

## Concepts

| id | Page |
|----|------|
| `sor-vs-derived` | [concepts/system-of-record-vs-derived.md](concepts/system-of-record-vs-derived.md) |
| `materialized-views-and-caches` | [concepts/materialized-views-and-caches.md](concepts/materialized-views-and-caches.md) |

(`batch-vs-stream-derived-state` relocated under domain `09` — **id unchanged**.)

## Relationships

| id | Page |
|----|------|
| `rel-sor-feeds-views` | [relationships/sor-feeds-views.md](relationships/sor-feeds-views.md) |

## Chapters

`ch01`, plus `ch10`–`ch12` (owned with domain `09`)

## Deviations that touch this domain

`dev-certification-derived-view`, `dev-coverage-denominator-codeql`

## Anti-band-aids

- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

## Repo path witness

- [Repo] `domains/01-data-flow-and-truth/README.md`
