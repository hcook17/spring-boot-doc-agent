"""Facts ledger tests — identity-relevant contracts for L3.

Each test docstring names the deviation it must catch. Full-string subject
equality is reserved for grammar-memo goldens (see test_symbol).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_engine.scanning.facts import (
    fact_emit_counts,
    facts_from_signals,
    facts_path_for_signals_out,
    write_facts_jsonl,
)
from doc_engine.scanning.symbol import SymbolError, parse


def test_facts_path_is_sibling_of_signals_out(tmp_path: Path) -> None:
    out = tmp_path / "run" / "spring_signals.json"
    assert facts_path_for_signals_out(out) == (tmp_path / "run" / "facts.jsonl").resolve()


def test_evidence_subject_remains_file_path_not_symbol() -> None:
    """Deviation: evidence rows wrongly use claim-symbols as subjects."""
    signals = {
        "scanners": ["ast-grep"],
        "evidence": {
            "controllers": [
                {
                    "file": "src/FooController.java",
                    "line": 12,
                    "match": "@RestController",
                    "rule_id": "web__rest_controller",
                }
            ]
        },
        "entity_table_map": {},
    }
    facts = facts_from_signals(signals)
    assert len(facts) == 1
    assert facts[0]["subject"] == "src/FooController.java"
    with pytest.raises(SymbolError):
        parse(facts[0]["subject"])


def test_contested_maps_to_distinct_symbols_and_stable_display() -> None:
    """Deviation: contested MAPS_TO collapses to one subject or loses display_name/fqcn."""
    signals = {
        "scanners": ["ast-grep"],
        "evidence": {},
        "entity_table_map": {
            "User": {
                "file": "pkg_a/User.java",
                "table": "a_user",
                "table_name_source": "annotation",
                "package": "com.example.pkg_a",
                "fqcn": "com.example.pkg_a.User",
                "status": "contested",
                "candidates": [
                    {
                        "file": "pkg_a/User.java",
                        "table": "a_user",
                        "table_name_source": "annotation",
                        "package": "com.example.pkg_a",
                        "fqcn": "com.example.pkg_a.User",
                    },
                    {
                        "file": "pkg_b/User.java",
                        "table": "b_user",
                        "table_name_source": "annotation",
                        "package": "com.example.pkg_b",
                        "fqcn": "com.example.pkg_b.User",
                    },
                ],
            }
        },
    }
    maps = [f for f in facts_from_signals(signals) if f["predicate"] == "MAPS_TO"]
    assert len(maps) == 2
    subjects = {f["subject"] for f in maps}
    assert len(subjects) == 2
    for subject in subjects:
        parsed = parse(subject)
        assert parsed.kind == "type"
        assert parsed.type_name == "User"
    assert {parse(s).namespaces for s in subjects} == {
        ("com", "example", "pkg_a"),
        ("com", "example", "pkg_b"),
    }
    assert all(f["qualifiers"].get("display_name") == "User" for f in maps)
    assert all(f["qualifiers"].get("symbol_kind") == "type" for f in maps)
    assert {f["qualifiers"]["fqcn"] for f in maps} == {
        "com.example.pkg_a.User",
        "com.example.pkg_b.User",
    }
    assert {f["object"] for f in maps} == {"a_user", "b_user"}
    assert all(f["qualifiers"].get("status") == "contested" for f in maps)


def test_uncontested_maps_to_requires_symbol_and_qualifiers() -> None:
    """Deviation: MAPS_TO emits bare class name or omits display_name/fqcn."""
    signals = {
        "scanners": ["filesystem", "ast-grep"],
        "evidence": {},
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "table_name_source": "annotation",
                "rule_id": "persistence__entity",
                "package": "com.acme",
                "fqcn": "com.acme.Order",
            }
        },
    }
    maps = [f for f in facts_from_signals(signals) if f["predicate"] == "MAPS_TO"]
    assert len(maps) == 1
    fact = maps[0]
    parsed = parse(fact["subject"])
    assert parsed.kind == "type"
    assert parsed.namespaces == ("com", "acme")
    assert parsed.type_name == "Order"
    assert fact["object"] == "orders"
    assert fact["qualifiers"]["display_name"] == "Order"
    assert fact["qualifiers"]["fqcn"] == "com.acme.Order"
    assert fact["qualifiers"]["symbol_kind"] == "type"
    assert "com.acme" in fact["qualifiers"]["fqcn"]


def test_write_rejects_bare_maps_to_subject(tmp_path: Path) -> None:
    """Deviation: write_facts_jsonl accepts MAPS_TO with simple-name subject."""
    bad = [
        {
            "predicate": "MAPS_TO",
            "subject": "User",
            "object": "users",
            "qualifiers": {"display_name": "User", "fqcn": "User", "symbol_kind": "type"},
            "file": "User.java",
            "line": None,
            "rule_id": None,
            "scanner": "ast-grep",
        }
    ]
    with pytest.raises(SymbolError, match="claim-symbol"):
        write_facts_jsonl(tmp_path / "facts.jsonl", bad)


def test_jsonl_round_trip_preserves_symbol_subjects(tmp_path: Path) -> None:
    """Deviation: write/load corrupts MAPS_TO identity fields."""
    signals = {
        "scanners": ["ast-grep"],
        "evidence": {
            "entities": [
                {
                    "file": "A.java",
                    "line": 3,
                    "match": "@Entity",
                    "rule_id": "persistence__entity",
                }
            ]
        },
        "entity_table_map": {
            "A": {
                "file": "A.java",
                "table": "a",
                "table_name_source": "default",
                "package": "com.example",
                "fqcn": "com.example.A",
            }
        },
    }
    facts = facts_from_signals(signals)
    path = tmp_path / "facts.jsonl"
    write_facts_jsonl(path, facts)
    loaded = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert loaded == facts
    maps = [f for f in loaded if f["predicate"] == "MAPS_TO"]
    assert parse(maps[0]["subject"]).fqcn == "com.example.A"


def test_fact_emit_counts_by_predicate_and_contested_status() -> None:
    """Deviation: emit counters mis-count MAPS_TO vs evidence (identity strings irrelevant)."""
    facts = [
        {
            "predicate": "persistence__entity",
            "subject": "A.java",
            "object": "@Entity",
            "qualifiers": {},
            "file": "A.java",
            "line": 1,
            "rule_id": "persistence__entity",
            "scanner": "ast-grep",
        },
        {
            "predicate": "MAPS_TO",
            "subject": "doc-engine spring . com/example/a/User#",
            "object": "a_user",
            "qualifiers": {"status": "contested"},
            "file": "pkg_a/User.java",
            "line": None,
            "rule_id": None,
            "scanner": "ast-grep",
        },
        {
            "predicate": "MAPS_TO",
            "subject": "doc-engine spring . com/example/b/User#",
            "object": "b_user",
            "qualifiers": {"status": "contested"},
            "file": "pkg_b/User.java",
            "line": None,
            "rule_id": None,
            "scanner": "ast-grep",
        },
        {
            "predicate": "MAPS_TO",
            "subject": "doc-engine spring . com/acme/Order#",
            "object": "orders",
            "qualifiers": {},
            "file": "Order.java",
            "line": None,
            "rule_id": None,
            "scanner": "ast-grep",
        },
    ]
    assert fact_emit_counts(facts) == {
        "facts_total": 4,
        "facts_maps_to": 3,
        "facts_maps_to_contested": 2,
        "facts_evidence": 1,
    }
