"""Eval scoring + transcript KPI stub tests."""

from __future__ import annotations

from stf.eval.scoring import estimate_main_context_peak, score_decompose
from tests.stf.conftest import build_minimal_valid_spec, build_minimal_valid_tasks


def test_answer_key_auto_score_passes_minimal_decompose() -> None:
    key = {
        "required_task_titles_substrings": ["probe", "fix"],
        "required_inventory_ids": ["INV-C1"],
        "threshold": 0.8,
    }
    result = score_decompose(
        build_minimal_valid_tasks(), key, spec=build_minimal_valid_spec()
    )
    assert result["pass"]


def test_transcript_metrics_define_peak_main_context_kpi() -> None:
    metrics = estimate_main_context_peak(
        [
            {"main_ctx": 10_000, "tool_result_kb": 12.0},
            {"main_ctx": 40_000, "tool_result_kb": 3.0},
        ]
    )
    assert metrics["peak_main_ctx"] == 40_000
    assert "kpi" in metrics
