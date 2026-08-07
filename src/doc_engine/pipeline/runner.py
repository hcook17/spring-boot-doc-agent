"""PipelineRunner — single executable stage graph with boundary validation."""

from __future__ import annotations

import json

from doc_engine.pipeline.context import PipelineContext, StageKind, StageResult, StageSpec
from doc_engine.pipeline.executor import MockStageExecutor, StageExecutor, SubprocessStageRunner
from doc_engine.pipeline.stages import build_stage_specs, manifest_fanout
from doc_engine.pipeline.validation import ArtifactValidationError, validate_artifact_file


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
        context.out_dir.mkdir(parents=True, exist_ok=True)
        context.signals_path = context.artifact_path("spring_signals.json")
        context.groups_path = context.artifact_path("groups.json")
        context.edges_path = context.artifact_path("cross_group_edges.json")
        context.preflight_path = context.artifact_path("capacity_preflight_report.json")

        results: list[tuple[str, StageResult]] = []
        for spec in self.stages:
            context.log("")
            context.log(f"--- {spec.name}")
            result = self._run_stage(spec, context)
            results.append((spec.name, result))
            if not result.success:
                context.log(f"  !! stage {spec.name} failed: {result.error or result.detail}")
                break
            try:
                self._validate_outputs(spec, context)
            except FileNotFoundError as exc:
                fail = StageResult(
                    success=False,
                    error=str(exc),
                    detail="missing_required_output",
                )
                results[-1] = (spec.name, fail)
                context.log(f"  !! stage {spec.name} failed: {exc}")
                break
            except (ArtifactValidationError, json.JSONDecodeError) as exc:
                fail = StageResult(
                    success=False,
                    error=str(exc),
                    detail="invalid_required_output",
                )
                results[-1] = (spec.name, fail)
                context.log(f"  !! stage {spec.name} failed: {exc}")
                break
            self._refresh_context_artifacts(context)
        return results

    def _run_stage(self, spec: StageSpec, context: PipelineContext) -> StageResult:
        if spec.manifest_stage:
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
            start = self.subprocess_runner.run(start_argv, context)
            if not start.success:
                return start

        if spec.kind == StageKind.DETERMINISTIC:
            if spec.argv_builder is None:
                return StageResult(success=False, error="deterministic stage missing argv_builder")
            result = self.subprocess_runner.run(spec.argv_builder(context), context)
        else:
            key = spec.generative_key or spec.name
            result = self.generative_executor.run_generative(key, context)

        if spec.manifest_stage:
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
            self.subprocess_runner.run(end_argv, context)

        return result

    def _validate_outputs(self, spec: StageSpec, context: PipelineContext) -> None:
        if not self.validate_boundaries or not spec.outputs:
            return
        name_map = {
            "spring_signals.json": "spring_signals",
            "groups.json": "groups",
            "summaries.json": "summaries",
            "interview_answers.json": "interview_answers",
        }
        for filename in spec.outputs:
            path = context.out_dir / filename
            if not path.is_file():
                raise FileNotFoundError(
                    f"stage {spec.name!r} did not produce required output {filename!r} "
                    f"at {path}"
                )
            artifact = name_map.get(filename)
            if not artifact:
                continue
            validate_artifact_file(artifact, path)

    def _refresh_context_artifacts(self, context: PipelineContext) -> None:
        if context.signals_path and context.signals_path.is_file():
            with context.signals_path.open(encoding="utf-8") as fh:
                context.signals = json.load(fh)
        if context.groups_path and context.groups_path.is_file():
            with context.groups_path.open(encoding="utf-8") as fh:
                context.groups = json.load(fh)
        if context.edges_path and context.edges_path.is_file():
            with context.edges_path.open(encoding="utf-8") as fh:
                context.edges = json.load(fh)
