"""Document-spring-repo pipeline orchestration package."""

from doc_engine.pipeline.artifacts import (
    ARTIFACT_FILENAMES,
    ARTIFACT_MODELS,
    GroupsArtifact,
    InterviewAnswersArtifact,
    SpringSignalsArtifact,
    SummariesArtifact,
)
from doc_engine.pipeline.context import (
    MANIFEST_STAGES,
    PipelineContext,
    StageKind,
    StageResult,
    StageSpec,
)
from doc_engine.pipeline.executor import (
    HttpLLMStageExecutor,
    MockStageExecutor,
    StageExecutor,
    SubprocessStageRunner,
)
from doc_engine.pipeline.runner import PipelineRunner
from doc_engine.pipeline.stages import build_stage_specs
from doc_engine.pipeline.validation import (
    ArtifactValidationError,
    require_gap_probe_artifact,
    require_stage0_siblings,
    validate_artifact_file,
    validate_artifacts_in_dir,
)

__all__ = [
    "ARTIFACT_FILENAMES",
    "ARTIFACT_MODELS",
    "ArtifactValidationError",
    "GroupsArtifact",
    "HttpLLMStageExecutor",
    "InterviewAnswersArtifact",
    "MANIFEST_STAGES",
    "MockStageExecutor",
    "PipelineContext",
    "PipelineRunner",
    "SpringSignalsArtifact",
    "StageExecutor",
    "StageKind",
    "StageResult",
    "StageSpec",
    "SubprocessStageRunner",
    "SummariesArtifact",
    "build_stage_specs",
    "require_gap_probe_artifact",
    "require_stage0_siblings",
    "validate_artifact_file",
    "validate_artifacts_in_dir",
]
