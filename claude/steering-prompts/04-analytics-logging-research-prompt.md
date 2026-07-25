---
category: Analytics & logging (run-level telemetry)
status: [Resolved — 2026-07-24/2026-07-25] premise largely stale as of 2026-07-23 (drift detection already built); item 1 (wiring `spring_drift_check.py` into `SKILL.md`/`README.md`) and item 2 (the still-open run-manifest half) are now both done — `scripts/run_manifest.py` exists, is CI-tested (31/31), and `spring_drift_check.py` gained an optional `--manifest run_manifest.json` baseline flag on 2026-07-25. See `CONSTRAINTS.md` "Integration gaps" item 3 and `claude/session-log.md` entries for 2026-07-24/2026-07-25.
verify:
  - path_exists:scripts/run_manifest.py
  - contains:scripts/spring_drift_check.py:--manifest
---

# Research + scaffold prompt: a run manifest for every pipeline invocation

Self-contained — read this without assuming any other conversation's context. First read `claude/steering-prompts/00-shared-research-standards.md` in this project for the research bar and methodology every finding here must meet.

## Update (2026-07-23): re-scope this — drift detection is built, integration is what's missing

This prompt originally framed drift detection as a research-and-build problem, treating a hypothetical `run_manifest.json` as "the cheapest first step toward" it. That's now backwards: a Cowork session staged and read `scripts/spring_drift_check.py` directly — it's a real, working two-tier drift detector already (Tier 1: whole-repo file-signature hashing against a prior scan's `file_signatures` map; Tier 2: for files that changed, targeted per-citation re-verification via `ast-grep`, re-deriving the same identity `spring_signal_scan.py` itself extracts per rule type, rather than naively comparing raw matched text). It explicitly is not wired into the pipeline and not triggered by CI, per its own docstring, and isn't mentioned in `README.md`.

**Re-scope the "what to scaffold" section below**: don't design drift detection from scratch. Instead, (1) wire `spring_drift_check.py` into the actual workflow — likely as an optional pipeline stage or a standalone `check-drift` command documented in `SKILL.md`/`README.md`, run against a prior `spring_signals.json` before deciding whether to re-run the full pipeline — and (2) the run-manifest idea below is still worth building, but reframed as the thing that *feeds* `spring_drift_check.py` (storing the repo commit hash and `file_signatures` state per run) rather than as a parallel, redundant drift mechanism. Read `spring_drift_check.py` and its test suite (`scripts/test_spring_drift_check.py`) in full before doing anything else in this category — don't re-derive its design from this prompt's original (now-outdated) framing below.

## The gap (as originally framed — now partially superseded, kept for context)

No pipeline run today produces any structured record of what happened — only the fourteen final markdown files. There's no way to answer, without reading all fourteen end to end: how many claims landed `Unknown` vs. `Evidenced` vs. `Confirmed`, how many interview questions were asked vs. answered vs. skipped, how long each stage took, or whether a subagent errored partway through. This part of the gap is still real and still open — `spring_drift_check.py` addresses code-evidence drift specifically, not run-level telemetry about the doc-generation stages themselves.

## Research

Search arXiv for documentation-drift detection and doc-to-code traceability mechanisms — largely superseded now that a real implementation exists to study directly instead; only worth doing if `spring_drift_check.py`'s own approach (content hashing + targeted structural re-verification) turns out to diverge from established practice in a way worth reconsidering.

Search GitHub, applying the star/push/DeepWiki methodology, for lightweight, dependency-free run-manifest/provenance-log patterns (MLflow, W&B) purely for schema inspiration for the still-open run-telemetry half of this prompt.

## What to scaffold and implement

1. **Wire in what already exists**: add a `SKILL.md`-documented way to run `spring_drift_check.py` against a prior `spring_signals.json` before a full re-run, and document it in `README.md` (it currently isn't mentioned there at all).
2. **The still-open half**: a `run_manifest.json`, written once per pipeline invocation, capturing timestamp, target repo path and commit hash, `file_signatures` (feeding `spring_drift_check.py` as its "prior scan" input directly, rather than requiring a separate `spring_signals.json` copy), per-stage timing and pass/fail state, evidence-tag counts per generated file, and the interview's answered/skipped breakdown. Keep its schema next to whatever `02-pluggability-research-prompt.md` produces.
3. Surface a short human-readable summary at the end of a run, and mention `spring_drift_check.py` as the recommended pre-flight check before a costly full re-run, not just after the fact.
