---
category: Pluggability
status: resolved (2026-07-28) — references/ move (2026-07-23) and inter-stage JSON schema/contract work
verify:
  - path_exists:skills/document-spring-repo/references/doc-taxonomy.md
  - path_absent:references
  - path_exists:src/doc_engine/tools/validate_artifacts.py
  - path_exists:src/doc_engine/tools/pipeline_validators.py
  - path_exists:scripts/schemas/spring_signals.schema.json
  - path_exists:src/doc_engine/pipeline/runner.py
  - contains:skills/document-spring-repo/SKILL.md:validate_artifacts.py
note: Anthropic plugin-structure and jsonschema-vs-Pydantic research items below were not written as separate docs; Pydantic models in src/doc_engine/pipeline/artifacts.py were chosen because pydantic is already in pyproject.toml (no new dependency). JSON Schema files in scripts/schemas/ are derived from those models.
---

# Research + scaffold prompt: formal contracts between pipeline stages

Self-contained — read this without assuming any other conversation's context. First read `claude/steering-prompts/00-shared-research-standards.md` in this project for the research bar and methodology every finding here must meet.

## Update (2026-07-23): the references/ item below is done — verified directly, not assumed

A Cowork session staged the actual repo file tree from the device and confirmed `references/` now lives at `skills/document-spring-repo/references/doc-taxonomy.md`, not at the plugin root. Whoever did this (likely as part of the six agreed handoff items) already fixed it. **Don't re-do this — it's closed.**

## Update (2026-07-28): schema/contract work is done

The four inter-stage JSON artifacts now have Pydantic boundary models (`src/doc_engine/pipeline/artifacts.py`), JSON Schema exports in `scripts/schemas/`, validation CLI (`scripts/validate_artifacts.py`), shipped mechanical validators (`scripts/pipeline_validators.py`), and a documented "Data contracts between stages" section in `skills/document-spring-repo/SKILL.md` with `validate_artifacts.py` calls at boundaries. Orchestration code lives in `src/doc_engine/pipeline/` (`PipelineRunner`, `StageExecutor` port, `MockStageExecutor` for local runs). Residual gap: CI does not validate artifacts from a full live pipeline run (no target-repo run in CI); fixture + unit tests cover contract shape instead.

`summaries.json` includes `cross_group_relationships` in the schema (confirmed against `agents/file-summarizer.md`). `spring_signals.json` reuses the existing `schema_version >= 2` convention.

## The gap (schema/contract part — resolved 2026-07-28)

Previously: the five-stage pipeline passed four JSON artifacts with no enforced schema. That gap is closed by the deliverables above. Keep this section as history — do not re-scaffold from scratch without reading what already ships.

## Research (optional follow-up, not blocking)

Search GitHub for how Anthropic's own reference plugins and skill repos structure the boundary between a skill's instructions, its reference material, and its subagents — `anthropics/claude-code`'s `plugins/plugin-dev`, and `anthropics/skills`' `skill-creator`. Check both for DeepWiki indexing and read the wiki if present before diving into raw source.

Search arXiv and GitHub for lightweight schema-validation approaches suited to a *local, no-new-dependency* Python pipeline — JSON Schema (the `jsonschema` PyPI package) is the obvious default; also check whether Pydantic would be a better fit given this pipeline's existing pure-stdlib approach. **Outcome in-repo:** Pydantic chosen (already a dependency).

## What to scaffold and implement (done — do not redo)

1. One schema file per artifact — `scripts/schemas/*.schema.json`, shapes match current producers/consumers.
2. A validation call at each stage boundary in `SKILL.md`'s instructions.
3. Document the contract explicitly in `SKILL.md` (Data contracts section), including `spring_drift_check.py` as a downstream consumer of `spring_signals.json`'s shape.
