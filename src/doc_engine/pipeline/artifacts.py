"""Typed boundary objects for inter-stage JSON artifacts (Fowler DTOs)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from doc_engine.pipeline.compliance import CertificationReport
from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES

VALID_SPRING_ROLES = frozenset({
    "controller", "service", "repository", "entity", "config", "security",
    "messaging-producer", "messaging-consumer", "test", "other",
})

InterviewStatus = Literal["answered", "skipped"]
ReviewLens = Literal["ddia", "testing"]
ReviewSeverity = Literal["informational", "worth-flagging"]
ResearchTier = Literal["A", "B", "C"]
ResearchVerdict = Literal["CONFIRMED", "PLAUSIBLE", "REFUTED", "UNRESOLVED"]


class EvidenceMatch(BaseModel):
    """One hit inside a spring_signals evidence bucket."""

    model_config = ConfigDict(extra="allow")

    file: str
    line: int | None = None
    match: str | None = None
    rule_id: str | None = None


class EntityTableEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    file: str
    table: str
    table_name_source: str | None = None
    rule_id: str | None = None
    match: str | None = None


class SpringSignalsArtifact(BaseModel):
    """spring_signals.json — Stage 0 system of record."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(ge=2)
    scanner_version: str = "unknown"
    repo_path: str
    files_scanned: dict[str, int]
    entity_table_map: dict[str, EntityTableEntry | dict[str, Any]]
    evidence: dict[str, list[EvidenceMatch]]
    file_signature_algorithm: str | None = None
    file_signatures: dict[str, str] | None = None
    redaction_zones: dict[str, Any] | None = None
    config_key_sets: dict[str, Any] | None = None
    scanners: list[str] | None = None


class SkippedFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    file: str
    reason: str


class GroupEntry(BaseModel):
    id: int
    files: list[str]
    est_tokens: int


class GroupsArtifact(BaseModel):
    """groups.json — partition_repo.py output."""

    repo_path: str
    max_tokens_per_group: int
    overlap: float
    total_files_considered: int
    total_files_skipped: int
    skipped: list[SkippedFile | dict[str, Any]]
    num_groups: int
    groups: list[GroupEntry]

    @field_validator("groups")
    @classmethod
    def groups_len_matches_num_groups(cls, groups: list[GroupEntry], info) -> list[GroupEntry]:
        num = info.data.get("num_groups")
        if num is not None and len(groups) != num:
            raise ValueError(f"groups length {len(groups)} != num_groups {num}")
        return groups


class FileSummaryEvidence(BaseModel):
    line: int = Field(ge=1)
    what: str = Field(min_length=1)


class FileSummaryEntry(BaseModel):
    """One file-summarizer output object — also the element type of summaries.json."""

    file: str
    cluster: list[str]
    summary: str
    relationships: list[str]
    cross_group_relationships: list[str]
    group_function: str
    spring_role: str
    evidence: list[FileSummaryEvidence]

    @field_validator("spring_role")
    @classmethod
    def spring_role_valid(cls, value: str) -> str:
        if value not in VALID_SPRING_ROLES:
            raise ValueError(f"spring_role {value!r} not in {sorted(VALID_SPRING_ROLES)}")
        return value


class SummariesArtifact(RootModel[list[FileSummaryEntry]]):
    """summaries.json — concatenated file-summarizer output."""


class InterviewAnswerEntry(BaseModel):
    id: str
    question: str
    status: InterviewStatus
    answer: str | None = None
    date: str


class InterviewAnswersArtifact(RootModel[list[InterviewAnswerEntry]]):
    """interview_answers.json — human-in-the-loop answers."""


# Phase 1 dual-emit ledger — closed record shape (DDIA SoR; additive evolution only).
# Bump FACTS_LEDGER_SCHEMA_VERSION when breaking the eight-field contract.
# Sequencing: claude/research/schema-contracts-decision-memo-2026-07-30.md slice 1.
FACTS_LEDGER_SCHEMA_VERSION = 2


