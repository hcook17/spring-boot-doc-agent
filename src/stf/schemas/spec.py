"""SPEC.md structured SoR (JSON) with markdown projection helpers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DataSourceRow(BaseModel):
    id: str
    data_need: str
    origin: str


class SpecDocument(BaseModel):
    schema_version: int = 1
    target: str
    goal: str
    input_kind: str = Field(
        default="feature",
        description="feature | review_remediation | spike",
    )
    requirements: list[str] = Field(default_factory=list)
    inventory: list[DataSourceRow] = Field(default_factory=list)
    critical_assumptions: list[str] = Field(default_factory=list)
    decisions: list[dict[str, str]] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    source_review: str | None = None

    def inventory_ids(self) -> set[str]:
        return {row.id for row in self.inventory}

    def to_markdown(self) -> str:
        lines = [
            f"# SPEC — {self.target}",
            "",
            f"**schema_version:** {self.schema_version}",
            f"**input_kind:** {self.input_kind}",
            "",
            "## Goal",
            "",
            self.goal,
            "",
            "## Requirements",
            "",
        ]
        for r in self.requirements:
            lines.append(f"- {r}")
        lines.extend(["", "## Data-source inventory", "", "| ID | Data need | Origin |", "|---|---|---|"])
        for row in self.inventory:
            lines.append(f"| {row.id} | {row.data_need} | {row.origin} |")
        lines.extend(["", "## Critical assumptions", ""])
        for a in self.critical_assumptions:
            lines.append(f"- {a}")
        if self.decisions:
            lines.extend(["", "## Decisions", "", "| Decision | Blocks | Resolution |", "|---|---|---|"])
            for d in self.decisions:
                lines.append(
                    f"| {d.get('decision', '')} | {d.get('blocks', '')} | {d.get('resolution', '')} |"
                )
        if self.out_of_scope:
            lines.extend(["", "## Out of scope", ""])
            for o in self.out_of_scope:
                lines.append(f"- {o}")
        if self.finding_ids:
            lines.extend(["", "## Seeded findings", ""])
            for fid in self.finding_ids:
                lines.append(f"- `{fid}`")
        if self.source_review:
            lines.extend(["", f"**Source review:** `{self.source_review}`", ""])
        return "\n".join(lines) + "\n"
