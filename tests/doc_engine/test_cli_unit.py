"""Unit coverage for doc-engine CLI helpers and command dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from doc_engine import cli


def _capture_main(monkeypatch: pytest.MonkeyPatch, target: str) -> list[list[str]]:
    """Patch ``target`` main() and return the list of argv lists it receives."""
    captured: list[list[str]] = []

    def fake_main(argv: list[str] | None = None) -> int:
        captured.append(list(argv or []))
        return 0

    monkeypatch.setattr(target, fake_main)
    return captured


def test_without_argparse_separator() -> None:
    assert cli._without_argparse_separator([]) == []
    assert cli._without_argparse_separator(["--", "a", "b"]) == ["a", "b"]
    assert cli._without_argparse_separator(["scan", "repo"]) == ["scan", "repo"]
    # Only a leading ``--`` is stripped; mid-argv separators are left alone.
    assert cli._without_argparse_separator(["query", "--", "x"]) == ["query", "--", "x"]


def test_scan_config_overrides(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    args = argparse.Namespace(
        scanners="ast-grep,codeql",
        sql_dialect="mysql",
        respect_gitignore=True,
        build_command="./gradlew",
        db_path="/tmp/db",
        trust_repo_config=False,
    )
    config = cli._scan_config(str(repo), args)
    assert config.scanners == ["ast-grep", "codeql"]
    assert config.sql_dialect == "mysql"
    assert config.respect_gitignore is True
    assert config.build_command == "./gradlew"
    assert config.db_path == "/tmp/db"


def test_cmd_docs_and_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    signals = tmp_path / "signals.json"
    signals.write_text("{}", encoding="utf-8")
    interview = tmp_path / "interview.json"
    interview.write_text("{}", encoding="utf-8")
    docs_out = tmp_path / "docs.json"
    docs_in = tmp_path / "bundle.json"
    docs_in.write_text('{"docs": {}}', encoding="utf-8")
    site_dir = tmp_path / "site"

    class FakeEngine:
        def generate_docs(self, _signals, interview_answers=None):
            return {"ok": True, "interview": interview_answers}

        def build_site(self, _bundle, out_dir=None, site_name=None):
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            return str(Path(out_dir) / "index.html")

    monkeypatch.setattr(cli, "Engine", FakeEngine)
    assert cli.cmd_docs(SimpleNamespace(
        signals=str(signals), interview=str(interview), out=str(docs_out),
    )) == 0
    assert json.loads(docs_out.read_text(encoding="utf-8"))["ok"] is True

    assert cli.cmd_site(SimpleNamespace(
        docs=str(docs_in), out_dir=str(site_dir), site_name="demo",
    )) == 0


def test_cmd_scan_codeql_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from doc_engine.scanning.spring import CodeQLScannerError

    class BoomEngine:
        def __init__(self, _config):
            pass

        def scan(self, *_args, **_kwargs):
            raise CodeQLScannerError("need build")

    monkeypatch.setattr(cli, "Engine", BoomEngine)
    monkeypatch.setattr(cli, "_scan_config", lambda *_args, **_kwargs: object())
    rc = cli.cmd_scan(SimpleNamespace(
        repo=str(tmp_path),
        out=str(tmp_path / "out.json"),
        allow_codeql_build=False,
    ))
    assert rc == 1


def test_cmd_pipeline_gates_assembles_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_main(monkeypatch, "doc_engine.pipeline.live_gates.main")
    args = SimpleNamespace(
        out_dir="/run",
        target_repo="/repo",
        docs_dir="/docs",
        compliance_profile="certified",
        strict_citations=True,
        no_write_check=True,
    )
    assert cli.cmd_pipeline_gates(args) == 0
    joined = " ".join(captured[0])
    assert "--out-dir" in joined
    assert "--target-repo" in joined
    assert "--docs-dir" in joined
    assert "--compliance-profile" in joined
    assert "--strict-citations" in joined
    assert "--no-write-check" in joined


def test_cmd_certification_verify_allow_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_main(monkeypatch, "doc_engine.tools.certification.main")
    assert cli.cmd_certification_verify(SimpleNamespace(
        path="/c.json", allow_mock=True,
    )) == 0
    assert "--allow-mock" in captured[0]


def test_cmd_query_strips_separator(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_main(monkeypatch, "doc_engine.tools.query_artifacts.main")
    assert cli.cmd_query(SimpleNamespace(query_argv=["--", "context-packet", "--run-dir", "r"])) == 0
    assert captured[0][0] != "--"
    assert "context-packet" in captured[0]
