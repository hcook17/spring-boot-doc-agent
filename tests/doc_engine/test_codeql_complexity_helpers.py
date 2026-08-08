"""Focused tests for CodeQL Principal-SE helper splits (complexipy ≤5)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from doc_engine.scanning._scanner_codeql import CodeQLBackend
from doc_engine.scanning.support import _codeql_runner as runner


def test_version_token_from_release_line():
    assert runner._version_token_from_line(
        "CodeQL command-line toolchain release 2.26.0."
    ) == "2.26.0"
    assert runner._version_token_from_line("no version here") is None


def test_parse_codeql_version_stdout_first_release_wins():
    stdout = "banner\nCodeQL command-line toolchain release 2.15.1.\ntrailer\n"
    assert runner._parse_codeql_version_stdout(stdout) == "2.15.1"


def test_parse_codeql_version_stdout_raises_when_unparseable():
    with pytest.raises(runner.CodeQLError, match="could not parse"):
        runner._parse_codeql_version_stdout("CodeQL is ready\n")


def test_repo_content_hash_walk_includes_java_and_build_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.java").write_text("class A {}", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "readme.md").write_text("ignore", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")

    digest = runner._repo_content_hash(tmp_path)
    assert len(digest) == 32
    # Excluding .git / readme must not change the hash of java+pom only.
    (tmp_path / "readme.md").write_text("changed", encoding="utf-8")
    assert runner._repo_content_hash(tmp_path) == digest


def test_rows_from_bqrs_json_uses_column_names_and_synthetics():
    raw = {
        "#select": {
            "columns": [{"name": "file", "kind": "String"}, {"kind": "String"}],
            "tuples": [["a.java", "x"], ["b.java", "y"]],
        }
    }
    rows = runner._rows_from_bqrs_json(raw)
    assert rows == [
        {"file": "a.java", "col_1": "x"},
        {"file": "b.java", "col_1": "y"},
    ]


def test_validated_build_command_wraps_build_command_error():
    with pytest.raises(runner.CodeQLError):
        runner._validated_build_command("")


def test_evidence_entry_raw_query_fields():
    entry = CodeQLBackend._evidence_entry_from_codeql_row(
        rel="src/Q.java",
        row={"line": 3, "query_kind": "native", "query_text": "SELECT 1"},
        match_text="@Query(\"SELECT 1\")",
        rule_id="raw_queries__query",
    )
    assert entry["query_kind"] == "native"
    assert entry["query"] == "SELECT 1"
    assert entry["file"] == "src/Q.java"


def test_evidence_entry_repository_falls_back_to_entity_name(monkeypatch):
    monkeypatch.setattr(
        "doc_engine.scanning._scanner_codeql.extract_repository",
        lambda _text: {"repository": "FooRepo"},
    )
    entry = CodeQLBackend._evidence_entry_from_codeql_row(
        rel="src/FooRepo.java",
        row={"line": 1, "entity_name": "Foo"},
        match_text="interface FooRepo",
        rule_id="persistence__repository",
    )
    assert entry["repository"] == "FooRepo"
    assert entry["entity"] == "Foo"


def test_entity_map_entry_inferred_and_explicit_table():
    inferred = CodeQLBackend._entity_map_entry(
        rel="src/Bar.java",
        class_name="Bar",
        match_text="@Entity class Bar {}",
        rule_id="persistence__entity",
        extracted=None,
        codeql_table=None,
    )
    assert inferred is not None
    class_name, map_entry = inferred
    assert class_name == "Bar"
    assert map_entry["table_name_source"] == "inferred-default-naming"
    assert map_entry["table"] == "bar"

    explicit = CodeQLBackend._entity_map_entry(
        rel="src/Bar.java",
        class_name="Bar",
        match_text="@Entity class Bar {}",
        rule_id="persistence__entity",
        extracted=None,
        codeql_table="bars",
    )
    assert explicit is not None
    _, explicit_entry = explicit
    assert explicit_entry["table"] == "bars"
    assert explicit_entry["table_name_source"] == "explicit"


def test_entity_map_entry_rejects_empty_inferred_class_name():
    assert (
        CodeQLBackend._entity_map_entry(
            rel="src/X.java",
            class_name="",
            match_text="",
            rule_id="persistence__entity",
            extracted=None,
            codeql_table=None,
        )
        is None
    )


def test_acked_java_paths_prefer_scan_context():
    ctx = SimpleNamespace(
        java_files=[
            SimpleNamespace(rel_path="b/B.java"),
            SimpleNamespace(rel_path="a/A.java"),
        ]
    )
    assert CodeQLBackend._acked_java_paths(ctx, ["z/Z.java"]) == [
        "a/A.java",
        "b/B.java",
    ]
    assert CodeQLBackend._acked_java_paths(None, ["z/Z.java"]) == ["z/Z.java"]


def test_covering_receipt_complete_when_acked_matches(monkeypatch):
    backend = CodeQLBackend()
    monkeypatch.setattr(backend, "version_hash", lambda: "abcd1234efgh5678")
    monkeypatch.setattr(
        "doc_engine.scanning.covering.java_scope_paths",
        lambda _sigs: ["a/A.java"],
    )
    monkeypatch.setattr(
        "doc_engine.scanning.covering.subset_root",
        lambda _sigs, paths: "root:" + ",".join(paths),
    )
    monkeypatch.setattr(
        "doc_engine.scanning.covering.build_receipt",
        lambda **kwargs: kwargs,
    )
    ctx = SimpleNamespace(
        file_signatures={"a/A.java": "sig"},
        java_files=[SimpleNamespace(rel_path="a/A.java")],
    )
    receipt = backend._covering_receipt_for_scan(ctx)
    assert receipt["status"] == "complete"
    assert receipt["acked_subset_root"] == receipt["expected_subset_root"]


def test_covering_receipt_fails_closed_on_mismatch(monkeypatch):
    backend = CodeQLBackend()
    monkeypatch.setattr(backend, "version_hash", lambda: "abcd1234efgh5678")
    monkeypatch.setattr(
        "doc_engine.scanning.covering.java_scope_paths",
        lambda _sigs: ["a/A.java", "b/B.java"],
    )
    monkeypatch.setattr(
        "doc_engine.scanning.covering.subset_root",
        lambda _sigs, paths: "root:" + ",".join(paths),
    )
    monkeypatch.setattr(
        "doc_engine.scanning.covering.build_receipt",
        lambda **kwargs: {**kwargs, "error": kwargs.get("error")},
    )
    ctx = SimpleNamespace(
        file_signatures={"a/A.java": "sig", "b/B.java": "sig"},
        java_files=[SimpleNamespace(rel_path="a/A.java")],
    )
    with pytest.raises(runner.CodeQLError, match="acked java subset"):
        backend._covering_receipt_for_scan(ctx)


def test_load_cached_scan_rows_skips_without_version(monkeypatch):
    monkeypatch.setattr(runner, "_load_results_cache", MagicMock(return_value=[{"file": "x"}]))
    assert (
        runner._load_cached_scan_rows(
            using_cache=True,
            scanner_version=None,
            repo_path=Path("."),
            pack_dir=Path("."),
            build_command="true",
            scan_context=None,
            cli_version="2.0.0",
        )
        is None
    )
    runner._load_results_cache.assert_not_called()
