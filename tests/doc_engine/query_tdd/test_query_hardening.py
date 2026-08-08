"""Query surface TDD — unit/property/security/smoke for E-Q0/E-Q1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from doc_engine.query.freshness import AssumeIndexed
from doc_engine.query.kinds import get_query_kind_spec, list_mcp_tool_names
from doc_engine.query.load import QueryError, QueryPathError, load_json
from doc_engine.query.mcp_tools import dispatch_tool
from doc_engine.query.providers import RedactionProvider
from doc_engine.query.rank import (
    estimate_tokens_from_serialized_json,
    replace_bulky_payload_with_row_ref_pointer,
    split_budget_into_primary_finding_and_risk_shares,
)
from doc_engine.query.registry import run_query


def test_assume_indexed_returns_unknown_not_fresh_indexed() -> None:
    assert AssumeIndexed().freshness_for("a.java") == "unknown"


def test_redaction_provider_expands_dict_shaped_zones() -> None:
    signals = {
        "redaction_zones": {
            "src/Secret.java": [{"line": 3, "reason": "password"}],
        }
    }
    rows = RedactionProvider().provide(
        "secrets",
        signals=signals,
        facts_rows=[],
        run_dir=Path("."),
        limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["path"] == "src/Secret.java"


def test_unknown_evidence_bucket_raises_not_empty_success() -> None:
    with pytest.raises(QueryError, match="unknown evidence bucket"):
        run_query(
            "evidence",
            signals={"evidence": {"security": []}},
            root=None,  # will fail root first if path used; in-memory ok
            bucket="secuirty",
        )


def test_query_kind_spec_registry_lists_mcp_tools() -> None:
    names = list_mcp_tool_names()
    assert "query_evidence" in names
    assert get_query_kind_spec("evidence").mcp_tool_name == "query_evidence"


def test_tokens_used_matches_serialized_emission_without_payload() -> None:
    item = {
        "provider": "evidence",
        "path": "A.java",
        "score": 1.0,
        "payload": {"huge": "y" * 5000},
    }
    emission = replace_bulky_payload_with_row_ref_pointer(item)
    assert "payload" not in emission
    assert estimate_tokens_from_serialized_json(emission) < estimate_tokens_from_serialized_json(
        item
    )


def test_budget_partition_never_overshoots_for_tiny_budgets() -> None:
    for b in range(0, 8):
        assert sum(split_budget_into_primary_finding_and_risk_shares(b)) == b


def test_mcp_dispatch_requires_server_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DOC_ENGINE_ROOT", raising=False)
    monkeypatch.delenv("DOC_ENGINE_RUN_DIR", raising=False)
    with pytest.raises(QueryPathError):
        dispatch_tool("query_evidence", {"signals": str(tmp_path / "s.json")})


def test_smoke_run_query_evidence_with_root(tmp_path: Path) -> None:
    """Smoke/sanity — happy path still works under mandatory root."""
    sig = tmp_path / "spring_signals.json"
    sig.write_text(
        json.dumps(
            {
                "evidence": {
                    "security": [
                        {
                            "file": "A.java",
                            "line": 1,
                            "match": "@PreAuthorize",
                            "rule_id": "security__pre_authorize",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    result = run_query("evidence", signals_path=sig, root=tmp_path, bucket="security", limit=10)
    assert result["rows"]
    assert result["kind"] == "evidence"
