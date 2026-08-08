"""Failure locator, deterministic sort, and Pi_B truncation budget."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


def failure_locator(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("layer") or ""),
            str(row.get("stratum") or ""),
            str(row.get("reason_class") or ""),
            str(row.get("file") or ""),
            str(row.get("line") if row.get("line") is not None else ""),
            str(row.get("simple_name") or row.get("subject") or ""),
        ]
    )


def _failure_sort_key(row: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        str(row.get("layer") or ""),
        str(row.get("stratum") or ""),
        str(row.get("reason_class") or ""),
        str(row.get("file") or ""),
        str(row.get("simple_name") or row.get("subject") or ""),
    )


def sort_failures(failures: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(row) for row in failures]
    rows.sort(key=_failure_sort_key)
    return rows


def apply_failure_budget(
    failures: Sequence[Mapping[str, Any]],
    budget: Optional[int],
    must_keep: Optional[Sequence[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pi_B on sorted failures; L(B) vs must-keep locator set."""
    ordered = sort_failures(failures)
    if budget is None or budget < 0:
        kept = ordered
        budget_value: Any = None
    else:
        kept = ordered[:budget]
        budget_value = budget

    kept_locators = {failure_locator(row) for row in kept}
    must_keep_locators = list(must_keep or [])
    if not must_keep_locators:
        loss = 0.0
        missed: List[str] = []
    else:
        missed = [
            locator
            for locator in must_keep_locators
            if locator not in kept_locators
        ]
        loss = len(missed) / len(must_keep_locators)

    truncation = {
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
    return kept, truncation
