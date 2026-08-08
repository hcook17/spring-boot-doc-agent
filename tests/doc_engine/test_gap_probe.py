"""Falsifiers for gap_probe rates + AET axioms A1–A5."""

from __future__ import annotations

from doc_engine.scanning.facts import facts_from_signals
from doc_engine.scanning.gap_probe import (
    GAP_PROBE_SCHEMA_VERSION,
    SCORING_ENV_CALLABLE,
    SCORING_ENV_POOLED,
    apply_failure_budget,
    build_gap_report,
    failure_locator,
    measure_r_coll,
    measure_r_lin,
    measure_r_sym,
    write_gap_report,
)
from doc_engine.scanning.symbol import format_type


def _report(signals, facts, **kwargs):
    return build_gap_report(signals, facts, covering_ok=True, covering_why="", **kwargs)


def test_contested_map_raises_r_coll() -> None:
    """Deviation: contested collision not reflected in R_coll."""
    clean = {
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "fqcn": "com.acme.Order",
                "package": "com.acme",
            }
        },
        "evidence": {},
    }
    contested = {
        "entity_table_map": {
            "User": {
                "file": "a/User.java",
                "table": "a_user",
                "status": "contested",
                "fqcn": "com.example.a.User",
                "package": "com.example.a",
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
        "evidence": {},
    }
    r_clean = measure_r_coll(clean)["rate"]
    r_bad = measure_r_coll(contested)["rate"]
    assert r_clean == 0.0
    assert r_bad == 1.0
    assert r_bad > r_clean


def test_bare_maps_to_subject_lowers_r_sym() -> None:
    """Deviation: illegal MAPS_TO subjects still scored as perfect R_sym."""
    good_facts = [
        {
            "predicate": "MAPS_TO",
            "subject": format_type("com.acme", "Order"),
            "object": "orders",
            "qualifiers": {
                "display_name": "Order",
                "fqcn": "com.acme.Order",
                "symbol_kind": "type",
            },
            "file": "Order.java",
            "line": None,
            "rule_id": None,
            "scanner": None,
        }
    ]
    bad_facts = [
        {
            "predicate": "MAPS_TO",
            "subject": "User",
            "object": "users",
            "qualifiers": {"display_name": "User", "fqcn": "User", "symbol_kind": "type"},
            "file": "User.java",
            "line": None,
            "rule_id": None,
            "scanner": None,
        }
    ]
    assert measure_r_sym(good_facts)["rate"] == 1.0
    assert measure_r_sym(bad_facts)["rate"] == 0.0


def test_null_query_stratum_isolated() -> None:
    """Deviation: null-query rows mixed into native available rate (callable env)."""
    signals = {
        "entity_table_map": {},
        "evidence": {
            "raw_queries": [
                {
                    "file": "A.java",
                    "line": 1,
                    "query_kind": "native",
                    "query": None,
                    "lineage": {"available": False},
                },
                {
                    "file": "B.java",
                    "line": 2,
                    "query_kind": "native",
                    "query": "SELECT 1",
                    "lineage": {"available": True},
                },
            ]
        },
    }
    lin = measure_r_lin(signals, scoring_env=SCORING_ENV_CALLABLE)
    assert lin["strata"]["null_query"]["denominator"] == 1
    assert lin["strata"]["null_query"]["numerator"] == 0
    assert lin["strata"]["native"]["denominator"] == 1
    assert lin["strata"]["native"]["rate"] == 1.0
    assert lin["mean_rate"] == 1.0  # null_query excluded from callable mean
    assert lin["failure_taxonomy"].get("null_query") == 1


def test_a1_callable_vs_pooled_moves_r_lin() -> None:
    """A1: scoring-env changes R_lin mean when null_query rows exist."""
    signals = {
        "entity_table_map": {},
        "evidence": {
            "raw_queries": [
                {
                    "file": "A.java",
                    "line": 1,
                    "query_kind": "native",
                    "query": None,
                    "lineage": {"available": False},
                },
                {
                    "file": "B.java",
                    "line": 2,
                    "query_kind": "native",
                    "query": "SELECT 1",
                    "lineage": {"available": True},
                },
            ]
        },
    }
    call = measure_r_lin(signals, scoring_env=SCORING_ENV_CALLABLE)
    pooled = measure_r_lin(signals, scoring_env=SCORING_ENV_POOLED)
    assert call["mean_rate"] == 1.0
    assert call["denominator"] == 1
    assert pooled["mean_rate"] == 0.5
    assert pooled["denominator"] == 2
    assert call["mean_rate"] != pooled["mean_rate"]


def test_a2_scoring_env_preserves_identity_rates() -> None:
    """A2: scoring-env does not invent identity failure."""
    signals = {
        "schema_version": 7,
        "scanner_version": "test",
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "package": "com.acme",
                "fqcn": "com.acme.Order",
            }
        },
        "evidence": {
            "raw_queries": [
                {
                    "file": "A.java",
                    "line": 1,
                    "query_kind": "native",
                    "query": None,
                    "lineage": {"available": False},
                },
                {
                    "file": "B.java",
                    "line": 2,
                    "query_kind": "native",
                    "query": "SELECT 1",
                    "lineage": {"available": True},
                },
            ],
            "deployment": [],
        },
    }
    facts = facts_from_signals(signals)
    report, _ = _report(signals, facts)
    assert report["rates"]["R_sym"]["rate"] == 1.0
    assert report["rates"]["R_coll"]["rate"] == 0.0
    assert report["rates"]["R_join"]["rate"] == 1.0
    delta = report["measurement"]["delta_r_scoring_env"]
    assert delta["R_sym"] == 0.0
    assert delta["R_coll"] == 0.0
    assert delta["R_join"] == 0.0
    assert delta["R_lin_mean"] == 0.5  # 1.0 callable - 0.5 pooled


