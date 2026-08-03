"""L5 thin drift_report schema contracts (slice 5).

Characterization fixture freezes the existing check_drift key set; contract
tests require schema_version, closed status vocabulary, registry, and
validate_artifact_file bite. Capacity preflight remains unschematized.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from doc_engine.pipeline.artifacts import ARTIFACT_FILENAMES, ARTIFACT_MODELS
from doc_engine.pipeline.validation import ArtifactValidationError, validate_artifact_file
from doc_engine.tools import spring_drift_check

# Eight STATUS_* strings already emitted by spring_drift_check (no inventions).
DRIFT_STATUSES = frozenset({
    spring_drift_check.STATUS_UNCHANGED,
    spring_drift_check.STATUS_CONFIRMED,
    spring_drift_check.STATUS_DRIFTED,
    spring_drift_check.STATUS_FILE_DELETED,
    spring_drift_check.STATUS_NO_RULE_FALLBACK,
    spring_drift_check.STATUS_UNKNOWN_NO_SIGNATURE,
    spring_drift_check.STATUS_CONFIG_STRUCTURE_CHANGED,
    spring_drift_check.STATUS_CONFIG_VALUES_ONLY_CHANGED,
})

# Root keys both check_drift return sites already emit (before schema_version).
_LEGACY_ROOT_KEYS = frozenset({
    "repo_path",
    "prior_scan_repo_path",
    "file_signatures_baseline",
    "file_summary",
    "citations_checked",
    "status_counts",
    "results",
})


def characterization_report(*, with_schema_version: bool = False) -> dict:
    """Minimal synthetic report matching today's check_drift shape."""
    report = {
        "repo_path": "/tmp/example-repo",
        "prior_scan_repo_path": "/tmp/example-repo",
        "file_signatures_baseline": {"source": "spring_signals.json"},
        "file_summary": {
            "unchanged": ["src/A.java"],
            "changed": [],
            "deleted": [],
            "added": [],
        },
        "citations_checked": 1,
        "status_counts": {spring_drift_check.STATUS_UNCHANGED: 1},
        "results": [
            {
                "source": "evidence.controllers",
                "file": "src/A.java",
                "line": 10,
                "rule_id": "web__rest_controller",
                "match": "@RestController",
                "status": spring_drift_check.STATUS_UNCHANGED,
                "tier": 1,
            }
        ],
    }
    if with_schema_version:
        report["schema_version"] = spring_drift_check.DRIFT_REPORT_SCHEMA_VERSION
    return report


def test_characterization_fixture_matches_legacy_key_set() -> None:
    report = characterization_report(with_schema_version=False)
    assert set(report) == _LEGACY_ROOT_KEYS
    assert set(report["file_summary"]) == {"unchanged", "changed", "deleted", "added"}
    assert set(report["results"][0]) >= {
        "source", "file", "line", "rule_id", "match", "status", "tier",
    }


def test_drift_status_literal_matches_writer_constants() -> None:
    from typing import get_args

    from doc_engine.pipeline.artifacts import DriftStatus

    assert set(get_args(DriftStatus)) == DRIFT_STATUSES


def test_schema_version_required() -> None:
    from doc_engine.pipeline.artifacts import DriftReportArtifact

    with pytest.raises(ValidationError):
        DriftReportArtifact.model_validate(characterization_report(with_schema_version=False))

    DriftReportArtifact.model_validate(characterization_report(with_schema_version=True))


@pytest.mark.parametrize("status", sorted(DRIFT_STATUSES))
def test_each_known_status_validates(status: str) -> None:
    from doc_engine.pipeline.artifacts import DriftReportArtifact

    report = characterization_report(with_schema_version=True)
    report["results"][0]["status"] = status
    report["status_counts"] = {status: 1}
    DriftReportArtifact.model_validate(report)


def test_unknown_status_rejected() -> None:
    from doc_engine.pipeline.artifacts import DriftReportArtifact

    report = characterization_report(with_schema_version=True)
    report["results"][0]["status"] = "not_a_real_status"
    with pytest.raises(ValidationError):
        DriftReportArtifact.model_validate(report)


def test_round_trip_preserves_required_identity() -> None:
    from doc_engine.pipeline.artifacts import DriftReportArtifact

    report = characterization_report(with_schema_version=True)
    dumped = DriftReportArtifact.model_validate(report).model_dump()
    assert dumped["schema_version"] == spring_drift_check.DRIFT_REPORT_SCHEMA_VERSION
    assert dumped["repo_path"] == report["repo_path"]
    assert dumped["citations_checked"] == 1
    assert dumped["results"][0]["status"] == spring_drift_check.STATUS_UNCHANGED
    assert dumped["results"][0]["file"] == "src/A.java"
    assert dumped["results"][0]["rule_id"] == "web__rest_controller"


def test_check_drift_emits_schema_version(tmp_path: Path) -> None:
    """Empty repo + empty signatures → early-exit path; version must ride the dict."""
    signals = {
        "schema_version": 2,
        "repo_path": str(tmp_path),
        "file_signatures": {},
        "evidence": {},
        "entity_table_map": {},
        "scanners": ["filesystem"],
    }
    report = spring_drift_check.check_drift(str(tmp_path), signals)
    assert report["schema_version"] == spring_drift_check.DRIFT_REPORT_SCHEMA_VERSION
    assert set(report) >= _LEGACY_ROOT_KEYS | {"schema_version"}


def test_drift_report_registered() -> None:
    assert "drift_report" in ARTIFACT_MODELS
    assert ARTIFACT_FILENAMES["drift_report"] == "drift_report.json"


def test_validate_artifact_file_accepts_fixture(tmp_path: Path) -> None:
    path = tmp_path / "drift_report.json"
    path.write_text(json.dumps(characterization_report(with_schema_version=True)), encoding="utf-8")
    model = validate_artifact_file("drift_report", path)
    assert model.schema_version == spring_drift_check.DRIFT_REPORT_SCHEMA_VERSION


def test_validate_artifact_file_rejects_bad_status(tmp_path: Path) -> None:
    report = characterization_report(with_schema_version=True)
    report["results"][0]["status"] = "bogus"
    path = tmp_path / "drift_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ArtifactValidationError):
        validate_artifact_file("drift_report", path)


def test_exported_schema_file_committed() -> None:
    from tests.conftest import REPO_ROOT

    schema_path = REPO_ROOT / "scripts" / "schemas" / "drift_report.schema.json"
    assert schema_path.is_file()
    from doc_engine.pipeline.artifacts import export_json_schemas

    assert "drift_report" in export_json_schemas()
