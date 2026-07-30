"""Unit tests for the Phase 1 dual-emit facts ledger."""

from __future__ import annotations

import json
from pathlib import Path

from doc_engine.scanning.facts import (
    facts_from_signals,
    facts_path_for_signals_out,
    write_facts_jsonl,
)


def test_facts_path_is_sibling_of_signals_out(tmp_path: Path) -> None:
    out = tmp_path / "run" / "spring_signals.json"
    assert facts_path_for_signals_out(out) == (tmp_path / "run" / "facts.jsonl").resolve()


def test_evidence_hit_projects_to_fact() -> None:
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
    fact = facts[0]
    assert fact["predicate"] == "web__rest_controller"
    assert fact["subject"] == "src/FooController.java"
    assert fact["object"] == "@RestController"
    assert fact["file"] == "src/FooController.java"
    assert fact["line"] == 12
    assert fact["rule_id"] == "web__rest_controller"
    assert fact["scanner"] == "ast-grep"


def test_contested_entity_emits_multi_maps_to() -> None:
    signals = {
        "scanners": ["ast-grep"],
        "evidence": {},
        "entity_table_map": {
            "User": {
                "file": "pkg_a/User.java",
                "table": "a_user",
                "table_name_source": "annotation",
                "status": "contested",
                "candidates": [
                    {
                        "file": "pkg_a/User.java",
                        "table": "a_user",
                        "table_name_source": "annotation",
                    },
                    {
                        "file": "pkg_b/User.java",
                        "table": "b_user",
                        "table_name_source": "annotation",
                    },
                ],
            }
        },
    }
    facts = facts_from_signals(signals)
    maps = [f for f in facts if f["predicate"] == "MAPS_TO" and f["subject"] == "User"]
    assert len(maps) >= 2
    tables = {f["object"] for f in maps}
    assert tables == {"a_user", "b_user"}
    assert all(f["qualifiers"].get("status") == "contested" for f in maps)


def test_uncontested_entity_emits_single_maps_to() -> None:
    signals = {
        "scanners": ["filesystem", "ast-grep"],
        "evidence": {},
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "table_name_source": "annotation",
                "rule_id": "persistence__entity",
            }
        },
    }
    facts = facts_from_signals(signals)
    maps = [f for f in facts if f["predicate"] == "MAPS_TO"]
    assert len(maps) == 1
    assert maps[0]["subject"] == "Order"
    assert maps[0]["object"] == "orders"
    assert maps[0]["scanner"] == "filesystem,ast-grep"


def test_jsonl_round_trip(tmp_path: Path) -> None:
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
            "A": {"file": "A.java", "table": "a", "table_name_source": "default"}
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


def test_fact_emit_counts_split_evidence_and_contested_maps() -> None:
    from doc_engine.scanning.facts import fact_emit_counts

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
            "subject": "User",
            "object": "a_user",
            "qualifiers": {"status": "contested"},
            "file": "pkg_a/User.java",
            "line": None,
            "rule_id": None,
            "scanner": "ast-grep",
        },
        {
            "predicate": "MAPS_TO",
            "subject": "User",
            "object": "b_user",
            "qualifiers": {"status": "contested"},
            "file": "pkg_b/User.java",
            "line": None,
            "rule_id": None,
            "scanner": "ast-grep",
        },
        {
            "predicate": "MAPS_TO",
            "subject": "Order",
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
