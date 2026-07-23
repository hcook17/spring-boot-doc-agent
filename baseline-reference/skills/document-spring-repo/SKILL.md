---
name: document-spring-repo
description: Scan a Spring Boot repository, ask the user clarifying questions about what static analysis can't determine (write ownership, external consumers, known limitations, intent behind unsecured endpoints), then generate a fixed set of fourteen markdown docs — readme, architecture, integrations, authorization, database, operations, observability, troubleshooting, configuration, change_impact, glossary, local_development, testing, known_limitations. Use whenever the user asks to document a Spring Boot repo, generate onboarding docs for a Java service, map out a legacy Spring codebase, or produce architecture/database/security documentation for a Spring Boot project. This is heavier than the generic document-repo pipeline — use this one specifically for Spring Boot/Spring Data/Spring Security codebases where the fourteen-file taxonomy applies.
---

# Document Spring Repo

Five stages. Two run in parallel across subagents (fast, code-only evidence gathering); one runs as a live conversation with the user (the interview — subagents can't do this, only the orchestrating thread can); the last runs in parallel again (fourteen independent doc-writing tasks).

Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` before Stage 4 — it defines what goes in each of the fourteen files, which evidence maps to which file, and — this is the part that actually matters — where the line is between "safe to infer from code" and "needs a clarifying question." Getting that boundary wrong is the main way this pipeline produces confident-sounding fiction instead of documentation.

**All five agent files — `file-summarizer.md`, `doc-writer.md`, `gap-analyzer.md`, `architect-segment.md`, and `architect-merge.md` — are registered Claude Code subagents**, each with proper YAML frontmatter (`name`, `description`, `tools`), dispatched by name via the Task tool. This wasn't always true of the last two: earlier drafts of `architect-segment.md`/`architect-merge.md` carried their source paper's (ArchAgent, arXiv:2601.13007) own literal Position/Objective/Reasoning-Steps prompt text — no frontmatter, and literal `{README}`/`{REPO}` placeholders under "Input Variables" instead of resolved content — which meant they had to be dispatched by hand (read the file, substitute the placeholders, send as a generic prompt), the same legitimate no-frontmatter pattern Anthropic's own `skill-creator` plugin uses for its `analyzer`/`comparator`/`grader` agents. Both have since been rewritten into native, frontmatter-complete prompts that keep the paper's methodology — node-naming fidelity, ignore-non-functional-code, subgraph aggregation, discrepancy-flagging against existing docs — without the placeholder-substitution mechanism, so they now dispatch exactly like the other three (see Stage 2 below).

## Stage 0 — Deterministic evidence gathering (no LLM)

Run both scripts against the target repo:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/spring_signal_scan.py" <repo_path> --out spring_signals.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/partition_repo.py" <repo_path> --max-tokens 120000 --out groups.json
```

`spring_signals.json` gives you AST-detected Spring markers (controllers, entities, security annotations, messaging, deployment files, etc.) — via ast-grep, see `scripts/spring_ast_grep_rules.yml` — plus an `entity_table_map` resolving JPA entity classes to table names. `groups.json` gives you the token-bounded, DFS-ordered file groups for Stage 1. Read both before proceeding.

`spring_signal_scan.py` shells out to the `ast-grep` binary, so it needs to be on `PATH` (the script's own error message links install instructions if it isn't).

Both scripts also accept an optional `--respect-gitignore` flag, off by default, that additionally excludes paths matched by the repo's own `.gitignore` on top of the hardcoded exclude list — default behavior (flag omitted) is unchanged.

Also grep for `TODO|FIXME|XXX|HACK` across the repo yourself (not worth a dedicated script) and keep the hits — they feed `known_limitations.md` as candidates, not facts.

## Stage 1 — Parallel file summarization

For every group in `groups.json`, dispatch a `file-summarizer` subagent — a registered subagent type (`agents/file-summarizer.md`) — in the same turn as its sibling groups, so they run concurrently. Give each one its group's file list (it reads the files itself via its own `Read`/`Grep`/`Glob` access) **and** the relevant slice of `spring_signals.json` (matches whose `file` field falls in that group) so it isn't rediscovering annotations the ast-grep pass already found — it should focus on business meaning, not re-detection. Also give each dispatch the **entire** `references` bucket from `spring_signals.json` — repo-wide, not scoped to that group. This is the one slice that's deliberately passed in full to every dispatch: it's file-summarizer's only way to see cross-group relationships (a controller in one group calling a service in another), since its own group's file list otherwise has no visibility outside itself, and the ~10% DFS overlap between adjacent groups only rescues relationships that happen to straddle two *adjacent* groups. It's cheap — file/line/package-or-import-text triples, not source — so passing all of it to every dispatch should be inexpensive regardless of repo size, but this is worth confirming against a real repo's actual `references` bucket size rather than just assumed. Each returns a JSON array, one object per file (`file`, `cluster`, `summary`, `relationships`, `cross_group_relationships`, `group_function`, `spring_role`).

Collect results into `summaries.json`.

## Stage 2 — Parallel architecture (segment + merge)

Same dispatch pattern as Stage 1 and Stage 3 — `architect-segment` and `architect-merge` are registered subagents (`agents/architect-segment.md`, `agents/architect-merge.md`), dispatched by name via the Task tool. Don't read their file text and hand-substitute placeholders — that workaround applied only to an earlier, pre-rewrite draft of these two files and no longer applies.

- **Segment, per group, in parallel:** dispatch an `architect-segment` subagent for every group in `groups.json`, in the same turn so they run concurrently, passing that group's file summaries from Stage 1 as its input.
- **Merge, once, after all segments return:** dispatch one `architect-merge` subagent, passing all the segment fragments together, plus the repo's existing README/architecture docs if present (omit that part if there's nothing to pass). Deliberately not parallelized — it needs the full set of fragments to resolve cross-segment edges and de-duplicate nodes that fall in the ~10% overlap between adjacent groups.

