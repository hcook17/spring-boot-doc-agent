---
category: Constraints (make them legible in one place)
status: not started
---

# Research + scaffold prompt: a single constraints/limitations file for the plugin itself

Read `claude/steering-prompts/00-shared-research-standards.md` in this repo first for the research bar and methodology every finding here must meet.

## The gap

The plugin's own real constraints are scattered rather than living in one place a new contributor reads first: no drift/re-sync detection (`README.md` states this directly), no ArchUnit/compiled-build verification, `ast-grep` must be on `PATH` at runtime, and a confidentiality rule (never embed a real client's repo name or files into the shipped plugin tree) that currently lives only in prose handoff notes rather than a standing rule in the repo itself.

## Research

Go back to the comparators already identified in this project's benchmark research (aider, repomix, gitingest, DeepWiki, Sourcegraph, Swimm) specifically for how each documents its own **known limitations, scope boundaries, and runtime prerequisites** — dedicated `LIMITATIONS.md`, a README section, issue labels, or nothing formal. Apply the DeepWiki check to each.

Also search for how other Claude Code plugins document runtime prerequisites (a binary needing to be on `PATH`, an API key, a Claude Code version) — match an emerging convention if one exists rather than inventing a new format.

## What to scaffold and implement

A single `CONSTRAINTS.md` at the plugin root, structured like `references/doc-taxonomy.md` structures per-file content — one entry per constraint, tagged by kind:

- **Runtime prerequisite** — `ast-grep` on `PATH`.
- **Deliberate scope cut** — no drift detection; link forward to whatever the analytics/logging prompt produces.
- **Known precision tradeoff** — ast-grep/text-based extraction vs. ArchUnit/compiled-bytecode analysis.
- **Confidentiality/handling rule** — promote the real-repo-name/content rule from a one-time handoff instruction to a standing rule here.

Cross-link this file from `README.md` and `SKILL.md`.
