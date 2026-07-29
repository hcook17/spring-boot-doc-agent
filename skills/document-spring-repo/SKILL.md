---
name: document-spring-repo
description: Scan a Spring Boot repository, ask the user clarifying questions about what static analysis can't determine (write ownership, external consumers, known limitations, intent behind unsecured endpoints), then generate a fixed set of fourteen markdown docs — readme, architecture, integrations, authorization, database, operations, observability, troubleshooting, configuration, change_impact, glossary, local_development, testing, known_limitations. Use whenever the user asks to document a Spring Boot repo, generate onboarding docs for a Java service, map out a legacy Spring codebase, or produce architecture/database/security documentation for a Spring Boot project. This is heavier than the generic document-repo pipeline — use this one specifically for Spring Boot/Spring Data/Spring Security codebases where the fourteen-file taxonomy applies.
---

# Document Spring Repo

Five conceptual stages. **Deterministic Stage 0 is owned by the `doc-engine` CLI** (stage graph SoT: `doc_engine.pipeline.build_stage_specs()`). This skill owns **live generative work** only: Task fan-out to agents, the interview, and post-run gates via the CLI.

## Prerequisites

1. `doc-engine` on `PATH` (`pip install -e .` from the product repo). Confirm with `doc-engine --help`.
2. Read `${CLAUDE_PLUGIN_ROOT}/CONSTRAINTS.md` once (plugin-local stub; points at full monorepo CONSTRAINTS when you have the checkout).
3. Read `${CLAUDE_PLUGIN_ROOT}/skills/document-spring-repo/references/doc-taxonomy.md` before Stage 4.

**Do not** invoke deterministic tools through the Claude plugin install tree — marketplace installs have no `scripts/` directory under the plugin root. Use `doc-engine pipeline …` only.

Historical script names (`validate_artifacts.py`, `spring_drift_check.py`, `spring_signal_scan.py`, `partition_repo.py`, `run_manifest.py`, `pipeline_validators.py`, `check_pipeline_output.py`, …) still exist as thin shims under the **product** repo’s `scripts/` and/or as package modules; the skill invokes them only via the orchestrator, never via a plugin-local path.

## Orchestrator entry points (deterministic)

| Goal | Command |
|------|---------|
| Stage 0 (then continue with this skill) | `doc-engine pipeline run <repo_path> --compliance-profile deterministic_only --out-dir <run_dir> --docs-in-target-repo` |
| Stop after a named stage | `doc-engine pipeline run <repo_path> --until <stage> --out-dir <run_dir>` |
| Fast signal-scan smoke | `doc-engine pipeline run <repo_path> --compliance-profile scan_only --out-dir <run_dir>` |
| Full mock E2E (CI / wiring check) | `doc-engine pipeline run <repo_path> --out-dir <run_dir>` |
| Gates after live generative stages | `doc-engine pipeline gates --out-dir <run_dir> --target-repo <repo_path> --docs-dir <repo_path>/docs` |
| Certification check | `doc-engine certification verify <run_dir>/certification.json` |

Stage names for `--until` come from `build_stage_specs()` (e.g. `signal_scan`, `partition`, `cross_group_edges`, `capacity_preflight`).

Every `pipeline run` writes `certification.json` under `--out-dir`. **`certified: true` with `generative_executor: mock`** means structural wiring passed — not human-quality docs. Live Claude runs must complete Stages 1–4 below and then `pipeline gates`.

Target repos may set `.doc-engine.yml`:

```yaml
compliance_profile: certified
```

## Data contracts

Artifacts cross stage boundaries. Shapes are enforced by Pydantic models in `doc_engine.pipeline.artifacts` (schemas also under `scripts/schemas/` in the product repo). The orchestrator validates at Stage 0 boundaries; after live Stages 1–4, run `doc-engine pipeline gates`.

| Artifact | Producer | Consumers |
|----------|----------|-----------|
| `spring_signals.json` | Stage 0 (CLI) | Stages 1–4 |
| `groups.json` | Stage 0 (CLI) | Stage 1 |
| `cross_group_edges.json` | Stage 0 (CLI) | Stage 1 |
| `summaries.json` | Stage 1 agents | Stages 2–4 |
| `interview_answers.json` | Stage 3 interview | Stage 4 |

Work in `--out-dir` (and `--docs-in-target-repo` for `docs/`). Manifest and signals land beside each other in the run directory.

**Agents** — `file-summarizer`, `doc-writer`, `gap-analyzer`, `architect-segment`, `architect-merge`, `software-architect-and-testing` — are registered subagents under `${CLAUDE_PLUGIN_ROOT}/agents/`, dispatched by name via Task.

## Stage 0 — Deterministic evidence (CLI only)

```bash
doc-engine pipeline run <repo_path> \
  --compliance-profile deterministic_only \
  --out-dir <run_dir> \
  --docs-in-target-repo
```

Optional drift pre-check before a full re-run: if you already have a prior `spring_signals.json`, the product tool `spring_drift_check.py` (monorepo `scripts/` shim / package path — not under the plugin root) can report what drifted. Prefer re-running Stage 0 when unsure. This remains an optional pre-flight: checking for drift before a full re-run — standalone, not CI-triggered.

Also grep for `TODO|FIXME|XXX|HACK` across the target repo yourself and keep the hits for `known_limitations.md`.

Read `spring_signals.json`, `groups.json`, and `cross_group_edges.json` from `<run_dir>` before Stage 1.

## Stage 1 — Parallel file summarization

Wrap in one conceptual stage (orchestrator already recorded Stage 0 timing in `run_manifest.json`).

For every group in `groups.json`, dispatch a `file-summarizer` subagent (`agents/file-summarizer.md`) concurrently. Pass: group file list, signal-scan slice for that group, that group’s `cross_group_edges.json` entry, and an absolute `output_path` (`summaries_group_<id>.json` under `<run_dir>`).

Concatenate per-group files into `summaries.json` (from `<run_dir>`):

```bash
python3 -c "import json,glob,os; d=os.environ['RUN_DIR']; json.dump([o for f in sorted(glob.glob(os.path.join(d,'summaries_group_*.json'))) for o in json.load(open(f))], open(os.path.join(d,'summaries.json'),'w'), indent=1)"
```

(Set `RUN_DIR` to `<run_dir>`, or inline the path.)

## Stage 2 — Parallel architecture (segment + merge)

- **Segment:** dispatch `architect-segment` per group → `arch_fragment_<id>.md` in `<run_dir>`.
- **Merge:** one `architect-merge` → `architecture_merged.md`.

## Stage 3 — Gap analysis, architecture/testing review, live interview

Dispatch in the same turn:

- `gap-analyzer` → `gap_questions.json` (use taxonomy “Interview-worthy” notes).
- `software-architect-and-testing` → `architecture_testing_review.json`.

**Then — in this orchestrating thread** — ask the user gap-analyzer’s questions. Record answers into `interview_answers.json`:

```json
[
  {"id": "integrations.who-calls-us", "question": "...", "status": "answered", "answer": "...", "date": "2026-07-24"},
  {"id": "known_limitations.retry-policy", "question": "...", "status": "skipped", "answer": null, "date": "2026-07-24"}
]
```

## Stage 4 — Parallel doc generation

For each of the fourteen taxonomy files, dispatch `doc-writer` with a distinct `docs/<name>.md` `output_path`, paths to evidence artifacts, and taxonomy instructions. Never overwrite a root `README.md` — use `docs/readme.md` when a root README exists.

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
