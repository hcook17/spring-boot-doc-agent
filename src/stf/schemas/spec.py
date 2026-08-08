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

    def _markdown_header(self) -> list[str]:
        return [
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

    def _markdown_requirements(self) -> list[str]:
        return [f"- {r}" for r in self.requirements]

    def _markdown_inventory(self) -> list[str]:
        lines = ["", "## Data-source inventory", "", "| ID | Data need | Origin |", "|---|---|---|"]
        for row in self.inventory:
            lines.append(f"| {row.id} | {row.data_need} | {row.origin} |")
        return lines

    def _markdown_assumptions(self) -> list[str]:
        lines = ["", "## Critical assumptions", ""]
        lines.extend(f"- {a}" for a in self.critical_assumptions)
        return lines

    def _markdown_decisions(self) -> list[str]:
        if not self.decisions:
            return []
        lines = ["", "## Decisions", "", "| Decision | Blocks | Resolution |", "|---|---|---|"]
        for d in self.decisions:
            lines.append(
                f"| {d.get('decision', '')} | {d.get('blocks', '')} | {d.get('resolution', '')} |"
            )
        return lines

    def _markdown_out_of_scope(self) -> list[str]:
        if not self.out_of_scope:
            return []
        return ["", "## Out of scope", ""] + [f"- {o}" for o in self.out_of_scope]

    def _markdown_findings(self) -> list[str]:
        if not self.finding_ids:
            return []
        return ["", "## Seeded findings", ""] + [f"- `{fid}`" for fid in self.finding_ids]

    def _markdown_source_review(self) -> list[str]:
        if not self.source_review:
            return []
        return ["", f"**Source review:** `{self.source_review}`", ""]

    def _markdown_optional_sections(self) -> list[str]:
        lines: list[str] = []
        lines.extend(self._markdown_out_of_scope())
        lines.extend(self._markdown_findings())
        lines.extend(self._markdown_source_review())
        return lines

    def to_markdown(self) -> str:
        lines = self._markdown_header()
        lines.extend(self._markdown_requirements())
        lines.extend(self._markdown_inventory())
        lines.extend(self._markdown_assumptions())
        lines.extend(self._markdown_decisions())
        lines.extend(self._markdown_optional_sections())
        return "\n".join(lines) + "\n"
