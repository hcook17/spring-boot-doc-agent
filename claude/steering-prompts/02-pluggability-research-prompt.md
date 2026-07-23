---
category: Pluggability
status: partially resolved (2026-07-23) — references/ already moved, verified directly against the repo
---

# Research + scaffold prompt: formal contracts between pipeline stages

Self-contained — read this without assuming any other conversation's context. First read `claude/steering-prompts/00-shared-research-standards.md` in this project for the research bar and methodology every finding here must meet.

## Update (2026-07-23): the references/ item below is done — verified directly, not assumed

A Cowork session staged the actual repo file tree from the device and confirmed `references/` now lives at `skills/document-spring-repo/references/doc-taxonomy.md`, not at the plugin root. Whoever did this (likely as part of the six agreed handoff items) already fixed it. **Don't re-do this — it's closed.** The remaining, still-open part of this prompt is the JSON schema/contract work below, which is unaffected by that fix.

Also worth knowing: `summaries.json`'s shape changed since this prompt was first written — it now includes a `cross_group_relationships` field (added alongside the cross-group reference index work), on top of the fields originally documented. Confirm the current shape directly against `skills/document-spring-repo/SKILL.md` and the real `agents/file-summarizer.md` before writing any schema — don't assume the shape described in this prompt's original text below is current; it wasn't, once already (see `claude/pending-delivery/SKILL.md`'s "Sync note (2026-07-23)").

## The gap (schema/contract part — still open)

The five-stage pipeline passes four JSON artifacts between stages — `spring_signals.json`, `groups.json`, `summaries.json`, `interview_answers.json` — and every one is an implicit contract: no schema, no validation, just shared understanding documented in prose across `SKILL.md` and the agent files. `spring_signal_scan.py`'s own docstring says the JSON shape was kept stable specifically so a scanner rewrite (regex → ast-grep) wouldn't require touching the rest of the pipeline. That's the right instinct, but it's enforced by nobody changing the shape, not by anything that would catch it if someone did — and the `cross_group_relationships` field addition above is a live example of exactly that kind of unenforced change happening.

Also worth noting: `spring_signal_scan.py`'s docstring (per `spring_drift_check.py`'s own comments) references a `schema_version` field and `schema_version >= 2` on `spring_signals.json` — meaning some notion of schema versioning may already exist informally. Check this directly before designing a schema from scratch; there may already be a versioning convention worth formalizing rather than inventing a new one.

## Research

Search GitHub for how Anthropic's own reference plugins and skill repos structure the boundary between a skill's instructions, its reference material, and its subagents — `anthropics/claude-code`'s `plugins/plugin-dev`, and `anthropics/skills`' `skill-creator`. Check both for DeepWiki indexing and read the wiki if present before diving into raw source.

Search arXiv and GitHub for lightweight schema-validation approaches suited to a *local, no-new-dependency* Python pipeline — JSON Schema (the `jsonschema` PyPI package) is the obvious default; also check whether Pydantic would be a better fit given this pipeline's existing pure-stdlib approach.

## What to scaffold and implement

1. One schema file per artifact (`spring_signals.schema.json`, `groups.schema.json`, `summaries.schema.json`, `interview_answers.schema.json`), placed alongside the scripts that produce them, describing the exact shape each has **right now** — verify by reading the real files directly, not from this prompt's history. Check for and reuse any existing `schema_version` convention rather than introducing a competing one.
2. A validation call at each stage boundary in `SKILL.md`'s instructions.
3. Document the contract explicitly in `SKILL.md` itself (a short "Data contracts between stages" section linking to the schema files), and note there that `spring_drift_check.py` is a downstream consumer of `spring_signals.json`'s shape too — any schema change needs to consider that consumer, not just the four pipeline stages.
