"""Tests for certification gate."""

import json
import tempfile
from pathlib import Path

import pytest

from doc_engine.tools.certification import load_certification, verify_certification


def _write_cert(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_verify_certified_true():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        _write_cert(path, {"certified": True, "compliance_profile": "scan_only"})
        ok, msg = verify_certification(path)
        assert ok
        assert "OK" in msg


def test_verify_not_certified():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        _write_cert(
            path,
            {
                "certified": False,
                "compliance_profile": "certified",
                "failures": ["gate:artifact_contract"],
            },
        )
        ok, msg = verify_certification(path)
        assert not ok
        assert "not certified" in msg


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


def test_verify_certification_script_main():
    from doc_engine.tools.certification import main

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "certification.json"
        _write_cert(path, {"certified": True})
        assert main([str(path)]) == 0
        _write_cert(path, {"certified": False})
        assert main([str(path)]) == 1
