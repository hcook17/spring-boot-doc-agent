"""Phase 3: Stage 0 deterministic PipelineRunner + early abort certification."""

from __future__ import annotations

from typing import Optional

from doc_engine.pipeline.executor import MockStageExecutor
from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import _write_certification_and_finish
from doc_engine.pipeline.runner import PipelineRunner


def phase_stage0(state: LocalRunState) -> Optional[int]:
    """Run deterministic Stage 0. Returns an exit code when the run aborts."""
    log = state.log
    runner = state.runner
    assert state.pipeline_ctx is not None

    log.rule("STAGE 0 — deterministic (PipelineRunner, real scripts)")
    det_runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=state.deterministic_specs,
    )
    det_results = det_runner.run(state.pipeline_ctx)
    for stage_name, stage_result in det_results:
        status = "OK" if stage_result.success else "FAIL"
        runner.record(
            f"pipeline:{stage_name}",
            status,
            0.0,
            stage_result.detail or stage_result.error or "",
        )
        if not stage_result.success:
            runner.aborted = True

    if runner.aborted:
        return _write_certification_and_finish(
            log,
            runner,
            state.profile,
            state.repo_path,
            state.out_dir,
            "none",
            allow_mock=state.allow_mock,
            notice_lines=["Run aborted before later stages — see above."],
        )
    return None
