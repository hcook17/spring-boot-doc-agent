---
name: document-spring-repo
description: Scan a Spring Boot repository, ask the user clarifying questions about what static analysis can't determine (write ownership, external consumers, known limitations, intent behind unsecured endpoints), then generate a fixed set of fourteen markdown docs — readme, architecture, integrations, authorization, database, operations, observability, troubleshooting, configuration, change_impact, glossary, local_development, testing, known_limitations. Use whenever the user asks to document a Spring Boot repo, generate onboarding docs for a Java service, map out a legacy Spring codebase, or produce architecture/database/security documentation for a Spring Boot project. This is heavier than the generic document-repo pipeline — use this one specifically for Spring Boot/Spring Data/Spring Security codebases where the fourteen-file taxonomy applies.
---

# Document Spring Repo

Five stages. Two run in parallel across subagents (fast, code-only evidence gathering); one runs as a live conversation with the user (the interview — subagents can't do this, only the orchestrating thread can); the last runs in parallel again (fourteen independent doc-writing tasks). Stage 3 itself now bundles two independent one-shot subagent dispatches (gap-analyzer, and software-architect-and-testing) ahead of that live interview — both read the same Stage 2 output and neither depends on the other, so they're dispatched in the same turn.

Read `${CLAUDE_PLUGIN_ROOT}/CONSTRAINTS.md` once before running this pipeline for real — it's the single place that collects this plugin's runtime prerequisites, integration gaps, precision tradeoffs, confidentiality rules, and enterprise-readiness gaps (license, CI, secret-redaction, and more).

Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` before Stage 4 — it defines what goes in each of the fourteen files, which evidence maps to which file, and — this is the part that actually matters — where the line is between "safe to infer from code" and "needs a clarifying question." Getting that boundary wrong is the main way this pipeline produces confident-sounding fiction instead of documentation.

## Data contracts between stages

Four JSON artifacts cross stage boundaries. Their shapes are enforced by Pydantic models in `src/doc_engine/pipeline/artifacts.py` and JSON Schema files in `scripts/schemas/` (derived from those models). Validate at each boundary — fail the run on shape drift rather than letting a downstream stage absorb it silently.

| Artifact | Producer | Consumers | Schema |
|----------|----------|-----------|--------|
| `spring_signals.json` | Stage 0 `spring_signal_scan.py` | partition (indirect), Stages 1–4, `spring_drift_check.py` | `scripts/schemas/spring_signals.schema.json` |
| `groups.json` | Stage 0 `partition_repo.py` | Stage 1, `capacity_preflight.py`, `build_cross_group_edges.py` | `scripts/schemas/groups.schema.json` |
| `summaries.json` | Stage 1 `file-summarizer` | Stages 2–4 | `scripts/schemas/summaries.schema.json` |
| `interview_answers.json` | Stage 3 orchestrator (live interview) | Stage 4, `run_manifest.py finalize` | `scripts/schemas/interview_answers.schema.json` |

After Stage 0 produces `spring_signals.json` and `groups.json`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifacts.py" spring_signals spring_signals.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifacts.py" groups groups.json
```

Or validate everything present in the run directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifacts.py" --all .
```

After Stage 1 concatenates `summaries.json`, validate again. After recording `interview_answers.json`, validate that file before Stage 4.

`spring_signals.json` carries `schema_version` (currently ≥ 2). Any schema change must consider `spring_drift_check.py` as a downstream consumer, not only the four pipeline stages.

The executable stage graph in code is `doc_engine.pipeline.build_stage_specs()` — SKILL.md stages map 1:1 to those names. See `src/doc_engine/pipeline/README.md` for the bounded-context map.

**All six agent files — `file-summarizer.md`, `doc-writer.md`, `gap-analyzer.md`, `architect-segment.md`, `architect-merge.md`, and `software-architect-and-testing.md` — are registered Claude Code subagents**, each with proper YAML frontmatter (`name`, `description`, `tools`), dispatched by name via the Task tool. This wasn't always true of the last two: earlier drafts of `architect-segment.md`/`architect-merge.md` carried their source paper's (ArchAgent, arXiv:2601.13007) own literal Position/Objective/Reasoning-Steps prompt text — no frontmatter, and literal `{README}`/`{REPO}` placeholders under "Input Variables" instead of resolved content — which meant they had to be dispatched by hand (read the file, substitute the placeholders, send as a generic prompt), the same legitimate no-frontmatter pattern Anthropic's own `skill-creator` plugin uses for its `analyzer`/`comparator`/`grader` agents. Both have since been rewritten into native, frontmatter-complete prompts that keep the paper's methodology — node-naming fidelity, ignore-non-functional-code, subgraph aggregation, discrepancy-flagging against existing docs — without the placeholder-substitution mechanism, so they now dispatch exactly like the other three (see Stage 2 below).

## Run-level telemetry: `run_manifest.py`

**Concurrency contract — read this before Stage 0, it governs every stage below:** `run_manifest.py start-stage`/`end-stage` are called exactly once per named stage (`signal_scan`, `partition`, `file_summarize`, `architect`, `gap_analysis_interview`, `architecture_testing_review`, `doc_writer`), **by the orchestrating thread only** — never from inside a subagent, and never once per individual parallel dispatch within a stage (e.g. not once per file-summarizer group). A subagent calling this itself, or the orchestrating thread calling it per-dispatch instead of once per stage, produces a read-modify-write race against the same `run_manifest.json` and silently loses updates — `run_manifest.py` has no locking to protect against that.

`run_manifest.json` is written to the same working directory the orchestrating thread already runs `spring_signal_scan.py --out spring_signals.json` etc. from — alongside `spring_signals.json`/`groups.json`/`summaries.json`/`interview_answers.json`, not into the target repo.

Kick off the run before Stage 0's own scripts:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_manifest.py" init <repo_path> --out run_manifest.json
```

## Stage 0 — Deterministic evidence gathering (no LLM)

Run both scripts against the target repo, each bracketed by its own manifest stage (they fail independently, so each gets its own timing/pass-fail record rather than being lumped together):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_manifest.py" start-stage run_manifest.json signal_scan
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/spring_signal_scan.py" <repo_path> --out spring_signals.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_manifest.py" end-stage run_manifest.json signal_scan --status complete

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_manifest.py" start-stage run_manifest.json partition
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/partition_repo.py" <repo_path> --max-tokens 120000 --out groups.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_manifest.py" end-stage run_manifest.json partition --status complete
```

Then resolve cross-group file relationships once, deterministically — it needs both of the above, so it runs after both and belongs to neither:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_cross_group_edges.py" groups.json spring_signals.json --out cross_group_edges.json
```

This replaces what Stage 1 used to do by broadcasting the whole `references` bucket to every dispatch and asking each subagent to string-match its way to the answer. Two reasons it moved here, and the second is the important one:

- **Cost.** Broadcasting ships `g × |R|` rows, and both `g` and `|R|` grow with repo size — so the volume is quadratic. Measured on a 109-file sample: 1030 rows broadcast, 75 actually load-bearing.
- **Kind.** It is a join over `package`/`import` text. Nothing about it needs inference, so having a language model do it once per group is both wasteful and less accurate than a hash join. Computed here it becomes a fact with `file:line` provenance — legitimately `[Evidenced — …]` — rather than an LLM guess the tag grammar cannot honestly label.

It also catches a case the prompt-based version explicitly could not: two files in the *same package* that landed in different groups have no `import` between them (Java doesn't require importing your own package), so no amount of import-matching finds them. A package index does.

(Use `--status failed --error "<what went wrong>"` on the matching `end-stage` call instead if a script exits non-zero.)

`spring_signals.json` gives you AST-detected Spring markers (controllers, entities, security annotations, messaging, deployment files, etc.) — via ast-grep, see `src/doc_engine/scanning/resources/spring_ast_grep_rules.yml` — plus an `entity_table_map` resolving JPA entity classes to table names. `groups.json` gives you the token-bounded, DFS-ordered file groups for Stage 1. Read both before proceeding.

`spring_signal_scan.py` shells out to the `ast-grep` binary, so it needs to be on `PATH` (the script's own error message links install instructions if it isn't).

Both scripts also accept an optional `--respect-gitignore` flag, off by default, that additionally excludes paths matched by the repo's own `.gitignore` on top of the hardcoded exclude list — default behavior (flag omitted) is unchanged.

Also grep for `TODO|FIXME|XXX|HACK` across the repo yourself (not worth a dedicated script) and keep the hits — they feed `known_limitations.md` as candidates, not facts.

### Optional pre-flight: checking for drift before a full re-run

If you already have a `spring_signals.json` from a prior scan of this same repo (schema_version >= 2), it's worth checking whether anything actually drifted before committing to a full five-stage re-run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/spring_drift_check.py" <repo_path> <prior_spring_signals.json> --out drift_report.json
```

If a prior pipeline run's `run_manifest.json` is also available and you want drift measured against the specific run that produced the currently-published docs (rather than against the raw `spring_signals.json` scan, which may predate that run or be shared across several runs), add `--manifest run_manifest.json` — its `file_signatures` becomes the tier-1 baseline instead; `spring_signals.json` is still required either way, since `run_manifest.json` never carries the `evidence`/`entity_table_map` tier-2 needs.

This re-hashes every file (cheap, tier 1) and, only for files that changed, re-verifies the specific fact each citation recorded via a targeted `ast-grep` re-run (tier 2) — not just "did the file change" but "is the cited entity/repository/query/annotation still there in essentially the same shape." Each citation in `drift_report.json` ends up `unchanged`, `confirmed_still_present`, `drifted`, `file_deleted`, or (for filename-based evidence with no `rule_id` to recheck, e.g. migration files) `suspected_drift_content_changed_no_rule_to_recheck`. Use the report to decide whether a full re-run is warranted or whether only the drifted files/claims need attention. This is standalone tooling — it isn't invoked automatically as part of Stage 0, and there's no CI wiring; you run it by hand when you have a prior scan to check against.

**Configuration/deployment files get a more specific pair of outcomes than the generic fallback above**, via the `config_key_sets` snapshot `spring_signal_scan.py` records for them (schema_version >= 5, `_config_keys.py`): `config_structure_changed` (a key was added or removed — an expected, structural evolution of the config's own shape) versus `config_values_only_changed_review_needed` (the exact same keys, but the file's content changed anyway — the only way that happens is a value changed under an unchanged key). That second one is the case worth a human look in a setup where these files are checked-in placeholders/dummies and real values are injected by an external service at deploy time: nothing should be editing a value in-repo if the key structure didn't also need to change, so a values-only diff is a signal something unusual happened, not routine config drift.

## Stage 1 — Parallel file summarization

Wrap this whole stage in one `start-stage run_manifest.json file_summarize --fanout <num_groups>` / `end-stage ... --status complete` pair — one call before dispatching the group subagents, one after they've all returned, not one pair per group.

For every group in `groups.json`, dispatch a `file-summarizer` subagent — a registered subagent type (`agents/file-summarizer.md`) — in the same turn as its sibling groups, so they run concurrently. Give each one its group's file list (it reads the files itself via its own `Read`/`Glob` access, plus `ast-grep` through a scoped `Bash` grant) **and** the relevant slice of `spring_signals.json` (matches whose `file` field falls in that group) so it isn't rediscovering annotations the ast-grep pass already found — it should focus on business meaning, not re-detection. Also give each dispatch **its own group's entry from `cross_group_edges.json`** — the `outbound` / `inbound` arcs and `same_package_outside` blocks for that group id, and nothing else. These are resolved facts, not hints: treat them the same way as the signal-scan slice, as ground truth to describe rather than a table to search.

Earlier versions of this stage passed the **entire** repo-wide `references` bucket to every dispatch instead, on the reasoning that it was cheap (file/line/import triples, not source) and was the subagent's only window outside its own group. The first real run showed the cost is `g × |R|` with both terms growing in repo size — quadratic — and that the work being paid for was a `package`/`import` string join executed by a language model once per group. Stage 0's `build_cross_group_edges.py` now does that join once, exactly, and ships each group only its boundary. Do not go back to broadcasting the bucket. **Give each dispatch an absolute `output_path`** — `summaries_group_<id>.json` in the run's working directory. Each subagent writes its own JSON array there (one object per file: `file`, `cluster`, `summary`, `relationships`, `cross_group_relationships`, `group_function`, `spring_role`, `evidence`) and returns only a one-line confirmation.

`evidence` is the array of `{"line": N, "what": "..."}` anchors behind that file's summary, and it is the reason Stage 4 can cite anything the ast-grep pass didn't already find. Stage 0 records a line per mechanical hit and Stage 4 is required to emit `path:line`, but Stages 1–3 were all line-free by schema — so a business-purpose claim used to reach `doc-writer` with a path and no line, leaving it to re-read the file, cite the file alone, or invent a number. Stage 1 is the only stage holding both the open file and the semantic claim, which is why the anchor is recorded here and nowhere else. `test_pipeline_stages.py` enforces the shape.

Then concatenate the per-group files into `summaries.json` with a one-liner, rather than pasting arrays through the orchestrator:

```bash
python3 -c "import json,glob; json.dump([o for f in sorted(glob.glob('summaries_group_*.json')) for o in json.load(open(f))], open('summaries.json','w'), indent=1)"
```

**Why the output path matters, and not just for tidiness.** Every subagent in this pipeline used to return its full output as its final message, which meant the orchestrating thread's context — not the per-group token budget — was the real ceiling on how large a repository this pipeline could document. Measured on `spring-petclinic` (49 Java files, the smallest realistic Spring repo, 2 groups): Stage 1 alone returned roughly 218k subagent tokens through the orchestrator, before Stage 2 had dispatched anything. Stage 4's fourteen concurrent doc-writers are several times larger again.

Note this ceiling is invisible to `capacity-preflight`, which measures group count, dispatch fan-out, and the size of the per-group edge slice sent *in* — all input quantities. Nothing estimates what comes back. So a run can pass preflight cleanly and still exhaust the orchestrator on return payloads.

## Stage 2 — Parallel architecture (segment + merge)

Wrap this whole stage — both segment and merge together — in one `start-stage run_manifest.json architect --fanout <num_groups + 1>` / `end-stage ... --status complete` pair (the `+1` is the single merge dispatch; `run_manifest.py`'s capacity-preflight tie-in already treats segment+merge as one combined stage for this same reason).

Same dispatch pattern as Stage 1 and Stage 3 — `architect-segment` and `architect-merge` are registered subagents (`agents/architect-segment.md`, `agents/architect-merge.md`), dispatched by name via the Task tool. Don't read their file text and hand-substitute placeholders — that workaround applied only to an earlier, pre-rewrite draft of these two files and no longer applies.

Both stages take an absolute `output_path` and return a one-line confirmation, same as Stage 1 — see the "why" note there.

- **Segment, per group, in parallel:** dispatch an `architect-segment` subagent for every group in `groups.json`, in the same turn so they run concurrently. Pass it the **path** to that group's `summaries_group_<id>.json` from Stage 1 (it has `Read`; don't inline the summaries), and an `output_path` of `arch_fragment_<id>.md`.
- **Merge, once, after all segments return:** dispatch one `architect-merge` subagent with the **paths** to every `arch_fragment_*.md`, an `output_path` of `architecture_merged.md`, and the paths of the repo's existing README/architecture docs if present (omit that part if there's nothing to pass). Deliberately not parallelized — it needs the full set of fragments to resolve cross-segment edges and de-duplicate nodes that fall in the ~10% overlap between adjacent groups.

This produces the diagram that feeds `architecture.md` and grounds several of the other thirteen files. `architect-merge` also cross-checks the merged diagram against any pre-existing README/architecture doc you passed it and flags conflicts in a dedicated "Discrepancies" section after the diagram (its own point 5) — surface that section as-is in `architecture.md` rather than re-deriving the comparison yourself.

## Stage 3 — Gap analysis and architecture/testing review, then live interview

Two independent one-shot subagent dispatches happen here, in the same turn — both need only Stage 2's output (`summaries.json` plus the merged architecture) and neither depends on the other's result — followed by the live interview, which depends on one of them (`gap-analyzer`) but not the other.

**Gap analysis.** Wrap the `gap-analyzer` dispatch plus the live interview that follows it in one `start-stage run_manifest.json gap_analysis_interview --fanout 1` / `end-stage ... --status complete` pair (`--fanout 1` because only the gap-analyzer dispatch is a subagent; the interview itself has zero subagent fan-out, it's the orchestrating thread talking to the user).

Dispatch one `gap-analyzer` subagent (`agents/gap-analyzer.md`) with the **paths** to `spring_signals.json`, `summaries.json` and the merged architecture, plus the TODO/FIXME grep hits, and an `output_path` of `gap_questions.json`. It writes there and returns a one-line confirmation; read the file yourself before starting the interview. It does **not** talk to the user — it returns a structured list of candidate clarifying questions, one per genuine gap, organized by which of the fourteen files each gap blocks. Use `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md`'s "Interview-worthy" notes per file as the standard for what counts as a genuine gap versus something safely inferable.

**Architecture/testing review — dispatched in the same turn as gap-analyzer above, not after it.** Wrap this in its own `start-stage run_manifest.json architecture_testing_review --fanout 1` / `end-stage ... --status complete` pair — a separate manifest stage from `gap_analysis_interview` even though both are dispatched together, since this one needs no live interview and finishes independently. Dispatch one `software-architect-and-testing` subagent (`agents/software-architect-and-testing.md`) with the **paths** to `spring_signals.json`, `summaries.json`, and the merged architecture, and an `output_path` of `architecture_testing_review.json`. It reviews the target repo through a DDIA (Designing Data-Intensive Applications, 2e) lens and an Effective Software Testing (Aniche) lens, using `ast-grep`/`semgrep` and — only when a finding genuinely hinges on it — bounded external research (arXiv, GitHub, deepwiki.com; see the agent file for the tiering discipline). It writes there and returns a one-line confirmation with its finding count; read the file yourself before Stage 4. Unlike `gap-analyzer`'s output, this one feeds Stage 4 directly with no user interaction in between — it doesn't ask questions, it produces evidence-backed findings the same way `file-summarizer` does.

**Then — in this orchestrating thread, not a subagent** — actually ask the user gap-analyzer's questions. Batch them sensibly (don't fire off 40 separate questions one at a time); group by file or by theme, and let the user answer "don't know" or "skip" for any of them. Record every answer, verbatim, with today's date, into `interview_answers.json`. If the user skips a question, write that down as a skip, not as a blank — a doc-writer should treat "asked, unanswered" differently from "never asked."

`interview_answers.json` is a JSON list of objects in this shape — `run_manifest.py finalize --interview-file interview_answers.json` (see Output, below) parses exactly this to compute the asked/answered/skipped counts it records:

```json
[
  {"id": "integrations.who-calls-us", "question": "...", "status": "answered", "answer": "...", "date": "2026-07-24"},
  {"id": "known_limitations.retry-policy", "question": "...", "status": "skipped", "answer": null, "date": "2026-07-24"}
]
```

Don't skip this stage even if the codebase looks self-explanatory. The whole reason it exists is that some categories (write ownership, external consumers, known limitations, deployment topology) are structurally invisible to static analysis regardless of how clean the code is.

**Mechanical gate — validate `summaries.json` and `gap_questions.json` before Stage 4.** Shape checks for the summarizer and gap-analyzer outputs live in `scripts/pipeline_validators.py` (same logic as `tests/test_pipeline_stages.py`). Run this after `summaries.json` exists and after `gap_questions.json` is written; do not dispatch doc-writers while it is failing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pipeline_validators.py" . --target-repo <repo_path>
```

Also validate artifact schemas at the boundary:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifacts.py" summaries summaries.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_artifacts.py" interview_answers interview_answers.json
```

## Stage 4 — Parallel doc generation

Wrap this whole stage in one `start-stage run_manifest.json doc_writer --fanout 14` / `end-stage ... --status complete` pair — fanout is always 14, one dispatch per output file.

Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` fully now if you haven't already. For **each of the fourteen files**, dispatch a `doc-writer` subagent (`agents/doc-writer.md`), in the same turn as its thirteen siblings, passing:
- which of the fourteen files it's writing (so it reads the right section of the taxonomy)
- an absolute **`output_path`** — the actual `docs/<name>.md` it should write. Each writer writes its own file directly; the orchestrator never relays document text. Give every dispatch a distinct path, since fourteen siblings write into one directory concurrently and a duplicated path silently destroys a file
- the **paths** to the relevant evidence (`spring_signals.json`, `summaries.json`, the merged architecture, `interview_answers.json`) rather than their contents — every doc-writer has `Read`
- for the `architecture.md` and `testing.md` dispatches specifically, also the **path** to `architecture_testing_review.json` from Stage 3 — `doc-taxonomy.md`'s entries for those two files say how to fold its findings in
- explicit instruction to mark anything neither evidenced nor answered as "Unknown" rather than infer it

Each returns a one-line confirmation with its path and per-tag counts. After all fourteen return, verify the directory before finalizing — a writer that failed to write is otherwise indistinguishable from one that wrote successfully:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_pipeline_output.py" docs/ --target-repo <repo_path>
```

**This is a gate, not a report — do not finalize the run or tell the user it succeeded while it is failing.** It replaces three guarantees that were previously carried only by instructions in `agents/doc-writer.md`, i.e. by asking a subagent nicely:

- **all fourteen taxonomy files exist, by name.** Counting to fourteen is not enough: two writers handed the same `output_path` produce fourteen writes with one name duplicated and another missing, which a count check passes.
- **no writer went outside `docs/`.** The target repo is a clean checkout before a run, so `git status --porcelain` afterwards is an exact record of what the fan-out actually wrote. This is the structural version of "write to exactly the path given and nowhere else" — it needs no cooperation from the agent. Pass `--no-write-check` if the target repo was already dirty going in.
- **every `[Evidenced — path:line]` citation resolves** to a real file, with a real line number, in the target repo — and every tag is well-formed.

What it deliberately does not check is whether a resolvable citation actually *supports* the sentence attached to it. That needs a model; see `skills/semantic-pipeline-eval/`.

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

Close out the run manifest before reporting back to the user:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_manifest.py" finalize run_manifest.json \
    --signals-file spring_signals.json --docs-dir docs/ --interview-file interview_answers.json
```

(Add `--preflight-file capacity_preflight_report.json` too, if `capacity-preflight` was run before this run — see `skills/capacity-preflight/SKILL.md`.) This prints a short human-readable summary — per-stage timing, total duration, evidence-tag totals, interview answered/skipped, and any stage that had to be auto-canceled because it never reported back. Fold that summary into what you tell the user: what was written, and — importantly — a summary of what ended up in "Unknown" across all fourteen files (the manifest's own `evidence_tag_counts` gives you this directly, no need to re-derive it by re-reading all fourteen files), so they can see at a glance what the interview didn't cover and decide whether it's worth a follow-up pass. Note: the finalized manifest's `file_signatures` field records the same hash-keyed shape `spring_drift_check.py` needs for its tier-1 pass — pass it via `--manifest run_manifest.json` (alongside the still-required `spring_signals.json`, for `evidence`/`entity_table_map`) to measure drift against the specific run that produced these docs, rather than against the raw scan; see the "Optional pre-flight" section above.

### Optional post-run check: confidentiality (secret leakage)

`spring_signals.json`'s `redaction_zones` (see `scripts/_secret_heuristics.py`) tells Stage 1/Stage 4 subagents which config/deployment lines look like they carry a real credential, and both `agents/file-summarizer.md` and `agents/doc-writer.md` are instructed not to transcribe those values. An instruction to a subagent is not a guarantee, though — the same way `spring_drift_check.py` mechanically re-verifies a citation rather than trusting it's still accurate, you can mechanically re-check whether a credential-shaped value actually made it into this run's own output:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_no_secrets_leaked.py" summaries.json docs/
```

Exits non-zero and prints `file:line` (never the matched value itself) if it finds one. Heuristic, not exhaustive — see that script's and `_secret_heuristics.py`'s own docstrings for what it does and doesn't catch. Standalone, like `spring_drift_check.py` above: not invoked automatically by this pipeline, and not CI-wired (this repo's CI has no target-repo run to check output from — see `CONSTRAINTS.md`).

### Optional post-run check: citation coverage (missing and mis-anchored citations)

`check_pipeline_output.py` above gates tag *shape* and citation *resolvability*, and both of those checks iterate over tags that are **already present** — `find_malformed_tags()` only matches bracket spans starting with a recognized tag word, and `resolve_evidenced_citations()` only iterates `[Evidenced]` matches. A sentence carrying no tag at all matches neither, so it isn't reported as failing; it's invisible to the gate. `skills/semantic-pipeline-eval/` has the same blind spot from the other side — it samples claims that already carry a tag.

That leaves an omitted citation as the one defect nothing in the pipeline reports:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/citation_coverage.py" docs/ --target-repo <repo_path>
```

Reports sentences that name a concrete repo artifact but carry no tag, and `[Evidenced — path:line]` citations whose claim names symbols that appear nowhere in the cited file (candidate fabricated citation) or in the file but far from the cited line (imprecise anchor). Heuristic worklists, so it exits 0 by default — `--strict` makes findings non-zero. Pass `--target-repo`: without it the anchor check can't run, and the script says so rather than returning clean and silent.

See `skills/citation-coverage/SKILL.md` for the authoring rules that reduce these findings in the first place — the checker is the backstop, not the fix.

## Testing this pipeline's own output

`scripts/test_pipeline_stages.py` is a mechanical (not LLM-judge) structural test suite for the LLM stages above — file-summarizer, architect-segment/architect-merge, gap-analyzer, software-architect-and-testing, doc-writer — none of which had any test coverage before this file, unlike the deterministic Stage 0 scripts. Run it the same way as the other suites:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_pipeline_stages.py" -v
```

It validates the exact required tag grammar (`[Evidenced — ...]`/`[Confirmed — ...]`/`[Unknown — ...]`/`[Per existing docs — ...]`), whether `[Evidenced — path:line]` citations actually resolve to real files/lines, `file-summarizer`'s and `gap-analyzer`'s required JSON output shapes, and whether architecture-diagram node labels trace back to real file/class names — against synthetic sample data by default. It can also validate a *real* completed pipeline run's actual output (`summaries.json`, the merged architecture diagram, `gap_questions.json`, and the fourteen `docs/*.md` files) if you point `PIPELINE_ARTIFACTS_DIR` (and, for citation resolution against the target repo, `PIPELINE_ARTIFACTS_TARGET_REPO`) at them — opt-in, skipped otherwise, same pattern as `test_partition_repo_real_world.py`.

`scripts/test_run_manifest.py` covers `run_manifest.py` itself (the telemetry tool this file wires in above, not one of the four LLM stages) — stage timing math, the retry case (a stage that failed and was restarted), the partial-run case (a stage never ended before `finalize`), and the `capacity_preflight` stage-key mapping. Run it the same way: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/test_run_manifest.py" -v`.

## What this deliberately does not do yet

- No cross-repository discovery beyond what the interview surfaces manually.
- No SQL-lineage-grade parsing of native queries — `raw_queries` entries tagged `native` in `spring_signals.json` are flagged as candidates for a real SQL parser, not run through one. If you want that level of rigor, that's a natural next add-on, not something this pipeline does today.
- No automatic re-run/drift detection. `scripts/spring_drift_check.py` (see the Stage 0 pre-flight section above) can tell you what's drifted since a prior scan, but it's a standalone script you run by hand — it isn't invoked automatically by this pipeline or by CI, and running the whole pipeline again remains the actual refresh mechanism once you've decided a re-run is warranted. `run_manifest.json` can now be fed in via `--manifest` as the tier-1 file-signature baseline (its `target_repo.commit_hash` is a real provenance record of the run that produced the currently-published docs, not just "a more recent hash"); `spring_signals.json` is still required regardless, for the `evidence`/`entity_table_map` tier-2 recheck needs that `run_manifest.json` doesn't carry.
- No verification against ArchUnit or a compiled build — `spring_signal_scan.py` parses raw source text via ast-grep/tree-sitter by design, trading some precision for not needing a build step or classpath. If you want higher fidelity (resolved inheritance, annotations picked up via meta-annotations, etc.), that's a legitimate upgrade path, not something worth blocking v1 on.
