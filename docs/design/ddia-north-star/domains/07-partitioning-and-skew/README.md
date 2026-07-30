---
id: domain-partitioning-and-skew
kind: domain
completeness: operational
tags: [domain, partitioning, skew, fanout, rebalancing]
related: [partition-key-and-hotspots, secondary-indexes-cross-partition, rel-partition-bounds-fanout, ch07]
last_refined: 2026-07-30
---

# Domain 07 — Partitioning and skew

**Job.** Choose how work and data are split; treat skew, secondary indexes, and rebalancing as first-class costs — not free concurrency.

## Concepts

| id | Page |
|----|------|
| `partition-key-and-hotspots` | [concepts/partition-key-and-hotspots.md](concepts/partition-key-and-hotspots.md) |
| `secondary-indexes-cross-partition` | [concepts/secondary-indexes-cross-partition.md](concepts/secondary-indexes-cross-partition.md) |

## Relationships

| id | Page |
|----|------|
| `rel-partition-bounds-fanout` | [relationships/partition-bounds-fanout.md](relationships/partition-bounds-fanout.md) |

## Chapters

`ch07` (primary); Stage-4 / capacity also cite `ch11` serving derived data

## Deviations that touch this domain

None filed yet. Raise thresholds without measuring Stage-4 shared-pool upper_bound would need a deviation.

## Anti-band-aids

- Fail if fan-out or group-count thresholds are raised to silence Stage-4 load without measuring the shared-pool upper_bound.
- Fail if a partition key is chosen without naming the hot-key / skew plan.

## Repo path witness

- [Repo] `src/doc_engine/tools/capacity_preflight.py`
- [Repo] `src/doc_engine/tools/partition_repo.py`
