---
category: Testability
status: partially resolved (2026-07-23; semantic layer added 2026-07-23) — tests/doc_engine/test_pipeline_stages.py covers mechanical/structural checks (for the current count run `python3 tests/doc_engine/test_pipeline_stages.py`; this field said "17/17 passing" until 2026-07-25, when the suite was actually at 29 — the hardcoded-count failure CLAUDE.md warns about, corrected here); skills/semantic-pipeline-eval/ now scaffolds the "narrow LLM-as-judge for genuinely qualitative judgments" this prompt originally deferred (see its own "What to scaffold" section below) — but it's a manually-invoked skill, not a CI-integrated check, so this prompt's full original scope (mechanical + judgment, both automated) still isn't entirely closed. See claude/session-log.md and STATUS.md.
verify:
  - path_exists:tests/doc_engine/test_pipeline_stages.py
  - path_exists:skills/semantic-pipeline-eval/SKILL.md
---

# Research + scaffold prompt: testability of the LLM stages

Read `claude/steering-prompts/00-shared-research-standards.md` in this repo first for the research bar and methodology every finding here must meet.

## The gap

This plugin generates 14 docs for brownfield Spring Boot repos across five pipeline stages (`skills/document-spring-repo/SKILL.md`). It has real, checked-in tests for its two deterministic scripts: `tests/doc_engine/test_partition_repo.py`, `tests/doc_engine/test_spring_signal_scan.py`, plus an opt-in `tests/doc_engine/test_partition_repo_real_world.py`. That's solid. Nothing tests the four LLM stages: Stage 1 (`file-summarizer`), Stage 2 (`architect-segment`/`architect-merge`), Stage 3 (`gap-analyzer`), Stage 4 (`doc-writer`, fourteen parallel calls). A prompt regression in any of these five agent files is currently invisible except by a human reading generated output and noticing something's wrong.

## Research

Search arXiv for papers on evaluating LLM/agent pipelines whose output is *structured claims with provenance* — FActScore (arXiv:2305.14251, already verified) is the closest existing precedent. Look for adjacent work on verifying citation/grounding accuracy in LLM-generated documentation, multi-agent pipeline evaluation, and detecting silent format drift in structured LLM output.

Search GitHub, applying the shared standards' star/push/DeepWiki methodology, for eval harnesses: `promptfoo`, `deepeval`, `openai/evals`, UK AISI's `inspect_ai`, `ragas`, and anything purpose-built for **structural/mechanical assertions on LLM output** (schema conformance, citation resolvability) rather than LLM-as-judge scoring — mechanical checks are cheaper and a better fit for this project's citation-tagging discipline.

## What to scaffold and implement

A fixture-based pipeline test, mechanical wherever possible:

1. A small synthetic Spring Boot repo fixture (mirroring `scripts/fixtures/spring_signals/`) sized to exercise all five agent stages.
2. Structural assertions, none requiring an LLM to grade: every substantive claim ends in one of the five required tags from `doc-writer.md`'s Rule 1; every `[Evidenced — path:line]` tag cites a real file/line; `Unknown` count doesn't silently balloon past a sane threshold; `gap-analyzer`'s question count is bounded and grouped by file; the merged architecture diagram's node names trace back to `summaries.json` entries.
3. Only fall back to LLM-as-judge for genuinely qualitative judgments, with as narrow a rubric as possible.

Deliver as `tests/doc_engine/test_pipeline_stages.py`, following the existing suites' skip-if-fixture-absent pattern, and update `SKILL.md`/`README.md` to mention how to run it.
