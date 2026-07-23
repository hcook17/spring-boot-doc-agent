---
category: Pluggability
status: not started
---

# Research + scaffold prompt: formal contracts between pipeline stages

Read `claude/steering-prompts/00-shared-research-standards.md` in this repo first for the research bar and methodology every finding here must meet.

## The gap

The five-stage pipeline passes four JSON artifacts between stages — `spring_signals.json`, `groups.json`, `summaries.json`, `interview_answers.json` — and every one is an implicit contract: no schema, no validation, just shared understanding documented in prose across `SKILL.md` and the agent files. Separately, `references/` currently sits as a plugin-root-level sibling of `skills/`, diverging from Anthropic's own convention and this plugin's own example precedent (`anthropics/claude-code`'s `plugins/plugin-dev`).

## Research

Search GitHub for how Anthropic's own reference plugins/skills structure the boundary between instructions, reference material, and subagents — `anthropics/claude-code`'s `plugins/plugin-dev`, and `anthropics/skills`' `skill-creator`. Check both for DeepWiki indexing first.

Search arXiv/GitHub for lightweight schema-validation approaches suited to a *local, no-new-dependency* Python pipeline — JSON Schema (`jsonschema` package) vs. Pydantic, weighed against this pipeline's existing stdlib-only preference.

## What to scaffold and implement

1. One schema file per artifact, describing the shape each already has today — formalize, don't redesign.
2. A validation call at each stage boundary in `SKILL.md`'s instructions.
3. Move `references/` under `skills/document-spring-repo/references/` to match the confirmed convention, updating every file that references the old path.
4. Document the contract explicitly in `SKILL.md` (a short "Data contracts between stages" section linking to the schema files).
