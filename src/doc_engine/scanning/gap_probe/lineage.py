"""R_lin: lineage availability rates under callable / pooled scoring envs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Optional

from .common import (
    SCORING_ENV_CALLABLE,
    SCORING_ENV_POOLED,
    _rate,
    _rate_block,
)


def _lineage_reason_class(reason: Optional[str]) -> str:
    if not reason:
        return "unavailable_unknown"
    if "InvalidSyntaxException" in reason or "unparsable" in reason.lower():
        return "dialect_or_syntax"
    if "contested" in reason.lower():
        return "contested_refuse"
    if "not found" in reason.lower() or "no entity" in reason.lower():
        return "entity_lookup"
    return "unavailable_other"


def _dominant_failure_stratum(lin: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Pick the mode failure_taxonomy reason for design_reopen (callable R_lin)."""
    tax = {k: v for k, v in (lin.get("failure_taxonomy") or {}).items() if k != "null_query"}
    if not tax:
        tax = lin.get("failure_taxonomy") or {}
    if not tax:
        return None
    reason, count = max(tax.items(), key=lambda kv: kv[1])
    return {"reason_class": reason, "count": count}


def _lineage_row_outcome(
    row: Mapping[str, Any],
    *,
    scoring_env: str,
) -> tuple[str, bool, Optional[Dict[str, Any]], Optional[str]]:
    """Classify one raw_queries row for R_lin.

    Returns (stratum, available, failure_or_None, taxonomy_key_or_None).
    """
    query = row.get("query")
    query_kind = str(row.get("query_kind") or "other")
    lineage = row.get("lineage") if isinstance(row.get("lineage"), Mapping) else {}
    available = bool(lineage.get("available"))

    if query is None:
        failure = {
            "layer": "lineage",
            "stratum": "null_query",
            "reason_class": "null_query",
            "file": row.get("file"),
            "line": row.get("line"),
            "query_kind": query_kind,
        }
        # Pooled folds uncallable rows into native as failed trials.
        stratum = "native" if scoring_env == SCORING_ENV_POOLED else "null_query"
        return stratum, False, failure, "null_query"

    stratum = query_kind if query_kind in {"native", "jpql"} else "other"
    if available:
        return stratum, True, None, None
    reason_class = _lineage_reason_class(
        lineage.get("reason") if isinstance(lineage, Mapping) else None
    )
    failure = {
        "layer": "lineage",
        "stratum": stratum,
        "reason_class": reason_class,
        "file": row.get("file"),
        "line": row.get("line"),
        "query_kind": query_kind,
        "reason": (lineage.get("reason") if isinstance(lineage, Mapping) else None),
    }
    return stratum, False, failure, reason_class


def measure_r_lin(
    signals: Mapping[str, Any],
    *,
    scoring_env: str = SCORING_ENV_CALLABLE,
) -> Dict[str, Any]:
    """Lineage rates under scoring environment `callable` (normative) or `pooled`."""
    if scoring_env not in {SCORING_ENV_CALLABLE, SCORING_ENV_POOLED}:
        raise ValueError(f"unknown scoring_env: {scoring_env}")

    evidence = signals.get("evidence") or {}
    rows = evidence.get("raw_queries") if isinstance(evidence, Mapping) else None
    if not isinstance(rows, list):
        rows = []

    strata: Dict[str, Dict[str, int]] = {}
    failures: List[Dict[str, Any]] = []
    taxonomy: Counter[str] = Counter()

    def bump(stratum: str, available: bool) -> None:
        slot = strata.setdefault(stratum, {"available": 0, "total": 0})
        slot["total"] += 1
        if available:
            slot["available"] += 1

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        stratum, available, failure, taxonomy_key = _lineage_row_outcome(
            row, scoring_env=scoring_env,
        )
        bump(stratum, available)
        if taxonomy_key is not None:
            taxonomy[taxonomy_key] += 1
        if failure is not None:
            failures.append(failure)

    rates: Dict[str, Any] = {}
    for stratum_name, slot in sorted(strata.items()):
        rates[stratum_name] = _rate_block(slot["available"], slot["total"])

    # Under callable, exclude null_query stratum from mean.
    if scoring_env == SCORING_ENV_CALLABLE:
        mean_slots = {
            name: slot for name, slot in strata.items() if name != "null_query"
        }
    else:
        mean_slots = strata
    weighted_num = sum(slot["available"] for slot in mean_slots.values())
    weighted_den = sum(slot["total"] for slot in mean_slots.values())

    return {
        "scoring_env": scoring_env,
        "strata": rates,
        "mean_rate": _rate(weighted_num, weighted_den),
        "numerator": weighted_num,
        "denominator": weighted_den,
        "callable_denominator": weighted_den,
        "failure_taxonomy": dict(sorted(taxonomy.items())),
        "failures": failures,
    }
