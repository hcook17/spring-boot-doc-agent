"""Falsifiers for doc-engine query — typed read views over Stage-0 artifacts.

Each test docstring names the deviation it must catch. Library logic lives in
``doc_engine.query``; CLI is a thin facade.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from doc_engine.query.envelope import QUERY_RESULT_SCHEMA_VERSION, apply_limit
from doc_engine.query.handlers import dependents, entity, evidence, facts, routes
from doc_engine.query.load import QueryError, QueryMissingError, QueryPathError, load_json, load_jsonl
from doc_engine.query.registry import get_query_handler, run_query
from doc_engine.real_fixture import real_artifacts_dir

FIXTURE_SIGNALS = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "fixtures"
    / "spring_signals"
)


def _signals_doc() -> dict:
    return {
        "schema_version": 2,
        "scanners": ["ast-grep"],
        "evidence": {
            "api_surface": [
                {
                    "file": "src/AController.java",
                    "line": 10,
                    "match": '@GetMapping("/api/a")',
                    "rule_id": "api_surface__mapping",
                },
                {
                    "file": "src/BController.java",
                    "line": 20,
                    "match": '@PostMapping("/api/b")',
                    "rule_id": "api_surface__mapping",
                },
                {
                    "file": "src/AController.java",
                    "line": 1,
                    "match": "@RestController",
                    "rule_id": "api_surface__controller",
                },
            ],
            "security": [
                {
                    "file": "src/AController.java",
                    "line": 9,
                    "match": '@PreAuthorize("hasRole(\'ADMIN\')")',
                    "rule_id": "security__pre_authorize",
                },
            ],
            "persistence": [
                {
                    "file": "src/User.java",
                    "line": 3,
                    "match": "@Entity",
                    "rule_id": "persistence__entity",
                },
            ],
            "references": [
                {
                    "file": "src/AController.java",
                    "line": 1,
                    "match": "package com.example.web;",
                    "rule_id": "references__package",
                },
                {
                    "file": "src/User.java",
                    "line": 1,
                    "match": "package com.example.domain;",
                    "rule_id": "references__package",
                },
                {
                    "file": "src/AController.java",
                    "line": 2,
                    "match": "import com.example.domain.User;",
                    "rule_id": "references__import",
                },
            ],
        },
        "entity_table_map": {
            "User": {
                "file": "src/User.java",
                "table": "users",
                "table_name_source": "annotation",
                "package": "com.example.domain",
                "fqcn": "com.example.domain.User",
                "status": "unique",
                "candidates": [],
            },
            "Order": {
                "file": "pkg_a/Order.java",
                "table": "a_order",
                "table_name_source": "annotation",
                "package": "com.example.a",
                "fqcn": "com.example.a.Order",
                "status": "contested",
                "candidates": [
                    {
                        "file": "pkg_a/Order.java",
                        "table": "a_order",
                        "package": "com.example.a",
                        "fqcn": "com.example.a.Order",
                    },
                    {
                        "file": "pkg_b/Order.java",
                        "table": "b_order",
                        "package": "com.example.b",
                        "fqcn": "com.example.b.Order",
                    },
                ],
            },
        },
    }


def _facts_rows() -> list[dict]:
    return [
        {
            "predicate": "MAPS_TO",
            "subject": "doc-engine spring . com/example/domain/User#",
            "object": "users",
            "qualifiers": {
                "display_name": "User",
                "fqcn": "com.example.domain.User",
                "symbol_kind": "type",
            },
            "file": "src/User.java",
            "line": 3,
            "rule_id": "persistence__entity",
            "scanner": "ast-grep",
        },
        {
            "predicate": "persistence__entity",
            "subject": "src/User.java",
            "object": "@Entity",
            "qualifiers": {},
            "file": "src/User.java",
            "line": 3,
            "rule_id": "persistence__entity",
            "scanner": "ast-grep",
        },
    ]


# ---------------------------------------------------------------------------
# Caps / envelope
# ---------------------------------------------------------------------------


def test_apply_limit_sets_truncated_when_rows_exceed_cap() -> None:
    """Deviation: uncapped dumps blow agent context (DDIA backpressure)."""
    rows = [{"i": i} for i in range(10)]
    out, truncated = apply_limit(rows, 3)
    assert len(out) == 3
    assert truncated is True


def test_apply_limit_clamps_absurd_limit() -> None:
    """Deviation: huge --limit bypasses the hard ceiling."""
    from doc_engine.query.envelope import MAX_LIMIT

    rows = [{"i": i} for i in range(MAX_LIMIT + 50)]
    out, truncated = apply_limit(rows, 10_000_000)
    assert len(out) == MAX_LIMIT
    assert truncated is True


def test_run_query_envelope_always_has_schema_and_truncated() -> None:
    """Deviation: bare list without envelope (agents cannot tell freshness/cap)."""
    result = run_query(
        "evidence",
        signals=_signals_doc(),
        bucket="persistence",
        limit=50,
    )
    assert result["schema_version"] == QUERY_RESULT_SCHEMA_VERSION
    assert "truncated" in result
    assert "rows" in result
    assert result["kind"] == "evidence"


# ---------------------------------------------------------------------------
# Evidence / routes
# ---------------------------------------------------------------------------


def test_evidence_filters_by_bucket_and_rule_id() -> None:
    """Deviation: returns every bucket when --bucket/--rule-id asked."""
    rows = evidence.query_evidence(
        _signals_doc(),
        bucket="api_surface",
        rule_id="api_surface__controller",
    )
    assert len(rows) == 1
    assert rows[0]["rule_id"] == "api_surface__controller"


def test_evidence_filters_by_file_substring() -> None:
    """Deviation: file filter ignored — agents re-read whole signals."""
    rows = evidence.query_evidence(
        _signals_doc(),
        bucket="persistence",
        file_contains="User.java",
    )
    assert len(rows) == 1
    assert "User.java" in rows[0]["file"]


def test_routes_defaults_to_api_surface_bucket() -> None:
    """Deviation: routes dumps persistence/security with api_surface."""
    rows = routes.query_routes(_signals_doc(), path_contains="/api/a")
    assert len(rows) == 1
    assert "/api/a" in (rows[0].get("match") or "")


# ---------------------------------------------------------------------------
# Facts / entity
# ---------------------------------------------------------------------------


def test_facts_filter_by_predicate_and_fqcn() -> None:
    """Deviation: facts query cannot find MAPS_TO by FQCN."""
    rows = facts.query_facts(
        _facts_rows(),
        predicate="MAPS_TO",
        fqcn="com.example.domain.User",
    )
    assert len(rows) == 1
    assert rows[0]["object"] == "users"


def test_entity_returns_contested_with_candidates() -> None:
    """Deviation: contested entity collapsed to unique or drops candidates."""
    rows = entity.query_entity(_signals_doc(), class_name="Order")
    assert len(rows) == 1
    assert rows[0]["status"] == "contested"
    assert len(rows[0]["candidates"]) == 2


def test_entity_lookup_by_table() -> None:
    """Deviation: table lookup misses unique entity_table_map entry."""
    rows = entity.query_entity(_signals_doc(), table="users")
    assert len(rows) == 1
    assert rows[0]["class_name"] == "User"


# ---------------------------------------------------------------------------
# Dependents
# ---------------------------------------------------------------------------


def test_dependents_finds_importers_of_type() -> None:
    """Deviation: dependents misses exact import arcs (LLM re-does the join)."""
    rows = dependents.query_dependents(
        _signals_doc(),
        target_file="src/User.java",
    )
    assert any(r.get("from") == "src/AController.java" and r.get("to") == "src/User.java" for r in rows)
    assert all(r.get("confidence") in ("exact", "package-fanout") for r in rows)


# ---------------------------------------------------------------------------
# route_trace (Phase 3)
# ---------------------------------------------------------------------------


def test_route_trace_joins_api_surface_with_same_file_security() -> None:
    """Deviation: route_trace returns mappings without co-located security hits."""
    from doc_engine.query.handlers import route_trace

    rows = route_trace.query_route_trace(_signals_doc(), path_contains="/api/a")
    assert len(rows) >= 1
    row = rows[0]
    assert "guards" in row
    assert any("PreAuthorize" in (g.get("match") or "") for g in row["guards"])


# ---------------------------------------------------------------------------
# Load / path safety
# ---------------------------------------------------------------------------


def test_load_json_missing_file_raises_not_empty_success(tmp_path: Path) -> None:
    """Deviation: missing artifact returns empty rows (false absence)."""
    with pytest.raises(QueryMissingError):
        load_json(tmp_path / "nope.json", root=tmp_path)


def test_load_json_requires_root(tmp_path: Path) -> None:
    """Deviation: C1 — opt-in containment (root=None allowed)."""
    p = tmp_path / "x.json"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(QueryPathError):
        load_json(p, root=None)


def test_load_json_invalid_raises(tmp_path: Path) -> None:
    """Deviation: corrupt JSON treated as empty success."""
    p = tmp_path / "bad.json"
    p.write_text("{not-json", encoding="utf-8")
    with pytest.raises(QueryError):
        load_json(p, root=tmp_path)


def test_load_jsonl_skips_blank_but_rejects_truncated_line(tmp_path: Path) -> None:
    """Deviation: truncated JSONL line silently dropped (chaos/fault injection)."""
    p = tmp_path / "facts.jsonl"
    p.write_text('{"predicate":"X","subject":"a","object":"b","qualifiers":{},"file":"f","line":1,"rule_id":"r","scanner":"s"}\n{bad\n', encoding="utf-8")
    with pytest.raises(QueryError):
        load_jsonl(p, root=tmp_path)


def test_path_outside_root_refused(tmp_path: Path) -> None:
    """Deviation: path escape / traversal accepted (untrusted artifact paths)."""
    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(QueryPathError):
        load_json(outside, root=root)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_symlink_escaping_root_refused(tmp_path: Path) -> None:
    """Deviation: symlink into escape path accepted as in-tree artifact."""
    root = tmp_path / "run"
    root.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text('{"ok": true}', encoding="utf-8")
    link = root / "signals.json"
    try:
        os.symlink(outside, link)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")
    # resolve() follows the link → outside root
    with pytest.raises(QueryPathError):
        load_json(link, root=root)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_evidence_exit_zero_and_truncated(tmp_path: Path) -> None:
    """Deviation: CLI dumps uncapped JSON or non-zero on valid input."""
    sig = tmp_path / "spring_signals.json"
    sig.write_text(json.dumps(_signals_doc()), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_engine.tools.query_artifacts",
            "evidence",
            "--signals",
            str(sig),
            "--bucket",
            "api_surface",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["truncated"] is True
    assert len(payload["rows"]) == 1


def test_cli_missing_signals_nonzero(tmp_path: Path) -> None:
    """Deviation: missing --signals exits 0 with empty envelope."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_engine.tools.query_artifacts",
            "evidence",
            "--signals",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0


