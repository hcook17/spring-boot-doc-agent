---
category: Constraints (make them legible in one place)
status: premise partially stale (2026-07-23) — drift detection already exists, verified directly against the repo
verify:
  - path_exists:CONSTRAINTS.md
  - path_exists:src/doc_engine/tools/spring_drift_check.py
---

# Research + scaffold prompt: a single constraints/limitations file for the plugin itself

Self-contained — read this without assuming any other conversation's context. First read `claude/steering-prompts/00-shared-research-standards.md` in this project for the research bar and methodology every finding here must meet.

## Update (2026-07-23): the "no drift detection" constraint below is wrong as stated

A Cowork session staged `scripts/spring_drift_check.py` directly from the device and read it: it's a real, already-built two-tier drift detector (cheap whole-repo file-signature hashing, then precise per-citation re-verification via targeted `ast-grep` re-runs only against files that changed). Its own docstring says plainly: "Standalone tool... not wired into the document-spring-repo pipeline, not triggered by CI." So the accurate constraint isn't "no drift detection exists" — it's "drift detection exists as a standalone script but isn't integrated into the pipeline or CI, and isn't mentioned in README.md at all." That's a meaningfully different, smaller gap than this prompt originally assumed. Don't research or design drift detection from scratch — that work is largely done; see `04-analytics-logging-research-prompt.md`'s matching update.

## The gap

The plugin's own real constraints are scattered rather than living in one place a new contributor reads first: `ast-grep` must be on `PATH` at runtime, a confidentiality rule that currently lives only in prose handoff notes rather than a standing rule in the repo itself, the precision tradeoff of source-text analysis over compiled bytecode/ArchUnit, and — now — the fact that a real drift-detection tool exists but is neither wired in nor documented. `README.md` (verified directly, current as of 2026-07-23) already documents the `ast-grep` dependency, the bytecode/ArchUnit tradeoff, and the SQLLineage soft dependency reasonably well — the actual gap is narrower than this prompt originally assumed: it's the confidentiality rule and the undocumented drift-check tool that are missing from any single "here's what this plugin doesn't do or needs" reference, not a wholesale absence of constraint documentation.

## Research

Go back to the comparators already identified in this project's benchmark research (aider, repomix, gitingest, DeepWiki, Sourcegraph, Swimm) specifically for how each documents its own **known limitations, scope boundaries, and runtime prerequisites**. Apply the DeepWiki check to each.

Also search for how other Claude Code plugins document runtime prerequisites and optional/soft dependencies (this plugin already has a good example worth matching elsewhere: `README.md`'s framing of SQLLineage as a "soft dependency" that degrades gracefully rather than failing the scan) — match an emerging convention if one exists.

## What to scaffold and implement

A single `CONSTRAINTS.md` at the plugin root, structured like `skills/document-spring-repo/references/doc-taxonomy.md` structures per-file content (this plugin's `references/` convention lives per-skill, not at the repo root) — one entry per constraint, tagged by kind:

- **Runtime prerequisite** — `ast-grep` on `PATH`; SQLLineage as a soft dependency (already well-documented in README, just needs cross-linking here).
- **Integration gap, not a scope cut** — `spring_drift_check.py` exists and works standalone but isn't wired into `SKILL.md`'s pipeline or triggered by CI. State it accurately as "built, not yet integrated" rather than "doesn't exist" — that's a smaller, more honest, and more actionable gap.
- **Known precision tradeoff** — ast-grep/text-based extraction vs. ArchUnit/compiled-bytecode analysis (already documented in README; cross-link).
- **Confidentiality/handling rule** — promote the real-repo-name/content rule from a one-time handoff instruction to a standing rule here; this one's genuinely still missing anywhere in the repo.

Cross-link this file from `README.md` and `SKILL.md`.
