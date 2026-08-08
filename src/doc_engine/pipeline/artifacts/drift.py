"""Drift-report artifact DTOs."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Closed status vocabulary for drift_report.json — mirror of STATUS_* in
# spring_drift_check (kept as Literal here to avoid pipeline↔tools import cycles;
# tests assert set-equality against the writer constants).
DriftStatus = Literal[
    "unchanged",
    "confirmed_still_present",
    "drifted",
    "file_deleted",
    "suspected_drift_content_changed_no_rule_to_recheck",
    "unknown_no_prior_signature",
    "config_structure_changed",
    "config_values_only_changed_review_needed",
]


class DriftResultRow(BaseModel):
    """One citation outcome in drift_report.results."""

    model_config = ConfigDict(extra="allow")

    source: str
    file: str | None = None
    line: int | None = None
    rule_id: str | None = None
    match: str | None = None
    status: DriftStatus
    tier: int
    detail: str | None = None


class DriftFileSummary(BaseModel):
    """Tier-1 file classification lists."""

    model_config = ConfigDict(extra="allow")

    unchanged: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)


class DriftBaselineProvenance(BaseModel):
    """Where tier-1 file_signatures came from (signals vs run_manifest)."""

    model_config = ConfigDict(extra="allow")

    source: str
    run_id: str | None = None
    repo_path: str | None = None
    commit_hash: str | None = None
    dirty: bool | None = None


class DriftReportArtifact(BaseModel):
    """drift_report.json — thin operator report from spring_drift_check (L5)."""

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(ge=1)
    repo_path: str
    prior_scan_repo_path: str | None = None
    file_signatures_baseline: DriftBaselineProvenance | dict[str, Any]
    file_summary: DriftFileSummary | dict[str, Any]
    citations_checked: int
    status_counts: dict[str, int]
    # Typed rows only — union-with-dict would skip DriftStatus checks on free dicts.
    results: list[DriftResultRow]
