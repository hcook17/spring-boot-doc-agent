---
id: domain-reliability-scalability-goals
kind: domain
completeness: partial
tags: [domain, reliability, scalability, maintainability, goals]
related: [maintainability-operability-evolvability, refactor-sequencing, domain-maintainability-and-change, ch13, ch14]
last_refined: 2026-07-30
---

# Domain 10 — Reliability, scalability, goals

**Job.** Own the three goal pillars (reliability, scalability, maintainability) as *what we optimize for*. Domain `05` owns day-to-day operability *how-to* and claim/status drift under change.

## Owns

- Goal definitions and tradeoffs among reliability / scalability / maintainability.
- Load-parameter honesty (upper_bounds, fan-out, partial failure).
- Integration / unbundling correctness themes from ch13 when framed as goals.

## Defers

- Operability playbooks and STATUS drift → domain `05`.
- Partition skew mechanics → domain `07`.
- Batch/stream mechanics → domain `09`.

## Concepts

Point to `maintainability-operability-evolvability` (domain 05) until a goals-specific concept is needed.

## Relationships

Use `refactor-sequencing` and `claims-and-status-drift` playbooks.

## Chapters

`ch13`, `ch14`; `ch09` surveyed here for partial-failure context.

## Completeness

Marked `partial` until this domain owns a local `concepts/` page.

## Anti-band-aids

- Fail if scale is 'fixed' only by raising warn thresholds without measurement.
- Fail if a temporary dual writer is left without expiry / revisit.

## Repo path witness

- [Repo] `domains/10-reliability-scalability-goals/README.md`
- [Repo] `src/doc_engine/tools/capacity_preflight.py`
