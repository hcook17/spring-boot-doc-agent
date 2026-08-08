"""Falsifiers for context_packet composer, freshness, and MCP dispatch."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.query.freshness import (
    AssumeIndexed,
    SignatureFreshness,
    label_item_path,
)
from doc_engine.query.load import QueryError, QueryMissingError, QueryPathError
from doc_engine.query.packet import CONTEXT_PACKET_SCHEMA_VERSION, run_context_packet
from doc_engine.query.rank import (
    bucket_priority,
    estimate_tokens,
    score_item,
    tokenize,
    trim_to_budget,
)


def _write_run_dir(tmp: Path, *, signatures: dict | None = None) -> Path:
    run = tmp / "run"
    run.mkdir()
    signals = {
        "schema_version": 2,
        "scanners": ["ast-grep"],
        "evidence": {
            "security": [
                {
                    "file": "src/Sec.java",
                    "line": 4,
                    "match": '@PreAuthorize("hasRole(\'ADMIN\')")',
                    "rule_id": "security__pre_authorize",
                }
            ],
            "api_surface": [
                {
                    "file": "src/Api.java",
                    "line": 10,
                    "match": '@GetMapping("/api/onboarding")',
                    "rule_id": "api_surface__mapping",
                }
            ],
            "references": [
                {
                    "file": "src/Api.java",
                    "line": 1,
                    "match": "package com.example;",
                    "rule_id": "references__package",
                }
            ],
        },
        "entity_table_map": {
            "User": {
                "file": "src/User.java",
                "table": "users",
                "fqcn": "com.example.User",
                "status": "contested",
                "candidates": [
                    {"file": "src/User.java", "table": "users", "fqcn": "com.example.User"},
                    {"file": "src/b/User.java", "table": "b_users", "fqcn": "com.example.b.User"},
                ],
            }
        },
        "redaction_zones": [{"file": "src/Sec.java", "line": 20, "reason": "credential"}],
        "file_signatures": signatures if signatures is not None else {},
    }
    (run / "spring_signals.json").write_text(json.dumps(signals), encoding="utf-8")
    facts = [
        {
            "predicate": "MAPS_TO",
            "subject": "doc-engine spring . com/example/User#",
            "object": "users",
            "qualifiers": {
                "display_name": "User",
                "fqcn": "com.example.User",
                "symbol_kind": "type",
                "status": "contested",
            },
            "file": "src/User.java",
            "line": 3,
            "rule_id": "persistence__entity",
            "scanner": "ast-grep",
        }
    ]
    (run / "facts.jsonl").write_text(
        "\n".join(json.dumps(f) for f in facts) + "\n", encoding="utf-8"
    )
    return run


# --- ranking ---


def test_tokenize_splits_on_non_alnum() -> None:
    assert "onboarding" in tokenize("fix /api/onboarding role")


def test_bucket_priority_security_beats_references() -> None:
    assert bucket_priority("security") > bucket_priority("references")


def test_score_item_boosts_request_overlap() -> None:
    """Deviation: ranking ignores request tokens (Mako packet useless)."""
    high = score_item(
        request="onboarding role check",
        path="src/Api.java",
        text='@GetMapping("/api/onboarding")',
        bucket="api_surface",
        contested=False,
    )
    low = score_item(
        request="onboarding role check",
        path="src/Other.java",
        text="unrelated",
        bucket="references",
        contested=False,
    )
    assert high > low


def test_trim_to_budget_respects_token_proxy() -> None:
    """Deviation: budgetTokens ignored — unbounded primaryContext."""
    items = [
        {
            "path": f"f{i}.java",
            "match": f"hit-{i}",
            "score": 1.0 - i * 0.01,
            "provider": "evidence",
            "reason": "stage-0",
            "bucket": "security",
            "payload": {"blob": "y" * 5000},
        }
        for i in range(20)
    ]
    kept, truncated, used = trim_to_budget(items, budget_tokens=50)
    assert truncated is True
    assert len(kept) < 20
    assert used <= 50 or (len(kept) == 1 and truncated)
    # Emission must be row_ref-shaped (Option A), not fat payload.
    assert all("row_ref" in k and "payload" not in k for k in kept)
    assert used == sum(estimate_tokens(k) for k in kept)


def test_context_packet_budget_trims_primary(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    pkt = run_context_packet("onboarding", run_dir=run, budget_tokens=80)
    assert pkt["truncated"] is True or pkt["tokensUsed"] <= 80
    assert len(pkt["primaryContext"]) + len(pkt["relatedContext"]) <= 15


def test_context_packet_hints_always_present(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    pkt = run_context_packet("zzz-no-match-xyz", run_dir=run, budget_tokens=4000)
    assert isinstance(pkt["_hints"], list)
    assert len(pkt["_hints"]) >= 1


def test_context_packet_corrupt_signals_fail_closed(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "spring_signals.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(QueryError):
        run_context_packet("x", run_dir=run)


def test_cli_context_packet(tmp_path: Path) -> None:
    run = _write_run_dir(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_engine.tools.query_artifacts",
            "context-packet",
            "--run-dir",
            str(run),
            "--request",
            "onboarding",
            "--budget-tokens",
            "2000",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "context-packet"


# --- freshness ---


def test_signature_freshness_stale_on_mismatch(tmp_path: Path) -> None:
    """Deviation: signature mismatch labeled fresh_indexed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    f = repo / "src"
    f.mkdir()
    target = f / "Sec.java"
    target.write_text("class Sec {}", encoding="utf-8")
    from doc_engine.core.walk import compute_file_signature

    good = compute_file_signature(str(target))
    policy = SignatureFreshness(
        repo_root=repo,
        signatures={"src/Sec.java": "deadbeef"},
    )
    assert label_item_path(policy, "src/Sec.java") == "stale"
    policy_ok = SignatureFreshness(repo_root=repo, signatures={"src/Sec.java": good})
    assert label_item_path(policy_ok, "src/Sec.java") == "fresh_indexed"


