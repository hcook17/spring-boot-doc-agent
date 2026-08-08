"""Focused tests for Principal-SE complexity helper splits (complexipy ≤5)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from doc_engine import cli
from doc_engine.config import loader
from doc_engine.core.context import ScanContext, _ingest_walked_file
from doc_engine.pipeline.local_runner_phases import support
from doc_engine.pipeline.local_runner_phases.context import (
    _ensure_todos,
    _partition_specs_by_kind,
)
from doc_engine.pipeline.context import StageKind
from doc_engine.real_fixture import (
    _any_path_matches_prefixes,
    _first_content_line,
    _normalize_changed_path,
    _path_matches_prefix,
    generative_paths_require_artifacts,
    stage0_paths_require_real_repo,
)


def test_split_scanner_names_strips_and_drops_blanks():
    assert cli._split_scanner_names(" fs , ,codeql, ") == ["fs", "codeql"]


def test_scan_cli_overrides_respects_flags():
    args = argparse.Namespace(
        scanners="fs,codeql",
        sql_dialect="postgres",
        respect_gitignore=True,
        build_command="mvn -q",
        db_path="/tmp/db",
    )
    overrides = cli._scan_cli_overrides(args)
    assert overrides["scanners"] == ["fs", "codeql"]
    assert overrides["sql_dialect"] == "postgres"
    assert overrides["respect_gitignore"] is True
    assert overrides["build_command"] == "mvn -q"
    assert overrides["db_path"] == "/tmp/db"


def test_settings_from_raw_coerces_scanners_and_extra(tmp_path: Path):
    raw = {
        "scanners": "fs, codeql",
        "extra": "not-a-dict",
        "sql_dialect": "ansi",
    }
    settings = loader._settings_from_raw(raw)
    assert settings.scanners == ["fs", "codeql"]
    assert settings.extra == {}

    path = tmp_path / ".doc-engine.json"
    path.write_text(json.dumps({"scanners": ["fs"], "extra": {"k": 1}}), encoding="utf-8")
    loaded = loader._load_config_dict(path)
    assert loaded["extra"] == {"k": 1}
    assert loader._settings_from_raw(loaded).extra == {"k": 1}


def test_scan_context_build_buckets_java_and_signatures(tmp_path: Path):
    (tmp_path / "A.java").write_text("class A {}", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    ctx = ScanContext.build(str(tmp_path))
    assert len(ctx.java_files) == 1
    assert len(ctx.non_java_files) == 1
    assert "A.java" in ctx.file_signatures
    assert "note.txt" in ctx.file_signatures


def test_ingest_skips_escape_outside_root(tmp_path: Path, monkeypatch):
    ctx = ScanContext(repo_path=str(tmp_path))
    warned: list[str] = []
    monkeypatch.setattr(
        "doc_engine.core.context.warn_skipped_escape",
        lambda rel, full: warned.append(rel),
    )
    monkeypatch.setattr(
        "doc_engine.core.context.is_path_inside_root",
        lambda full, root: False,
    )
    _ingest_walked_file(ctx, str(tmp_path / "A.java"), str(tmp_path))
    assert warned
    assert not ctx.java_files


def test_first_content_line_skips_comments_and_bom():
    text = "\ufeff# comment\n\n  /tmp/spring\n"
    assert _first_content_line(text) == "/tmp/spring"
    assert _first_content_line("# only\n") is None


def test_path_prefix_helpers_normalize_and_match():
    assert _normalize_changed_path("./src\\doc_engine\\query\\x.py") == (
        "src/doc_engine/query/x.py"
    )
    assert _path_matches_prefix("src/doc_engine/query", "src/doc_engine/query/")
    assert _any_path_matches_prefixes(
        ["./src/doc_engine/pipeline/x.py"],
        ("src/doc_engine/pipeline/",),
    )
    assert stage0_paths_require_real_repo(["src/doc_engine/scanning/a.py"])
    assert generative_paths_require_artifacts(["src/doc_engine/pipeline/a.py"])
    assert not generative_paths_require_artifacts(["README.md"])


def test_partition_specs_by_kind():
    specs = [
        SimpleNamespace(kind=StageKind.DETERMINISTIC, name="a"),
        SimpleNamespace(kind=StageKind.GENERATIVE, name="b"),
        SimpleNamespace(kind=StageKind.DETERMINISTIC, name="c"),
    ]
    det, gen = _partition_specs_by_kind(specs)
    assert [s.name for s in det] == ["a", "c"]
    assert [s.name for s in gen] == ["b"]


def test_record_pipeline_stage_results_sets_abort():
    runner = SimpleNamespace(results=[], aborted=False)

    def record(label, status, seconds, detail=""):
        runner.results.append((label, status, seconds, detail))

    runner.record = record
    ok = SimpleNamespace(success=True, detail="fine", error=None)
    bad = SimpleNamespace(success=False, detail="", error="boom")
    support._record_pipeline_stage_results(
        runner, [("s1", ok), ("s2", bad)], ok_status="OK"
    )
    assert runner.aborted is True
    assert runner.results[0][1] == "OK"
    assert runner.results[1][1] == "FAIL"


def test_certification_failure_summary_lists_stages_and_gates():
    runner = SimpleNamespace(
        gate_records=[
            SimpleNamespace(id="g1", required=True, status="fail"),
            SimpleNamespace(id="g2", required=False, status="fail"),
            SimpleNamespace(id="g3", required=True, status="ok"),
        ]
    )
    report = SimpleNamespace(
        stages=[
            SimpleNamespace(name="stage_a", status="fail"),
            SimpleNamespace(name="stage_b", status="ok"),
        ]
    )
    summary = support._certification_failure_summary(runner, report)
    assert "stages: stage_a" in summary
    assert "gates: g1" in summary


def test_ensure_todos_writes_when_missing(tmp_path: Path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    ctx = SimpleNamespace(
        todos=None,
        repo_path=tmp_path,
        out_dir=out,
    )
    monkeypatch.setattr(
        "doc_engine.pipeline.local_runner_phases.context.sweep_todos",
        lambda _repo: [{"todo": 1}],
    )
    written: dict = {}

    def _write(path, data):
        written["path"] = path
        written["data"] = data

    monkeypatch.setattr(
        "doc_engine.pipeline.local_runner_phases.context._write_json",
        _write,
    )
    _ensure_todos(ctx)
    assert ctx.todos == [{"todo": 1}]
    assert written["data"] == [{"todo": 1}]
