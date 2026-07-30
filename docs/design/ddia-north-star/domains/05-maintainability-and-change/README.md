---
id: domain-maintainability-and-change
kind: domain
completeness: operational
tags: [domain, maintainability, evolvability]
related: [maintainability-operability-evolvability, refactor-sequencing, claims-and-status-drift]
last_refined: 2026-07-30
---

# Domain 05 — Maintainability and change

**Job.** Operability, accidental complexity, and how claims/status stay honest under change.

## Concepts

| id | Page |
|----|------|
| `maintainability-operability-evolvability` | [concepts/maintainability-operability-evolvability.md](concepts/maintainability-operability-evolvability.md) |

## Relationships

Use playbooks: `refactor-sequencing`, `claims-and-status-drift`, `architecture-decision-review`.

## Chapters

`ch01` (maintainability axes), `ch13`–`ch14`

## Anti-band-aids

- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

## Repo path witness

- [Repo] `domains/05-maintainability-and-change/README.md`
