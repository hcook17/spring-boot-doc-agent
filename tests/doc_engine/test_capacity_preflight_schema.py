"""Slice-5 thin capacity_preflight_report schema contracts.

Characterization fixture freezes the Stage-0 / L2b writer intersection;
contract tests require schema_version, closed stage4_metric_kind vocabulary,
registry, and validate_artifact_file bite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES, ARTIFACT_MODELS
from doc_engine.pipeline.validation import ArtifactValidationError, validate_artifact_file
from doc_engine.tools import capacity_preflight

STAGE4_METRIC_KINDS = frozenset({
    "partial_proxy_pre_stage4",
    "measured_stage4_inputs",
})

# Intersection of Stage-0 compute_preflight and L2b compute_stage4_calibration
# root keys (before schema_version), plus the shared stage4_* pool fields.
_LEGACY_SHARED_ROOT_KEYS = frozenset({
    "repo_path",
    "stage4_metric_kind",
    "stage4_included_now",
    "stage4_omitted_not_estimated",
    "stage4_shared_pool_upper_bound_est_tokens",
    "stage4_summaries_est_tokens",
    "stage4_interview_answers_est_tokens",
    "stage4_interview_answers_omitted",
    "stage4_signals_est_tokens",
    "stage4_signals_omitted",
    "stage4_aggregate_input_upper_bound_est_tokens",
    "stage4_return_payloads_estimated",
    "warnings",
})


def characterization_stage0_report(*, with_schema_version: bool = False) -> dict:
    """Minimal synthetic Stage-0 report matching today's compute_preflight shape."""
    report = {
        "repo_path": "/tmp/example-repo",
        "num_groups": 2,
        "max_tokens_per_group": 120000,
        "stage_fanout": {
            "stage1_file_summarizer": 2,
            "stage2_architect_segment": 2,
            "stage2_architect_merge": 1,
            "stage3_gap_analyzer": 1,
            "stage3_software_architect_and_testing": 1,
            "stage4_doc_writer": 14,
        },
        "total_fanout": 21,
        "stage1_slice_est_tokens_max": 10,
        "stage1_slice_est_tokens_mean": 5,
        "stage1_slice_est_tokens_total": 10,
        "stage1_slice_est_tokens_per_group": {"0": 5, "1": 5},
        "stage4_metric_kind": "partial_proxy_pre_stage4",
        "stage4_included_now": [
            "group_est_tokens_proxy_for_summaries",
            "spring_signals_optional",
        ],
        "stage4_omitted_not_estimated": [
            "interview_answers",
            "architecture_merge_beyond_summary_proxy",
            "stage4_return_payloads",
        ],
        "stage4_shared_pool_upper_bound_est_tokens": 200,
        "stage4_summaries_est_tokens": 200,
        "stage4_interview_answers_est_tokens": 0,
        "stage4_interview_answers_omitted": True,
        "stage4_signals_est_tokens": 0,
        "stage4_signals_omitted": True,
        "stage4_aggregate_input_upper_bound_est_tokens": 2800,
        "stage4_return_payloads_estimated": False,
        "edge_join_stats": {},
        "warnings": [],
    }
    if with_schema_version:
        report["schema_version"] = (
            capacity_preflight.CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION
        )
    return report


def characterization_calibration_report(*, with_schema_version: bool = False) -> dict:
    """Minimal synthetic L2b calibration report matching compute_stage4_calibration."""
    report = {
        "repo_path": "/tmp/example-repo",
        "mode": "stage4_calibration",
        "stage4_metric_kind": "measured_stage4_inputs",
        "stage4_included_now": ["summaries"],
        "stage4_omitted_not_estimated": [
            "interview_answers",
            "spring_signals",
            "stage4_return_payloads",
        ],
        "stage4_shared_pool_upper_bound_est_tokens": 50,
        "stage4_summaries_est_tokens": 50,
        "stage4_interview_answers_est_tokens": 0,
        "stage4_interview_answers_omitted": True,
        "stage4_signals_est_tokens": 0,
        "stage4_signals_omitted": True,
        "stage4_aggregate_input_upper_bound_est_tokens": 700,
        "stage4_return_payloads_estimated": False,
        "stage4_proxy_comparison": None,
        "warnings": [],
    }
    if with_schema_version:
        report["schema_version"] = (
            capacity_preflight.CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION
        )
    return report


def test_characterization_shared_keys_are_writer_intersection() -> None:
    stage0 = characterization_stage0_report(with_schema_version=False)
    calib = characterization_calibration_report(with_schema_version=False)
    assert set(stage0) & set(calib) == _LEGACY_SHARED_ROOT_KEYS


def test_stage4_metric_kind_literal_matches_writer_vocabulary() -> None:
    from doc_engine.pipeline.artifacts import Stage4MetricKind

    assert set(get_args(Stage4MetricKind)) == STAGE4_METRIC_KINDS


