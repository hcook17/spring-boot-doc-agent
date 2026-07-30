---
id: sor-vs-derived
kind: concept
completeness: operational
tags: [sor, derived, redundancy, cache, index]
epub_anchors:
  - { chapter: 1, fragment: sec_introduction_derived, title: "Systems of Record and Derived Data" }
related: [materialized-views-and-caches, trust-but-verify-and-auditability, choosing-sor-vs-view]
last_refined: 2026-07-30
---

# System of record vs derived data

## In one sentence

The system of record holds each fact once as the canonical source; derived data is recomputable from that source (caches, indexes, materialized views, trained models).

## When to open

- Is this file/artifact authoritative, or a recomputable view?
- Docs say X but code reads Y — which is SoR?
- Should we merge two writers or re-derive from facts?

## Core claims

- SoR (source of truth): new input is written here first; representation is typically normalized; on discrepancy, SoR wins by definition.
- Derived: transformed/processed from another system; if lost, it can be rebuilt from the source.
- Derived data is redundant but often essential for read performance; one SoR can feed many views.
- Analytical systems are usually derived; operational services often mix SoR and derived.

## Tradeoffs

- Treating a derived view as SoR → silent drift and dual writers.
- Refusing all derived data → unusable read latency / scan cost.
- LWW-merging two SoR candidates → lossy (see `replication-lag-and-lww`).

## Repo analogues

- SoR: rule YAML / CodeQL `rule_id`s, fixture corpora, stage/gate facts, `facts.jsonl`.
- Derived: `certification.json` (B2.5), STATUS/CONSTRAINTS prose, CI comments, coverage baselines, `<!-- derived: -->` counts.

## Review checks

1. Does the diff name a single writer for each fact?
2. If two artifacts can disagree, is it clear which wins?
3. Can the “view” be deleted and rebuilt from stated inputs?

## Refactor signals

- Dual homes for the same claim (docs path ≠ gate path).
- Hand-edited counts that should be derivations.

## Anti-patterns seen

- `rule_coverage` docs claimed `rule_fixtures/` while runtime reads `scripts/fixtures/spring_signals/` + CodeQL ids.
- STATUS “Next engineering” lagging after B1–B5 landed on the queue.

## See also

- `choosing-sor-vs-view`, `materialized-views-and-caches`, `claude/research/certification-derived-view-2026-07-30.md`
