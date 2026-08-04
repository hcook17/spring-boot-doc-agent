"""Shared certification fixture helpers for profile-complete stage lists."""

from __future__ import annotations

from doc_engine.pipeline.compliance import (
    GENERATIVE_EXTERNAL_STAGE,
    ComplianceProfile,
    StageRecord,
    deterministic_stage_names,
    generative_stage_names,
    required_stage_names_for_profile,
)


def ok_stages_for(
    profile: ComplianceProfile,
    *,
    generative_executor: str = "none",
) -> list[StageRecord]:
    """One ok StageRecord per required profile stage (omit-none).

    For ``generative_executor=live``, record deterministic required stages plus
    ``generative_external`` (live rewrite shape) instead of each generative name.
    """
    required = required_stage_names_for_profile(profile)
    if generative_executor == "live":
        det = deterministic_stage_names()
        stages = [
            StageRecord(name=n, status="ok")
            for n in sorted(required & det)
        ]
        if profile == ComplianceProfile.CERTIFIED:
            stages.append(
                StageRecord(
                    name=GENERATIVE_EXTERNAL_STAGE,
                    status="ok",
                    executor="live",
                    detail="test fixture live external",
                )
            )
        return stages
    return [StageRecord(name=n, status="ok") for n in sorted(required)]


def ok_det_stages_for(profile: ComplianceProfile) -> list[StageRecord]:
    """Deterministic required stages only (prior for live_gates rewrite)."""
    required = required_stage_names_for_profile(profile)
    det = deterministic_stage_names()
    return [StageRecord(name=n, status="ok") for n in sorted(required & det)]
