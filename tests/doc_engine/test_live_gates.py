"""B2 — live certification chain: gates rewrite cert; verify requires live."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from doc_engine.pipeline.compliance import (
    CERTIFIED_GATE_IDS,
    ComplianceProfile,
    GateRecord,
    StageRecord,
    build_certification_report,
    write_certification_json,
)
from doc_engine.pipeline import live_gates
from doc_engine.tools.certification import main as cert_main
from doc_engine.tools.certification import verify_certification


def _live_ok_gates() -> list[GateRecord]:
    return [
        GateRecord(id=gid, label=gid, status="ok")
        for gid in sorted(CERTIFIED_GATE_IDS)
    ]


def test_verify_rejects_mock_without_allow_mock():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=_live_ok_gates(),
            generative_executor="mock",
        )
        assert report.certified is True
        path = write_certification_json(tmp, report)
        ok, msg = verify_certification(path)
        assert not ok
        assert "generative_executor" in msg
        assert "mock" in msg

        ok2, _ = verify_certification(path, allow_mock=True)
        assert ok2
        assert cert_main([str(path)]) == 1
        assert cert_main([str(path), "--allow-mock"]) == 0


def test_verify_rejects_none_without_allow_mock():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_certification_report(
            ComplianceProfile.SCAN_ONLY,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=[
                GateRecord(
                    id="validate_artifacts_spring_signals",
                    label="signals",
                    status="ok",
                )
            ],
            generative_executor="none",
        )
        path = write_certification_json(tmp, report)
        ok, msg = verify_certification(path)
        assert not ok
        assert "none" in msg


def test_verify_accepts_live_certified():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=_live_ok_gates(),
            generative_executor="live",
        )
        path = write_certification_json(tmp, report)
        ok, msg = verify_certification(path)
        assert ok
        assert "OK" in msg
        assert cert_main([str(path)]) == 0


def test_live_gates_rewrites_cert_with_executor_live():
    """Stale mock certified:true must not survive a failing live gates pass."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        docs = out / "docs"
        docs.mkdir()
        # Prior mock certificate claims certified — live gates must overwrite it.
        prior = build_certification_report(
            ComplianceProfile.CERTIFIED,
            str(out / "repo"),
            str(out),
            stages=[StageRecord(name="signal_scan", status="ok")],
            gates=_live_ok_gates(),
            generative_executor="mock",
        )
        write_certification_json(out, prior)
        assert prior.certified is True

        def _fail_validate(_out_dir: str) -> int:
            return 1

        def _ok_validators(_out: str, _repo: str) -> tuple[int, str]:
            return 0, "ok"

        def _fail_subprocess(_argv: list[str]) -> tuple[int, str]:
            return 1, "planted failure"

        with mock.patch.object(
            live_gates.gates, "run_validate_all_artifacts", _fail_validate
        ), mock.patch.object(
            live_gates.gates, "run_pipeline_validators", _ok_validators
        ), mock.patch.object(
            live_gates.gates, "run_subprocess_gate", _fail_subprocess
        ):
            code = live_gates.run_live_gates(
                out_dir=str(out),
                repo_path=str(out / "repo"),
                docs_dir=str(docs),
                no_write_check=True,
            )
        assert code == 1
        data = json.loads((out / "certification.json").read_text(encoding="utf-8"))
        assert data["generative_executor"] == "live"
        assert data["certified"] is False
        assert any("validate_artifacts_all" in f for f in data["failures"])

        ok, msg = verify_certification(out / "certification.json")
        assert not ok
        assert "not certified" in msg


def test_live_gates_passing_writes_live_certified(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        docs = out / "docs"
        docs.mkdir()
        (out / "summaries.json").write_text("[]\n", encoding="utf-8")

        monkeypatch.setattr(
            live_gates.gates, "run_validate_all_artifacts", lambda _o: 0
        )
        monkeypatch.setattr(
            live_gates.gates,
            "run_pipeline_validators",
            lambda _o, _r: (0, "ok"),
        )
        monkeypatch.setattr(
            live_gates.gates,
            "run_subprocess_gate",
            lambda _argv: (0, "ok"),
        )

        code = live_gates.run_live_gates(
            out_dir=str(out),
            repo_path=str(out / "repo"),
            docs_dir=str(docs),
            no_write_check=True,
        )
        assert code == 0
        data = json.loads((out / "certification.json").read_text(encoding="utf-8"))
        assert data["generative_executor"] == "live"
        assert data["certified"] is True
        ok, _ = verify_certification(out / "certification.json")
        assert ok
