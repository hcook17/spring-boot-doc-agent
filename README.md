# spring-boot-doc-agent

**doc-engine** is a portable orchestrator for documenting Spring Boot repositories — scan, interview, and generate a fixed 14-file documentation set with machine-enforceable `certification.json` gates.

The **Claude Code plugin** (`adapters/claude/`) is an optional adapter for live generative stages. CI and local deterministic runs should use the CLI:

```bash
pip install -e .
doc-engine pipeline run /path/to/spring-repo --out-dir pipeline-artifacts
doc-engine certification verify pipeline-artifacts/certification.json
```

See [`docs/product-architecture.md`](docs/product-architecture.md) for kernel vs adapter layout.

## Pipeline

```
Stage 0  Deterministic scan (no LLM)     spring_signal_scan.py + partition_repo.py
Stage 1  Parallel file summarization      file-summarizer × N groups, concurrent
Stage 2  Parallel architecture            architect-segment × N groups (concurrent) → architect-merge (single)
Stage 3  Gap analysis + architecture/     gap-analyzer (single, prepares questions) +
         testing review + LIVE interview  software-architect-and-testing (single, DDIA/testing findings)
                                           → orchestrator asks gap-analyzer's questions directly
Stage 4  Parallel doc generation          doc-writer × 14 files, concurrent
```

