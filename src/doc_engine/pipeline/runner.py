"""PipelineRunner — single executable stage graph with boundary validation."""

from __future__ import annotations

import json

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES
from doc_engine.pipeline.context import PipelineContext, StageKind, StageResult, StageSpec
from doc_engine.pipeline.executor import MockStageExecutor, StageExecutor, SubprocessStageRunner
from doc_engine.pipeline.stages import build_stage_specs, manifest_fanout
from doc_engine.pipeline.validation import ArtifactValidationError, validate_artifact_file

# Reverse registry: filename → artifact key (schema-validated when registered).
_FILENAME_TO_ARTIFACT = {filename: name for name, filename in ARTIFACT_FILENAMES.items()}


def _stage_failure_result(error: str, detail: str) -> StageResult:
    """Build a failed StageResult with a stable detail code."""
    return StageResult(success=False, error=error, detail=detail)


def _start_manifest_stage(
    runner: SubprocessStageRunner,
    spec: StageSpec,
    context: PipelineContext,
) -> StageResult | None:
    """Record start-stage in the run manifest; return failure or None on success."""
    if not spec.manifest_stage:
        return None
    fanout = manifest_fanout(spec, context)
    start_argv = [
        context.python,
        "-m",
        "doc_engine.tools.run_manifest",
        "start-stage",
        str(context.manifest_path),
        spec.manifest_stage,
    ]
    if fanout is not None:
        start_argv.extend(["--fanout", str(fanout)])
    start = runner.run(start_argv, context)
    if not start.success:
        return start
    return None


def _end_manifest_argv(
    spec: StageSpec,
    context: PipelineContext,
    result: StageResult,
) -> list[str]:
    """Build the run_manifest end-stage argv for a completed stage body."""
    status = "complete" if result.success else "failed"
    end_argv = [
        context.python,
        "-m",
        "doc_engine.tools.run_manifest",
        "end-stage",
        str(context.manifest_path),
        spec.manifest_stage,
        "--status",
        status,
    ]
    if not result.success:
        end_argv.extend(["--error", result.error or result.detail or "stage failed"])
    return end_argv


def _end_manifest_stage(
    runner: SubprocessStageRunner,
    spec: StageSpec,
    context: PipelineContext,
    result: StageResult,
) -> StageResult:
    """Record end-stage; fail the stage if end-stage itself fails after success."""
    if not spec.manifest_stage:
        return result
    end = runner.run(_end_manifest_argv(spec, context, result), context)
    if not result.success:
        return result
    if end.success:
        return result
    return _stage_failure_result(
        end.error or end.detail or "end-stage failed",
        "manifest_end_stage_failed",
    )


def _execute_stage_body(
    subprocess_runner: SubprocessStageRunner,
    generative_executor: StageExecutor,
    spec: StageSpec,
    context: PipelineContext,
) -> StageResult:
    """Run the deterministic argv builder or generative executor for one stage."""
    if spec.kind == StageKind.DETERMINISTIC:
        if spec.argv_builder is None:
            return _stage_failure_result(
                "deterministic stage missing argv_builder",
                "missing_argv_builder",
            )
        return subprocess_runner.run(spec.argv_builder(context), context)
    key = spec.generative_key or spec.name
    return generative_executor.run_generative(key, context)


def _validate_one_output(spec: StageSpec, context: PipelineContext, filename: str) -> None:
    """Ensure one declared output exists and passes schema validation when registered."""
    path = context.out_dir / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"stage {spec.name!r} did not produce required output {filename!r} "
            f"at {path}"
        )
    artifact = _FILENAME_TO_ARTIFACT.get(filename)
    if artifact is None:
        return
    validate_artifact_file(artifact, path)


def _load_json_if_present(path) -> object | None:
    """Return parsed JSON when *path* exists, else None."""
    if path is None or not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class PipelineRunner:
    """Orchestrates deterministic subprocess stages and generative StageExecutor stages."""

    def __init__(
        self,
        subprocess_runner: SubprocessStageRunner | None = None,
        generative_executor: StageExecutor | None = None,
        stages: list[StageSpec] | None = None,
        validate_boundaries: bool = True,
    ):
        self.subprocess_runner = subprocess_runner or SubprocessStageRunner()
        self.generative_executor = generative_executor or MockStageExecutor()
        self.stages = stages or build_stage_specs()
        self.validate_boundaries = validate_boundaries

    def run(self, context: PipelineContext) -> list[tuple[str, StageResult]]:
        self._prepare_context_paths(context)
        results: list[tuple[str, StageResult]] = []
        for spec in self.stages:
            if not self._run_one_stage_into(results, spec, context):
                break
        return results

    def _prepare_context_paths(self, context: PipelineContext) -> None:
        """Create the out dir and stamp well-known artifact paths onto context."""
        context.out_dir.mkdir(parents=True, exist_ok=True)
        context.signals_path = context.artifact_path("spring_signals.json")
        context.groups_path = context.artifact_path("groups.json")
        context.edges_path = context.artifact_path("cross_group_edges.json")
        context.preflight_path = context.artifact_path("capacity_preflight_report.json")

    def _run_one_stage_into(
        self,
        results: list[tuple[str, StageResult]],
        spec: StageSpec,
        context: PipelineContext,
    ) -> bool:
        """Run one stage; append result; return False when the pipeline should stop."""
        context.log("")
        context.log(f"--- {spec.name}")
        result = self._run_stage(spec, context)
        results.append((spec.name, result))
        if not result.success:
            context.log(f"  !! stage {spec.name} failed: {result.error or result.detail}")
            return False
        fail = self._boundary_failure_after_stage(spec, context)
        if fail is not None:
            results[-1] = (spec.name, fail)
            context.log(f"  !! stage {spec.name} failed: {fail.error}")
            return False
        self._refresh_context_artifacts(context)
        return True

    def _boundary_failure_after_stage(
        self,
        spec: StageSpec,
        context: PipelineContext,
    ) -> StageResult | None:
        """Validate declared outputs; return a StageResult on boundary failure."""
        try:
            self._validate_outputs(spec, context)
        except FileNotFoundError as exc:
            return _stage_failure_result(str(exc), "missing_required_output")
        except (ArtifactValidationError, json.JSONDecodeError) as exc:
            return _stage_failure_result(str(exc), "invalid_required_output")
        return None

    def _run_stage(self, spec: StageSpec, context: PipelineContext) -> StageResult:
        start_failure = _start_manifest_stage(self.subprocess_runner, spec, context)
        if start_failure is not None:
            return start_failure
        result = _execute_stage_body(
            self.subprocess_runner,
            self.generative_executor,
            spec,
            context,
        )
        return _end_manifest_stage(self.subprocess_runner, spec, context, result)

    def _validate_outputs(self, spec: StageSpec, context: PipelineContext) -> None:
        if not self.validate_boundaries or not spec.outputs:
            return
        for filename in spec.outputs:
            _validate_one_output(spec, context, filename)

    def _refresh_context_artifacts(self, context: PipelineContext) -> None:
        signals = _load_json_if_present(context.signals_path)
        if signals is not None:
            context.signals = signals
        groups = _load_json_if_present(context.groups_path)
        if groups is not None:
            context.groups = groups
        edges = _load_json_if_present(context.edges_path)
        if edges is not None:
            context.edges = edges
