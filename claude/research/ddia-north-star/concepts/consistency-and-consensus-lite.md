---
id: consistency-and-consensus-lite
kind: concept
completeness: partial
tags: [consistency, consensus, linearizability, coordination]
epub_anchors:
  - { chapter: 10, title: "Linearizability" }
  - { chapter: 10, title: "Consensus" }
related: [replication-lag-and-lww, transactions-and-integrity-lite, sor-vs-derived]
last_refined: 2026-07-30
---

# Consistency and consensus (lite)

## In one sentence

Strong consistency and consensus are coordination tools for uniqueness and agreement — use them when asynchronous derivation cannot uphold the constraint.

## When to open

- “Do we need a lock / single leader / compare-and-set?”
- Uniqueness constraints across writers.
- When derive-async would allow divergent certified states.

## Core claims

- Linearizability is intuitive and expensive; not every read needs it.
- Consensus shows up as leader election, CAS, shared logs, atomic commit.
- Coordination-avoiding designs prefer derived views + idempotence when integrity allows.
- Partial completeness here: deepen before sole authority on exotic consensus variants.

## Tradeoffs

- Over-coordinating → latency and outage coupling.
- Under-coordinating → divergent “truth” across nodes/views.

## Repo analogues

- Certification fold rules (stage fail always fails) instead of per-agent consensus protocol.
- Single writer for denylist / baseline update flags.

## Review checks

1. What invariant requires agreement among writers?
2. Is async derive + verify enough?
3. If completeness is `partial`, did the review reopen Tier A for the disputed point?

## Refactor signals

- Introducing distributed locks for a problem that is a missing SoR.

## Anti-patterns seen

- (thin) Prefer citing this page as orientation; escalate to epub Ch10 when designing new distributed coordination.

## See also

- `trust-but-verify-and-auditability`, `replication-lag-and-lww`
