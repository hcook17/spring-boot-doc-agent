"""Facts ledger artifact DTOs (Phase 1 dual-emit SoR)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

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
