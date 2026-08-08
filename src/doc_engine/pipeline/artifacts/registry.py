"""Artifact registry: model map, filenames, JSON Schema export."""

from typing import Any

from pydantic import BaseModel

from doc_engine.pipeline.artifacts.capacity import CapacityPreflightReportArtifact
from doc_engine.pipeline.artifacts.drift import DriftReportArtifact
from doc_engine.pipeline.artifacts.edges_gap import (
    CrossGroupEdgesArtifact,
    GapQuestionsArtifact,
)
from doc_engine.pipeline.artifacts.facts_model import (
    FACTS_LEDGER_SCHEMA_VERSION,
    FactsArtifact,
)
from doc_engine.pipeline.artifacts.interview import InterviewAnswersArtifact
from doc_engine.pipeline.artifacts.partition import GroupsArtifact
from doc_engine.pipeline.artifacts.review import ArchitectureTestingReviewArtifact
from doc_engine.pipeline.artifacts.signals import SpringSignalsArtifact, SummariesArtifact
from doc_engine.pipeline.compliance import CertificationReport

ARTIFACT_MODELS: dict[str, type[BaseModel]] = {
    "spring_signals": SpringSignalsArtifact,
    "groups": GroupsArtifact,
    "summaries": SummariesArtifact,
    "interview_answers": InterviewAnswersArtifact,
    "facts": FactsArtifact,
    "certification": CertificationReport,
    "cross_group_edges": CrossGroupEdgesArtifact,
    "gap_questions": GapQuestionsArtifact,
    "architecture_testing_review": ArchitectureTestingReviewArtifact,
    "drift_report": DriftReportArtifact,
    "capacity_preflight_report": CapacityPreflightReportArtifact,
}

ARTIFACT_FILENAMES: dict[str, str] = {
    "spring_signals": "spring_signals.json",
    "groups": "groups.json",
    "summaries": "summaries.json",
    "interview_answers": "interview_answers.json",
    "facts": "facts.jsonl",
    "certification": "certification.json",
    "cross_group_edges": "cross_group_edges.json",
    "gap_questions": "gap_questions.json",
    "architecture_testing_review": "architecture_testing_review.json",
    "drift_report": "drift_report.json",
    "capacity_preflight_report": "capacity_preflight_report.json",
}

# Artifacts stored as JSON Lines (one object per line), not a single JSON value.
JSONL_ARTIFACTS: frozenset[str] = frozenset({"facts"})


def export_json_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schema dicts for each artifact type."""
    schemas: dict[str, dict[str, Any]] = {}
    for name, model in ARTIFACT_MODELS.items():
        schema = model.model_json_schema()
        if name == "facts":
            schema["title"] = "FactsArtifact"
            schema["description"] = (
                f"facts.jsonl dual-emit ledger (schema_version={FACTS_LEDGER_SCHEMA_VERSION}); "
                "on disk: UTF-8 JSON Lines, one Fact object per line"
            )
            schema["x-doc-engine-schema-version"] = FACTS_LEDGER_SCHEMA_VERSION
            schema["x-doc-engine-encoding"] = "jsonl"
        schemas[name] = schema
    return schemas
