"""Typed boundary objects for inter-stage JSON artifacts (Fowler DTOs)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

VALID_SPRING_ROLES = frozenset({
    "controller", "service", "repository", "entity", "config", "security",
    "messaging-producer", "messaging-consumer", "test", "other",
})

InterviewStatus = Literal["answered", "skipped"]


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


ARTIFACT_MODELS: dict[str, type[BaseModel]] = {
    "spring_signals": SpringSignalsArtifact,
    "groups": GroupsArtifact,
    "summaries": SummariesArtifact,
    "interview_answers": InterviewAnswersArtifact,
}

ARTIFACT_FILENAMES: dict[str, str] = {
    "spring_signals": "spring_signals.json",
    "groups": "groups.json",
    "summaries": "summaries.json",
    "interview_answers": "interview_answers.json",
}


def export_json_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schema dicts for each artifact type."""
    schemas: dict[str, dict[str, Any]] = {}
    for name, model in ARTIFACT_MODELS.items():
        schemas[name] = model.model_json_schema()
    return schemas
