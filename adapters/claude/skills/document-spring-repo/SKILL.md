---
name: document-spring-repo
description: Scan a Spring Boot repository, ask the user clarifying questions about what static analysis can't determine (write ownership, external consumers, known limitations, intent behind unsecured endpoints), then generate a fixed set of fourteen markdown docs — readme, architecture, integrations, authorization, database, operations, observability, troubleshooting, configuration, change_impact, glossary, local_development, testing, known_limitations. Use whenever the user asks to document a Spring Boot repo, generate onboarding docs for a Java service, map out a legacy Spring codebase, or produce architecture/database/security documentation for a Spring Boot project. This is heavier than the generic document-repo pipeline — use this one specifically for Spring Boot/Spring Data/Spring Security codebases where the fourteen-file taxonomy applies.
---

# Document Spring Repo

Five conceptual stages. **Stage graph SoT:** `doc_engine.pipeline.stages.build_stage_specs()` (deterministic argv + generative choreography metadata via `generative_choreography()`). This skill owns **live generative execution** only: Task fan-out to the agents named in that SoT, the interview when `requires_human_interview` is set, and post-run gates via the CLI.

## Prerequisites

1. `doc-engine` on `PATH` (`pip install -e .` from the product repo). Confirm with `doc-engine --help`.
2. Read `${CLAUDE_PLUGIN_ROOT}/CONSTRAINTS.md` once (plugin-local stub; points at full monorepo CONSTRAINTS when you have the checkout).
3. Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` before Stage 4.

**Do not** invoke deterministic tools through the Claude plugin install tree — marketplace installs have no `scripts/` directory under the plugin root. Use `doc-engine pipeline …` only.

## Orchestrator entry points (deterministic)

| Goal | Command |
|------|---------|
| Stage 0 (then continue with this skill) | `doc-engine pipeline run <repo_path> --compliance-profile deterministic_only --out-dir <run_dir> --docs-in-target-repo` |
| Stop after a named stage | `doc-engine pipeline run <repo_path> --until <stage> --out-dir <run_dir>` |
| Fast signal-scan smoke | `doc-engine pipeline run <repo_path> --compliance-profile scan_only --out-dir <run_dir>` |
| Full mock E2E (CI / wiring check) | `doc-engine pipeline run <repo_path> --out-dir <run_dir>` |
| Gates after live generative stages | `doc-engine pipeline gates --out-dir <run_dir> --target-repo <repo_path> --docs-dir <repo_path>/docs` |
| Certification check | `doc-engine certification verify <run_dir>/certification.json` |

Stage names for `--until` and generative agent bindings come from `build_stage_specs()` / `generative_choreography()` — do not maintain a second stage list here.

Every `pipeline run` writes `certification.json` under `--out-dir`. **`certified: true` with `generative_executor: mock`** means structural wiring passed — not human-quality docs. Live Claude runs must complete generative stages below and then `pipeline gates`.

Target repos may set `.doc-engine.yml`:

```yaml
compliance_profile: certified
```

## Data contracts

Artifacts cross stage boundaries. Shapes are enforced by Pydantic models in `doc_engine.pipeline.artifacts`. The orchestrator validates at Stage 0 boundaries; after live generative stages, run `doc-engine pipeline gates`.

| Artifact | Producer | Consumers |
|----------|----------|-----------|
| `spring_signals.json` | Stage 0 (CLI) | generative stages |
| `facts.jsonl` | Stage 0 (CLI, dual-emit) | gap_analysis_interview / doc_writer (contested identity) |
| `groups.json` | Stage 0 (CLI) | file_summarize / architect |
| `cross_group_edges.json` | Stage 0 (CLI) | file_summarize |
| `summaries.json` | file_summarize agents | later generative stages |
| `interview_answers.json` | gap_analysis_interview | doc_writer |

Work in `--out-dir` (and `--docs-in-target-repo` for `docs/`). Manifest and signals land beside each other in the run directory.

**Agents** — bind via `generative_choreography()` (`file-summarizer`, `doc-writer`, `gap-analyzer`, `architect-segment`, `architect-merge`, `software-architect-and-testing`) under `${CLAUDE_PLUGIN_ROOT}/agents/`, dispatched by name via Task.

## Stage 0 — Deterministic evidence (CLI only)

```bash
doc-engine pipeline run <repo_path> \
  --compliance-profile deterministic_only \
  --out-dir <run_dir> \
  --docs-in-target-repo
```

Optional drift pre-check: `python -m doc_engine.tools.spring_drift_check`. Prefer re-running Stage 0 when unsure. Boundary validation uses `validate_artifacts.py` / `python -m doc_engine.tools.validate_artifacts`.

Also collect `TODO`/`FIXME`/`XXX`/`HACK` candidates for `known_limitations.md` via
structural search (`ast-grep` on Java — comments are AST nodes) or from
file-summarizer evidence; **do not** use text `grep`/`rg` (denied for agents).
Keep hits as candidates, not facts — see doc-taxonomy.md.

Read `spring_signals.json`, `facts.jsonl`, `groups.json`, and `cross_group_edges.json` from `<run_dir>` before generative work. Prefer `doc-engine query …` for bounded lookups (see `${CLAUDE_PLUGIN_ROOT}/SEARCH.md`).

## Generative stages (live adapter)

Follow `generative_choreography()` order. Summary (must match the SoT — if prose and SoT disagree, SoT wins):

1. **file_summarize** — agent `file-summarizer` per group → concatenate `summaries_group_*.json` into `summaries.json`.
2. **architect** — `architect-segment` per group, then `architect-merge`.
3. **gap_analysis_interview** — `gap-analyzer` + `software-architect-and-testing`, then **human interview in this thread** (`requires_human_interview`) → `interview_answers.json`.
4. **doc_writer** — `doc-writer` × fourteen taxonomy files under `docs/`.

Concatenate per-group summaries:

```bash
python3 -c "import json,glob,os; d=os.environ['RUN_DIR']; json.dump([o for f in sorted(glob.glob(os.path.join(d,'summaries_group_*.json'))) for o in json.load(open(f))], open(os.path.join(d,'summaries.json'),'w'), indent=1)"
```

Interview answer shape:

```json
[
  {"id": "integrations.who-calls-us", "question": "...", "status": "answered", "answer": "...", "date": "2026-07-24"},
  {"id": "known_limitations.retry-policy", "question": "...", "status": "skipped", "answer": null, "date": "2026-07-24"}
]
```

Never overwrite a root `README.md` — use `docs/readme.md` when a root README exists.

## Finish (gates + certification)

```bash
doc-engine pipeline gates \
  --out-dir <run_dir> \
  --target-repo <repo_path> \
  --docs-dir <repo_path>/docs

doc-engine certification verify <run_dir>/certification.json
```

Do not tell the user the run succeeded while gates fail.

## What this deliberately does not do

- No plugin-local deterministic tool tree — tools live in the `doc-engine` package.
- No duplicating `build_stage_specs()` as bash one-liners in this file.
- No automatic cross-repo discovery beyond the interview.
- Regenerating docs remains a deliberate re-run of Stage 0 + generative stages.
