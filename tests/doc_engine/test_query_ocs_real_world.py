"""Opt-in query / context_packet validation against the canonical real Spring checkout.

Point ``DOC_ENGINE_REAL_REPO`` (or ``local-runs/real-repo.path``) at a local
Spring Boot tree — for the first pilot that is the OCS API service checkout.
Never commit that path.

Artifact lane (fast; uses regen'd Stage-0 outputs)::

    # after: python scripts/ci/regen_real_repo_artifacts.py
    DOC_ENGINE_REAL_ARTIFACTS_DIR=local-runs/real-repo-latest \\
        pytest tests/doc_engine/test_query_ocs_real_world.py -v

With the real repo / artifacts unset, every test is skipped (normal for CI).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.paths import repo_root
from doc_engine.query.mcp_tools import dispatch_tool
from doc_engine.query.packet import run_context_packet
from doc_engine.query.registry import run_query
from doc_engine.query.schema_check import validate_envelope
from doc_engine.real_fixture import real_artifacts_dir, real_repo_path, require_real_repo

REPO_ROOT = repo_root()


def _artifacts() -> Path:
    art = real_artifacts_dir(prefer_default=True)
    if art is None:
        pytest.skip("DOC_ENGINE_REAL_ARTIFACTS_DIR / local-runs/real-repo-latest unset")
    if not art.is_absolute():
        art = REPO_ROOT / art
    signals = art / "spring_signals.json"
    if not signals.is_file():
        pytest.skip(f"missing {signals} — run scripts/ci/regen_real_repo_artifacts.py")
    return art


@pytest.fixture(scope="module")
def ocs_artifacts() -> Path:
    return _artifacts()


@pytest.fixture(scope="module")
def ocs_repo() -> Path:
    try:
        return require_real_repo()
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


def test_ocs_references_query_stays_capped(ocs_artifacts: Path) -> None:
    """Deviation: OCS-scale references (~8k+) dump uncapped through query."""
    result = run_query(
        "evidence",
        signals_path=ocs_artifacts / "spring_signals.json",
        bucket="references",
        limit=25,
    )
    assert len(result["rows"]) <= 25
    assert result["truncated"] is True
    assert result["count"] == len(result["rows"])


def test_ocs_api_surface_and_persistence_nonempty(ocs_artifacts: Path) -> None:
    """Deviation: real OCS signals have empty api_surface/persistence (bad regen)."""
    api = run_query(
        "routes",
        signals_path=ocs_artifacts / "spring_signals.json",
        limit=50,
    )
    pers = run_query(
        "evidence",
        signals_path=ocs_artifacts / "spring_signals.json",
        bucket="persistence",
        limit=50,
    )
    assert api["count"] >= 1
    assert pers["count"] >= 1


def test_ocs_entity_lookup_roundtrip(ocs_artifacts: Path) -> None:
    """Deviation: entity_table_map on OCS not queryable by class name."""
    signals = json.loads((ocs_artifacts / "spring_signals.json").read_text(encoding="utf-8"))
    etm = signals.get("entity_table_map") or {}
    assert etm, "OCS scan should find entities"
    class_name = next(iter(etm.keys()))
    result = run_query(
        "entity",
        signals_path=ocs_artifacts / "spring_signals.json",
        class_name=class_name,
        limit=10,
    )
    assert result["count"] >= 1
    assert result["rows"][0]["class_name"] == class_name


def test_ocs_facts_maps_to(ocs_artifacts: Path) -> None:
    """Deviation: facts.jsonl dual-emit missing MAPS_TO on real OCS run."""
    facts = ocs_artifacts / "facts.jsonl"
    assert facts.is_file()
    result = run_query(
        "facts",
        facts_path=facts,
        predicate="MAPS_TO",
        limit=20,
    )
    assert result["count"] >= 1
    assert all(r.get("predicate") == "MAPS_TO" for r in result["rows"])


def test_ocs_context_packet_envelope(ocs_artifacts: Path, ocs_repo: Path) -> None:
    """Deviation: context_packet fails or empties on real OCS run-dir."""
    pkt = run_context_packet(
        "LearningObject API persistence authorization",
        run_dir=ocs_artifacts,
        budget_tokens=4000,
        repo_path=ocs_repo,
    )
    validate_envelope("context_packet", pkt)
    assert pkt["empty"] is False
    assert pkt["primaryContext"]
    assert pkt["_hints"]
    assert pkt["tokensUsed"] <= pkt["budgetTokens"] or pkt["truncated"]
    # freshness labels present when repo_path set
    labeled = pkt["primaryContext"] + pkt["relatedContext"]
    assert any(i.get("freshness") in ("live", "fresh_indexed", "stale", "unknown") for i in labeled)


def test_ocs_cli_context_packet(ocs_artifacts: Path) -> None:
    """Deviation: CLI context-packet cannot load OCS artifact dir."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_engine.tools.query_artifacts",
            "context-packet",
            "--run-dir",
            str(ocs_artifacts),
            "--request",
            "controller mapping",
            "--budget-tokens",
            "2000",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "context-packet"
    assert payload["empty"] is False


def test_ocs_mcp_context_packet(ocs_artifacts: Path) -> None:
    """Deviation: MCP dispatch cannot serve OCS run-dir."""
    out = dispatch_tool(
        "context_packet",
        {
            "request": "repository entity table",
            "run_dir": str(ocs_artifacts),
            "budget_tokens": 2000,
        },
    )
    assert out["kind"] == "context-packet"
    assert out["empty"] is False


def test_ocs_dependents_nonzero_when_references_present(ocs_artifacts: Path) -> None:
    """Deviation: dependents returns nothing on import-rich OCS signals."""
    result = run_query(
        "dependents",
        signals_path=ocs_artifacts / "spring_signals.json",
        limit=30,
    )
    # OCS has thousands of references — expect some resolved arcs
    assert result["count"] >= 1
    assert all(r.get("confidence") in ("exact", "package-fanout") for r in result["rows"])


def test_ocs_pointer_file_resolves(ocs_repo: Path) -> None:
    """Deviation: local-runs/real-repo.path ignored for query lane."""
    pointed = real_repo_path()
    assert pointed is not None
    assert pointed.resolve() == ocs_repo.resolve()
