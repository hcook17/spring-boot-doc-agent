"""Phase 6: generative Stages 1–4 mock run + abort path."""

from __future__ import annotations

from typing import Optional

from doc_engine.pipeline.local_runner_phases.state import LocalRunState
from doc_engine.pipeline.local_runner_phases.support import _write_certification_and_finish
from doc_engine.pipeline.mock_stages import find_existing_readme
from doc_engine.pipeline.runner import PipelineRunner


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
    gen_results = gen_runner.run(state.pipeline_ctx)
    for stage_name, stage_result in gen_results:
        status = "MOCK" if stage_result.success else "FAIL"
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
            "mock",
            allow_mock=state.allow_mock,
            notice_lines=["Run aborted after generative stage failure — see above."],
        )

    if existing_readme := find_existing_readme(state.repo_path):
        log("")
        log(
            f"  note: {existing_readme} already exists in the target repo. A real run "
            f"never overwrites it — the generated overview goes to docs/readme.md."
        )
    return None
