---
id: domain-transactions-and-concurrency
kind: domain
completeness: partial
tags: [domain, transactions, concurrency, isolation]
related: [transactions-and-integrity-lite, trust-but-verify-and-auditability, domain-integrity-and-verification, ch08]
last_refined: 2026-07-30
---

# Domain 08 — Transactions and concurrency

**Job.** Own concurrent writers, isolation language, and lost-update risk. Domain `04` owns witnesses/gates; this domain owns the concurrency vocabulary when two writers touch the same fact.

## Owns

- ACID/isolation meaning for product controls.
- Concurrent RMW / lost-update language (`transactions-and-integrity-lite`).
- When serializability is required vs when recompute-from-SoR suffices.

## Defers

- Vacuous-gate / witness design → domain `04` (`rel-gate-needs-witness`).
- LWW as conflict policy → domain `03`.
- Consensus → domain `06` (usually deferred).

## Concepts

| id | Page |
|----|------|
| `transactions-and-integrity-lite` | [../04-integrity-and-verification/concepts/transactions-and-integrity-lite.md](../04-integrity-and-verification/concepts/transactions-and-integrity-lite.md) (`partial` — shared pointer; deepen when concurrent writers land) |

## Relationships

None yet — prefer `rel-conflict-vs-recompute` (domain 03) and `rel-gate-needs-witness` (domain 04) until a concurrency-specific edge appears.

## Chapters

`ch08`

## Completeness

Marked `partial` until this domain owns a local `concepts/` page.

## Anti-band-aids

- Fail if 'transactional' is claimed without stating isolation level.
- Fail if concurrent baseline/claim writers ship without naming lost-update risk.

## Repo path witness

- [Repo] `domains/08-transactions-and-concurrency/README.md`
