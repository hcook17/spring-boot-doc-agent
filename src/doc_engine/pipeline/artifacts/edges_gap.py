"""Cross-group edges and gap-questions artifact DTOs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from doc_engine.tools.doc_tag_utils import VALID_DOC_FILES


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
