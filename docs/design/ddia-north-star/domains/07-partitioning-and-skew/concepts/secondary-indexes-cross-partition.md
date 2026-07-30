---
id: secondary-indexes-cross-partition
kind: concept
completeness: operational
tags: [partition, secondary-index, scatter-gather]
epub_anchors:
  - { chapter: 7, title: "Partitioning and Secondary Indexes" }
related: [partition-key-and-hotspots, rel-partition-bounds-fanout, materialized-views-and-caches, ch07]
last_refined: 2026-07-30
path: domains/07-partitioning-and-skew/concepts/secondary-indexes-cross-partition.md

---

# Secondary indexes and cross-partition queries

## In one sentence

Secondary indexes and queries that are not keyed by the partition key reintroduce coordination — local-index scatter/gather or a global index that itself must be partitioned.

## When to open

- A “simple” lookup by non-key attribute across groups.
- Coverage / signal joins that must touch every partition’s boundary.
- Temptation to broadcast a full evidence bucket to every worker.

## Core claims

- Local secondary index: each partition holds its own index → query fans out (scatter/gather).
- Global secondary index: one index covers all keys → the index is another partitioned dataset with its own skew.
- Cross-partition operations pay coordination cost the primary key path avoided.
- Broadcasting a repo-wide bucket to every dispatch is the extreme of scatter — engineered away here by partitioned Stage-1 edges.

## Tradeoffs

- Local index: write-local, read-expensive (fan-out).
- Global index: read-cheap for that attribute, write amplification + index skew.
- Avoiding secondary access patterns entirely may force worse primary keys.

## Repo analogues

- Stage-1: partitioned `cross_group_edges` slices (local boundary) vs old broadcast references.
- Stage-4: fourteen writers each receiving the **merged** shared pool ≈ global view of summaries (upper_bound cost).
- Coverage joins keyed by `rule_id` / path — cross-cutting relative to DFS groups.

## Review checks

- Fail if a design reintroduces full-bucket broadcast to every Stage-1 dispatch without a deviation.
- Fail if a cross-partition query cost is treated as free because “we already partitioned.”
- Fail if Stage-4’s merged pool is ignored when arguing that partitioned Stage-1 fixed capacity.

## Refactor signals

- New artifact that must be attached in full to every group.
- Query plans that scan all groups for a secondary attribute with no budget.

## Anti-patterns seen

- capacity_preflight measuring removed broadcast long after Stage 0 switched to partitioned edges (~21× overstatement).

## See also

- `partition-key-and-hotspots`, `rel-partition-bounds-fanout`, `materialized-views-and-caches`