class Fact(BaseModel):
    """One facts.jsonl record — system-of-record row beside spring_signals.json.

    All eight keys are always present. ``extra=forbid`` keeps the ledger from
    silently growing undocumented columns (Ch5 explicit schema discipline).
    """

    model_config = ConfigDict(extra="forbid")

    predicate: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    object: str | None = None
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    file: str | None = None
    line: int | None = None
    rule_id: str | None = None
    scanner: str | None = None

    @field_validator("line")
    @classmethod
    def line_positive_when_set(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("line must be >= 1 when present")
        return value


class FactsArtifact(RootModel[list[Fact]]):
    """facts.jsonl — ordered list of Fact records (JSON Lines on disk)."""


# --- Slice 2–4: certification + derived edges + LLM views (schema-contracts memo) ---


class CrossGroupEdgeArc(BaseModel):
    """One cut arc in cross_group_edges.json (outbound/inbound)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    via: str | None = None
    confidence: str | None = None
    static_import: bool | None = None


class SamePackageOutside(BaseModel):
    model_config = ConfigDict(extra="allow")

    package: str
    files_in_group: list[str]
    files_outside_group: list[str]


class CrossGroupBucket(BaseModel):
    model_config = ConfigDict(extra="allow")

    outbound: list[CrossGroupEdgeArc | dict[str, Any]] = Field(default_factory=list)
    inbound: list[CrossGroupEdgeArc | dict[str, Any]] = Field(default_factory=list)
    same_package_outside: list[SamePackageOutside | dict[str, Any]] = Field(default_factory=list)


class CrossGroupEdgesArtifact(BaseModel):
    """cross_group_edges.json — Stage 0 partitioned join (derived)."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = 1
    repo_path: str | None = None
    num_groups: int
    references_rows: int | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    groups: dict[str, CrossGroupBucket | dict[str, Any]]


class GapQuestionEntry(BaseModel):
    """One gap-analyzer question object."""

    model_config = ConfigDict(extra="allow")

    blocks_file: str
    topic: str = Field(min_length=1)
    question: str = Field(min_length=1)
    evidence: str = Field(min_length=1)

    @field_validator("blocks_file")
    @classmethod
    def blocks_file_in_fourteen(cls, value: str) -> str:
        if value not in VALID_DOC_FILES:
            raise ValueError(f"blocks_file {value!r} not one of the fourteen output files")
        return value


class GapQuestionsArtifact(RootModel[list[GapQuestionEntry]]):
    """gap_questions.json — Stage 3 gap-analyzer output."""


class ReviewEvidenceAnchor(BaseModel):
    model_config = ConfigDict(extra="allow")

    line: int = Field(ge=1)
    what: str = Field(min_length=1)
    file: str | None = None


class ReviewResearchSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    tier: ResearchTier
    identifier: str | None = None
    url: str | None = None
    checked_date: str | None = None
    what_it_showed: str | None = None


class ReviewExternalResearch(BaseModel):
    model_config = ConfigDict(extra="allow")

    question: str | None = None
    sources: list[ReviewResearchSource | dict[str, Any]] = Field(default_factory=list)
    verdict: ResearchVerdict | None = None


class ArchitectureTestingReviewFinding(BaseModel):
    """One software-architect-and-testing finding."""

    model_config = ConfigDict(extra="allow")

    lens: ReviewLens
    concept: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    evidence: list[ReviewEvidenceAnchor] = Field(min_length=1)
    severity: ReviewSeverity
    external_research: ReviewExternalResearch | dict[str, Any] | None = None


class ArchitectureTestingReviewArtifact(RootModel[list[ArchitectureTestingReviewFinding]]):
    """architecture_testing_review.json — JSON array of findings."""


# Closed status vocabulary for drift_report.json — mirror of STATUS_* in
# spring_drift_check (kept as Literal here to avoid pipeline↔tools import cycles;
# tests assert set-equality against the writer constants).
DriftStatus = Literal[
    "unchanged",
    "confirmed_still_present",
    "drifted",
    "file_deleted",
    "suspected_drift_content_changed_no_rule_to_recheck",
    "unknown_no_prior_signature",
    "config_structure_changed",
    "config_values_only_changed_review_needed",
]


class DriftResultRow(BaseModel):
    """One citation outcome in drift_report.results."""

    model_config = ConfigDict(extra="allow")

    source: str
    file: str | None = None
    line: int | None = None
    rule_id: str | None = None
    match: str | None = None
    status: DriftStatus
    tier: int
    detail: str | None = None


class DriftFileSummary(BaseModel):
    """Tier-1 file classification lists."""

    model_config = ConfigDict(extra="allow")

    unchanged: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)


class DriftBaselineProvenance(BaseModel):
    """Where tier-1 file_signatures came from (signals vs run_manifest)."""

    model_config = ConfigDict(extra="allow")

    source: str
    run_id: str | None = None
    repo_path: str | None = None
    commit_hash: str | None = None
    dirty: bool | None = None


class DriftReportArtifact(BaseModel):
    """drift_report.json — thin operator report from spring_drift_check (L5)."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(ge=1)
    repo_path: str
    prior_scan_repo_path: str | None = None
    file_signatures_baseline: DriftBaselineProvenance | dict[str, Any]
    file_summary: DriftFileSummary | dict[str, Any]
    citations_checked: int
    status_counts: dict[str, int]
    # Typed rows only — union-with-dict would skip DriftStatus checks on free dicts.
    results: list[DriftResultRow]


# Closed metric_kind vocabulary for capacity_preflight_report.json — mirror of
# estimate_stage4_shared_pool_tokens / measure_stage4_shared_pool_tokens writers
# (Literal here avoids pipeline↔tools import cycles; tests assert equality).
Stage4MetricKind = Literal["partial_proxy_pre_stage4", "measured_stage4_inputs"]


class CapacityWarningRow(BaseModel):
    """One threshold warning in capacity_preflight_report.warnings."""

    model_config = ConfigDict(extra="allow")

    dimension: str
    value: Any
    threshold: Any
    message: str


class CapacityPreflightReportArtifact(BaseModel):
    """capacity_preflight_report.json — thin operator report (slice-5 residual).

    Required keys are the intersection of Stage-0 ``compute_preflight`` and
    L2b ``compute_stage4_calibration`` writers (plus ``schema_version``).
    Mode-specific keys (fan-out / slice stats / ``mode`` / proxy comparison)
    ride ``extra="allow"`` — do not invent fields without writers.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(ge=1)
    repo_path: str
    stage4_metric_kind: Stage4MetricKind
    stage4_included_now: list[str]
    stage4_omitted_not_estimated: list[str]
    stage4_shared_pool_upper_bound_est_tokens: int
    stage4_summaries_est_tokens: int
    stage4_interview_answers_est_tokens: int = 0
    stage4_interview_answers_omitted: bool = True
    stage4_signals_est_tokens: int
    stage4_signals_omitted: bool
    stage4_aggregate_input_upper_bound_est_tokens: int
    stage4_return_payloads_estimated: bool
    warnings: list[CapacityWarningRow]


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