def test_assume_indexed_when_no_repo() -> None:
    assert label_item_path(AssumeIndexed(), "src/X.java") == "unknown"


def test_missing_signatures_unknown(tmp_path: Path) -> None:
    """Deviation: missing file_signatures crashes instead of unknown."""
    run = _write_run_dir(tmp_path, signatures=None)
    # empty dict → unknown for paths not live-hashed
    pkt = run_context_packet(
        "security",
        run_dir=run,
        budget_tokens=4000,
        repo_path=None,
    )
    # without repo_path, freshness defaults to unknown via AssumeIndexed
    assert pkt["primaryContext"]
    for item in pkt["primaryContext"]:
        assert item.get("freshness") == "unknown"


def test_packet_with_repo_marks_stale(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "Sec.java").write_text("class Sec {}", encoding="utf-8")
    (repo / "src" / "Api.java").write_text("class Api {}", encoding="utf-8")
    (repo / "src" / "User.java").write_text("class User {}", encoding="utf-8")
    run = _write_run_dir(tmp_path, signatures={"src/Sec.java": "deadbeef", "src/Api.java": "deadbeef"})
    pkt = run_context_packet(
        "security PreAuthorize",
        run_dir=run,
        budget_tokens=4000,
        repo_path=repo,
    )
    freshes = {i.get("path"): i.get("freshness") for i in pkt["primaryContext"] + pkt["relatedContext"]}
    if "src/Sec.java" in freshes:
        assert freshes["src/Sec.java"] == "stale"


# --- MCP ---


def test_mcp_dispatch_context_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from doc_engine.query.mcp_tools import dispatch_tool

    run = _write_run_dir(tmp_path)
    monkeypatch.setenv("DOC_ENGINE_ROOT", str(tmp_path))
    out = dispatch_tool(
        "context_packet",
        {"request": "onboarding", "run_dir": str(run), "budget_tokens": 2000},
    )
    assert out["kind"] == "context-packet"


def test_mcp_path_escape_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from doc_engine.query.mcp_tools import dispatch_tool

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DOC_ENGINE_ROOT", str(root))
    with pytest.raises((QueryPathError, QueryMissingError, QueryError)):
        dispatch_tool(
            "query_evidence",
            {"signals": str(outside), "bucket": "security"},
        )


def test_mcp_help_lists_tools() -> None:
    from doc_engine.query.mcp_tools import dispatch_tool

    out = dispatch_tool("doc_engine_help", {})
    assert "context_packet" in out["tools"]


def test_envelope_schema_check_context_packet(tmp_path: Path) -> None:
    from doc_engine.query.schema_check import validate_envelope

    run = _write_run_dir(tmp_path)
    pkt = run_context_packet("onboarding", run_dir=run, budget_tokens=2000)
    validate_envelope("context_packet", pkt)


def test_fake_provider_strategy(tmp_path: Path) -> None:
    """Deviation: composer ignores PacketProvider strategies (E4-T2)."""

    class FakeProvider:
        name = "fake"

        def provide(self, request, *, signals, facts_rows, run_dir, limit):
            return [
                {
                    "provider": "fake",
                    "path": "src/Fake.java",
                    "line": 1,
                    "match": request,
                    "bucket": "security",
                    "reason": "fake",
                    "payload": {},
                    "contested": False,
                }
            ]

    run = _write_run_dir(tmp_path)
    pkt = run_context_packet(
        "whatever",
        run_dir=run,
        budget_tokens=4000,
        providers=[FakeProvider()],
    )
    assert pkt["providersUsed"] == ["fake"]
    assert any(i.get("path") == "src/Fake.java" for i in pkt["primaryContext"])


def test_mcp_stdio_initialize_roundtrip() -> None:
    from adapters.mcp.server import handle_message

    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp is not None
    assert resp["result"]["serverInfo"]["name"] == "doc-engine-query"
