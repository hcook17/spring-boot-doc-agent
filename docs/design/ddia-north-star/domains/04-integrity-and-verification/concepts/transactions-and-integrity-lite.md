---
id: transactions-and-integrity-lite
kind: concept
completeness: partial
tags: [transactions, isolation, lost-update, write-skew]
epub_anchors:
  - { chapter: 8, title: "Preventing Lost Updates" }
  - { chapter: 8, title: "Write Skew and Phantoms" }
related: [consistency-and-consensus-lite, trust-but-verify-and-auditability]
last_refined: 2026-07-30
path: domains/04-integrity-and-verification/concepts/transactions-and-integrity-lite.md

---

# Transactions and integrity (lite)

## In one sentence

Transactions protect multi-object integrity only as far as isolation and application logic allow — lost updates and write skew remain under weak isolation.

## When to open

- Concurrent writers to the same logical entity (maps, baselines, cert stages).
- “We used a transaction so integrity is fine.”
- Review language for lost update / write skew.

## Core claims

- Lost update: two read-modify-writes where one overwrite drops the other.
- Write skew: each transaction upholds a local predicate; together they break a global invariant.
- Atomicity ≠ correct application semantics.
- Marked `partial`: enough vocabulary for reviews; deepen Ch8 for new concurrency control designs.

## Tradeoffs

- Serializable isolation costs throughput.
- Application-level CAS / version fields (`@Version`) as optimistic control.

## Repo analogues

- Semgrep rule `architecture_ddia__entity_no_version_field` (optimistic concurrency smell).
- Baseline updates should be single-writer (`--update` / `--update-fp-baseline`).

## Review checks

1. Can two processes RMW the same artifact?
2. Is there a version/CAS/lock story?
3. Are we mis-calling “atomic file replace” a transaction guarantee?

## Refactor signals

- Read JSON, mutate, write JSON without compare-and-swap across agents.

## Anti-patterns seen

- (thin) Use as review vocabulary; reopen epub for novel isolation designs.

## See also

- `replication-lag-and-lww`, `sor-vs-derived`
