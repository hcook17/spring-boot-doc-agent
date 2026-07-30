---
id: domain-integrity-and-verification
kind: domain
completeness: operational
tags: [domain, integrity, audit]
related: [transactions-and-integrity-lite, trust-but-verify-and-auditability, rel-gate-needs-witness]
last_refined: 2026-07-30
---

# Domain 04 — Integrity and verification

**Job.** Atomicity / integrity language where we need it; every trust claim needs a witness (fixture, ratchet, audit trail).

## Concepts

| id | Page |
|----|------|
| `transactions-and-integrity-lite` | [concepts/transactions-and-integrity-lite.md](concepts/transactions-and-integrity-lite.md) |
| `trust-but-verify-and-auditability` | [concepts/trust-but-verify-and-auditability.md](concepts/trust-but-verify-and-auditability.md) |

## Relationships

| id | Page |
|----|------|
| `rel-gate-needs-witness` | [relationships/gate-needs-witness.md](relationships/gate-needs-witness.md) |

## Chapters

`ch08`, `ch09` (lite), `ch14` themes

## Deviations

`dev-fp-ratchet-separate-from-recall`

## Anti-band-aids

- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

## Repo path witness

- [Repo] `domains/04-integrity-and-verification/README.md`
