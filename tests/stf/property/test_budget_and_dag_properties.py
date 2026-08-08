"""Property tests — budget/DAG algebra invariants (Hypothesis-style without dep)."""

from __future__ import annotations

from stf.graph.dag import compute_waves
from doc_engine.query.rank import (
    estimate_tokens_from_serialized_json,
    keep_highest_scoring_items_within_token_budget,
    replace_bulky_payload_with_row_ref_pointer,
    split_budget_into_primary_finding_and_risk_shares,
    truncate_nested_lists_that_exceed_cap,
)


def test_budget_shares_always_sum_exactly_to_requested_budget() -> None:
    for budget in range(0, 64):
        primary, finding, risk = split_budget_into_primary_finding_and_risk_shares(budget)
        assert primary + finding + risk == budget
        assert primary >= 0
        assert finding >= 0
        assert risk >= 0


def test_wave_partition_covers_every_task_exactly_once() -> None:
    graphs = [
        {"T0": [], "T1": ["T0"], "T2": ["T1"]},
        {"T0": [], "T1": [], "T2": ["T0", "T1"]},
        {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]},
    ]
    for graph in graphs:
        waves = compute_waves(graph)
        flat = [task_id for wave in waves for task_id in wave]
        assert sorted(flat) == sorted(graph)
        for wave in waves:
            for task_id in wave:
                assert all(dep not in wave for dep in graph[task_id])


def test_trim_never_reports_tokens_used_below_serialized_emission_cost() -> None:
    items = [
        {
            "provider": "evidence",
            "path": f"f{i}.java",
            "score": float(i),
            "payload": {"blob": "x" * 200, "guards": list(range(80))},
        }
        for i in range(5)
    ]
    for budget in (0, 1, 10, 50, 200, 1000):
        kept, truncated, tokens_used = keep_highest_scoring_items_within_token_budget(
            items, budget
        )
        if budget == 0:
            assert kept == []
            continue
        per_item = sum(estimate_tokens_from_serialized_json(i) for i in kept)
        assert tokens_used == per_item
        assert "payload" not in (kept[0] if kept else {})
        if not truncated:
            assert tokens_used <= budget


def test_nested_list_cap_truncates_guards_but_preserves_object_shape() -> None:
    payload = {"guards": [{"i": i} for i in range(120)], "ok": True}
    capped, did_truncate = truncate_nested_lists_that_exceed_cap(payload, max_list_length=50)
    assert did_truncate
    assert len(capped["guards"]) == 50
    assert capped["ok"] is True


def test_emission_item_drops_bulky_payload_in_favor_of_row_ref() -> None:
    emission = replace_bulky_payload_with_row_ref_pointer(
        {
            "provider": "route-trace",
            "path": "A.java",
            "line": 1,
            "score": 1.0,
            "payload": {"guards": list(range(100))},
        }
    )
    assert "payload" not in emission
    assert emission["row_ref"]["path"] == "A.java"
    assert emission.get("nested_truncated") is True
