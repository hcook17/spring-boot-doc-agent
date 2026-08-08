"""Finding inventory — adversarial review ingress."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    SPIKE = "spike"


class FindingLink(BaseModel):
    """TraceDev-style edge: finding → path → related test/mutant."""

    kind: str = Field(description="path | test | mutant | arxiv | deepwiki | other")
    target: str
    note: str | None = None


class Finding(BaseModel):
    schema_version: int = 1
    id: str = Field(min_length=1)
    severity: FindingSeverity
    title: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    suggested_fix: str | None = None
    links: list[FindingLink] = Field(default_factory=list)
    source_doc: str | None = None
    epic_hint: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