Output: `docs/readme.md` (or `docs/README.md` won't clobber an existing root README), `architecture.md`, `integrations.md`, `authorization.md`, `database.md`, `operations.md`, `observability.md`, `troubleshooting.md`, `configuration.md`, `change_impact.md`, `glossary.md`, `local_development.md`, `testing.md`, `known_limitations.md`.

## Why the interview stage exists

Several of the fourteen files ask questions code cannot answer on its own — who else calls your endpoints, whether a table has one writer or several, whether a TODO comment is an accepted shortcut or forgotten debt. `skills/document-spring-repo/references/doc-taxonomy.md` spells out, file by file, where that line sits. The `gap-analyzer` subagent drafts the candidate questions; only the orchestrating conversation (not a subagent) actually asks you, since subagents in Claude Code run to completion and report back — they don't pause mid-task for interactive input.

Every generated file tags its claims as **evidenced in code**, **confirmed in interview**, or **unknown** — on purpose, so staleness and gaps stay visible instead of getting smoothed over.

## On the deterministic scan (`spring_signal_scan.py`)

Java structural detection runs on [ast-grep](https://ast-grep.github.io/) (tree-sitter-based AST matching), not regex — see `src/doc_engine/scanning/resources/spring_ast_grep_rules.yml` for the rule set. It's still source-text analysis, not bytecode — no build step or classpath required, at some cost in precision (it won't resolve inherited annotations or interfaces implemented indirectly). See `claude/research/source-text-vs-bytecode-analysis.md` for a deeper comparison against compiled-bytecode/ArchUnit-style analysis. Needs the `ast-grep` binary on `PATH`:

```bash
pip install -r requirements.txt   # pins ast-grep-cli, sqllineage, pathspec
```

That is the pinned path, and the one CI uses. `cargo install ast-grep` and `npm install -g @ast-grep/cli` also work, but they install an unpinned binary outside `requirements.txt` — and if you have already installed `ast-grep` that way, the two can shadow each other on `PATH` and you may not be running the version you think you are. See `claude/tool-quirks.md`'s `ast-grep` PATH-shadowing entry; `ast-grep --version` tells you which one won.

Tested against the fixture repo in `scripts/test_fixtures/spring_signals/` (run `pytest tests/test_spring_signal_scan.py -v`) — controller, entities (including one with extra annotations stacked on top of `@Entity`/`@Table`, and one with only `@Entity`), repositories (including an `@Repository`-annotated one, and a same-package class that deliberately isn't a repository), a JPQL and a native `@Query`, a multi-line security annotation, `application.yml`, `Dockerfile`. It correctly separates the JPQL query from the native one regardless of argument order, resolves each entity's own table independently (rather than pairing the first `@Table` found in a file with the first class found in the same file, which silently mismatched in any file with more than one entity), and doesn't false-positive `@EntityScan` as `@Entity` — that last one was a real bug in the original regex version, caught by running it against a large production Spring Boot codebase during this rewrite, not just the synthetic fixture.

This started as a regex scanner and was rewritten to ast-grep specifically because two of the regex version's precision gaps — multi-line annotations, and treating `@EntityScan` as if it were `@Entity` — turned out to matter on real code, not just in theory. If you want still higher fidelity later (resolved inheritance, annotations picked up via meta-annotations), swapping in an ArchUnit-based scanner (which analyzes compiled bytecode) is a reasonable next upgrade path; the JSON output shape is deliberately simple so that swap wouldn't require touching the rest of the pipeline — the same property that let this swap happen without touching anything downstream of it.

**Native-query lineage**: `raw_queries` entries tagged `"query_kind": "native"` now get best-effort source/target table extraction via [SQLLineage](https://sqllineage.io), in a `lineage` field on the entry (`{"available": true, "source_tables": [...], "target_tables": [...]}` on success, `{"available": false, "reason": "..."}` on failure). This is a **soft dependency** — unlike `ast-grep`, a missing `sqllineage` install (`pip install sqllineage`) or a query SQLLineage can't parse (an exotic dialect feature, a Spring SpEL expression like `:#{#tenant}` that isn't real bind-parameter syntax) degrades that one entry's `lineage` field rather than failing the scan. Spring's own `:name`/`?`/`?1` bind-parameter placeholders aren't valid SQL grammar in any dialect either, so they're substituted with a harmless literal before parsing — lineage only needs table-level structure, not the bound values. The dialect defaults to `ansi` (SQLLineage's own generic baseline, since this scanner has no way to know the target database) — pass `--sql-dialect mysql` (or `postgres`, `oracle`, `sqlite`, `tsql`, etc.) to `spring_signal_scan.py` for better accuracy if you know it. Entries tagged `"query_kind": "jpql"` also get a `lineage` field now, for the bounded common case: a single-entity `FROM <Entity> <alias>` clause (no joins, no association traversal, no JPQL-only functions like `SIZE()`) resolves via `resolve_jpql_to_lineage()`, which looks the entity up in `entity_table_map` (built from `@Entity`/`@Table` scanning), rewrites the query, and hands it to the same SQLLineage path native queries use. No published technique or usable open-source tool exists for general JPQL/HQL-to-SQL lineage translation (verified 2026-07-25 — see `claude/session-log.md`), so anything outside that bounded case (joins, `u.orders.total`-style traversal, `@Entity(name=...)` overrides, polymorphic `FROM`, embedded/composite keys) still degrades to `{"available": false, "reason": "..."}` rather than attempting a guess — see `CONSTRAINTS.md`'s "Known precision tradeoffs" item 2 for the full, current boundary.

## On drift detection (`spring_drift_check.py`)

Once you have a `spring_signals.json` from a prior scan of a repo, `python -m doc_engine.tools.spring_drift_check` checks whether it's still accurate against the repo's current state: a cheap whole-repo file-signature hash (tier 1) tells you which files changed at all, and only for those, a targeted `ast-grep` re-run (tier 2) re-verifies the specific fact each citation recorded — entity/table mapping, repository type args, query text, or annotation shape — rather than flagging every citation in a changed file just because *something* in it moved. It exists because a comment fix three lines from a cited annotation shouldn't read as drift on every fact the file happens to also contain.

```bash
python -m doc_engine.tools.spring_signal_scan <repo_path> --out spring_signals.json
# ... time passes, repo changes ...
python -m doc_engine.tools.spring_drift_check <repo_path> spring_signals.json --out drift_report.json

# Or, to measure drift against a specific document-spring-repo pipeline run's
# run_manifest.json instead of the raw scan (its target_repo.commit_hash is a
# provenance record of exactly what the currently-published docs saw):
python -m doc_engine.tools.spring_drift_check <repo_path> spring_signals.json \
    --manifest run_manifest.json --out drift_report.json
```

`spring_signals.json` is required either way — `run_manifest.json` records `file_signatures` (the tier-1 baseline `--manifest` overrides) but never `evidence`/`entity_table_map`, which tier 2 needs regardless of which baseline is used.

Tested via `pytest tests/test_spring_drift_check.py -v`, a real integration test suite (real `ast-grep` subprocesses against mutated copies of the same fixture repo `test_spring_signal_scan.py` uses) — see `skills/document-spring-repo/SKILL.md`'s Stage 0 for how to use the report as a pre-flight check before deciding whether a full pipeline re-run is warranted.

This is deliberately standalone, not a bug: no LLM calls, no CI wiring, not invoked automatically by the `document-spring-repo` pipeline. You run it by hand, pointing it at a repo and a prior scan, and use its report to decide what (if anything) needs a closer look.

## On the architecture/testing review agent (`software-architect-and-testing`)

Stage 3 also dispatches `software-architect-and-testing` (`agents/software-architect-and-testing.md`), which reviews the target repo through two books' lenses — [Designing Data-Intensive Applications, 2e](https://dataintensive.net/) (partitioning, replication/consistency, schema evolution, batch/stream processing) and *Effective Software Testing* (Aniche, Manning) (specification-based/boundary gaps, structural gaps, test-double discipline, named test smells) — feeding `architecture.md` and `testing.md` specifically. Its findings are evidenced the ordinary way (a real `path:line`, checked with `ast-grep` or, for the cross-cutting/multi-line patterns ast-grep's single-file matching doesn't reach cleanly, [semgrep](https://semgrep.dev) — see `scripts/spring_semgrep_rules.yml`, with the same non-vacuity gate `rule_coverage.py` holds the ast-grep ruleset to: `scripts/semgrep_rule_coverage.py`). When a finding hinges on whether an external library or pattern is a reasonable choice, it does bounded, tiered research (arXiv, GitHub filtered by stars and recent pushes, deepwiki.com as orientation only) rather than trusting memory — see the agent file and `claude/steering-prompts/00-shared-research-standards.md`/`10-review-persona-and-standards.md` for the exact discipline. Needs `semgrep` on `PATH` in addition to `ast-grep` — also pinned in `requirements.txt`.

## Testing the LLM stages

Only the deterministic scripts had test coverage until now. `	ests/test_pipeline_stages.py` adds mechanical (not LLM-judge) structural tests for the four LLM stages — file-summarizer, architect-segment/architect-merge, gap-analyzer, doc-writer — checking the required `[Evidenced — ...]`/`[Confirmed — ...]`/`[Unknown — ...]`/`[Per existing docs — ...]` tag grammar, whether `[Evidenced — path:line]` citations actually resolve to real files/lines, each stage's required JSON output shape, and whether architecture-diagram node labels trace back to real file/class names:

```bash
pytest tests/test_pipeline_stages.py -v
```

By default it runs against synthetic sample data shaped like each agent's documented output (no LLM calls — subagents can't be driven from a plain Python process outside a live session). Point `PIPELINE_ARTIFACTS_DIR` at a real completed run's output to additionally validate real generated docs, same opt-in pattern as `test_partition_repo_real_world.py`.

## Semantic evaluation and capacity preflight

`test_pipeline_stages.py` (above) only checks the *shape* of the four LLM stages' output — it never judges whether an `[Evidenced]` claim is actually true, or whether a `[Confirmed]` tag is really backed by a real interview answer. `skills/semantic-pipeline-eval/` adds that judgment layer: run it against a completed pipeline's `PIPELINE_ARTIFACTS_DIR` to sample evidenced claims for truthfulness, flag unmatched `[Confirmed]` tags and Mermaid syntax issues (via `python -m doc_engine.tools.semantic_eval_helpers`'s mechanical pre-pass), and check for cross-doc contradictions — see that skill's `SKILL.md` for the full rubric and its two-lane human sign-off (escalated findings, plus a random confidence spot-check over the judge's own `Supported` verdicts).

Separately, `skills/capacity-preflight/` turns this plugin's stated-but-unverified scale assumptions (chars/N token heuristic, uncapped subagent fan-out, the per-group `cross_group_edges.json` slice each Stage-1 dispatch carries) into concrete numbers for one specific target repo before you commit to a full run — `python -m doc_engine.tools.capacity_preflight` imports `partition_repo.py`'s, `spring_signal_scan.py`'s and `build_cross_group_edges.py`'s own logic rather than re-estimating from scratch. Use it before pointing the pipeline at a large or unfamiliar repo.

## Pipeline contracts and local orchestration

Inter-stage JSON artifacts (`spring_signals.json`, `groups.json`, `summaries.json`, `interview_answers.json`) have enforced shapes — see `skills/document-spring-repo/SKILL.md` "Data contracts between stages" and `scripts/schemas/`. Validate after each stage boundary:

```bash
python -m doc_engine.tools.validate_artifacts --all <run-directory>
```

Mechanical summarizer/gap-analyzer shape gates (before doc-writer fan-out in a real run):

```bash
python -m doc_engine.tools.pipeline_validators <run-directory> --target-repo <repo_path>
```

Code-level stage graph and bounded-context map: `src/doc_engine/pipeline/README.md`. End-to-end local run (deterministic stages real, LLM stages mocked):

```bash
python -m doc_engine.pipeline.local_runner /abs/path/to/spring-repo
```

## Constraints

`CONSTRAINTS.md` at the plugin root is the single place that collects this plugin's real runtime prerequisites, integration gaps, precision tradeoffs, confidentiality rules, and enterprise-readiness gaps (license, CI, RBAC, audit trail, and more) — read it before evaluating this plugin for use beyond your own machine. `MATURITY_ASSESSMENT.md` at the plugin root builds on top of it with an overall maturity scorecard, a drift-from-modern-practice analysis, and an adoption gate checklist — read that one specifically before adopting this plugin across an organization.

## Status and contributing

`STATUS.md` at the plugin root is a single, in-place-edited snapshot of what's done vs. pending on this plugin's own scaffolding work, and the next concrete action — read it before picking up any of `claude/steering-prompts/`. `CONTRIBUTING.md` has this repo's write-then-verify rule for anything written through a device bridge, remote tool, or a prior session's unverified claim about repo state. `claude/llms/README.md` indexes this repo's own PR history, one file per PR, each pairing a summary with deterministic `git`/`grep` commands to verify its claims directly instead of trusting the prose. `claude/tool-quirks.md` (see `skills/tool-quirks/SKILL.md`) is a separate index for odd behavior in the ambient tools/environment this repo is worked in — `gh`, `git`, MCP tools, Windows/Git-Bash quirks — distinct from this plugin's own document-generation logic.

## Install

**Kernel (any IDE / CI):**

```bash
pip install -r requirements.txt
pip install -e .
doc-engine pipeline run <repo_path> --out-dir pipeline-artifacts
```

**Claude Code adapter (optional — live generative stages + skills):**

```bash
claude plugin marketplace add ./spring-boot-doc-agent
claude plugin install spring-boot-doc-agent@spring-boot-doc-agent-marketplace
```

Marketplace entry installs `adapters/claude/` as `CLAUDE_PLUGIN_ROOT`. Example target-repo config: [`docs/examples/.doc-engine.yml`](docs/examples/.doc-engine.yml).

## Before you use this for real

1. `adapters/claude/plugin.json` and `.claude-plugin/marketplace.json` both name a real author, and `plugin.json`'s `license` is `"MIT"`, matching the root `LICENSE` file. (`marketplace.json` carries no `license` field of its own — it inherits by reference, since its plugin entry points at `adapters/claude/`.) Confirm both still say what you want before sharing this beyond your own machine.
2. Read `adapters/claude/skills/document-spring-repo/references/doc-taxonomy.md` once yourself before the first real run — it's the actual spec for what "good" looks like per file, and it's worth knowing what it does and doesn't ask about.
3. Make sure `ast-grep` is on `PATH` (see above) before the first run — Stage 0 will fail fast with an install pointer if it isn't.
4. Try it on one real (ideally smaller) service first. All <!-- derived: pipeline_agent_count -->6<!-- /derived --> `adapters/claude/agents/` files are native Claude Code subagent prompts now (not literal text adapted from a paper or another plugin) — `architect-segment`/`architect-merge` still carry forward the source paper's methodology (node-naming fidelity, subgraph aggregation, discrepancy-flagging), just reimplemented rather than copied.
5. The interview stage will feel slow the first time — that's by design, not a bug. It's the only stage doing something a script fundamentally cannot.