"""Tests for PipelineRunner with MockStageExecutor."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from doc_engine.pipeline.context import PipelineContext, StageKind, StageSpec
from doc_engine.pipeline.executor import MockStageExecutor, SubprocessStageRunner
from doc_engine.pipeline.runner import PipelineRunner
from doc_engine.pipeline.stages import build_stage_specs
from doc_engine.pipeline.validation import validate_artifact_file
from tests.conftest import FIXTURE_DIR, FIXTURE_SNAPSHOT_PATH


@pytest.fixture
def pipeline_context(tmp_path):
    repo = FIXTURE_DIR
    out = tmp_path / "run"
    out.mkdir()
    docs = out / "docs"
    docs.mkdir()
    return PipelineContext(
        repo_path=Path(repo),
        out_dir=out,
        manifest_path=out / "run_manifest.json",
        docs_dir=docs,
        python=sys.executable,
        today="2026-07-27",
        respect_gitignore=False,
        max_tokens=120000,
        log=lambda _msg: None,
    )


def test_pipeline_runner_with_fixture_signals_and_mock_generative(pipeline_context):
    """Use committed spring_signals fixture, run partition+edges, mock generative stages."""
    shutil.copy(FIXTURE_SNAPSHOT_PATH, pipeline_context.out_dir / "spring_signals.json")
    validate_artifact_file("spring_signals", pipeline_context.out_dir / "spring_signals.json")

    all_specs = build_stage_specs()
    # Skip init (needs real repo path) and signal_scan (needs ast-grep); fixture supplies signals.
    deterministic = [
        s for s in all_specs
        if s.kind == StageKind.DETERMINISTIC
        and s.name not in ("init_manifest", "signal_scan", "gap_probe")
    ]
    generative = [s for s in all_specs if s.kind == StageKind.GENERATIVE]

    # init_manifest still needed for manifest stages
    init_spec = next(s for s in all_specs if s.name == "init_manifest")
    init_runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=[init_spec],
    )
    init_results = init_runner.run(pipeline_context)
    assert all(r.success for _, r in init_results)

    pipeline_context.signals_path = pipeline_context.out_dir / "spring_signals.json"
    with pipeline_context.signals_path.open(encoding="utf-8") as fh:
        pipeline_context.signals = json.load(fh)

    det_runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=deterministic,
    )
    det_results = det_runner.run(pipeline_context)
    failed = [name for name, r in det_results if not r.success]
    assert not failed, f"deterministic stages failed: {failed}"

    mock_handlers = {
        "file_summarize": lambda ctx: _write_summaries(ctx),
        "architect": lambda ctx: _write_arch(ctx),
        "gap_analysis_interview": lambda ctx: _write_interview(ctx),
        "doc_writer": lambda ctx: _write_doc(ctx),
    }
    gen_runner = PipelineRunner(
        generative_executor=MockStageExecutor(mock_handlers),
        stages=generative,
    )
    gen_results = gen_runner.run(pipeline_context)
    failed_gen = [name for name, r in gen_results if not r.success]
    assert not failed_gen, f"generative stages failed: {failed_gen}"

    assert (pipeline_context.out_dir / "summaries.json").is_file()
    assert (pipeline_context.out_dir / "interview_answers.json").is_file()
    assert (pipeline_context.docs_dir / "readme.md").is_file()


def test_subprocess_stage_runner_records_failure(pipeline_context):
    runner = SubprocessStageRunner()
    result = runner.run(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        pipeline_context,
    )
    assert not result.success


def test_missing_required_output_is_stage_failure_not_crash(pipeline_context):
    """Declared outputs must fail cleanly as StageResult, not raise FileNotFoundError."""
    spec = StageSpec(
        name="noop_missing_facts",
        kind=StageKind.DETERMINISTIC,
        outputs=("facts.jsonl",),
        argv_builder=lambda ctx: [ctx.python, "-c", "pass"],
    )
    runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=[spec],
        validate_boundaries=True,
    )
    results = runner.run(pipeline_context)
    assert len(results) == 1
    name, result = results[0]
    assert name == "noop_missing_facts"
    assert result.success is False
    assert result.detail == "missing_required_output"
    assert result.error is not None
    assert "facts.jsonl" in result.error


def test_malformed_required_output_is_stage_failure_not_crash(pipeline_context):
    """Schema-invalid declared outputs fail as StageResult, not an uncaught exception."""
    spec = StageSpec(
        name="noop_bad_signals",
        kind=StageKind.DETERMINISTIC,
        outputs=("spring_signals.json",),
        argv_builder=lambda ctx: [
            ctx.python,
            "-c",
            (
                "import json, pathlib, sys; "
                "p = pathlib.Path(sys.argv[1]); "
                "p.write_text(json.dumps({'schema_version': 7}), encoding='utf-8')"
            ),
            str(pipeline_context.out_dir / "spring_signals.json"),
        ],
    )
    runner = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=[spec],
        validate_boundaries=True,
    )
    results = runner.run(pipeline_context)
    assert len(results) == 1
    name, result = results[0]
    assert name == "noop_bad_signals"
    assert result.success is False
    assert result.detail == "invalid_required_output"
    assert result.error is not None


def test_end_stage_failure_fails_otherwise_successful_stage(pipeline_context):
    """H3: a failing end-stage must not leave the stage marked success."""

    class FlakyManifestRunner:
        def run(self, argv, context):
            from doc_engine.pipeline.context import StageResult

            if "end-stage" in argv:
                return StageResult(
                    success=False, error="manifest locked", detail="end failed"
                )
            return StageResult(success=True, detail="ok")

    spec = StageSpec(
        name="noop_with_manifest",
        kind=StageKind.DETERMINISTIC,
        manifest_stage="signal_scan",
        outputs=(),
        argv_builder=lambda ctx: [ctx.python, "-c", "pass"],
    )
    runner = PipelineRunner(
        subprocess_runner=FlakyManifestRunner(),
        generative_executor=MockStageExecutor({}),
        stages=[spec],
        validate_boundaries=False,
    )
    results = runner.run(pipeline_context)
    assert len(results) == 1
    _, result = results[0]
    assert result.success is False
    assert result.detail == "manifest_end_stage_failed"


def _write_summaries(ctx: PipelineContext) -> str:
    path = ctx.out_dir / "summaries.json"
    path.write_text(
        json.dumps([{
            "file": "src/main/java/com/example/billing/Invoice.java",
            "cluster": [],
            "summary": "test",
            "relationships": [],
            "cross_group_relationships": [],
            "group_function": "billing",
            "spring_role": "entity",
            "evidence": [{"line": 1, "what": "entity"}],
        }]),
        encoding="utf-8",
    )
    return "1 summary"


def _write_arch(ctx: PipelineContext) -> str:
    (ctx.out_dir / "architecture_merged.md").write_text("# arch\n", encoding="utf-8")
    return "architecture"


def _write_interview(ctx: PipelineContext) -> str:
    path = ctx.out_dir / "interview_answers.json"
    path.write_text(
        json.dumps([{
            "id": "q1",
            "question": "q?",
            "status": "answered",
            "answer": "a",
            "date": ctx.today,
        }]),
        encoding="utf-8",
    )
    return "1 answer"


def _write_doc(ctx: PipelineContext) -> str:
    (ctx.docs_dir / "readme.md").write_text("# readme\n", encoding="utf-8")
    return "readme"