def test_schema_version_required() -> None:
    from doc_engine.pipeline.artifacts import CapacityPreflightReportArtifact

    with pytest.raises(ValidationError):
        CapacityPreflightReportArtifact.model_validate(
            characterization_stage0_report(with_schema_version=False)
        )

    CapacityPreflightReportArtifact.model_validate(
        characterization_stage0_report(with_schema_version=True)
    )


@pytest.mark.parametrize("kind", sorted(STAGE4_METRIC_KINDS))
def test_each_known_metric_kind_validates(kind: str) -> None:
    from doc_engine.pipeline.artifacts import CapacityPreflightReportArtifact

    report = characterization_stage0_report(with_schema_version=True)
    report["stage4_metric_kind"] = kind
    CapacityPreflightReportArtifact.model_validate(report)


def test_unknown_metric_kind_rejected() -> None:
    from doc_engine.pipeline.artifacts import CapacityPreflightReportArtifact

    report = characterization_stage0_report(with_schema_version=True)
    report["stage4_metric_kind"] = "upper_bound"
    with pytest.raises(ValidationError):
        CapacityPreflightReportArtifact.model_validate(report)


def test_calibration_mode_validates() -> None:
    from doc_engine.pipeline.artifacts import CapacityPreflightReportArtifact

    CapacityPreflightReportArtifact.model_validate(
        characterization_calibration_report(with_schema_version=True)
    )


def test_round_trip_preserves_required_identity() -> None:
    from doc_engine.pipeline.artifacts import CapacityPreflightReportArtifact

    report = characterization_stage0_report(with_schema_version=True)
    dumped = CapacityPreflightReportArtifact.model_validate(report).model_dump()
    assert dumped["schema_version"] == (
        capacity_preflight.CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION
    )
    assert dumped["repo_path"] == report["repo_path"]
    assert dumped["stage4_metric_kind"] == "partial_proxy_pre_stage4"
    assert dumped["stage4_return_payloads_estimated"] is False


def test_compute_preflight_emits_schema_version() -> None:
    groups = {
        "repo_path": "/fake/repo",
        "max_tokens_per_group": 120000,
        "num_groups": 1,
        "groups": [{"id": 0, "files": ["a.java"], "est_tokens": 10}],
    }
    edges = {
        "num_groups": 1,
        "groups": {"0": {"outbound": [], "inbound": [], "same_package_outside": []}},
        "stats": {},
    }
    report = capacity_preflight.compute_preflight(
        "/fake/repo", groups_data=groups, edges=edges,
        group_warn_threshold=1000, fanout_warn_threshold=1000,
        stage4_shared_tokens_warn_threshold=10_000_000,
    )
    assert report["schema_version"] == (
        capacity_preflight.CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION
    )
    assert set(report) >= _LEGACY_SHARED_ROOT_KEYS | {
        "schema_version", "num_groups", "stage_fanout", "edge_join_stats",
    }


def test_compute_stage4_calibration_emits_schema_version() -> None:
    report = capacity_preflight.compute_stage4_calibration(
        "/fake/repo",
        summaries_data=[{"file": "a.java", "summary": "s"}],
        stage4_shared_tokens_warn_threshold=10_000_000,
    )
    assert report["schema_version"] == (
        capacity_preflight.CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION
    )
    assert report["mode"] == "stage4_calibration"
    assert report["stage4_metric_kind"] == "measured_stage4_inputs"


def test_capacity_preflight_report_registered() -> None:
    assert "capacity_preflight_report" in ARTIFACT_MODELS
    assert (
        ARTIFACT_FILENAMES["capacity_preflight_report"]
        == "capacity_preflight_report.json"
    )


def test_validate_artifact_file_accepts_fixture(tmp_path: Path) -> None:
    path = tmp_path / "capacity_preflight_report.json"
    path.write_text(
        json.dumps(characterization_stage0_report(with_schema_version=True)),
        encoding="utf-8",
    )
    model = validate_artifact_file("capacity_preflight_report", path)
    assert model.schema_version == (
        capacity_preflight.CAPACITY_PREFLIGHT_REPORT_SCHEMA_VERSION
    )


def test_validate_artifact_file_rejects_bad_metric_kind(tmp_path: Path) -> None:
    report = characterization_stage0_report(with_schema_version=True)
    report["stage4_metric_kind"] = "bogus"
    path = tmp_path / "capacity_preflight_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ArtifactValidationError):
        validate_artifact_file("capacity_preflight_report", path)


def test_exported_schema_file_committed() -> None:
    from tests.conftest import REPO_ROOT

    schema_path = (
        REPO_ROOT / "scripts" / "schemas" / "capacity_preflight_report.schema.json"
    )
    assert schema_path.is_file()
    from doc_engine.pipeline.artifacts import export_json_schemas

    assert "capacity_preflight_report" in export_json_schemas()
