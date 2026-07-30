"""Control-wiring regressions: controls that must bite where they claim to.

Seed only already-true invariants so this suite stays green without Phase B.
Friend-review blockers land with their wiring asserts in the same change.
"""

from __future__ import annotations

import sys

from doc_engine.pipeline.context import PipelineContext, StageKind, StageSpec
from doc_engine.pipeline.executor import MockStageExecutor
from doc_engine.pipeline.runner import PipelineRunner
from doc_engine.pipeline.stages import build_stage_specs


def test_signal_scan_declares_facts_jsonl_output() -> None:
    spec = next(s for s in build_stage_specs() if s.name == "signal_scan")
    assert "facts.jsonl" in spec.outputs
    assert "spring_signals.json" in spec.outputs


def test_missing_facts_jsonl_is_stage_failure_not_crash(tmp_path) -> None:
    """Declared outputs fail as StageResult — not an uncaught FileNotFoundError."""
    out = tmp_path / "run"
    out.mkdir()
    docs = out / "docs"
    docs.mkdir()
    ctx = PipelineContext(
        repo_path=tmp_path,
        out_dir=out,
        manifest_path=out / "run_manifest.json",
        docs_dir=docs,
        python=sys.executable,
        today="2026-07-30",
        respect_gitignore=False,
        max_tokens=120000,
        log=lambda _msg: None,
    )
    spec = StageSpec(
        name="noop_missing_facts",
        kind=StageKind.DETERMINISTIC,
        outputs=("facts.jsonl",),
        argv_builder=lambda c: [c.python, "-c", "pass"],
    )
    results = PipelineRunner(
        generative_executor=MockStageExecutor({}),
        stages=[spec],
        validate_boundaries=True,
    ).run(ctx)
    assert len(results) == 1
    _name, result = results[0]
    assert result.success is False
    assert result.detail == "missing_required_output"
    assert result.error is not None
    assert "facts.jsonl" in result.error
