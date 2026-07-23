---
category: Analytics & logging (run-level telemetry)
status: not started
---

# Research + scaffold prompt: a run manifest for every pipeline invocation

Read `claude/steering-prompts/00-shared-research-standards.md` in this repo first for the research bar and methodology every finding here must meet.

## The gap

No pipeline run produces any structured record of what happened — only the fourteen final markdown files. There's no way to answer, without reading all fourteen end to end: how many claims landed `Unknown` vs. `Evidenced` vs. `Confirmed`, how many interview questions were asked vs. answered vs. skipped, how long each stage took, or whether a subagent errored partway through. A run manifest is also the cheapest first step toward real drift detection.

## Research

Search arXiv for documentation-drift detection and doc-to-code traceability mechanisms (content hashing, line-anchor tracking, embedding-similarity thresholds), not just position papers on why drift matters.

Search GitHub, applying the star/push/DeepWiki methodology, for (1) doc-drift/doc-freshness tools beyond Swimm, and (2) lightweight, dependency-free run-manifest/provenance-log patterns from ML pipeline tooling (MLflow, W&B) purely for schema inspiration, filtered to what's implementable as a local JSON file with zero new services.

## What to scaffold and implement

A `run_manifest.json`, written once per pipeline invocation, capturing: timestamp, target repo path and commit hash; per-stage timing and pass/fail state; evidence-tag counts per generated file (computed by grepping the actual docs for the five required tags); `gap-analyzer`'s question count and the interview's answered/skipped breakdown; and file-level content signatures if `spring_signal_scan.py` already computes them (check current state — a `compute_file_signature`/`file_signatures` mechanism may already exist specifically for future drift-check tooling to re-walk and re-hash).

Keep the manifest's own schema next to whatever the pluggability prompt (`02`) produces. Surface a short human-readable summary at the end of a run, not just the raw JSON.