This produces the diagram that feeds `architecture.md` and grounds several of the other thirteen files. `architect-merge` also cross-checks the merged diagram against any pre-existing README/architecture doc you passed it and flags conflicts in a dedicated "Discrepancies" section after the diagram (its own point 5) — surface that section as-is in `architecture.md` rather than re-deriving the comparison yourself.

## Stage 3 — Gap analysis, then live interview

Dispatch one `gap-analyzer` subagent (`agents/gap-analyzer.md`) with `spring_signals.json`, `summaries.json`, the merged architecture, and the TODO/FIXME grep hits. It does **not** talk to the user — it returns a structured list of candidate clarifying questions, one per genuine gap, organized by which of the fourteen files each gap blocks. Use `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md`'s "Interview-worthy" notes per file as the standard for what counts as a genuine gap versus something safely inferable.

**Then — in this orchestrating thread, not a subagent** — actually ask the user these questions. Batch them sensibly (don't fire off 40 separate questions one at a time); group by file or by theme, and let the user answer "don't know" or "skip" for any of them. Record every answer, verbatim, with today's date, into `interview_answers.json`. If the user skips a question, write that down as a skip, not as a blank — a doc-writer should treat "asked, unanswered" differently from "never asked."

Don't skip this stage even if the codebase looks self-explanatory. The whole reason it exists is that some categories (write ownership, external consumers, known limitations, deployment topology) are structurally invisible to static analysis regardless of how clean the code is.

## Stage 4 — Parallel doc generation

Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` fully now if you haven't already. For **each of the fourteen files**, dispatch a `doc-writer` subagent (`agents/doc-writer.md`), in the same turn as its thirteen siblings, passing:
- which of the fourteen files it's writing (so it reads the right section of the taxonomy)
- the relevant evidence: `spring_signals.json` slice, `summaries.json`, the merged architecture, `interview_answers.json`
- explicit instruction to mark anything neither evidenced nor answered as "Unknown" rather than infer it

## Output

Write to the target repo's `docs/` directory:
```
docs/
├── readme.md              (or leave existing README.md alone and write here instead)
├── architecture.md
├── integrations.md
├── authorization.md
├── database.md
├── operations.md
├── observability.md
├── troubleshooting.md
├── configuration.md
├── change_impact.md
├── glossary.md
├── local_development.md
├── testing.md
└── known_limitations.md
```

Never silently overwrite an existing `README.md` at the repo root — if one exists, write the generated overview to `docs/readme.md` and tell the user there's a pre-existing README they may want to reconcile it with.

Tell the user what was written, and — importantly — surface a short summary of what ended up in "Unknown" across all fourteen files, so they can see at a glance what the interview didn't cover and decide whether it's worth a follow-up pass.

## What this deliberately does not do yet

- No cross-repository discovery beyond what the interview surfaces manually.
- No SQL-lineage-grade parsing of native queries — `raw_queries` entries tagged `native` in `spring_signals.json` are flagged as candidates for a real SQL parser, not run through one. If you want that level of rigor, that's a natural next add-on, not something this pipeline does today.
- No re-run/drift detection. Re-running the whole pipeline is the refresh mechanism.
- No verification against ArchUnit or a compiled build — `spring_signal_scan.py` parses raw source text via ast-grep/tree-sitter by design, trading some precision for not needing a build step or classpath. If you want higher fidelity (resolved inheritance, annotations picked up via meta-annotations, etc.), that's a legitimate upgrade path, not something worth blocking v1 on.

## Sync note (2026-07-23)

This project copy was found stale during a chat review — it was missing two changes already merged into the repo's `main` branch: the `--respect-gitignore` flag mention in Stage 0, and the entire cross-group reference index addition in Stage 1 (repo-wide `references` bucket passed to every `file-summarizer` dispatch, plus the `cross_group_relationships` output field). Re-synced from the actual on-device file at `skills/document-spring-repo/SKILL.md` rather than assumed. If this file diverges from the repo again, prefer re-staging and diffing the real file over trusting this copy.