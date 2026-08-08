"""Architecture/testing review artifact DTOs.

No ``from __future__ import annotations`` — field types reference StrEnums from
``vocab`` and must resolve at class-body time for Pydantic.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel

from doc_engine.pipeline.artifacts.vocab import (
    ResearchTiers,
    ResearchVerdict,
    ReviewLens,
    ReviewSeverity,
)


class ReviewEvidenceAnchor(BaseModel):
    model_config = ConfigDict(extra="allow")

    line: int = Field(ge=1)
    what: str = Field(min_length=1)
    file: str | None = None


class ReviewResearchSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    tier: ResearchTiers
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
