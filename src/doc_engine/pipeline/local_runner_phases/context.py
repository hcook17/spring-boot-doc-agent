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


def _ensure_citation_pool(ctx: PipelineContext):
    if ctx.pool is None and ctx.signals:
        ctx.pool = load_citations(ctx.signals, str(ctx.repo_path))
    return ctx.pool


def _handler_file_summarize(ctx: PipelineContext, log):
    _ensure_citation_pool(ctx)
    return mock_file_summaries(
        str(ctx.out_dir), ctx.groups, ctx.pool, ctx.edges, log,
    )


def _handler_architect(ctx: PipelineContext, log):
    _ensure_citation_pool(ctx)
    return mock_architecture(str(ctx.out_dir), ctx.groups, ctx.pool, log)


def _ensure_todos(ctx: PipelineContext) -> None:
    if ctx.todos:
        return
    hits = sweep_todos(str(ctx.repo_path))
    todo_path = ctx.out_dir / "todo_hits.json"
    _write_json(str(todo_path), hits)
    ctx.todos = hits


def _handler_gap(ctx: PipelineContext, log):
    _ensure_citation_pool(ctx)
    _ensure_todos(ctx)
    return mock_gap_and_interview(
        str(ctx.out_dir), ctx.pool, ctx.todos, ctx.today, log,
    )


def _handler_doc_writer(ctx: PipelineContext, log):
    _ensure_citation_pool(ctx)
    answers = _read_json(str(ctx.out_dir / "interview_answers.json"))
    readme = ctx.existing_readme or find_existing_readme(str(ctx.repo_path))
    return mock_docs(
        str(ctx.docs_dir), ctx.pool, ctx.todos, answers, ctx.today, readme, log,
    )


def _build_mock_executor(log) -> MockStageExecutor:
    return MockStageExecutor({
        "file_summarize": lambda ctx: _handler_file_summarize(ctx, log),
        "architect": lambda ctx: _handler_architect(ctx, log),
        "gap_analysis_interview": lambda ctx: _handler_gap(ctx, log),
        "doc_writer": lambda ctx: _handler_doc_writer(ctx, log),
    })


def _select_specs_for_state(state: LocalRunState):
    """Return selected stage specs, or an int exit code on profile error."""
    try:
        return stages_for_profile(
            state.profile,
            build_stage_specs(),
            skip_signal_scan=state.skip_signal_scan,
            until_stage=state.until_stage,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _partition_specs_by_kind(selected_specs):
    deterministic = [
        spec for spec in selected_specs if spec.kind == StageKind.DETERMINISTIC
    ]
    generative = [
        spec for spec in selected_specs if spec.kind == StageKind.GENERATIVE
    ]
    return deterministic, generative


def _record_reused_signal_scan(state: LocalRunState) -> None:
    if not state.skip_signal_scan:
        return
    state.runner.record(
        "pipeline:signal_scan",
        "OK",
        0.0,
        f"reused --signals-file {os.path.abspath(state.args.signals_file)}",
    )


def phase_build_context(state: LocalRunState) -> Optional[int]:
    """Wire context + mock handlers and select stages for the profile."""
    args = state.args
    log = state.log

    state.pipeline_ctx = PipelineContext(
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
    state.mock_executor = _build_mock_executor(log)

    selected_specs = _select_specs_for_state(state)
    if isinstance(selected_specs, int):
        return selected_specs

    if state.until_stage:
        log(f"  until stage   : {state.until_stage}")

    state.selected_specs = selected_specs
    state.deterministic_specs, state.generative_specs = _partition_specs_by_kind(
        selected_specs
    )
    _record_reused_signal_scan(state)
    return None
