"""Derived-view fold: certification.json from stage/gate SoR rows.

``certification.json`` is recomputed here — never LWW-merged with pipeline
facts. See ``docs/design/ddia-north-star/deviations/dev-certification-derived-view.md``
and domains/01 SoR vs derived.
"""

from __future__ import annotations

from datetime import datetime, timezone

from doc_engine.pipeline.compliance import (
    CERTIFICATION_SCHEMA_VERSION,
    GENERATIVE_EXTERNAL_STAGE,
    CertificationReport,
    ComplianceProfile,
    GateRecord,
    GenerativeExecutor,
    RecordStatus,
    StageExecutorKind,
    StageRecord,
    gates_required_for_profile,
    generative_stage_names,
    required_stage_names_for_profile,
)


def _stage_fold_failures(
    stages: list[StageRecord],
    required_stages: frozenset[str],
    generative_executor: GenerativeExecutor,
) -> list[str]:
    """Failures from recorded stage rows (fail / required skip / mock-under-live)."""
    failures: list[str] = []
    for stage in stages:
        if stage.status == RecordStatus.FAIL:
            failures.append(f"stage:{stage.name}:{stage.status}")
        elif stage.status == RecordStatus.SKIPPED and stage.name in required_stages:
            failures.append(f"stage:{stage.name}:skipped")
        if (
            generative_executor == GenerativeExecutor.LIVE
            and stage.executor == StageExecutorKind.MOCK
        ):
            failures.append(f"stage:{stage.name}:mock_under_live")
    return failures


def _gate_fold_failures(
    gates: list[GateRecord],
    required_ids: frozenset[str],
    generative_executor: GenerativeExecutor,
) -> list[str]:
    """Failures from gate rows and profile-required gate ids."""
    failures: list[str] = []
    by_id = {gate.id: gate for gate in gates}
    for gate in gates:
        if gate.required and gate.status != RecordStatus.OK:
            failures.append(f"gate:{gate.id}:{gate.status}")
    for gate_id in sorted(required_ids):
        # Live gates intentionally do not rerun pytest; the skipped gate is
        # recorded separately with required=False. Treating it as a missing or
        # not-required profile gate would make the live path self-fail.
        if (
            generative_executor == GenerativeExecutor.LIVE
            and gate_id == "test_pipeline_stages"
        ):
            continue
        gate = by_id.get(gate_id)
        if gate is None:
            failures.append(f"gate:{gate_id}:missing")
        elif not gate.required:
            # Presence alone is not enough — required=False forges the fold.
            failures.append(f"gate:{gate_id}:not_required")
        elif gate.status != RecordStatus.OK:
            # Already recorded above when required=True; keep explicit for
            # profile-required ids so the failure list is complete if the
            # earlier loop is ever narrowed.
            if f"gate:{gate_id}:{gate.status}" not in failures:
                failures.append(f"gate:{gate_id}:{gate.status}")
    return failures


def _missing_required_stage_failures(
    stages: list[StageRecord],
    required_stages: frozenset[str],
    generative_executor: GenerativeExecutor,
) -> list[str]:
    """Omission ≠ success: required stages never recorded fail the fold."""
    failures: list[str] = []
    recorded = {stage.name for stage in stages}
    generative_names = generative_stage_names()
    live_external_ok = generative_executor == GenerativeExecutor.LIVE and any(
        stage.name == GENERATIVE_EXTERNAL_STAGE and stage.status == RecordStatus.OK
        for stage in stages
    )
    for name in sorted(required_stages):
        if name in recorded:
            continue
        if live_external_ok and name in generative_names:
            continue
        failures.append(f"stage:{name}:missing")
    return failures


def build_certification_report(
    profile: ComplianceProfile,
    repo_path: str,
    out_dir: str,
    stages: list[StageRecord],
    gates: list[GateRecord],
    generative_executor: GenerativeExecutor = GenerativeExecutor.NONE,
    *,
    allow_mock: bool = False,
) -> CertificationReport:
    """Assemble certification.json from stage and gate audit records.

    ``certified`` is true only when the fold rules pass over **recorded**
    stage/gate rows (fails, required skips, gate failures/missings,
    mock-under-live, CERTIFIED+mock/none without ``allow_mock``). It is
    **not** Stage-0 covering / gap_probe / doc-quality completeness — see
    ``completeness_claim: fold_of_recorded_rows``.
    An empty gate list cannot certify when the profile lists required gates.
    """
    required_stages = required_stage_names_for_profile(profile)
    required_ids = gates_required_for_profile(profile)
    failures: list[str] = []
    failures.extend(_stage_fold_failures(stages, required_stages, generative_executor))
    failures.extend(_gate_fold_failures(gates, required_ids, generative_executor))
    failures.extend(
        _missing_required_stage_failures(stages, required_stages, generative_executor),
    )

    # CERTIFIED + mock/none is not a live adoption fold unless allow_mock.
    if (
        profile == ComplianceProfile.CERTIFIED
        and generative_executor in (GenerativeExecutor.NONE, GenerativeExecutor.MOCK)
        and not allow_mock
    ):
        failures.append(f"generative_executor:{generative_executor}:allow_mock_required")

    return CertificationReport(
        schema_version=CERTIFICATION_SCHEMA_VERSION,
        compliance_profile=profile.value,
        certified=len(failures) == 0,
        repo_path=repo_path,
        out_dir=out_dir,
        timestamp=datetime.now(timezone.utc).isoformat(),
        generative_executor=generative_executor,
        completeness_claim="fold_of_recorded_rows",
        profile_gate_ids=sorted(required_ids),
        stages=stages,
        gates=gates,
        failures=failures,
    )
