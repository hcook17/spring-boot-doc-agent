"""Spring signals + file-summary artifact DTOs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

VALID_SPRING_ROLES = frozenset({
    "controller", "service", "repository", "entity", "config", "security",
    "messaging-producer", "messaging-consumer", "test", "other",
})


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
