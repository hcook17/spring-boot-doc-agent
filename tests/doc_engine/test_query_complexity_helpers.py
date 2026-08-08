"""Focused tests for query Principal-SE helper splits (complexipy ≤5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_engine.core.walk import compute_file_signature
from doc_engine.query import freshness, load, packet, providers, registry, schema_check
from doc_engine.query.handlers import dependents, entity, evidence, facts, route_trace
from doc_engine.query.load import QueryError


def test_parse_jsonl_object_rejects_non_object(tmp_path: Path):
    with pytest.raises(QueryError, match="must be object"):
        load._parse_jsonl_object(tmp_path / "f.jsonl", 1, "[]")


def test_load_jsonl_skips_blanks_and_parses_rows(tmp_path: Path):
    path = tmp_path / "facts.jsonl"
    path.write_text('\n{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")
    assert load.load_jsonl(path, root=tmp_path) == [{"a": 1}, {"b": 2}]


def test_stale_paths_from_drift_report_lists_and_files_map():
    report = {
        "changed_files": ["a.java", {"file": "b.java"}],
        "files": {
            "c.java": {"status": "stale"},
            "d.java": {"status": "ok"},
        },
    }
    assert freshness.stale_paths_from_drift_report(report) == {
        "a.java",
        "b.java",
        "c.java",
    }


def test_arcs_for_direction_filters_want_file():
    entry = {
        "outbound": [
            {"from": "A.java", "to": "B.java"},
            {"from": "C.java", "to": "D.java"},
            "skip",
        ]
    }
    rows = dependents._arcs_for_direction(entry, "outbound", "A.java")
    assert len(rows) == 1
    assert rows[0]["direction"] == "outbound"
    assert rows[0]["from"] == "A.java"


def test_rel_path_is_live_matches_signature(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "A.java"
    f.write_text("class A {}", encoding="utf-8")
    rel = "src/A.java"
    sig = compute_file_signature(str(f))
    assert packet._rel_path_is_live(tmp_path.resolve(), {rel: sig}, rel)
    assert not packet._rel_path_is_live(tmp_path.resolve(), {rel: "dead"}, rel)


def test_query_route_trace_keeps_mapping_rows_with_guards():
    signals = {
        "evidence": {
            "api_surface": [
                {
                    "file": "A.java",
                    "line": 1,
                    "match": '@GetMapping("/api")',
                    "rule_id": "api_surface__mapping",
                },
                {
                    "file": "A.java",
                    "line": 2,
                    "match": "@RestController",
                    "rule_id": "api_surface__controller",
                },
            ],
            "security": [
                {
                    "file": "A.java",
                    "line": 3,
                    "match": "@PreAuthorize",
                    "rule_id": "security__pre_authorize",
                },
            ],
        }
    }
    rows = route_trace.query_route_trace(signals, path_contains="/api")
    assert len(rows) == 1
    assert rows[0]["guards"][0]["rule_id"] == "security__pre_authorize"


def test_fact_passes_helpers_compose():
    row = {
        "predicate": "MAPS_TO",
        "file": "src/A.java",
        "subject": "User",
        "qualifiers": {"fqcn": "com.example.User"},
    }
    assert facts._fact_passes(
        row,
        predicate="MAPS_TO",
        file_contains="src/",
        fqcn="com.example.User",
        subject_contains="User",
    )
    assert not facts._fact_passes(
        row,
        predicate="UNPROVEN",
        file_contains=None,
        fqcn=None,
        subject_contains=None,
    )


def test_filter_bucket_and_entity_helpers():
    evidence_doc = {
        "api_surface": [
            {"file": "A.java", "rule_id": "r1", "match": "x"},
            "bad",
            {"file": "B.java", "rule_id": "r2", "match": "y"},
        ]
    }
    rows = evidence._filter_bucket(
        evidence_doc, "api_surface", rule_id="r1", file_contains=None, match_contains=None
    )
    assert len(rows) == 1 and rows[0]["bucket"] == "api_surface"

    signals = {
        "entity_table_map": {
            "User": {"table": "users", "candidates": [{"table": "usr"}]},
            "Order": "bad",
        }
    }
    found = entity.query_entity(signals, table="usr")
    assert len(found) == 1 and found[0]["class_name"] == "User"


def test_facts_provider_and_invoke_handler_helpers(tmp_path: Path):
    provider = providers.FactsProvider()
    rows = provider.provide(
        "req",
        signals={},
        facts_rows=[
            {"predicate": "REFERENCES", "object": "x"},
            {"predicate": "MAPS_TO", "file": "A.java", "object": "t"},
            {
                "predicate": "X",
                "qualifiers": {"status": "contested"},
                "object": "c",
            },
        ],
        run_dir=tmp_path,
        limit=10,
    )
    assert len(rows) == 2
    assert rows[0]["reason"] == "fact MAPS_TO"

    class Spec:
        handler = staticmethod(lambda fr, **_f: list(fr))
        requires_signals = False
        requires_facts = True
        accepts_edges = False

    out = registry._invoke_handler(Spec(), sig=None, fr=[{"a": 1}], ed=None, filters={})
    assert out == [{"a": 1}]
    with pytest.raises(load.QueryMissingError):
        registry._invoke_handler(Spec(), sig=None, fr=None, ed=None, filters={})


def test_validate_envelope_kind_specific(tmp_path: Path, monkeypatch):
    schema = {"required": ["kind", "rows"]}
    monkeypatch.setattr(schema_check, "load_schema", lambda _k: schema)
    with pytest.raises(QueryError, match="missing keys"):
        schema_check.validate_envelope("query_result", {"kind": "query-result"})
    with pytest.raises(QueryError, match="must be a list"):
        schema_check.validate_envelope(
            "query_result", {"kind": "query-result", "rows": {}}
        )
