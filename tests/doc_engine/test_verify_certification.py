"""Tests for certification gate — fixtures minted via production builder.

Cause this suite locks (schema-contracts / CertificationReport.model_validate):
hand-rolled ``{"certified": True}`` (and other incomplete dicts) used to satisfy
``verify_certification`` before load_certification schema-gated. After the gate,
those fixtures fail schema *before* the certified bit is read — CI then saw
``assert False`` / missing ``"not certified"`` / ``main`` exit 1. Mint through
``build_certification_report`` + ``write_certification_json`` only.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from doc_engine.pipeline.compliance import (
    SCAN_ONLY_GATE_ID,
    ComplianceProfile,
    GateRecord,
    StageRecord,
    build_certification_report,
    write_certification_json,
)
from doc_engine.tools.certification import load_certification, verify_certification


def _ok_gates_for(profile: ComplianceProfile) -> list[GateRecord]:
    from doc_engine.pipeline.compliance import gates_required_for_profile

    return [
        GateRecord(id=gid, label=gid, status="ok")
        for gid in sorted(gates_required_for_profile(profile))
    ]


def _write_incomplete(path: Path, data: dict) -> None:
    """Deliberately bypass the builder — only for schema-rejection cases."""
    path.write_text(json.dumps(data), encoding="utf-8")


def test_verify_certified_true():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=_ok_gates_for(ComplianceProfile.CERTIFIED),
            generative_executor="live",
        )
        assert report.certified is True
        path = write_certification_json(tmp, report)
        ok, msg = verify_certification(path)
        assert ok
        assert "OK" in msg


def test_verify_not_certified():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=[
                GateRecord(
                    id="validate_artifacts_all",
                    label="artifacts",
                    status="fail",
                    detail="contract broken",
                )
            ],
            generative_executor="live",
        )
        assert report.certified is False
        assert any("validate_artifacts_all" in f for f in report.failures)
        path = write_certification_json(tmp, report)
        ok, msg = verify_certification(path)
        assert not ok
        assert "not certified" in msg
        assert "certification schema" not in msg


def test_verify_missing_file():
    ok, msg = verify_certification(Path("/nonexistent/certification.json"))
    assert not ok
    assert "not found" in msg


def test_load_certification_invalid_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_certification(path)


@pytest.mark.parametrize(
    "payload",
    [
        {"certified": True},
        {"certified": True, "compliance_profile": "scan_only"},
        {
            "certified": False,
            "compliance_profile": "certified",
            "failures": ["gate:artifact_contract"],
        },
        {"certified": False},
    ],
    ids=[
        "certified_true_only",
        "certified_true_scan_only_profile",
        "not_certified_with_failures_only",
        "certified_false_only",
    ],
)
def test_pre_schema_incomplete_dicts_fail_schema_gate(payload: dict):
    """Exact HEAD fixture shapes that broke CI after CertificationReport gating."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        _write_incomplete(path, payload)
        with pytest.raises(ValueError, match="certification schema"):
            load_certification(path)
        ok, msg = verify_certification(path)
        assert not ok
        assert "certification schema" in msg
        # Schema path — must not look like a well-formed "not certified" report.
        assert "not certified" not in msg


def test_incomplete_cert_fails_schema_gate():
    """Alias kept for discoverability — certified:true alone is not enough."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        _write_incomplete(path, {"certified": True})
        with pytest.raises(ValueError, match="certification schema"):
            load_certification(path)
        ok, msg = verify_certification(path)
        assert not ok
        assert "certification schema" in msg


def test_builder_round_trip_load_accepts_full_report():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_certification_report(
            ComplianceProfile.SCAN_ONLY,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=[
                GateRecord(id=SCAN_ONLY_GATE_ID, label="signals", status="ok"),
            ],
        )
        path = write_certification_json(tmp, report)
        data = load_certification(path)
        assert data["certified"] is True
        assert data["repo_path"] == "/repo"
        assert data["compliance_profile"] == "scan_only"
        assert SCAN_ONLY_GATE_ID in data["profile_gate_ids"]


def test_verify_certification_script_main():
    from doc_engine.tools.certification import main

    with tempfile.TemporaryDirectory() as tmp:
        ok_report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=_ok_gates_for(ComplianceProfile.CERTIFIED),
            generative_executor="live",
        )
        path = write_certification_json(tmp, ok_report)
        assert main([str(path)]) == 0

        bad_report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="fail", detail="exit 1")],
            gates=_ok_gates_for(ComplianceProfile.CERTIFIED),
            generative_executor="live",
        )
        write_certification_json(tmp, bad_report)
        assert main([str(path)]) == 1


def test_main_rejects_incomplete_certified_true_dict():
    """Regression: main([path]) used to return 0 on {\"certified\": True} alone."""
    from doc_engine.tools.certification import main

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        _write_incomplete(path, {"certified": True})
        assert main([str(path)]) == 1
