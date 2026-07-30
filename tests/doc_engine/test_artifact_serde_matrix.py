"""Registry-driven serde property stubs for pipeline artifacts.

Slice 1 of schema-contracts-decision-memo-2026-07-30: registered artifacts
exercise RT / closed-world checks; unschematized names are skipped with reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from doc_engine.pipeline.artifacts import ARTIFACT_MODELS, Fact, JSONL_ARTIFACTS
from doc_engine.pipeline.validation import validate_artifact_file
from doc_engine.scanning.facts import facts_from_signals, write_facts_jsonl

# Remaining operator / parallel-track artifacts (slices 5+ / hand schema).
_UNSCHEMATIZED = {
    "drift_report": "slice 5 — operator report",
    "capacity_preflight_report": "slice 5 — operator report",
    "run_manifest": "parallel hand-schema track",
}


@pytest.mark.parametrize("artifact", sorted(ARTIFACT_MODELS))
def test_registered_artifact_has_model(artifact: str) -> None:
    assert artifact in ARTIFACT_MODELS


@pytest.mark.parametrize("artifact,reason", sorted(_UNSCHEMATIZED.items()))
def test_unschematized_artifacts_documented(artifact: str, reason: str) -> None:
    assert artifact not in ARTIFACT_MODELS
    assert reason


def test_facts_serde_round_trip_contract_projection(tmp_path: Path) -> None:
    """Deviation: closed Fact encode/decode loses required keys or MAPS_TO identity.

    Serde SoT is Fact closed-world round-trip; symbol spelling checked via parse.
    """
    from doc_engine.scanning.symbol import parse

    signals = {
        "scanners": ["ast-grep"],
        "evidence": {
            "controllers": [{
                "file": "C.java",
                "line": 2,
                "match": "@RestController",
                "rule_id": "web__rest_controller",
            }]
        },
        "entity_table_map": {
            "User": {
                "status": "contested",
                "table": "a_user",
                "candidates": [
                    {
                        "file": "a/User.java",
                        "table": "a_user",
                        "package": "com.example.a",
                        "fqcn": "com.example.a.User",
                    },
                    {
                        "file": "b/User.java",
                        "table": "b_user",
                        "package": "com.example.b",
                        "fqcn": "com.example.b.User",
                    },
                ],
            }
        },
    }
    facts = facts_from_signals(signals)
    path = tmp_path / "facts.jsonl"
    write_facts_jsonl(path, facts)
    model = validate_artifact_file("facts", path)
    decoded = [f.model_dump() for f in model.root]
    expected = [Fact.model_validate(f).model_dump() for f in facts]
    assert decoded == expected
    maps = [f for f in decoded if f["predicate"] == "MAPS_TO"]
    assert len(maps) == 2
    assert len({f["subject"] for f in maps}) == 2
    assert {parse(f["subject"]).namespaces for f in maps} == {
        ("com", "example", "a"),
        ("com", "example", "b"),
    }


def test_facts_drop_required_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Fact.model_validate({"subject": "only"})


def test_jsonl_encoding_flag() -> None:
    assert "facts" in JSONL_ARTIFACTS
