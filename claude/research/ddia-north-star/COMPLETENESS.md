# Completeness matrix (v1)

**Last refined:** 2026-07-30.

Honest inventory of what was extracted into this catalog vs what remains outline-only. Gaps are backlog — enrich **in place** (same `id`s), do not spawn parallel trees.

## Extraction depth (session → catalog)

| Depth | Coverage | Catalog treatment |
|-------|----------|-------------------|
| Structural SoR of epub | Package, NCX 477 points, sect1/2/3, H5/H6 leaf kinds | [taxonomy.md](taxonomy.md) `operational` |
| Deep paraphrases | Ch1 SoR/derived; Ch2 materialize + NFRs; Ch5 evolution; Ch11 batch/serve; Ch12 streams/views; Ch13 philosophy/audit | Chapter atlas `operational` + linked concepts `operational` |
| Medium | Ch3–4 models/storage; Ch6 replication/LWW; Ch8/10 lite | Chapter `partial`; lite concepts `partial` or `operational` where enough |
| Outline | Ch7 sharding; Ch9 distributed troubles; Ch14 ethics | Chapter `outline` — not decision authority |

## Chapter × concept (link presence)

Legend: `O` = chapter marked operational and claims written; `P` = partial; `.` = outline / thin; `x` = concept linked from chapter.

| Ch | completeness | sor | mat-view | schema | batch/stream | trust | LWW | encode | maint | consen | txn |
|----|--------------|-----|----------|--------|--------------|-------|-----|--------|-------|--------|-----|
| 01 | O | x | | | x | | | | x | | |
| 02 | O | | x | | | | | | x | | |
| 03 | P | x | x | | | | | x | | | |
| 04 | P | | x | | x | | | | | | |
| 05 | O | | | x | | | | x | | | |
| 06 | P | | | | | | x | | | x | |
| 07 | . | | | | | | | | x | x | |
| 08 | P | | | | | | | | | x | x |
| 09 | . | | | | | x | | | x | | |
| 10 | P | | | | | x | | | | x | |
| 11 | O | x | x | | x | | | | | | |
| 12 | O | x | x | | x | | | | | | |
| 13 | O | x | | | x | x | | | | | |
| 14 | . | | | | | x | | | x | | |

## Concept / playbook completeness

| id | kind | completeness | Notes |
|----|------|--------------|-------|
| taxonomy | taxonomy | operational | Measured package/section/leaf model |
| ch01–ch14 | chapter | see matrix | |
| sor-vs-derived | concept | operational | Core for coverage + cert |
| materialized-views-and-caches | concept | operational | Multi-gate / multi-view |
| schema-evolution-and-data-outlives-code | concept | operational | Baselines, STATUS lag |
| batch-vs-stream-derived-state | concept | operational | Batch vs continuous derive |
| trust-but-verify-and-auditability | concept | operational | Vacuous gates, end-to-end |
| replication-lag-and-lww | concept | operational | Anti-LWW (B2.5 prior art) |
| encoding-and-compatibility | concept | operational | Schema compat |
| maintainability-operability-evolvability | concept | operational | NFR triad |
| consistency-and-consensus-lite | concept | partial | Enough for “when derive is not enough” |
| transactions-and-integrity-lite | concept | partial | Lost update / write skew language |
| coverage-gates | playbook | operational | L1 pos/neg/recall |
| claims-and-status-drift | playbook | operational | Docs vs runtime |
| choosing-sor-vs-view | playbook | operational | |
| architecture-decision-review | playbook | operational | |
| refactor-sequencing | playbook | operational | |

## Explicit backlog (do not pretend done)

1. Deep digests for Ch7, Ch9, Ch14 subsections → raise from `outline`.
2. Expand `consistency-and-consensus-lite` / `transactions-and-integrity-lite` to `operational` when a PR needs them as sole authority.
3. Optional: script to regenerate INDEX from `catalog.json` (v1 INDEX is hand-maintained; sync test guards drift).
4. Optional: `scripts/ci/check_ddia_north_star.py` beyond the pytest sync test.