def test_doc_engine_query_facade(tmp_path: Path) -> None:
    """Deviation: doc-engine query subcommand missing from public facade."""
    sig = tmp_path / "spring_signals.json"
    sig.write_text(json.dumps(_signals_doc()), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "doc_engine.cli",
            "query",
            "entity",
            "--signals",
            str(sig),
            "--class",
            "User",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "entity"
    assert payload["rows"][0]["class_name"] == "User"


def test_unknown_kind_raises() -> None:
    """Deviation: unknown kind silently no-ops."""
    with pytest.raises(KeyError):
        get_query_handler("not-a-kind")


@pytest.mark.skipif(
    real_artifacts_dir(prefer_default=True) is None,
    reason="real artifacts unset — see test_query_ocs_real_world.py",
)
def test_real_artifacts_evidence_stays_capped() -> None:
    """Deviation: OCS-scale references dump uncapped through query.

    Prefer the dedicated suite ``test_query_ocs_real_world.py``; this keeps a
    thin cap check in the unit module when the artifact lane is present.
    """
    from doc_engine.paths import repo_root
    from doc_engine.real_fixture import real_artifacts_dir

    art = real_artifacts_dir(prefer_default=True)
    assert art is not None
    if not art.is_absolute():
        art = repo_root() / art
    signals = art / "spring_signals.json"
    if not signals.is_file():
        pytest.skip("spring_signals.json missing — run regen_real_repo_artifacts.py")
    result = run_query(
        "evidence",
        signals_path=signals,
        root=art,
        bucket="references",
        limit=25,
    )
    assert len(result["rows"]) <= 25
    assert result["truncated"] is True or len(result["rows"]) < 25

# ---------------------------------------------------------------------------
# E-Q0 / E-Q1 merge-gate falsifiers
# ---------------------------------------------------------------------------


def test_unknown_evidence_bucket_raises() -> None:
    """Deviation: H3 - typo bucket returns empty success."""
    signals = _signals_doc()
    with pytest.raises(QueryError, match="unknown evidence bucket"):
        evidence.query_evidence(signals, bucket="secuirty")


def test_unknown_facts_predicate_raises() -> None:
    """Deviation: H3 - typo predicate returns empty success."""
    rows = _facts_rows()
    with pytest.raises(QueryError, match="unknown facts predicate"):
        facts.query_facts(rows, predicate="MAPS_TOO")


def test_redaction_provider_dict_zones_produce_risks() -> None:
    """Deviation: H2 - production {rel_path: [hits]} yields empty risks."""
    from doc_engine.query.providers import RedactionProvider

    signals = {
        "redaction_zones": {
            "application.yml": [
                {"line": 12, "heuristic": "key-name:password"},
                {"line": 40, "heuristic": "aws_access_key_id"},
            ]
        }
    }
    items = RedactionProvider().provide(
        "secrets",
        signals=signals,
        facts_rows=[],
        run_dir=Path("."),
        limit=10,
    )
    assert len(items) == 2
    assert items[0]["path"] == "application.yml"
    assert "password" in (items[0]["match"] or "")


def test_estimate_tokens_counts_full_emission() -> None:
    """Deviation: C2 - estimate_tokens ignores payload while emission includes it."""
    from doc_engine.query.rank import estimate_tokens, to_emission_item

    fat = {
        "provider": "evidence",
        "path": "src/A.java",
        "line": 1,
        "match": "hit",
        "bucket": "security",
        "reason": "x",
        "score": 1.0,
        "payload": {"blob": "y" * 4000},
    }
    emission = to_emission_item(fat)
    assert "payload" not in emission
    assert "row_ref" in emission
    assert estimate_tokens(emission) == len(json.dumps(emission, ensure_ascii=False)) // 4
    assert estimate_tokens({**emission, "payload": fat["payload"]}) > estimate_tokens(emission)


def test_assume_indexed_returns_unknown() -> None:
    """Deviation: M1 - AssumeIndexed always claims fresh_indexed."""
    from doc_engine.query.freshness import AssumeIndexed, label_item_path

    assert label_item_path(AssumeIndexed(), "does/not/exist.java") == "unknown"


def test_partition_budget_never_overshoots() -> None:
    """Deviation: N1 - max(1,...) primary+finding+risk exceeds small budgets."""
    from doc_engine.query.rank import partition_budget

    for budget in range(0, 12):
        primary, finding, risk = partition_budget(budget)
        assert primary + finding + risk == budget
        assert primary >= 0
        assert finding >= 0
        assert risk >= 0


def test_apply_nested_cap_truncates_guards() -> None:
    """Deviation: H1 - nested guards unbounded; truncated lies."""
    from doc_engine.query.envelope import apply_nested_cap

    row = {"file": "A.java", "guards": [{"i": i} for i in range(200)]}
    capped, truncated = apply_nested_cap([row], max_list=50)
    assert truncated is True
    assert len(capped[0]["guards"]) == 50
