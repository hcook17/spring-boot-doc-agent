# StageExecutor adapter pattern (defer HTTP until named customer)

This package orchestrates the document-spring-repo pipeline with a **ports and adapters** split:

| Port | Production adapter | Local / CI adapter |
|------|-------------------|-------------------|
| `SubprocessStageRunner` | runs `scripts/*.py` Stage 0 tools | same |
| `StageExecutor` (generative) | **Claude Code** — SKILL.md dispatches `agents/*.md` via Task | `MockStageExecutor` |
| `HttpLLMStageExecutor` | **not implemented** | stub only |

## Claude Code adapter (documentation-only)

Production runs do not call `PipelineRunner` from Python inside Claude Code today. The SKILL orchestrator is equivalent when it:

1. Runs the same subprocess commands as `build_stage_specs()` (`spring_signal_scan.py`, `partition_repo.py`, etc.).
2. Dispatches generative work to subagents with the artifact paths in `PipelineContext`.
3. Calls `validate_artifacts.py` at stage boundaries (see SKILL.md data contracts).
4. Runs `pipeline_validators.run_stage5_gate()` before doc-writer fan-out when `summaries.json` / `gap_questions.json` exist.

Mapping generative stages to agents:

| `generative_key` | Agent(s) |
|------------------|----------|
| `file_summarize` | `file-summarizer` (per group) |
| `architect` | `architect-segment` + `architect-merge` |
| `gap_analysis_interview` | `gap-analyzer` + live user interview (human — not inside `StageExecutor`) |
| `doc_writer` | `doc-writer` (fourteen files) |

Interview Q&A stays in the orchestrating thread by design (product differentiator).

## HttpLLMStageExecutor

`HttpLLMStageExecutor` in `executor.py` is a deliberate stub. Implement it only when a concrete non-Claude customer integration is specified (Azure OpenAI, etc.). Requirements for a real adapter:

- Read agent prompts from `agents/*.md` paths, not embedded Python strings.
- Respect `CONSTRAINTS.md` network egress policy.
- Honor artifact paths and run `validate_artifacts.py` after each write.
- Do not duplicate Task parallelism — fan-out belongs in the adapter or an external worker pool.

## Retry and idempotency (Newman)

| Stage | Retry | Idempotency notes |
|-------|-------|-------------------|
| `signal_scan` | safe to rerun | overwrites `spring_signals.json` |
| `partition` | safe to rerun | overwrites `groups.json` |
| generative stages | rerun overwrites downstream artifacts | prior `summaries.json` invalidates architecture + docs |
| `run_manifest` `cached` | orchestrator may skip a stage | manifest records `cached` status |

Do not mutate upstream artifacts in place — write new files per stage (DDIA write-once handoff).
