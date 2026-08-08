"""Capacity-preflight artifact DTOs."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Closed metric_kind vocabulary for capacity_preflight_report.json — mirror of
# estimate_stage4_shared_pool_tokens / measure_stage4_shared_pool_tokens writers
# (Literal here avoids pipeline↔tools import cycles; tests assert equality).
Stage4MetricKind = Literal["partial_proxy_pre_stage4", "measured_stage4_inputs"]


class CapacityWarningRow(BaseModel):
    """One threshold warning in capacity_preflight_report.warnings."""

    model_config = ConfigDict(extra="allow")

    dimension: str
    value: Any
    threshold: Any
    message: str


class CapacityPreflightReportArtifact(BaseModel):
    """capacity_preflight_report.json — thin operator report (slice-5 residual).

    Required keys are the intersection of Stage-0 ``compute_preflight`` and
    L2b ``compute_stage4_calibration`` writers (plus ``schema_version``).
    Mode-specific keys (fan-out / slice stats / ``mode`` / proxy comparison)
    ride ``extra="allow"`` — do not invent fields without writers.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(ge=1)
    repo_path: str
    stage4_metric_kind: Stage4MetricKind
    stage4_included_now: list[str]
    stage4_omitted_not_estimated: list[str]
    stage4_shared_pool_upper_bound_est_tokens: int
    stage4_summaries_est_tokens: int
    stage4_interview_answers_est_tokens: int = 0
    stage4_interview_answers_omitted: bool = True
    stage4_signals_est_tokens: int
    stage4_signals_omitted: bool
    stage4_aggregate_input_upper_bound_est_tokens: int
    stage4_return_payloads_estimated: bool
    warnings: list[CapacityWarningRow]