def test_a3_collision_only_does_not_force_dialect_lineage_reopen() -> None:
    """A3: collision-only fixture must not set lineage dominant to dialect_or_syntax."""
    signals = {
        "entity_table_map": {
            "User": {
                "file": "a/User.java",
                "table": "a_user",
                "status": "contested",
                "fqcn": "com.example.a.User",
                "package": "com.example.a",
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
        "evidence": {"raw_queries": [], "deployment": []},
    }
    facts = [
        {
            "predicate": "MAPS_TO",
            "subject": format_type("com.example.a", "User"),
            "object": "a_user",
            "qualifiers": {
                "display_name": "User",
                "fqcn": "com.example.a.User",
                "symbol_kind": "type",
            },
            "file": "a/User.java",
            "line": None,
            "rule_id": None,
            "scanner": None,
        }
    ]
    report, _ = _report(signals, facts)
    assert report["design_reopen"]["path_a_to_symbols"] is True
    dominant = report["design_reopen"]["lineage_dominant_stratum"]
    assert dominant is None or dominant.get("reason_class") != "dialect_or_syntax"


def test_a4_truncation_loss_monotone_in_b() -> None:
    """A4: B' < B => L(B') >= L(B) on planted must-keep set."""
    failures = [
        {
            "layer": "lineage",
            "stratum": "native",
            "reason_class": "dialect_or_syntax",
            "file": f"F{i}.java",
            "line": i,
        }
        for i in range(5)
    ]
    locs = [failure_locator(f) for f in failures]
    must_keep = [locs[0], locs[4]]  # first and last in sort order
    _, t_full = apply_failure_budget(failures, budget=5, must_keep=must_keep)
    _, t_mid = apply_failure_budget(failures, budget=2, must_keep=must_keep)
    _, t_zero = apply_failure_budget(failures, budget=0, must_keep=must_keep)
    assert t_full["L"] <= t_mid["L"] <= t_zero["L"]
    assert t_full["L"] == 0.0
    assert t_zero["L"] == 1.0


def test_a5_truncation_slot_typed() -> None:
    """A5: truncation loss lives under measurement.truncation only."""
    signals = {
        "entity_table_map": {},
        "evidence": {
            "raw_queries": [
                {
                    "file": "A.java",
                    "line": 1,
                    "query_kind": "native",
                    "query": "SELECT 1",
                    "lineage": {"available": False, "reason": "InvalidSyntaxException"},
                }
            ],
            "deployment": [],
        },
    }
    report, _ = _report(signals, facts=[], failure_budget=0, must_keep=["x"])
    trunc = report["measurement"]["truncation"]
    assert trunc["slot"] == "truncation_loss"
    assert "L" in trunc
    assert "truncation" not in report["uncertainty"]
    assert report["uncertainty"]["slot"] == "comparison_index"
    assert GAP_PROBE_SCHEMA_VERSION == 3
    assert report["schema_version"] == 3


def test_healthy_dual_emit_join_and_sym() -> None:
    """Deviation: healthy Path A + facts emit reports R_join/R_sym < 1."""
    signals = {
        "schema_version": 7,
        "scanner_version": "test",
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "package": "com.acme",
                "fqcn": "com.acme.Order",
            }
        },
        "evidence": {"raw_queries": [], "deployment": []},
    }
    facts = facts_from_signals(signals)
    report, failures = _report(signals, facts)
    assert report["rates"]["R_sym"]["rate"] == 1.0
    assert report["rates"]["R_coll"]["rate"] == 0.0
    assert report["rates"]["R_join"]["rate"] == 1.0
    assert report["uncertainty"]["U"] == 0.0
    # Dual-emit may stamp UNPROVEN for non-callable families — claim must not
    # look like full_support when S3 stamps exist.
    if report["uncertainty"]["unproven"] or report["uncertainty"]["callable_absence"]:
        assert report["uncertainty"]["claim"] == "comparison_index_with_unscored_s3"
    else:
        assert report["uncertainty"]["claim"] == "comparison_index_full_support"
    assert "callable_absence" in report["uncertainty"]
    assert "unproven" in report["uncertainty"]
    assert failures == []
    assert report["rates"]["R_sym"]["callable_denominator"] == 1


