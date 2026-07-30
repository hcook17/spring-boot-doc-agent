---
id: rel-batch-feeds-serving
kind: relationship
completeness: operational
tags: [relationship, batch, serving, derived]
related: [batch-vs-stream-derived-state, materialized-views-and-caches, rel-sor-feeds-views, ch11]
last_refined: 2026-07-30
path: domains/09-derived-data-processing/relationships/batch-feeds-serving.md

---

# Relationship: Batch feeds serving

## In one sentence

Batch (or stream) jobs derive views from an immutable SoR snapshot; serving loads those views — the job must not become a live SoR writer.

## Who

- **Writer (SoR):** operational facts / rules / fixtures / facts.jsonl owner.
- **Deriver:** batch/stream job regenerating catalogs, coverage results, certification, docs.
- **Serving readers:** CI, humans, dashboards consuming the loaded view.

## What

Edge: `SoR --batch/stream--> Staging --load--> Serving view`. Forbidden: `Batch --live-write--> SoR`.

## When

Rebuilding large derived artifacts; choosing stage+load vs incremental update; reviewing dual-writer risk.

## Where

`_build_catalog.py`, coverage/report scripts, certification derived view, future incremental pipelines.

## Why

Live row writes from bulk jobs create dual writers and unauditable history (`dev-certification-derived-view`).

## How

1. Name immutable inputs (commit, fixture corpus, ruleset version).
2. Write to staging / replace-on-success artifact.
3. Point readers at the new view; delete old if rebuild-safe.
4. On conflict with SoR: fix SoR or regenerator — cite `rel-sor-feeds-views`.

## Anti-band-aids

- Fail if a batch or stream job writes the SoR live without stage+load or a filed deviation.
- Fail if freshness needs are unspecified yet stream is treated as required.

## Repo path witness

- [Repo] `docs/design/ddia-north-star/_build_catalog.py`

## See also

`batch-vs-stream-derived-state`, `materialized-views-and-caches`, `ch11`
