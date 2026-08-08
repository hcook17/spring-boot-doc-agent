"""ADR-005 blocker records."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class BlockerClass(str, Enum):
    INVENTORY_DRIFT = "inventory-drift"
    DECISION = "decision"
    ASSUMPTION = "assumption"
    DAG_COLLISION = "dag-collision"


class BlockerStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class Blocker(BaseModel):
    schema_version: int = 1
    id: str
    title: str
    status: BlockerStatus = BlockerStatus.OPEN
    falsified: str
    evidence: str
    class_: BlockerClass = Field(alias="class")
    blast_radius_tasks: list[str] = Field(default_factory=list)
    blast_radius_inventory: list[str] = Field(default_factory=list)
    resume_wave: int = 0
    resolved_by: str | None = None
    resolved_date: str | None = None

    model_config = {"populate_by_name": True}
