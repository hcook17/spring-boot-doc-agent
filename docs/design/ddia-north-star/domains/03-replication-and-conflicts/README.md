---
id: domain-replication-and-conflicts
kind: domain
completeness: operational
tags: [domain, replication, lww]
related: [replication-lag-and-lww, rel-conflict-vs-recompute]
last_refined: 2026-07-30
---

# Domain 03 — Replication and conflicts

**Job.** When copies diverge, choose recompute / single-writer / explicit merge — never silent LWW of two SoRs.

## Concepts

| id | Page |
|----|------|
| `replication-lag-and-lww` | [concepts/replication-lag-and-lww.md](concepts/replication-lag-and-lww.md) |

## Relationships

| id | Page |
|----|------|
| `rel-conflict-vs-recompute` | [relationships/conflict-vs-recompute.md](relationships/conflict-vs-recompute.md) |

## Chapters

`ch06`, `ch07` (partial depth OK where lite)

## Deviations

`dev-certification-derived-view` (LWW of certification vs facts forbidden)

## Anti-band-aids

- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

## Repo path witness

- [Repo] `domains/03-replication-and-conflicts/README.md`
