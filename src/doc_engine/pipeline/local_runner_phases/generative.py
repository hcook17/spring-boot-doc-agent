"""Phase 6: generative Stages 1–4 mock run + abort path."""

from __future__ import annotations

from typing import Optional

from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import (
    _record_pipeline_stage_results,
    _write_certification_and_finish,
)
from doc_engine.pipeline.mock_stages import find_existing_readme
from doc_engine.pipeline.runner import PipelineRunner


def _note_existing_readme(state: LocalRunState) -> None:
    existing_readme = find_existing_readme(state.repo_path)
    if not existing_readme:
        return
    state.log("")
    state.log(
        f"  note: {existing_readme} already exists in the target repo. A real run "
        f"never overwrites it — the generated overview goes to docs/readme.md."
    )


def phase_generative(state: LocalRunState) -> Optional[int]:
    """Run mocked generative stages. Returns exit code on abort."""
    log = state.log
    runner = state.runner
    assert state.pipeline_ctx is not None
    assert state.mock_executor is not None

    log.rule("STAGES 1-4 — MOCKED subagent fan-out (PipelineRunner)")
    gen_runner = PipelineRunner(
        generative_executor=state.mock_executor,
        stages=state.generative_specs,
    )
    _record_pipeline_stage_results(
        runner, gen_runner.run(state.pipeline_ctx), ok_status="MOCK"
    )

    if runner.aborted:
        return _write_certification_and_finish(
            log,
            runner,
            state.profile,
            state.repo_path,
            state.out_dir,
            "mock",
            allow_mock=state.allow_mock,
            notice_lines=["Run aborted after generative stage failure — see above."],
        )

    _note_existing_readme(state)
    return None
