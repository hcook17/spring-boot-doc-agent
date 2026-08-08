"""Typed boundary objects for inter-stage JSON artifacts (Fowler DTOs).

Facade re-export of subdomain SoR modules — encoding schemas + wire vocab live
in the package modules; this view is derived convenience for callers.
"""

from doc_engine.pipeline.artifacts.capacity import (
    CapacityPreflightReportArtifact,
    CapacityWarningRow,
    Stage4MetricKind,
)
from doc_engine.pipeline.artifacts.drift import (
    DriftBaselineProvenance,
    DriftFileSummary,
    DriftReportArtifact,
    DriftResultRow,
    DriftStatus,
)
from doc_engine.pipeline.artifacts.edges_gap import (
    CrossGroupBucket,
    CrossGroupEdgeArc,
    CrossGroupEdgesArtifact,
    GapQuestionEntry,
    GapQuestionsArtifact,
    SamePackageOutside,
)
from doc_engine.pipeline.artifacts.facts_model import (
    FACTS_LEDGER_SCHEMA_VERSION,
    Fact,
    FactsArtifact,
)
from doc_engine.pipeline.artifacts.interview import (
    InterviewAnswerEntry,
    InterviewAnswersArtifact,
)
from doc_engine.pipeline.artifacts.partition import (
    GroupEntry,
    GroupsArtifact,
    SkippedFile,
)
from doc_engine.pipeline.artifacts.registry import (
    ARTIFACT_FILENAMES,
    ARTIFACT_MODELS,
    JSONL_ARTIFACTS,
    export_json_schemas,
)
from doc_engine.pipeline.artifacts.review import (
    ArchitectureTestingReviewArtifact,
    ArchitectureTestingReviewFinding,
    ReviewEvidenceAnchor,
    ReviewExternalResearch,
    ReviewResearchSource,
)
from doc_engine.pipeline.artifacts.signals import (
    VALID_SPRING_ROLES,
    EntityTableEntry,
    EvidenceMatch,
    FileSummaryEntry,
    FileSummaryEvidence,
    SpringSignalsArtifact,
    SummariesArtifact,
)
from doc_engine.pipeline.artifacts.vocab import (
    InterviewStatus,
    ResearchTiers,
    ResearchVerdict,
    ReviewLens,
    ReviewSeverity,
)

__all__ = [
    "ARTIFACT_FILENAMES",
    "ARTIFACT_MODELS",
    "ArchitectureTestingReviewArtifact",
    "ArchitectureTestingReviewFinding",
    "CapacityPreflightReportArtifact",
    "CapacityWarningRow",
    "CrossGroupBucket",
    "CrossGroupEdgeArc",
    "CrossGroupEdgesArtifact",
    "DriftBaselineProvenance",
    "DriftFileSummary",
    "DriftReportArtifact",
    "DriftResultRow",
    "DriftStatus",
    "EntityTableEntry",
    "EvidenceMatch",
    "FACTS_LEDGER_SCHEMA_VERSION",
    "Fact",
    "FactsArtifact",
    "FileSummaryEntry",
    "FileSummaryEvidence",
    "GapQuestionEntry",
    "GapQuestionsArtifact",
    "GroupEntry",
    "GroupsArtifact",
    "InterviewAnswerEntry",
    "InterviewAnswersArtifact",
    "InterviewStatus",
    "JSONL_ARTIFACTS",
    "ResearchTiers",
    "ResearchVerdict",
    "ReviewEvidenceAnchor",
    "ReviewExternalResearch",
    "ReviewLens",
    "ReviewResearchSource",
    "ReviewSeverity",
    "SamePackageOutside",
    "SkippedFile",
    "SpringSignalsArtifact",
    "Stage4MetricKind",
    "SummariesArtifact",
    "VALID_SPRING_ROLES",
    "export_json_schemas",
]
