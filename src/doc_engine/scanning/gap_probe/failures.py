"""Failure locator, deterministic sort, and Pi_B truncation budget."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def _locator_field(row: Mapping[str, Any], key: str) -> str:
    return str(row.get(key) or "")


def _locator_line(row: Mapping[str, Any]) -> str:
    line = row.get("line")
    if line is None:
        return ""
    return str(line)


def _locator_name(row: Mapping[str, Any]) -> str:
    return str(row.get("simple_name") or row.get("subject") or "")


def failure_locator(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            _locator_field(row, "layer"),
            _locator_field(row, "stratum"),
            _locator_field(row, "reason_class"),
            _locator_field(row, "file"),
            _locator_line(row),
            _locator_name(row),
        ]
    )


def _failure_sort_key(row: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        _locator_field(row, "layer"),
        _locator_field(row, "stratum"),
        _locator_field(row, "reason_class"),
        _locator_field(row, "file"),
        _locator_name(row),
    )


def sort_failures(failures: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(row) for row in failures]
    rows.sort(key=_failure_sort_key)
    return rows


def _select_budgeted(
    ordered: List[Dict[str, Any]],
    budget: Optional[int],
) -> Tuple[List[Dict[str, Any]], Any]:
    if budget is None or budget < 0:
        return ordered, None
    return ordered[:budget], budget


def _must_keep_loss(
    must_keep_locators: Sequence[str],
    kept_locators: set[str],
) -> Tuple[float, List[str]]:
    if not must_keep_locators:
        return 0.0, []
    missed = [
        locator
        for locator in must_keep_locators
        if locator not in kept_locators
    ]
    return len(missed) / len(must_keep_locators), missed


def _truncation_report(
    *,
    ordered: Sequence[Mapping[str, Any]],
    kept: Sequence[Mapping[str, Any]],
    budget: Optional[int],
    budget_value: Any,
    must_keep_locators: Sequence[str],
) -> Dict[str, Any]:
    loss, missed = _must_keep_loss(
        must_keep_locators,
        {failure_locator(row) for row in kept},
    )
    return {
        "slot": "truncation_loss",
        "B": budget_value if budget_value is not None else len(ordered),
        "B_infinite": budget is None,
        "failures_total": len(ordered),
        "failures_kept": len(kept),
        "must_keep_count": len(must_keep_locators),
        "must_keep_missed": missed,
        "L": loss,
        "truncation_alarm": bool(must_keep_locators) and loss > 0.0,
    }


def apply_failure_budget(
    failures: Sequence[Mapping[str, Any]],
    budget: Optional[int],
    must_keep: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pi_B on sorted failures; L(B) vs must-keep locator set."""
    ordered = sort_failures(failures)
    kept, budget_value = _select_budgeted(ordered, budget)
    must_keep_locators = list(must_keep or [])
    truncation = _truncation_report(
        ordered=ordered,
        kept=kept,
        budget=budget,
        budget_value=budget_value,
        must_keep_locators=must_keep_locators,
    )
    return kept, truncation
