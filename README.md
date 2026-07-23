# spring-boot-doc-agent

A Claude Code plugin that scans a Spring Boot repository, asks you the questions static analysis genuinely can't answer, and generates a fixed 14-file documentation set.

## Pipeline

```
Stage 0  Deterministic scan (no LLM)     spring_signal_scan.py + partition_repo.py
Stage 1  Parallel file summarization      file-summarizer × N groups, concurrent
Stage 2  Parallel architecture            architect-segment × N groups (concurrent) → architect-merge (single)
Stage 3  Gap analysis + LIVE interview    gap-analyzer (single, prepares questions) → orchestrator asks you directly
Stage 4  Parallel doc generation          doc-writer × 14 files, concurrent
```

Output: `docs/readme.md` (or `docs/README.md` won't clobber an existing root README), `architecture.md`, `integrations.md`, `authorization.md`, `database.md`, `operations.md`, `observability.md`, `troubleshooting.md`, `configuration.md`, `change_impact.md`, `glossary.md`, `local_development.md`, `testing.md`, `known_limitations.md`.

## Why the interview stage exists

Several of the fourteen files ask questions code cannot answer on its own — who else calls your endpoints, whether a table has one writer or several, whether a TODO comment is an accepted shortcut or forgotten debt. `skills/document-spring-repo/references/doc-taxonomy.md` spells out, file by file, where that line sits. The `gap-analyzer` subagent drafts the candidate questions; only the orchestrating conversation (not a subagent) actually asks you, since subagents in Claude Code run to completion and report back — they don't pause mid-task for interactive input.

Every generated file tags its claims as **evidenced in code**, **confirmed in interview**, or **unknown** — on purpose, so staleness and gaps stay visible instead of getting smoothed over.

## On the deterministic scan (`spring_signal_scan.py`)

Java structural detection runs on [ast-grep](https://ast-grep.github.io/) (tree-sitter-based AST matching), not regex — see `scripts/spring_ast_grep_rules.yml` for the rule set. It's still source-text analysis, not bytecode — no build step or classpath required, at some cost in precision (it won't resolve inherited annotations or interfaces implemented indirectly). Needs the `ast-grep` binary on `PATH`:

```bash
cargo install ast-grep       # or: npm install -g @ast-grep/cli
```

Tested against the fixture repo in `scripts/test_fixtures/spring_signals/` (run `python3 scripts/test_spring_signal_scan.py -v`) — controller, entities (including one with extra annotations stacked on top of `@Entity`/`@Table`, and one with only `@Entity`), repositories (including an `@Repository`-annotated one, and a same-package class that deliberately isn't a repository), a JPQL and a native `@Query`, a multi-line security annotation, `application.yml`, `Dockerfile`. It correctly separates the JPQL query from the native one regardless of argument order, resolves each entity's own table independently (rather than pairing the first `@Table` found in a file with the first class found in the same file, which silently mismatched in any file with more than one entity), and doesn't false-positive `@EntityScan` as `@Entity` — that last one was a real bug in the original regex version, caught by running it against a large production Spring Boot codebase during this rewrite, not just the synthetic fixture.

This started as a regex scanner and was rewritten to ast-grep specifically because two of the regex version's precision gaps — multi-line annotations, and treating `@EntityScan` as if it were `@Entity` — turned out to matter on real code, not just in theory. If you want still higher fidelity later (resolved inheritance, annotations picked up via meta-annotations), swapping in an ArchUnit-based scanner (which analyzes compiled bytecode) is a reasonable next upgrade path; the JSON output shape is deliberately simple so that swap wouldn't require touching the rest of the pipeline — the same property that let this swap happen without touching anything downstream of it.

**Native-query lineage**: `raw_queries` entries tagged `"query_kind": "native"` now get best-effort source/target table extraction via [SQLLineage](https://sqllineage.io), in a `lineage` field on the entry (`{"available": true, "source_tables": [...], "target_tables": [...]}` on success, `{"available": false, "reason": "..."}` on failure). This is a **soft dependency** — unlike `ast-grep`, a missing `sqllineage` install (`pip install sqllineage`) or a query SQLLineage can't parse (an exotic dialect feature, a Spring SpEL expression like `:#{#tenant}` that isn't real bind-parameter syntax) degrades that one entry's `lineage` field rather than failing the scan. Spring's own `:name`/`?`/`?1` bind-parameter placeholders aren't valid SQL grammar in any dialect either, so they're substituted with a harmless literal before parsing — lineage only needs table-level structure, not the bound values. The dialect defaults to `ansi` (SQLLineage's own generic baseline, since this scanner has no way to know the target database) — pass `--sql-dialect mysql` (or `postgres`, `oracle`, `sqlite`, `tsql`, etc.) to `spring_signal_scan.py` for better accuracy if you know it. Entries tagged `"query_kind": "jpql"` still never get a `lineage` field, and this is fundamental rather than a gap to close later — JPQL references entity names, not table names, and isn't valid SQL grammar at all, a known, documented limitation of general-purpose SQL lineage tools generally, not something specific to this scanner or to SQLLineage.

## Constraints

`CONSTRAINTS.md` at the plugin root is the single place that collects this plugin's real runtime prerequisites, integration gaps, precision tradeoffs, confidentiality rules, and enterprise-readiness gaps (license, CI, RBAC, audit trail, and more) — read it before evaluating this plugin for use beyond your own machine.

## Install (local, not yet published)

```bash
claude plugin marketplace add ./spring-boot-doc-agent
claude plugin install spring-boot-doc-agent@spring-boot-doc-agent-marketplace
```

## Before you use this for real

1. `.claude-plugin/plugin.json` and `marketplace.json` already have a real author; `license` is still `"UNLICENSED"` — set a real one if you're sharing this beyond your own machine.
2. Read `skills/document-spring-repo/references/doc-taxonomy.md` once yourself before the first real run — it's the actual spec for what "good" looks like per file, and it's worth knowing what it does and doesn't ask about.
3. Make sure `ast-grep` is on `PATH` (see above) before the first run — Stage 0 will fail fast with an install pointer if it isn't.
4. Try it on one real (ideally smaller) service first. All five `agents/` files are native Claude Code subagent prompts now (not literal text adapted from a paper or another plugin) — `architect-segment`/`architect-merge` still carry forward the source paper's methodology (node-naming fidelity, subgraph aggregation, discrepancy-flagging), just reimplemented rather than copied.
5. The interview stage will feel slow the first time — that's by design, not a bug. It's the only stage doing something a script fundamentally cannot.