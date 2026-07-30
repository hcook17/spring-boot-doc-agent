---
id: maintainability-operability-evolvability
kind: concept
completeness: operational
tags: [maintainability, operability, evolvability, simplicity]
epub_anchors:
  - { chapter: 2, title: "Operability: Making Life Easy for Operations" }
  - { chapter: 2, title: "Simplicity: Managing Complexity" }
  - { chapter: 2, title: "Evolvability: Making Change Easy" }
related: [refactor-sequencing, architecture-decision-review]
last_refined: 2026-07-30
path: domains/05-maintainability-and-change/concepts/maintainability-operability-evolvability.md

---

# Maintainability: operability, simplicity, evolvability

## In one sentence

Maintainability splits into making operations possible, keeping accidental complexity down, and making change cheap as requirements move.

## When to open

- Is this control operable by humans/agents without folklore?
- Big-bang vs sequenced change.
- Complexity that slows every later edit.

## Core claims

- Operability: good ops can work around incomplete software; good software rarely survives bad ops.
- Simplicity: accidental complexity raises bug and schedule risk (ball of mud).
- Evolvability: requirements churn — design for change at system boundaries, not only local TDD.
- Automation helps but escalates the skill needed for residual edge cases.

## Tradeoffs

- More abstraction ≠ more simplicity.
- One mega-PR vs many reversible slices.
- Docs that are not operable (wrong paths) destroy evolvability of process.

## Repo analogues

- Packaging pause; adoption-blocker sequencing B1–B5 then L1…
- `pre_pr` / CI hard suites as operability.
- North-star load protocol: one page, not whole tree.

## Review checks

1. Can a new agent run the check from README/CI alone?
2. Does the change reduce or increase interlocking assumptions?
3. Is there a rollback/derive path?

## Refactor signals

- Undocumented cwd-dependent behavior.
- Controls that only work on one engineer’s checkout path.

## Anti-patterns seen

- CI comments pointing at deleted fixture paths.

## See also

- `refactor-sequencing`, `claims-and-status-drift`
