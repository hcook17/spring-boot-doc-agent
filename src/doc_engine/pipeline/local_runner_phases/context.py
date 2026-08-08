"""Phase 2: PipelineContext, mock generative handlers, stage selection."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from doc_engine.pipeline.compliance import stages_for_profile
from doc_engine.pipeline.context import PipelineContext, StageKind
from doc_engine.pipeline.executor import MockStageExecutor
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.mock_stages import (
    _read_json,
    _write_json,
    find_existing_readme,
    load_citations,
    mock_architecture,
    mock_docs,
    mock_file_summaries,
    mock_gap_and_interview,
    sweep_todos,
)
from doc_engine.pipeline.stages import build_stage_specs


def phase_build_context(state: LocalRunState) -> Optional[int]:
    """Wire context + mock handlers and select stages for the profile."""
    args = state.args
    log = state.log
    runner = state.runner

    pipeline_ctx = PipelineContext(
        repo_path=Path(state.repo_path),
        out_dir=Path(state.out_dir),
        manifest_path=Path(state.manifest),
        docs_dir=Path(state.docs_dir),
        python=state.py,
        today=state.today,
        respect_gitignore=args.respect_gitignore,
        max_tokens=args.max_tokens,
        existing_readme=find_existing_readme(state.repo_path),
        log=log,
    )
    state.pipeline_ctx = pipeline_ctx
    state.mock_executor = _build_mock_executor(log)

    all_specs = build_stage_specs()
    try:
        selected_specs = stages_for_profile(
            state.profile,
            all_specs,
            skip_signal_scan=state.skip_signal_scan,
            until_stage=state.until_stage,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if state.until_stage:
        log(f"  until stage   : {state.until_stage}")

    state.selected_specs = selected_specs
    state.deterministic_specs = [
        spec for spec in selected_specs if spec.kind == StageKind.DETERMINISTIC
    ]
    state.generative_specs = [
        spec for spec in selected_specs if spec.kind == StageKind.GENERATIVE
    ]

    # Reused Path A is not an omitted required stage — record it as ok for the fold.
    if state.skip_signal_scan:
        runner.record(
            "pipeline:signal_scan",
            "OK",
            0.0,
            f"reused --signals-file {os.path.abspath(args.signals_file)}",
        )
    return None


def _build_mock_executor(log) -> MockStageExecutor:
    def _ensure_pool(ctx: PipelineContext):
        if ctx.pool is None and ctx.signals:
            ctx.pool = load_citations(ctx.signals, str(ctx.repo_path))
        return ctx.pool

    def handler_file_summarize(ctx: PipelineContext):
        _ensure_pool(ctx)
        return mock_file_summaries(
            str(ctx.out_dir), ctx.groups, ctx.pool, ctx.edges, log,
        )

    def handler_architect(ctx: PipelineContext):
        _ensure_pool(ctx)
        return mock_architecture(str(ctx.out_dir), ctx.groups, ctx.pool, log)

    def handler_gap(ctx: PipelineContext):
        _ensure_pool(ctx)
        if not ctx.todos:
            hits = sweep_todos(str(ctx.repo_path))
            todo_path = ctx.out_dir / "todo_hits.json"
            _write_json(str(todo_path), hits)
            ctx.todos = hits
        return mock_gap_and_interview(
            str(ctx.out_dir), ctx.pool, ctx.todos, ctx.today, log,
        )

    def handler_doc_writer(ctx: PipelineContext):
        _ensure_pool(ctx)
        answers = _read_json(str(ctx.out_dir / "interview_answers.json"))
        readme = ctx.existing_readme or find_existing_readme(str(ctx.repo_path))
        return mock_docs(
            str(ctx.docs_dir), ctx.pool, ctx.todos, answers, ctx.today, readme, log,
        )

    return MockStageExecutor({
        "file_summarize": handler_file_summarize,
        "architect": handler_architect,
        "gap_analysis_interview": handler_gap,
        "doc_writer": handler_doc_writer,
    })
