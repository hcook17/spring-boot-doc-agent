"""TASKS.md structured SoR — DAG, waves, ledger, blockers."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from stf.schemas.blockers import Blocker


class LedgerState(str, Enum):
    """Magentic-style orchestrator ledger fields."""

    PLAN = "plan"
    PROGRESS = "progress"
    STALL = "stall"
    RESET = "reset"
    DONE = "done"


class TaskBlock(BaseModel):
    id: str
    title: str
    goal: str
    inputs: list[dict[str, str]] = Field(
        default_factory=list,
        description="[{origin, datum}, ...] origin is T<n> | inventory id | new",
    )
    depends: list[str] = Field(default_factory=list)
    gates: list[str] = Field(default_factory=list, description="T0 assumption → gated tasks")
    data_modeling: str = "n/a"
    locate: str = ""
    tests: str = ""
    implement: str = ""
    verify: str = ""
    acceptance: str = ""
    status: str | None = None
    wave: int | None = None


class TasksDocument(BaseModel):
    schema_version: int = 1
    target: str
    source_spec: str
    why_this_order: str = ""
    decisions: list[dict[str, str]] = Field(default_factory=list)
    tasks: list[TaskBlock] = Field(default_factory=list)
    blockers: list[Blocker] = Field(default_factory=list)
    ledger: LedgerState = LedgerState.PLAN
    resume_wave: int = 0
    validation_token: str | None = Field(
        default=None,
        description="2+N SoD: Reviewer issues token; Implement cannot self-approve DONE",
    )
    suite_baseline: dict[str, object] = Field(default_factory=dict)

    def task_map(self) -> dict[str, TaskBlock]:
        return {t.id: t for t in self.tasks}

    def open_blockers(self) -> list[Blocker]:
        from stf.schemas.blockers import BlockerStatus

        return [b for b in self.blockers if b.status == BlockerStatus.OPEN]
