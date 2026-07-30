"""Compliance profiles, gate checklists, and certification.json emission."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from doc_engine.pipeline.context import StageKind, StageSpec


class ComplianceProfile(StrEnum):
    SCAN_ONLY = "scan_only"
    DETERMINISTIC_ONLY = "deterministic_only"
    CERTIFIED = "certified"


SCAN_ONLY_GATE_ID = "validate_artifacts_spring_signals"
DETERMINISTIC_ONLY_GATE_ID = "validate_artifacts_all"

CERTIFIED_GATE_IDS = frozenset({
    "validate_artifacts_all",
    "pipeline_validators",
    "check_pipeline_output",
    "citation_coverage",
    "check_no_secrets_leaked",
    "test_pipeline_stages",
})


def gates_required_for_profile(profile: ComplianceProfile) -> frozenset[str]:
    """Return stable gate IDs required for certification under a profile."""
    if profile == ComplianceProfile.SCAN_ONLY:
        return frozenset({SCAN_ONLY_GATE_ID})
    if profile == ComplianceProfile.DETERMINISTIC_ONLY:
        return frozenset({DETERMINISTIC_ONLY_GATE_ID})
    return CERTIFIED_GATE_IDS


GenerativeExecutor = Literal["none", "mock", "live"]


class StageRecord(BaseModel):
    name: str
    status: Literal["ok", "fail", "skipped"]
    detail: str = ""


class GateRecord(BaseModel):
    id: str
    label: str
    status: Literal["ok", "fail", "skipped"]
    required: bool = True
    detail: str = ""


class CertificationReport(BaseModel):
    schema_version: int = 1
    compliance_profile: str
    certified: bool
    repo_path: str
    out_dir: str
    timestamp: str
    generative_executor: GenerativeExecutor = "none"
    profile_gate_ids: list[str] = Field(default_factory=list)
    stages: list[StageRecord] = Field(default_factory=list)
    gates: list[GateRecord] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


def resolve_compliance_profile(
    config: Any,
    args: Any,
) -> ComplianceProfile:
    """Merge CLI flags and repo config into one compliance profile."""
    explicit = getattr(args, "compliance_profile", None)
    if explicit:
        return ComplianceProfile(explicit)
    if getattr(args, "deterministic_only", False):
        return ComplianceProfile.DETERMINISTIC_ONLY
    if config is not None:
        profile = config.compliance_profile
        if isinstance(profile, ComplianceProfile):
            return profile
        return ComplianceProfile(profile)
    return ComplianceProfile.CERTIFIED


def stages_for_profile(
    profile: ComplianceProfile,
    all_specs: list[StageSpec],
    *,
    skip_signal_scan: bool = False,
    until_stage: str | None = None,
) -> list[StageSpec]:
    """Return the stage graph subset required by a compliance profile.

    If ``until_stage`` is set, truncate after that stage name (inclusive).
    Stage names come from ``build_stage_specs()`` — the single SoT for the graph.
    """
    if profile == ComplianceProfile.CERTIFIED:
        specs = list(all_specs)
    elif profile == ComplianceProfile.DETERMINISTIC_ONLY:
        specs = [s for s in all_specs if s.kind == StageKind.DETERMINISTIC]
    else:
        allowed = {"init_manifest", "signal_scan"}
        specs = [s for s in all_specs if s.name in allowed]

    if skip_signal_scan:
        specs = [s for s in specs if s.name != "signal_scan"]

    if until_stage:
        names = [s.name for s in specs]
        if until_stage not in names:
            known = ", ".join(s.name for s in all_specs)
            raise ValueError(
                f"unknown --until stage {until_stage!r}; "
                f"known stage names: {known}"
            )
        cut = names.index(until_stage) + 1
        specs = specs[:cut]
    return specs


def _stage_status_from_runner(status: str) -> Literal["ok", "fail", "skipped"]:
    if status in ("OK", "MOCK"):
        return "ok"
    if status == "SKIPPED":
        return "skipped"
    return "fail"


def build_certification_report(
    profile: ComplianceProfile,
    repo_path: str,
    out_dir: str,
    stages: list[StageRecord],
    gates: list[GateRecord],
    generative_executor: GenerativeExecutor = "none",
) -> CertificationReport:
    """Assemble certification.json from stage and gate audit records.

    ``certified`` is true only when every stage is ok *and* every gate id
    required by ``profile`` is present with status ok. An empty gate list
    therefore cannot certify — that was a vacuity hole (profile_gate_ids
    listed requirements the audit never satisfied).
    """
    failures: list[str] = []
    for stage in stages:
        if stage.status != "ok":
            failures.append(f"stage:{stage.name}:{stage.status}")
    by_id = {gate.id: gate for gate in gates}
    for gate in gates:
        if gate.required and gate.status != "ok":
            failures.append(f"gate:{gate.id}:{gate.status}")
    required_ids = gates_required_for_profile(profile)
    for gate_id in sorted(required_ids):
        if gate_id not in by_id:
            failures.append(f"gate:{gate_id}:missing")

    return CertificationReport(
        compliance_profile=profile.value,
        certified=len(failures) == 0,
        repo_path=repo_path,
        out_dir=out_dir,
        timestamp=datetime.now(timezone.utc).isoformat(),
        generative_executor=generative_executor,
        profile_gate_ids=sorted(required_ids),
        stages=stages,
        gates=gates,
        failures=failures,
    )


def write_certification_json(out_dir: str | Path, report: CertificationReport) -> Path:
    """Write certification.json into the run artifact directory."""
    path = Path(out_dir) / "certification.json"
    path.write_text(
        json.dumps(report.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def stage_records_from_runner_results(
    results: list[tuple[str, str, float, str]],
    prefix: str = "pipeline:",
) -> list[StageRecord]:
    """Convert Runner.results entries for pipeline stages into StageRecords."""
    records: list[StageRecord] = []
    for label, status, _seconds, detail in results:
        if not label.startswith(prefix):
            continue
        name = label[len(prefix):]
        records.append(
            StageRecord(
                name=name,
                status=_stage_status_from_runner(status),
                detail=detail,
            )
        )
    return records