def test_vacuous_uncertainty_is_null_not_zero() -> None:
    """Deviation: empty dens published U=0.0 as if healthy Stage-0."""
    from doc_engine.scanning.gap_probe import compute_uncertainty

    block = compute_uncertainty(None, None, None, None, callable_absence=0, unproven=3)
    assert block["U"] is None
    assert block["claim"] == "vacuous_no_support_with_s3_stamps"
    assert block["unproven"] == 3
    assert block["support"] == []


def test_vacuous_without_s3_stamps() -> None:
    from doc_engine.scanning.gap_probe import compute_uncertainty

    block = compute_uncertainty(None, None, None, None)
    assert block["U"] is None
    assert block["claim"] == "vacuous_no_support"


def test_uncertainty_propagates_absence_unproven_counts() -> None:
    from doc_engine.scanning.gap_probe import compute_uncertainty

    block = compute_uncertainty(
        0.0, 1.0, 1.0, 1.0, callable_absence=2, unproven=5
    )
    assert block["U"] == 0.0
    assert block["callable_absence"] == 2
    assert block["unproven"] == 5
    assert block["claim"] == "comparison_index_with_unscored_s3"


def test_partial_support_claim() -> None:
    """Deviation: one measured dens + imputed rest still looked like full U."""
    from doc_engine.scanning.gap_probe import compute_uncertainty

    block = compute_uncertainty(0.0, None, None, None)
    assert block["U"] == 0.0
    assert block["claim"] == "comparison_index_partial_support"
    assert block["support"] == ["coll"]
    assert set(block["imputed_axes"]) == {"join", "lin", "code"}


def test_unscored_s3_outranks_partial_support() -> None:
    from doc_engine.scanning.gap_probe import compute_uncertainty

    block = compute_uncertainty(0.0, None, None, None, unproven=1)
    assert block["claim"] == "comparison_index_with_unscored_s3"


def test_write_gap_report_roundtrip(tmp_path) -> None:
    """Deviation: gap_report artifacts not written deterministically."""
    report = {"schema_version": GAP_PROBE_SCHEMA_VERSION, "rates": {"R_sym": {"rate": 1.0}}}
    failures = [
        {
            "layer": "facts",
            "stratum": "maps_to_symbol",
            "reason_class": "unparseable_or_non_type",
            "subject": "User",
        }
    ]
    write_gap_report(tmp_path, report, failures)
    assert (tmp_path / "gap_report.json").is_file()
    assert (tmp_path / "gap_failures.jsonl").is_file()
    lines = (tmp_path / "gap_failures.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"subject": "User"' in lines[0]


def test_rate_registry_keys_match_schema_rates() -> None:
    """OCP registry must expose exactly the closed R_* schema keys."""
    from doc_engine.scanning.gap_probe import RATE_REGISTRY

    assert tuple(spec.key for spec in RATE_REGISTRY) == (
        "R_sym",
        "R_coll",
        "R_join",
        "R_lin",
        "R_code_dep",
        "R_absence",
        "R_recall",
    )


def test_registry_hooks_drive_uncertainty_and_design_reopen() -> None:
    """Assembly hooks are registry-owned; report only adds truncation_alarm."""
    from doc_engine.scanning.gap_probe import RATE_REGISTRY

    u_keys = tuple(s.key for s in RATE_REGISTRY if s.uncertainty_inputs is not None)
    reopen_keys = tuple(s.key for s in RATE_REGISTRY if s.design_reopen is not None)
    extra_keys = tuple(s.key for s in RATE_REGISTRY if s.extra_failures is not None)
    assert u_keys == ("R_coll", "R_join", "R_lin", "R_code_dep", "R_absence")
    assert reopen_keys == ("R_coll", "R_join", "R_lin", "R_absence", "R_recall")
    assert extra_keys == ("R_recall",)

    signals = {
        "schema_version": 7,
        "scanner_version": "test",
        "entity_table_map": {
            "Order": {
                "file": "Order.java",
                "table": "orders",
                "package": "com.acme",
                "fqcn": "com.acme.Order",
            }
        },
        "evidence": {"raw_queries": [], "deployment": []},
    }
    facts = facts_from_signals(signals)
    report, _ = _report(signals, facts)
    assert set(report["design_reopen"]) == {
        "path_a_to_symbols",
        "join_incomplete",
        "lineage_dominant_stratum",
        "truncation_alarm",
        "structural_recall_misses",
        "unproven_present",
        "absence_present",
        "vacuous_uncertainty",
        "untrusted_planted_recall",
        "r_absence_failure_mass",
    }
    assert set(report["uncertainty"]["residuals"]) == {
        "R_coll",
        "join_gap",
        "lineage_gap",
        "code_dep_gap",
    }
    assert report["uncertainty"]["slot"] == "comparison_index"
    assert "U" in report["uncertainty"]
