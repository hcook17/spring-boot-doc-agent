---
id: rel-sor-feeds-views
kind: relationship
completeness: operational
tags: [relationship, sor, derived]
related: [sor-vs-derived, materialized-views-and-caches, choosing-sor-vs-view, dev-certification-derived-view]
last_refined: 2026-07-30
path: domains/01-data-flow-and-truth/relationships/sor-feeds-views.md

---

# Relationship: SoR feeds views

## In one sentence

One writer (SoR) produces facts; zero or more derived views recompute or materialize for readers — views never become a second writer.

## Who

- **Writer:** the SoR owner (ruleset, facts.jsonl, gate inputs, schema SoR).
- **Readers:** humans, CI comments, STATUS, certification, coverage baselines, dashboards.
- **Accountable on conflict:** SoR owner; view maintainers recompute.

## What

Edge: `SoR --derives--> View`. Not: `View --overrides--> SoR`.

## When

Design time (choose homes), CI (regenerate views), incidents (do not LWW-merge).

## Where

Pipeline facts → certification; CodeQL ids + spring_signals → coverage results; code → STATUS/CONSTRAINTS prose (derived claims).

## Why

Dual writers create silent drift; LWW hides which fact was true (`replication-lag-and-lww`).

## How

1. Name the SoR path.
2. Name the view path and regenerator.
3. On disagreement: fix SoR or regenerator — never hand-merge the view without a [deviation](../../deviations/).

## Anti-band-aids

- Fail if a dual writer, silent LWW, or vacuous gate ships without a deviation or SoR fix.

## Repo path witness

- [Repo] `domains/01-data-flow-and-truth/relationships/sor-feeds-views.md`

## See also

`choosing-sor-vs-view`, `dev-certification-derived-view`
