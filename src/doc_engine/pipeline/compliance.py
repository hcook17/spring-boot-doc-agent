"""Compliance profiles, gate checklists, and certification.json emission.

``certification.json`` is a **derived view** over stage/gate facts: only
``build_certification_report`` (in ``certification_fold``) computes
``certified`` / ``failures``. ``completeness_claim`` is always
``fold_of_recorded_rows`` â€” the bit is not Stage-0 covering / gap
measurement / doc quality. See
``claude/research/certification-derived-view-2026-07-30.md`` and
``docs/design/ddia-north-star/deviations/dev-certification-derived-view.md``.

This module owns the SoR-ish profile/config surface (enums, record models,
required-stage/gate helpers, writers). The fold assembler lives in
``certification_fold`` and is re-exported here for a stable import path.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from doc_engine._compat import StrEnum
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

# Synthetic stage row written by live_gates derivation (not in build_stage_specs).
GENERATIVE_EXTERNAL_STAGE = "generative_external"

CERTIFICATION_SCHEMA_VERSION = 1


def gates_required_for_profile(profile: ComplianceProfile) -> frozenset[str]:
    """Return stable gate IDs required for certification under a profile."""
    if profile == ComplianceProfile.SCAN_ONLY:
        return frozenset({SCAN_ONLY_GATE_ID})
    if profile == ComplianceProfile.DETERMINISTIC_ONLY:
        return frozenset({DETERMINISTIC_ONLY_GATE_ID})
    return CERTIFIED_GATE_IDS


class GenerativeExecutor(StrEnum):
    """How generative stages were executed for this certification fold."""

    NONE = "none"
    MOCK = "mock"
    LIVE = "live"


class StageExecutorKind(StrEnum):
    """Per-stage executor stamp on StageRecord (not the StageExecutor Protocol)."""

    DETERMINISTIC = "deterministic"
    NONE = "none"
    MOCK = "mock"
    LIVE = "live"


class RecordStatus(StrEnum):
    """Normalized ok/fail/skipped on certification stage and gate rows."""

    OK = "ok"
    FAIL = "fail"
    SKIPPED = "skipped"


class StageRecord(BaseModel):
    name: str
    status: RecordStatus
    detail: str = ""
    executor: StageExecutorKind = StageExecutorKind.DETERMINISTIC


class GateRecord(BaseModel):
    id: str
    label: str
    status: RecordStatus
    required: bool = True
    detail: str = ""


class CertificationReport(BaseModel):
    schema_version: int = CERTIFICATION_SCHEMA_VERSION
    compliance_profile: str
    certified: bool
    repo_path: str
    out_dir: str
    timestamp: str
    generative_executor: GenerativeExecutor = GenerativeExecutor.NONE
    # Bare-minimum honesty: certified is a fold over recorded stage/gate rows,
    # not Stage-0 covering / gap_probe / doc-quality completeness.
    completeness_claim: Literal["fold_of_recorded_rows"] = "fold_of_recorded_rows"
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


def citations_are_strict(
    profile: ComplianceProfile,
    *,
    force_strict: bool = False,
) -> bool:
    """Whether citation_coverage findings should fail the run.

    Same rule as ``local_runner``: certified profile always strict; otherwise
    only when the caller passes ``--strict-citations``.
    """
    return profile == ComplianceProfile.CERTIFIED or force_strict


def _specs_for_profile(profile: ComplianceProfile, all_specs: list[StageSpec]) -> list[StageSpec]:
    """Select the stage subset for a compliance profile (before filters)."""
    if profile == ComplianceProfile.CERTIFIED:
        return list(all_specs)
    if profile == ComplianceProfile.DETERMINISTIC_ONLY:
        return [spec for spec in all_specs if spec.kind == StageKind.DETERMINISTIC]
    return _scan_only_specs(all_specs)


def _scan_only_specs(all_specs: list[StageSpec]) -> list[StageSpec]:
    """Stages allowed under the scan_only compliance profile."""
    allowed = {"init_manifest", "signal_scan"}
    return [spec for spec in all_specs if spec.name in allowed]


def _truncate_until_stage(
    specs: list[StageSpec],
    until_stage: str,
    all_specs: list[StageSpec],
) -> list[StageSpec]:
    """Keep stages through *until_stage* inclusive; raise on unknown name."""
    names = [spec.name for spec in specs]
    if until_stage not in names:
        known = ", ".join(spec.name for spec in all_specs)
        raise ValueError(
            f"unknown --until stage {until_stage!r}; "
            f"known stage names: {known}"
        )
    cut = names.index(until_stage) + 1
    return specs[:cut]


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
    specs = _specs_for_profile(profile, all_specs)
    if skip_signal_scan:
        specs = [spec for spec in specs if spec.name != "signal_scan"]
    if until_stage:
        specs = _truncate_until_stage(specs, until_stage, all_specs)
    return specs


@lru_cache(maxsize=1)
def deterministic_stage_names() -> frozenset[str]:
    """Names of StageKind.DETERMINISTIC stages from ``build_stage_specs()``."""
    from doc_engine.pipeline.stages import build_stage_specs

    return frozenset(
        spec.name
        for spec in build_stage_specs()
        if spec.kind == StageKind.DETERMINISTIC
    )


@lru_cache(maxsize=1)
def generative_stage_names() -> frozenset[str]:
    """Names of StageKind.GENERATIVE stages from ``build_stage_specs()``."""
    from doc_engine.pipeline.stages import build_stage_specs

    return frozenset(
        spec.name for spec in build_stage_specs() if spec.kind == StageKind.GENERATIVE
    )


def required_stage_names_for_profile(profile: ComplianceProfile) -> frozenset[str]:
    """Stage names the profile expects to have run (skips of these fail cert)."""
    from doc_engine.pipeline.stages import build_stage_specs

    return frozenset(
        spec.name for spec in stages_for_profile(profile, build_stage_specs())
    )


def _stage_status_from_runner(status: str) -> RecordStatus:
    if status in ("OK", "MOCK"):
        return RecordStatus.OK
    if status == "SKIPPED":
        return RecordStatus.SKIPPED
    return RecordStatus.FAIL


def _skipped_stage_executor(stage_name: str) -> StageExecutorKind:
    """Executor stamp for a SKIPPED runner stage row."""
    if stage_name in generative_stage_names():
        return StageExecutorKind.NONE
    return StageExecutorKind.DETERMINISTIC


def _generative_stage_executor(status: str) -> StageExecutorKind:
    """Executor stamp for a non-skipped generative stage."""
    # OK without MOCK ⇒ non-mock generative adapter (live-in-runner).
    # Fail/error must not be labelled live.
    if status == "OK":
        return StageExecutorKind.LIVE
    return StageExecutorKind.NONE


def _stage_executor_from_runner(
    status: str,
    stage_name: str,
) -> StageExecutorKind:
    """Preserve mock-ness; classify OK stages by graph kind."""
    if status == "MOCK":
        return StageExecutorKind.MOCK
    if status == "SKIPPED":
        return _skipped_stage_executor(stage_name)
    if stage_name not in generative_stage_names():
        return StageExecutorKind.DETERMINISTIC
    return _generative_stage_executor(status)


def write_certification_json(out_dir: str | Path, report: CertificationReport) -> Path:
    """Write certification.json into the run artifact directory."""
    path = Path(out_dir) / "certification.json"
    path.write_text(
        json.dumps(report.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _should_drop_prior_stage(
    stage: StageRecord,
    deterministic_names: frozenset[str],
    generative_names: frozenset[str],
) -> bool:
    """True when a prior stage row must not survive a live gates rewrite."""
    if stage.name in generative_names or stage.name == GENERATIVE_EXTERNAL_STAGE:
        return True
    if stage.executor in (StageExecutorKind.MOCK, StageExecutorKind.LIVE):
        return True
    if (
        stage.name not in deterministic_names
        and stage.executor != StageExecutorKind.DETERMINISTIC
    ):
        return True
    return False


def _normalize_kept_prior_stage(
    stage: StageRecord,
    deterministic_names: frozenset[str],
) -> StageRecord | None:
    """Return a kept prior row (deterministic-labelled), or None to drop."""
    if stage.name in deterministic_names:
        if stage.executor != StageExecutorKind.DETERMINISTIC:
            return stage.model_copy(
                update={"executor": StageExecutorKind.DETERMINISTIC}
            )
        return stage
    if stage.executor == StageExecutorKind.DETERMINISTIC:
        # Non-graph deterministic-labelled row (unusual); keep as-is.
        return stage
    return None


def stages_for_live_certification(prior: list[StageRecord]) -> list[StageRecord]:
    """Derive stage facts for a live gates rewrite (not a LWW merge).

    Keep deterministic prior rows; drop generative history (including legacy v1
    rows that default ``executor=deterministic``); append ``generative_external``.
    """
    deterministic_names = deterministic_stage_names()
    generative_names = generative_stage_names()
    kept: list[StageRecord] = []
    for stage in prior:
        if _should_drop_prior_stage(stage, deterministic_names, generative_names):
            continue
        normalized = _normalize_kept_prior_stage(stage, deterministic_names)
        if normalized is not None:
            kept.append(normalized)
    kept.append(
        StageRecord(
            name=GENERATIVE_EXTERNAL_STAGE,
            status=RecordStatus.OK,
            executor=StageExecutorKind.LIVE,
            detail="docs produced outside PipelineRunner; proven by live gates",
        )
    )
    return kept


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
                executor=_stage_executor_from_runner(status, name),
            )
        )
    return records


# Late import: fold module depends on types/helpers above; re-export keeps
# `from doc_engine.pipeline.compliance import build_certification_report` stable.
from doc_engine.pipeline.certification_fold import (  # noqa: E402, F401
    build_certification_report,
)
