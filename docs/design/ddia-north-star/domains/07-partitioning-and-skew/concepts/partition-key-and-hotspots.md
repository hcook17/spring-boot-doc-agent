---
id: partition-key-and-hotspots
kind: concept
completeness: operational
tags: [partition, skew, hotspot, key]
epub_anchors:
  - { chapter: 7, title: "Partitioning of Key-Value Data" }
  - { chapter: 7, title: "Partitioning and Replication" }
related: [secondary-indexes-cross-partition, rel-partition-bounds-fanout, maintainability-operability-evolvability, ch07]
last_refined: 2026-07-30
path: domains/07-partitioning-and-skew/concepts/partition-key-and-hotspots.md

---

# Partition key and hotspots

## In one sentence

The partition key decides which shard owns a record; a bad key creates permanent hotspots that no cache band-aid permanently fixes.

## When to open

- Choosing how to split Stage-0 groups / Stage-1 dispatches.
- A single group or key path dominates latency or token cost.
- Temptation to “just raise the fan-out threshold” after one hot partition.

## Core claims

- Partitioning scales by splitting data/work; the key choice dominates skew.
- Hot keys / celebrity keys overload one partition while others idle.
- Rebalancing moves partitions — it is an operational event, not free magic.
- Overlap in group planning (this product) can double-count files in upper_bound estimates — label them as such.

## Tradeoffs

- Fine partitions → more fan-out and cross-partition coordination.
- Coarse partitions → simpler ops, higher hotspot risk.
- Hashing spreads load but hurts range queries and locality.

## Repo analogues

- `partition_repo.build_groups` planning target vs actual group count under skew.
- Stage-1 edge slice **max** (one hot group) vs total (sum) in `capacity_preflight`.
- Stage-4 shared-pool **upper_bound** after merging all group summaries — quiet Stage-1 ≠ quiet Stage-4.

## Review checks

- Fail if a partition key is chosen without naming the hot-key / skew plan.
- Fail if only the Stage-1 slice sum is cited while ignoring the max single dispatch.
- Fail if Stage-4 shared-pool upper_bound is omitted when arguing capacity is fine.

## Refactor signals

- One group’s `est_tokens` or edge slice dwarfs peers.
- Raising `--fanout-warn-threshold` / `--group-warn-threshold` without Stage-4 measurement.

## Anti-patterns seen

- Preflight that measured only Stage-1 after cross-group edges landed, under-stating Stage-4 load (adoption L2).

## See also

- `rel-partition-bounds-fanout`, `secondary-indexes-cross-partition`, `ch07`
