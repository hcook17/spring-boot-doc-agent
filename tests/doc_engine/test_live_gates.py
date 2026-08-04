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
from tests.doc_engine.cert_helpers import ok_det_stages_for, ok_stages_for


def _live_ok_gates() -> list[GateRecord]:
    return [
        GateRecord(id=gid, label=gid, status="ok")
        for gid in sorted(CERTIFIED_GATE_IDS)
    ]


def test_verify_rejects_mock_without_allow_mock():
    with tempfile.TemporaryDirectory() as tmp:
        # Builder itself refuses CERTIFIED+mock without allow_mock.
        denied = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=ok_stages_for(ComplianceProfile.CERTIFIED, generative_executor="mock"),
            gates=_live_ok_gates(),
            generative_executor="mock",
        )
        assert denied.certified is False
        assert "generative_executor:mock:allow_mock_required" in denied.failures

        # Issued under allow_mock — verify still requires the flag (refold + gate).
        report = build_certification_report(
            ComplianceProfile.CERTIFIED,
            "/repo",
            tmp,
            stages=ok_stages_for(ComplianceProfile.CERTIFIED, generative_executor="mock"),
            gates=_live_ok_gates(),
            generative_executor="mock",
            allow_mock=True,
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
            stages=ok_stages_for(ComplianceProfile.SCAN_ONLY),
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
            stages=ok_stages_for(ComplianceProfile.CERTIFIED, generative_executor="live"),
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
            stages=ok_stages_for(ComplianceProfile.CERTIFIED, generative_executor="mock"),
            gates=_live_ok_gates(),
            generative_executor="mock",
            allow_mock=True,
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
        # Live rewrite keeps det priors; plant a complete det prior so omission
        # cannot vacuous-certify from generative_external alone.
        prior = build_certification_report(
            ComplianceProfile.DETERMINISTIC_ONLY,
            str(out / "repo"),
            str(out),
            stages=ok_det_stages_for(ComplianceProfile.CERTIFIED),
            gates=[GateRecord(id="validate_artifacts_all", label="all", status="ok")],
            generative_executor="none",
        )
        write_certification_json(out, prior)

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
        assert data["schema_version"] == 1
        stage_names = [s["name"] for s in data["stages"]]
        assert "generative_external" in stage_names
        assert "doc_writer" not in stage_names
        assert all("executor" in s for s in data["stages"])
        ok, _ = verify_certification(out / "certification.json")
        assert ok


def test_live_gates_strips_mock_generative_and_survives_skipped_poison(monkeypatch):
    """Prior mock generative + skipped rows must not poison a live rewrite."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        docs = out / "docs"
        docs.mkdir()
        (out / "summaries.json").write_text("[]\n", encoding="utf-8")
        prior = build_certification_report(
            ComplianceProfile.CERTIFIED,
            str(out / "repo"),
            str(out),
            stages=[
                *ok_det_stages_for(ComplianceProfile.CERTIFIED),
                StageRecord(name="doc_writer", status="ok", executor="mock"),
                StageRecord(name="architect", status="skipped", executor="none"),
            ],
            gates=_live_ok_gates(),
            generative_executor="mock",
        )
        # Prior may be uncertified due to skipped required stage; live rewrite must
        # still be able to certify from derived stages + passing gates.
        write_certification_json(out, prior)

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
        assert data["certified"] is True
        assert data["generative_executor"] == "live"
        names = {s["name"] for s in data["stages"]}
        assert "signal_scan" in names
        assert "generative_external" in names
        assert "doc_writer" not in names
        assert "architect" not in names
        assert not any("mock_under_live" in f for f in data["failures"])


def _plant_weak_docs(docs: Path) -> None:
    """Untagged class claim — citation_coverage finding under --strict."""
    (docs / "readme.md").write_text(
        "The InvoiceController handles invoice lookups on every request.\n",
        encoding="utf-8",
    )


def _mock_non_citation_gates(monkeypatch):
    """Stub validate/validators/secrets/pipeline-output; run real citation_coverage."""
    import subprocess as sp

    monkeypatch.setattr(
        live_gates.gates, "run_validate_all_artifacts", lambda _o: 0
    )
    monkeypatch.setattr(
        live_gates.gates,
        "run_pipeline_validators",
        lambda _o, _r: (0, "ok"),
    )

    def _subprocess_real_cc(argv: list[str]) -> tuple[int, str]:
        joined = " ".join(argv)
        if "doc_engine.tools.citation_coverage" in joined:
            proc = sp.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            body = (proc.stdout or "") + (proc.stderr or "")
            return proc.returncode, body
        return 0, "ok"

    monkeypatch.setattr(live_gates.gates, "run_subprocess_gate", _subprocess_real_cc)


def test_certified_profile_fails_live_gates_on_weak_citations(monkeypatch):
    """B3: certified ⇒ strict citations; planted untagged claim fails the gate."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        docs = out / "docs"
        docs.mkdir()
        repo = out / "repo"
        repo.mkdir()
        (out / "summaries.json").write_text("[]\n", encoding="utf-8")
        _plant_weak_docs(docs)
        _mock_non_citation_gates(monkeypatch)

        code = live_gates.run_live_gates(
            out_dir=str(out),
            repo_path=str(repo),
            docs_dir=str(docs),
            compliance_profile="certified",
            no_write_check=True,
        )
        assert code == 1
        data = json.loads((out / "certification.json").read_text(encoding="utf-8"))
        assert data["certified"] is False
        assert any("citation_coverage" in f for f in data["failures"])


def test_non_certified_profile_allows_weak_citations_as_worklist(monkeypatch):
    """B3: deterministic_only keeps citation_coverage as a worklist (exit 0)."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        docs = out / "docs"
        docs.mkdir()
        repo = out / "repo"
        repo.mkdir()
        (out / "summaries.json").write_text("[]\n", encoding="utf-8")
        _plant_weak_docs(docs)
        _mock_non_citation_gates(monkeypatch)
        prior = build_certification_report(
            ComplianceProfile.DETERMINISTIC_ONLY,
            str(repo),
            str(out),
            stages=ok_det_stages_for(ComplianceProfile.CERTIFIED),
            gates=[GateRecord(id="validate_artifacts_all", label="all", status="ok")],
            generative_executor="none",
        )
        write_certification_json(out, prior)

        code = live_gates.run_live_gates(
            out_dir=str(out),
            repo_path=str(repo),
            docs_dir=str(docs),
            compliance_profile="deterministic_only",
            no_write_check=True,
        )
        assert code == 0
        data = json.loads((out / "certification.json").read_text(encoding="utf-8"))
        assert data["certified"] is True


def test_force_strict_citations_overrides_non_certified_profile(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        docs = out / "docs"
        docs.mkdir()
        repo = out / "repo"
        repo.mkdir()
        (out / "summaries.json").write_text("[]\n", encoding="utf-8")
        _plant_weak_docs(docs)
        _mock_non_citation_gates(monkeypatch)

        code = live_gates.run_live_gates(
            out_dir=str(out),
            repo_path=str(repo),
            docs_dir=str(docs),
            compliance_profile="scan_only",
            strict_citations=True,
            no_write_check=True,
        )
        assert code == 1
