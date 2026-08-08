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

_LIVE_SKIPPED_PYTEST_GATE = "test_pipeline_stages"


def _stage_status_failures(
    stage: StageRecord,
    required_stages: frozenset[str],
) -> list[str]:
    """Fail/skip fold failures for one recorded stage row."""
    if stage.status == RecordStatus.FAIL:
        return [f"stage:{stage.name}:{stage.status}"]
    if stage.status == RecordStatus.SKIPPED and stage.name in required_stages:
        return [f"stage:{stage.name}:skipped"]
    return []


def _mock_under_live_failure(
    stage: StageRecord,
    generative_executor: GenerativeExecutor,
) -> str | None:
    """Reject mock executor stamps when the fold claims a live run."""
    if generative_executor != GenerativeExecutor.LIVE:
        return None
    if stage.executor != StageExecutorKind.MOCK:
        return None
    return f"stage:{stage.name}:mock_under_live"


def _stage_fold_failures(
    stages: list[StageRecord],
    required_stages: frozenset[str],
    generative_executor: GenerativeExecutor,
) -> list[str]:
    """Failures from recorded stage rows (fail / required skip / mock-under-live)."""
    failures: list[str] = []
    for stage in stages:
        failures.extend(_stage_status_failures(stage, required_stages))
        mock_failure = _mock_under_live_failure(stage, generative_executor)
        if mock_failure is not None:
            failures.append(mock_failure)
    return failures


def _append_unique(failures: list[str], failure: str) -> None:
    if failure not in failures:
        failures.append(failure)


def _recorded_required_gate_failures(gates: list[GateRecord]) -> list[str]:
    """Failures for gates already present that are required but not ok."""
    return [
        f"gate:{gate.id}:{gate.status}"
        for gate in gates
        if gate.required and gate.status != RecordStatus.OK
    ]


def _skip_live_pytest_gate(
    gate_id: str,
    generative_executor: GenerativeExecutor,
) -> bool:
    """True when live gates intentionally omit the pytest profile gate."""
    return (
        generative_executor == GenerativeExecutor.LIVE
        and gate_id == _LIVE_SKIPPED_PYTEST_GATE
    )


def _profile_gate_id_failure(
    gate_id: str,
    gate: GateRecord | None,
    existing_failures: list[str],
) -> str | None:
    """One profile-required gate failure, or None when the gate is ok."""
    if gate is None:
        return f"gate:{gate_id}:missing"
    if not gate.required:
        # Presence alone is not enough — required=False forges the fold.
        return f"gate:{gate_id}:not_required"
    if gate.status == RecordStatus.OK:
        return None
    # May already be recorded by _recorded_required_gate_failures;
    # keep explicit so profile-required ids stay complete if that loop
    # is ever narrowed.
    failure = f"gate:{gate_id}:{gate.status}"
    if failure in existing_failures:
        return None
    return failure


def _profile_gate_fold_failures(
    gates_by_id: dict[str, GateRecord],
    required_ids: frozenset[str],
    generative_executor: GenerativeExecutor,
    existing_failures: list[str],
) -> list[str]:
    """Failures for profile-required gate ids (missing / not_required / not ok)."""
    failures: list[str] = []
    for gate_id in sorted(required_ids):
        if _skip_live_pytest_gate(gate_id, generative_executor):
            continue
        failure = _profile_gate_id_failure(
            gate_id, gates_by_id.get(gate_id), existing_failures
        )
        if failure is not None:
            _append_unique(failures, failure)
    return failures


def _gate_fold_failures(
    gates: list[GateRecord],
    required_ids: frozenset[str],
    generative_executor: GenerativeExecutor,
) -> list[str]:
    """Failures from gate rows and profile-required gate ids."""
    failures = _recorded_required_gate_failures(gates)
    gates_by_id = {gate.id: gate for gate in gates}
    failures.extend(
        _profile_gate_fold_failures(
            gates_by_id, required_ids, generative_executor, failures,
        ),
    )
    return failures


def _live_external_covers_generative(stages: list[StageRecord]) -> bool:
    """True when generative_external OK stands in for missing generative stages."""
    return any(
        stage.name == GENERATIVE_EXTERNAL_STAGE and stage.status == RecordStatus.OK
        for stage in stages
    )


def _is_covered_missing_stage(
    name: str,
    recorded: set[str],
    generative_names: frozenset[str],
    live_external_ok: bool,
) -> bool:
    """True when a required stage name is already accounted for."""
    if name in recorded:
        return True
    return live_external_ok and name in generative_names


def _missing_required_stage_failures(
    stages: list[StageRecord],
    required_stages: frozenset[str],
    generative_executor: GenerativeExecutor,
) -> list[str]:
    """Omission ≠ success: required stages never recorded fail the fold."""
    failures: list[str] = []
    recorded = {stage.name for stage in stages}
    generative_names = generative_stage_names()
    live_external_ok = (
        generative_executor == GenerativeExecutor.LIVE
        and _live_external_covers_generative(stages)
    )
    for name in sorted(required_stages):
        if _is_covered_missing_stage(
            name, recorded, generative_names, live_external_ok
        ):
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
