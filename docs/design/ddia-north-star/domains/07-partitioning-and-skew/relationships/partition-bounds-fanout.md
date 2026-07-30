---
id: rel-partition-bounds-fanout
kind: relationship
completeness: operational
tags: [relationship, partition, fanout, capacity]
related: [partition-key-and-hotspots, secondary-indexes-cross-partition, claims-and-status-drift, ch07]
last_refined: 2026-07-30
path: domains/07-partitioning-and-skew/relationships/partition-bounds-fanout.md

---

# Relationship: Partition bounds fan-out

## In one sentence

Group/partition count drives Stage-1/2 fan-out; Stage-4 fan-out is bounded by the taxonomy (`VALID_DOC_FILES`) while each writer still pays for the **merged** shared evidence pool — measure both, label Stage-0 tokens as `partial_proxy_pre_stage4` and post-artifact sizes as `measured_stage4_inputs`, and do not estimate return payloads as zero.

## Who

- **Writer (SoR):** pipeline dispatch graph + `partition_repo` / edges / `VALID_DOC_FILES`; after Stage 1/3, on-disk `summaries.json` / `interview_answers.json` / `spring_signals.json`.
- **Readers:** `capacity_preflight_report.json` / L2b calibration report, operators deciding whether to run Stages 1–4.
- **Accountable on conflict:** SoR (pipeline + on-disk artifacts) wins; the report is a derived view.

## What

Edge: `Partition → Fan-out cost`. Stage-1 cost scales with cut size (max slice matters). Stage-4 dispatch count is fixed by taxonomy; Stage-4 **input** cost scales with merged pool × writers.

## When

Before a full five-stage run; after summaries/interview exist (L2b calibration); when reviewing adoption L2 / L2b. Raising warn thresholds only after a documented mid-size measured run.

## Where

`src/doc_engine/tools/capacity_preflight.py`, `partition_repo.py`, Stage 0 edges, Stage 4 doc-writers.

## Why

Measuring only Stage-1 after partitioned edges under-states Stage-4. Raising `--fanout-warn-threshold` alone is a band-aid. Inventing Stage-0 interview sizes or claiming the default 80k threshold is calibrated without a mid-size run is also a band-aid.

## How

1. Derive Stage-4 count from `VALID_DOC_FILES` (not a magic 14).
2. At Stage 0, report `stage4_metric_kind: partial_proxy_pre_stage4` with
   `stage4_omitted_not_estimated` (interview / architecture beyond proxy / returns)
   and `stage4_return_payloads_estimated: false`. Numeric `*_upper_bound_*` fields
   are warn-threshold numbers only — not a claim that Stage-4 capacity risk is closed.
3. After artifacts exist (L2b), measure with `--summaries-file` →
   `metric_kind: measured_stage4_inputs`; optional proxy comparison is derived.
   Returns stay omitted. Do not change the default `--stage4-shared-tokens-warn-threshold`
   without documenting a mid-size run.
4. Warn on shared-pool (proxy or measured) separately from Stage-1 slice max.
5. Cite this relationship / domain 07 in the PR.

## Anti-band-aids

- Fail if fan-out or group-count thresholds are raised to silence Stage-4 load without measuring the shared-pool (proxy at Stage 0; on-disk inputs after Stage 1).
- Fail if return payloads are treated as estimated when the report says they are not.
- Fail if Stage-0 invents interview token sizes, or if the default 80k warn threshold is changed without a documented mid-size calibration.

## Repo path witness

- [Repo] `src/doc_engine/tools/capacity_preflight.py`

## See also

`partition-key-and-hotspots`, `claims-and-status-drift`, adoption queue L2 / L2b
