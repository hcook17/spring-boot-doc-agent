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


def sort_failures(failures: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(f) for f in failures]
    rows.sort(
        key=lambda f: (
            str(f.get("layer") or ""),
            str(f.get("stratum") or ""),
            str(f.get("reason_class") or ""),
            str(f.get("file") or ""),
            str(f.get("simple_name") or f.get("subject") or ""),
        )
    )
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
        b_val: Any = None
    else:
        kept = ordered[:budget]
        b_val = budget

    kept_locs = {failure_locator(f) for f in kept}
    star = list(must_keep or [])
    if not star:
        loss = 0.0
        missed: List[str] = []
    else:
        missed = [loc for loc in star if loc not in kept_locs]
        loss = len(missed) / len(star)

    truncation = {
        "slot": "truncation_loss",
        "B": b_val if b_val is not None else len(ordered),
        "B_infinite": budget is None,
        "failures_total": len(ordered),
        "failures_kept": len(kept),
        "must_keep_count": len(star),
        "must_keep_missed": missed,
        "L": loss,
        "truncation_alarm": bool(star) and loss > 0.0,
    }
    return kept, truncation
